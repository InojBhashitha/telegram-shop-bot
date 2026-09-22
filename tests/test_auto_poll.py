"""Tests for Background Payment Auto-Polling worker."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus, PaymentStatus, TopUpStatus
from app.database.repositories import order_repo, payment_repo, topup_repo, user_repo
from app.payments.base import PaymentStatusResult
from app.services import order_service, payment_service


class TestAutoPollQueries:
    """Test repository queries used by auto-polling worker."""

    @pytest.mark.asyncio
    async def test_get_pending_payment_orders(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]
        product = sample_data["product"]

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptopay",
            requested_amount=order.amount,
            provider_invoice_id="inv_test_query",
        )

        orders = await order_repo.get_pending_payment_orders(session, max_age_minutes=60)
        assert len(orders) >= 1
        found = next((o for o in orders if o.id == order.id), None)
        assert found is not None
        assert found.payment is not None
        assert found.user is not None
        assert found.product is not None

    @pytest.mark.asyncio
    async def test_get_pending_topups(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]

        topup = await topup_repo.create(
            session,
            user_id=user.id,
            amount=Decimal("25.00"),
            provider="cryptopay",
            provider_invoice_id="topup_query_test",
        )

        topups = await topup_repo.get_pending_topups(session, max_age_minutes=60)
        assert len(topups) >= 1
        found = next((t for t in topups if t.id == topup.id), None)
        assert found is not None
        assert found.user is not None


class TestAutoPollWorker:
    """Test polling worker logic and automated fulfillment."""

    @pytest.mark.asyncio
    async def test_poll_orders_auto_fulfills_and_delivers(
        self, session: AsyncSession, sample_data: dict, monkeypatch
    ):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "cryptopay_api_token", "test_token")
        monkeypatch.setattr(get_settings(), "crypto_provider", "cryptopay")

        user = sample_data["user"]
        product = sample_data["product"]

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptopay",
            requested_amount=order.amount,
            provider_invoice_id="inv_auto_poll_888",
            provider_payment_id="inv_auto_poll_888",
        )

        mock_bot = AsyncMock()

        # Mock CryptoPayProvider.get_payment_status to return PAID status
        mock_status = PaymentStatusResult(
            payment_id="inv_auto_poll_888",
            status="PAID",
            actually_paid=order.amount,
            pay_currency="USDT",
        )

        with patch("app.payments.cryptopay.CryptoPayProvider.get_payment_status", return_value=mock_status):
            stats = await payment_service.poll_pending_orders_and_topups(
                session, bot=mock_bot, max_age_minutes=60
            )

        assert stats["orders_checked"] >= 1
        assert stats["orders_fulfilled"] >= 1

        # Order must now be FULFILLED in database
        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.FULFILLED

        # Delivery message must have been sent to user via Telegram
        assert mock_bot.send_message.call_count >= 1
        user_call = next(
            c for c in mock_bot.send_message.call_args_list
            if c[1]["chat_id"] == user.telegram_id
        )
        assert "Payment Confirmed" in user_call[1]["text"]

    @pytest.mark.asyncio
    async def test_poll_topups_auto_credits_balance(
        self, session: AsyncSession, sample_data: dict, monkeypatch
    ):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "cryptopay_api_token", "test_token")
        monkeypatch.setattr(get_settings(), "crypto_provider", "cryptopay")

        user = sample_data["user"]
        assert user.balance == Decimal("0.00")

        topup = await topup_repo.create(
            session,
            user_id=user.id,
            amount=Decimal("15.00"),
            provider="cryptopay",
            provider_invoice_id="topup_poll_999",
            payment_url="https://t.me/CryptoBot?start=123",
        )

        mock_bot = AsyncMock()

        mock_status = PaymentStatusResult(
            payment_id="topup_poll_999",
            status="PAID",
            actually_paid=Decimal("15.00"),
            pay_currency="USDT",
        )

        with patch("app.payments.cryptopay.CryptoPayProvider.get_payment_status", return_value=mock_status):
            stats = await payment_service.poll_pending_orders_and_topups(
                session, bot=mock_bot, max_age_minutes=60
            )

        assert stats["topups_checked"] >= 1
        assert stats["topups_credited"] >= 1

        # Check balance was credited
        updated_user = await user_repo.get_by_id(session, user.id)
        assert updated_user.balance == Decimal("15.00")

        # Topup status is PAID
        updated_topup = await topup_repo.get_by_id(session, topup.id)
        assert updated_topup.status == TopUpStatus.PAID

        # Confirmation message sent to customer
        assert mock_bot.send_message.called
        call_args = mock_bot.send_message.call_args[1]
        assert call_args["chat_id"] == user.telegram_id
        assert "Balance Top-Up Confirmed" in call_args["text"]
