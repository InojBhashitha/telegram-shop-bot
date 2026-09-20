"""Tests for OxaPay payment provider and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.main import create_api
from app.database.models import Inventory, InventoryStatus, OrderStatus, PaymentStatus
from app.database.repositories import order_repo, payment_repo
from app.payments.oxapay import OxaPayProvider
from app.services import order_service, payment_service


def _make_oxapay_provider(key: str = "test_oxapay_merchant_key") -> OxaPayProvider:
    return OxaPayProvider(merchant_key=key)


def _compute_oxapay_signature(body: bytes, key: str = "test_oxapay_merchant_key") -> str:
    return hmac.new(key.encode("utf-8"), body, hashlib.sha512).hexdigest()


class TestOxaPaySignatures:
    """Test OxaPay HMAC-SHA512 webhook signature verification."""

    def test_signature_verification_valid(self):
        provider = _make_oxapay_provider()
        body = json.dumps({"trackId": 12345, "status": "Paid"}).encode("utf-8")
        sig = _compute_oxapay_signature(body)

        headers = {"hmac": sig}
        assert provider.verify_webhook(headers, body) is True

    def test_signature_verification_case_insensitive_header(self):
        provider = _make_oxapay_provider()
        body = b'{"status": "Paid"}'
        sig = _compute_oxapay_signature(body)

        headers = {"HMAC": sig}
        assert provider.verify_webhook(headers, body) is True

    def test_signature_verification_invalid(self):
        provider = _make_oxapay_provider()
        body = b'{"status": "Paid"}'
        headers = {"HMAC": "invalid_hmac_sha512"}
        assert provider.verify_webhook(headers, body) is False

    def test_signature_verification_missing_header(self):
        provider = _make_oxapay_provider()
        body = b'{"status": "Paid"}'
        assert provider.verify_webhook({}, body) is False


class TestOxaPayWebhookProcessing:
    """Test webhook processing for OxaPay in payment_service."""

    @pytest.mark.asyncio
    async def test_oxapay_webhook_fulfills_order(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_oxapay_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="oxapay",
            requested_amount=order.amount,
            provider_invoice_id="track_654321",
            provider_payment_id="track_654321",
        )

        webhook_data = {
            "trackId": 654321,
            "orderId": order.public_order_id,
            "status": "Paid",
            "amount": float(order.amount),
            "currency": "USDT",
            "payAmount": float(order.amount),
            "payCurrency": "USDT",
            "type": "payment",
        }

        res = await payment_service.process_webhook(session, provider, webhook_data)
        assert res is not None
        assert res["action"] == "fulfilled"

        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.FULFILLED

        updated_payment = await payment_repo.get_by_order_id(session, order.id)
        assert updated_payment.status == PaymentStatus.FINISHED
        assert updated_payment.payment_currency == "USDT"

    @pytest.mark.asyncio
    async def test_oxapay_webhook_confirming_status(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_oxapay_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="oxapay",
            requested_amount=order.amount,
            provider_invoice_id="track_confirming_999",
        )

        webhook_data = {
            "trackId": "track_confirming_999",
            "orderId": order.public_order_id,
            "status": "Confirming",
        }

        res = await payment_service.process_webhook(session, provider, webhook_data)
        assert res is not None
        assert res["action"] == "updated"

        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.PAYMENT_PROCESSING

    @pytest.mark.asyncio
    async def test_provider_factory(self):
        from app.payments import get_payment_provider
        p = get_payment_provider("oxapay")
        assert p.provider_name == "oxapay"


class TestOxaPayWebhookEndpoint:
    """Test HTTP POST /api/webhooks/crypto/oxapay endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_signature_valid(self, monkeypatch):
        from app.config import get_settings
        from app.database.database import close_db, get_engine, get_session, init_db
        from app.database.models import Base, Category, Product, User

        await init_db()
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        test_key = "oxapay_test_endpoint_key"
        monkeypatch.setattr(get_settings(), "oxapay_merchant_key", test_key)
        monkeypatch.setattr(get_settings(), "crypto_provider", "oxapay")

        try:
            async with get_session() as session:
                user = User(telegram_id=999222, username="testoxapay", first_name="OP")
                session.add(user)
                cat = Category(name="Cat2", icon="📦", active=True)
                session.add(cat)
                await session.flush()
                prod = Product(category_id=cat.id, name="P2", description="D2", price=Decimal("15.00"), currency="USD", active=True)
                session.add(prod)
                await session.flush()
                inv = Inventory(product_id=prod.id, content="test_key_oxapay", status=InventoryStatus.AVAILABLE)
                session.add(inv)
                await session.flush()

                result = await order_service.create_order(session, user.id, prod.id)
                order = result["order"]

                await payment_repo.create(
                    session,
                    order_id=order.id,
                    provider="oxapay",
                    requested_amount=order.amount,
                    provider_invoice_id="endpoint_track_777",
                    provider_payment_id="endpoint_track_777",
                )
                public_order_id = order.public_order_id
                order_amount = float(order.amount)

            webhook_payload = {
                "trackId": 777,
                "orderId": public_order_id,
                "status": "Paid",
                "amount": order_amount,
                "currency": "LTC",
                "payAmount": order_amount,
                "payCurrency": "LTC",
            }
            body_bytes = json.dumps(webhook_payload).encode("utf-8")
            sig = _compute_oxapay_signature(body_bytes, key=test_key)

            app = create_api()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhooks/crypto/oxapay",
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "HMAC": sig,
                    },
                )

            assert resp.status_code == 200
            assert resp.text == "ok"
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_endpoint_signature_invalid(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "oxapay_merchant_key", "secret_key_123")

        app = create_api()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/crypto/oxapay",
                content=b'{"test": 123}',
                headers={
                    "Content-Type": "application/json",
                    "HMAC": "bad_signature",
                },
            )

        assert resp.status_code == 400
        assert "signature_invalid" in resp.text
