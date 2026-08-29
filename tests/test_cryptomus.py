"""Tests for Cryptomus payment provider and webhook verification."""

from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus, PaymentStatus
from app.database.repositories import order_repo, payment_repo
from app.payments.cryptomus import CryptomusProvider
from app.services import order_service, payment_service


def _make_cryptomus_provider() -> CryptomusProvider:
    """Create a test Cryptomus provider instance."""
    return CryptomusProvider(
        merchant_id="test-merchant-uuid",
        payment_key="test_payment_api_key",
    )


def _sign_cryptomus_payload(payload: dict, payment_key: str = "test_payment_api_key") -> str:
    """Compute Cryptomus MD5 signature for a payload."""
    payload_without_sign = {k: v for k, v in payload.items() if k != "sign"}
    json_str = json.dumps(
        payload_without_sign, ensure_ascii=False, separators=(",", ":")
    ).replace("\\/", "/")
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    return hashlib.md5((b64_str + payment_key).encode("utf-8")).hexdigest()


class TestCryptomusSignatures:
    """Test Cryptomus signature creation and verification."""

    def test_signature_generation(self):
        provider = _make_cryptomus_provider()
        payload = {"amount": "10.00", "currency": "USD", "order_id": "CD-100"}
        sig = provider._generate_signature(payload)
        expected_sig = _sign_cryptomus_payload(payload)
        assert sig == expected_sig

    def test_valid_webhook_verification(self):
        provider = _make_cryptomus_provider()
        payload = {
            "type": "payment",
            "uuid": "41a1a2b1-6a0e-4bf8-b210-234252352352",
            "order_id": "CD-20260829-000001",
            "amount": "15.00",
            "payment_amount": "15.00",
            "payment_status": "paid",
            "status": "paid",
            "is_final": True,
        }
        sig = _sign_cryptomus_payload(payload)
        payload["sign"] = sig

        body = json.dumps(payload).encode("utf-8")
        assert provider.verify_webhook({}, body) is True

    def test_invalid_webhook_signature(self):
        provider = _make_cryptomus_provider()
        payload = {
            "type": "payment",
            "uuid": "41a1a2b1-6a0e-4bf8-b210-234252352352",
            "order_id": "CD-20260829-000001",
            "status": "paid",
            "sign": "invalid_md5_signature",
        }
        body = json.dumps(payload).encode("utf-8")
        assert provider.verify_webhook({}, body) is False

    def test_missing_sign_field(self):
        provider = _make_cryptomus_provider()
        payload = {
            "uuid": "41a1a2b1-6a0e-4bf8-b210-234252352352",
            "status": "paid",
        }
        body = json.dumps(payload).encode("utf-8")
        assert provider.verify_webhook({}, body) is False

    def test_tampered_payload_verification(self):
        provider = _make_cryptomus_provider()
        payload = {
            "uuid": "41a1a2b1-6a0e-4bf8-b210-234252352352",
            "order_id": "CD-1",
            "amount": "10.00",
            "status": "paid",
        }
        sig = _sign_cryptomus_payload(payload)
        payload["sign"] = sig

        # Tamper with amount
        payload["amount"] = "1.00"
        body = json.dumps(payload).encode("utf-8")
        assert provider.verify_webhook({}, body) is False


class TestCryptomusPaymentProcessing:
    """Test Cryptomus webhook processing logic and order fulfillment."""

    @pytest.mark.asyncio
    async def test_process_paid_webhook(self, session: AsyncSession, sample_data: dict):
        """Test that a Cryptomus 'paid' status webhook fulfills the order."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_cryptomus_provider()

        # Create order
        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        # Create payment record
        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptomus",
            requested_amount=order.amount,
            provider_invoice_id="cryptomus_uuid_123",
            provider_payment_id="cryptomus_uuid_123",
        )

        webhook_data = {
            "uuid": "cryptomus_uuid_123",
            "order_id": order.public_order_id,
            "amount": str(order.amount),
            "payment_amount": str(order.amount),
            "payment_status": "paid",
            "status": "paid",
            "is_final": True,
        }

        res = await payment_service.process_webhook(session, provider, webhook_data)
        assert res is not None
        assert res["action"] == "fulfilled"

        # Verify order is fulfilled
        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.FULFILLED

    @pytest.mark.asyncio
    async def test_process_processing_status(self, session: AsyncSession, sample_data: dict):
        """Test that Cryptomus 'process' or 'check' status moves order to PAYMENT_PROCESSING."""
        user = sample_data["user"]
        product = sample_data["product"]
        provider = _make_cryptomus_provider()

        result = await order_service.create_order(session, user.id, product.id)
        order = result["order"]

        await payment_repo.create(
            session,
            order_id=order.id,
            provider="cryptomus",
            requested_amount=order.amount,
            provider_invoice_id="cryptomus_uuid_456",
        )

        webhook_data = {
            "uuid": "cryptomus_uuid_456",
            "order_id": order.public_order_id,
            "status": "process",
        }

        res = await payment_service.process_webhook(session, provider, webhook_data)
        assert res["action"] == "updated"

        updated_order = await order_repo.get_by_id(session, order.id)
        assert updated_order.status == OrderStatus.PAYMENT_PROCESSING

    @pytest.mark.asyncio
    async def test_provider_factory(self):
        """Test payment provider factory."""
        from app.payments import get_payment_provider
        p1 = get_payment_provider("cryptomus")
        assert p1.provider_name == "cryptomus"

        p2 = get_payment_provider("nowpayments")
        assert p2.provider_name == "nowpayments"
