"""Tests for Crypto Pay (@CryptoBot) payment provider and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.main import create_api
from app.database.models import Inventory, InventoryStatus, OrderStatus, PaymentStatus, TopUpStatus
from app.database.repositories import order_repo, payment_repo, topup_repo, user_repo
from app.payments.cryptopay import CryptoPayProvider
from app.services import order_service, payment_service, topup_service


def _make_cryptopay_provider(token: str = "test_cryptopay_token_123") -> CryptoPayProvider:
    return CryptoPayProvider(api_token=token)


def _compute_cryptopay_signature(body: bytes, token: str = "test_cryptopay_token_123") -> str:
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


class TestCryptoPaySignatures:
    """Test Crypto Pay signature verification."""

    def test_signature_verification_valid(self):
        provider = _make_cryptopay_provider()
        body = json.dumps({"update_id": 1, "update_type": "invoice_paid"}).encode("utf-8")
        sig = _compute_cryptopay_signature(body)

        headers = {"crypto-pay-api-signature": sig}
        assert provider.verify_webhook(headers, body) is True

    def test_signature_verification_case_insensitive_header(self):
        provider = _make_cryptopay_provider()
        body = b'{"status": "paid"}'
        sig = _compute_cryptopay_signature(body)

        headers = {"Crypto-Pay-Api-Signature": sig}
        assert provider.verify_webhook(headers, body) is True

    def test_signature_verification_invalid(self):
        provider = _make_cryptopay_provider()
        body = b'{"status": "paid"}'
        headers = {"crypto-pay-api-signature": "invalid_sig_abc123"}
        assert provider.verify_webhook(headers, body) is False

    def test_signature_verification_missing_header(self):
        provider = _make_cryptopay_provider()
        body = b'{"status": "paid"}'
        assert provider.verify_webhook({}, body) is False


class TestCryptoPayWebhookProcessing:
    """Test webhook processing for Crypto Pay in payment_service."""

    @pytest.mark.asyncio
    async def test_cryptopay_webhook_fulfills_order(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_cryptopay_provider()

        # Create order
        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        # Create payment record
        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptopay",
            requested_amount=order.amount,
            provider_invoice_id="inv_998877",
            provider_payment_id="inv_998877",
        )

        webhook_data = {
            "update_id": 101,
            "update_type": "invoice_paid",
            "payload": {
                "invoice_id": 998877,
                "status": "paid",
                "payload": order.public_order_id,
                "amount": str(order.amount),
                "paid_amount": str(order.amount),
                "paid_asset": "USDT",
            },
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
    async def test_cryptopay_webhook_waiting_status(
        self, session: AsyncSession, sample_data: dict
    ):
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_cryptopay_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptopay",
            requested_amount=order.amount,
            provider_invoice_id="inv_active_123",
        )

        webhook_data = {
            "payload": {
                "invoice_id": "inv_active_123",
                "status": "active",
                "payload": order.public_order_id,
            }
        }

        res = await payment_service.process_webhook(session, provider, webhook_data)
        assert res is not None
        assert res["action"] == "updated"

        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.PENDING_PAYMENT

    @pytest.mark.asyncio
    async def test_provider_factory(self):
        from app.payments import get_payment_provider
        p = get_payment_provider("cryptopay")
        assert p.provider_name == "cryptopay"


class TestCryptoPayWebhookEndpoint:
    """Test HTTP POST /api/webhooks/crypto/cryptopay endpoint."""

    @pytest.mark.asyncio
    async def test_endpoint_signature_valid(self, monkeypatch):
        from app.config import get_settings
        from app.database.database import close_db, get_engine, get_session, init_db
        from app.database.models import Base, Category, Product, User

        await init_db()
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        test_token = "cryptopay_test_endpoint_token"
        monkeypatch.setattr(get_settings(), "cryptopay_api_token", test_token)
        monkeypatch.setattr(get_settings(), "crypto_provider", "cryptopay")

        try:
            async with get_session() as session:
                user = User(telegram_id=999111, username="testcryptopay", first_name="CP")
                session.add(user)
                cat = Category(name="Cat1", icon="📦", active=True)
                session.add(cat)
                await session.flush()
                prod = Product(category_id=cat.id, name="P1", description="D1", price=Decimal("10.00"), currency="USD", active=True)
                session.add(prod)
                await session.flush()
                inv = Inventory(product_id=prod.id, content="test_key_123", status=InventoryStatus.AVAILABLE)
                session.add(inv)
                await session.flush()

                result = await order_service.create_order(session, user.id, prod.id)
                order = result["order"]

                await payment_repo.create(
                    session,
                    order_id=order.id,
                    provider="cryptopay",
                    requested_amount=order.amount,
                    provider_invoice_id="endpoint_inv_555",
                    provider_payment_id="endpoint_inv_555",
                )
                public_order_id = order.public_order_id
                order_amount = str(order.amount)

            webhook_payload = {
                "update_id": 555,
                "update_type": "invoice_paid",
                "payload": {
                    "invoice_id": 555,
                    "status": "paid",
                    "payload": public_order_id,
                    "amount": order_amount,
                    "paid_amount": order_amount,
                    "paid_asset": "TON",
                },
            }
            body_bytes = json.dumps(webhook_payload).encode("utf-8")
            sig = _compute_cryptopay_signature(body_bytes, token=test_token)

            app = create_api()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhooks/crypto/cryptopay",
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "crypto-pay-api-signature": sig,
                    },
                )

            assert resp.status_code == 200
            assert resp.text == "ok"
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_endpoint_signature_invalid(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "cryptopay_api_token", "some_secret_token")

        app = create_api()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/crypto/cryptopay",
                content=b'{"test": 123}',
                headers={
                    "Content-Type": "application/json",
                    "crypto-pay-api-signature": "bogus_signature",
                },
            )

        assert resp.status_code == 400
        assert "signature_invalid" in resp.text
