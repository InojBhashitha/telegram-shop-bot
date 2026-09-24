"""Tests for Customer Referral & Affiliate System."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import create_api
from app.config import get_settings
from app.database.database import close_db, get_engine, get_session, init_db
from app.database.models import Base, Order, OrderStatus, Product, User
from app.database.repositories import referral_repo, user_repo
from app.services import order_service, referral_service, user_service


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_db()


@pytest_asyncio.fixture
async def sample_referrer_and_buyer():
    """Seed referrer, category, and product in test database."""
    from app.database.models import Category, Inventory, InventoryStatus

    async with get_session() as s:
        referrer = User(
            telegram_id=777001,
            username="top_affiliate",
            first_name="TopAffiliate",
            balance=Decimal("0.00"),
            referral_code="ref_topaffiliate123",
        )
        s.add(referrer)

        cat = Category(name="Streaming", icon="🎬", active=True)
        s.add(cat)
        await s.flush()

        product = Product(
            category_id=cat.id,
            name="Netflix 4K 1-Month",
            description="Ultra HD subscription",
            price=Decimal("20.00"),
            currency="USD",
            active=True,
        )
        s.add(product)
        await s.flush()

        inv = Inventory(
            product_id=product.id,
            content="netflix_user:netflix_pass",
            status=InventoryStatus.AVAILABLE,
        )
        s.add(inv)
        await s.flush()

        return {"referrer": referrer, "product": product, "category": cat}


class TestReferralSystem:
    """Test referral linking, validation, commission calculations, and notifications."""

    @pytest.mark.asyncio
    async def test_bind_referral_with_token(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]
        mock_bot = AsyncMock()

        async with get_session() as s:
            buyer_dict = await user_service.get_or_create_user(
                s,
                telegram_id=888001,
                username="new_buyer",
                first_name="BuyerOne",
                referral_code=referrer.referral_code,
                bot=mock_bot,
            )
            buyer = buyer_dict["user"]
            assert buyer.referred_by == referrer.id

            # Verify referral table
            ref_record = await referral_repo.get_referral_by_referred_id(s, buyer.id)
            assert ref_record is not None
            assert ref_record.referrer_user_id == referrer.id
            assert ref_record.referred_user_id == buyer.id

        # Verify bot sent join celebration notification to referrer
        assert mock_bot.send_message.called
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == referrer.telegram_id
        assert "New Referral Joined" in call_kwargs["text"]
        assert "5.0% commission" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_bind_referral_with_numeric_telegram_id(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]
        mock_bot = AsyncMock()

        async with get_session() as s:
            buyer_dict = await user_service.get_or_create_user(
                s,
                telegram_id=888002,
                username="numeric_buyer",
                first_name="BuyerTwo",
                referral_code=f"ref_{referrer.telegram_id}",
                bot=mock_bot,
            )
            buyer = buyer_dict["user"]
            assert buyer.referred_by == referrer.id

        assert mock_bot.send_message.called

    @pytest.mark.asyncio
    async def test_self_referral_prevented(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]

        async with get_session() as s:
            res = await referral_service.bind_referral(
                s,
                new_user=referrer,
                referral_code=referrer.referral_code,
            )
            assert res is None
            assert referrer.referred_by is None

    @pytest.mark.asyncio
    async def test_cannot_override_existing_referral(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]

        async with get_session() as s:
            # First bind
            user = await user_repo.get_or_create_user(s, telegram_id=888003, username="buyer_three")
            await referral_service.bind_referral(s, user, referrer.referral_code)
            assert user.referred_by == referrer.id

            # Attempt re-binding with different code
            second_ref = await user_repo.get_or_create_user(s, telegram_id=777002, username="other_affiliate")
            second_ref.referral_code = "ref_secondaffiliate"
            await s.flush()

            res = await referral_service.bind_referral(s, user, second_ref.referral_code)
            assert res is None
            assert user.referred_by == referrer.id

    @pytest.mark.asyncio
    async def test_order_fulfillment_credits_referral_commission(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]
        product = sample_referrer_and_buyer["product"]
        mock_bot = AsyncMock()

        async with get_session() as s:
            # 1. Create buyer referred by referrer
            buyer = await user_repo.get_or_create_user(s, telegram_id=888004, username="loyal_buyer")
            await referral_service.bind_referral(s, buyer, referrer.referral_code)

            # 2. Buyer creates order for $20.00
            order_data = await order_service.create_order(
                s,
                user_id=buyer.id,
                product_id=product.id,
                quantity=1,
            )
            order = order_data["order"]
            assert order.amount == Decimal("20.00")

            # 3. Mark paid
            await order_service.mark_paid(s, order.id)

            # 4. Mock bot instance for fulfill_order notifications
            from unittest.mock import patch
            with patch("app.services.referral_service._get_active_bot", return_value=mock_bot):
                result = await order_service.fulfill_order(s, order.id)
                assert result is not None

            # 5. Check referrer wallet balance: 5% of $20.00 = $1.00
            updated_referrer = await user_repo.get_by_id(s, referrer.id)
            assert updated_referrer.balance == Decimal("1.00")

            # 6. Check referral commissions audit table
            total_earned = await referral_repo.get_total_commissions_earned(s, referrer.id)
            assert total_earned == Decimal("1.00")

            recent = await referral_repo.get_recent_commissions(s, referrer.id)
            assert len(recent) == 1
            assert recent[0].commission_amount == Decimal("1.00")
            assert recent[0].order_amount == Decimal("20.00")
            assert recent[0].commission_rate == Decimal("5.00")

        # 7. Check Telegram notification to referrer
        assert mock_bot.send_message.called
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == referrer.telegram_id
        assert "Referral Commission Earned" in call_kwargs["text"]
        assert "+$1.00" in call_kwargs["text"]
        assert "$1.00" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_order_fulfillment_commission_idempotency(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]
        product = sample_referrer_and_buyer["product"]

        async with get_session() as s:
            buyer = await user_repo.get_or_create_user(s, telegram_id=888005, username="repeat_buyer")
            await referral_service.bind_referral(s, buyer, referrer.referral_code)

            order_data = await order_service.create_order(s, user_id=buyer.id, product_id=product.id, quantity=1)
            order = order_data["order"]
            await order_service.mark_paid(s, order.id)

            # First commission processing
            c1 = await referral_service.process_order_commission(s, order)
            assert c1 == Decimal("1.00")

            # Second commission processing on same order (should be skipped)
            c2 = await referral_service.process_order_commission(s, order)
            assert c2 is None

            # Balance should still be $1.00, not $2.00
            updated_referrer = await user_repo.get_by_id(s, referrer.id)
            assert updated_referrer.balance == Decimal("1.00")

    @pytest.mark.asyncio
    async def test_webapp_referral_api(self, sample_referrer_and_buyer):
        referrer = sample_referrer_and_buyer["referrer"]

        app = create_api()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/webapp/referral?telegram_id={referrer.telegram_id}")
            assert resp.status_code == 200
            data = resp.json()

            assert "referral_link" in data
            assert referrer.referral_code in data["referral_link"]
            assert data["commission_rate"] == 5.0
            assert "recent_commissions" in data
            assert data["total_earned"] == "0.00"
