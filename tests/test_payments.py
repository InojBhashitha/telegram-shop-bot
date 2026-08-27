"""Tests for payment webhook verification and processing."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus, PaymentStatus
from app.database.repositories import order_repo, payment_repo
from app.payments.nowpayments import NOWPaymentsProvider
from app.services import order_service, payment_service


def _make_provider() -> NOWPaymentsProvider:
    """Create a test provider instance."""
    return NOWPaymentsProvider(
        api_key="test_key",
        ipn_secret="test_secret",
        sandbox=True,
    )


def _sign_payload(payload: dict, secret: str = "test_secret") -> str:
    """Create a valid HMAC-SHA512 signature for a payload."""
    sorted_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        secret.encode(), sorted_body.encode(), hashlib.sha512
    ).hexdigest()


class TestWebhookVerification:
    """Test webhook signature verification."""

    def test_valid_signature(self):
        provider = _make_provider()
        payload = {"payment_id": "123", "payment_status": "finished"}
        sig = _sign_payload(payload)
        body = json.dumps(payload).encode()
        headers = {"x-nowpayments-sig": sig}

        assert provider.verify_webhook(headers, body) is True

    def test_invalid_signature(self):
        provider = _make_provider()
        payload = {"payment_id": "123", "payment_status": "finished"}
        body = json.dumps(payload).encode()
        headers = {"x-nowpayments-sig": "invalid_signature"}

        assert provider.verify_webhook(headers, body) is False

    def test_missing_signature_header(self):
        provider = _make_provider()
        body = json.dumps({"test": "data"}).encode()
        headers = {}

        assert provider.verify_webhook(headers, body) is False

    def test_tampered_body(self):
        provider = _make_provider()
        payload = {"payment_id": "123", "payment_status": "finished"}
        sig = _sign_payload(payload)

        # Tamper with the body
        tampered = {"payment_id": "123", "payment_status": "finished", "extra": "data"}
        body = json.dumps(tampered).encode()
        headers = {"x-nowpayments-sig": sig}

        assert provider.verify_webhook(headers, body) is False

    def test_empty_ipn_secret(self):
        provider = NOWPaymentsProvider("key", "", sandbox=True)
        body = json.dumps({"test": "data"}).encode()
        headers = {"x-nowpayments-sig": "something"}

        assert provider.verify_webhook(headers, body) is False


class TestPaymentProcessing:
    """Test payment webhook processing logic."""

    @pytest.mark.asyncio
    async def test_process_finished_webhook(self, session: AsyncSession, sample_data: dict):
        """Test that a 'finished' webhook fulfills the order."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_provider()

        # Create order
        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        # Create payment record manually (normally done by payment_service)
        payment = await payment_repo.create(
            session,
            order_id=order.id,
            provider="nowpayments",
            requested_amount=order.amount,
            provider_invoice_id="inv_123",
        )

        # Process webhook
        webhook_data = {
            "payment_id": "pay_456",
            "payment_status": "finished",
            "order_id": order.public_order_id,
            "actually_paid": "0.0045",
            "pay_currency": "btc",
        }

        result = await payment_service.process_webhook(session, provider, webhook_data)
        assert result is not None
        assert result["action"] == "fulfilled"

        # Verify order is fulfilled
        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.FULFILLED

    @pytest.mark.asyncio
    async def test_duplicate_webhook_skipped(self, session: AsyncSession, sample_data: dict):
        """Test that duplicate webhooks are skipped (idempotency)."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="nowpayments",
            requested_amount=order.amount,
            provider_invoice_id="inv_789",
        )

        webhook_data = {
            "payment_id": "pay_789",
            "payment_status": "finished",
            "order_id": order.public_order_id,
            "actually_paid": "0.0045",
        }

        # First webhook
        r1 = await payment_service.process_webhook(session, provider, webhook_data)
        assert r1["action"] == "fulfilled"

        # Second webhook (duplicate)
        r2 = await payment_service.process_webhook(session, provider, webhook_data)
        assert r2["action"] == "skipped"

    @pytest.mark.asyncio
    async def test_confirming_status_updates_order(self, session: AsyncSession, sample_data: dict):
        """Test that 'confirming' status moves order to PAYMENT_PROCESSING."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="nowpayments",
            requested_amount=order.amount,
        )

        webhook_data = {
            "payment_id": "pay_101",
            "payment_status": "confirming",
            "order_id": order.public_order_id,
        }

        result = await payment_service.process_webhook(session, provider, webhook_data)
        assert result["action"] == "updated"

        updated = await order_repo.get_by_id(session, order.id)
        assert updated.status == OrderStatus.PAYMENT_PROCESSING

    @pytest.mark.asyncio
    async def test_expired_webhook_cancels_order(self, session: AsyncSession, sample_data: dict):
        """Test that 'expired' webhook cancels the order."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="nowpayments",
            requested_amount=order.amount,
        )

        webhook_data = {
            "payment_id": "pay_exp",
            "payment_status": "expired",
            "order_id": order.public_order_id,
        }

        result = await payment_service.process_webhook(session, provider, webhook_data)
        assert result["action"] == "expired"


class TestAdminAuth:
    """Test admin authorization."""

    def test_admin_id_check(self):
        from app.config import get_settings
        settings = get_settings()
        assert settings.is_admin(111111)
        assert not settings.is_admin(999999)
