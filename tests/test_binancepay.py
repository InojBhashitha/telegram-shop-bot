"""Tests for Binance Pay payment provider and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus, PaymentStatus
from app.database.repositories import order_repo, payment_repo
from app.payments.binancepay import BinancePayProvider
from app.services import order_service, payment_service


def _make_binancepay_provider() -> BinancePayProvider:
    """Create a test Binance Pay provider instance."""
    return BinancePayProvider(
        api_key="test_certificate_sn_api_key",
        secret_key="test_secret_key_12345",
    )


class TestBinancePaySignatures:
    """Test Binance Pay HMAC-SHA512 signature creation and verification."""

    def test_signature_generation(self):
        provider = _make_binancepay_provider()
        timestamp = "1726800000000"
        nonce = "abcdef1234567890abcdef1234567890"
        body = '{"orderAmount":10.0,"currency":"USDT"}'

        sig = provider._generate_signature(timestamp, nonce, body)

        # Re-compute expected
        payload = f"{timestamp}\n{nonce}\n{body}\n"
        expected_sig = hmac.new(
            b"test_secret_key_12345",
            payload.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest().upper()

        assert sig == expected_sig

    def test_build_headers(self):
        provider = _make_binancepay_provider()
        body = '{"test":"payload"}'
        headers = provider._build_headers(body)

        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        assert "BinancePay-Timestamp" in headers
        assert "BinancePay-Nonce" in headers
        assert headers["BinancePay-Certificate-SN"] == "test_certificate_sn_api_key"
        assert "BinancePay-Signature" in headers

    def test_valid_webhook_verification(self):
        provider = _make_binancepay_provider()
        headers = {
            "BinancePay-Timestamp": "1726800000000",
            "BinancePay-Nonce": "abcdef1234567890abcdef1234567890",
            "BinancePay-Certificate-SN": "test_api_key",
            "BinancePay-Signature": "ANY_SIGNATURE",
        }
        body = json.dumps({"bizType": "PAY", "bizStatus": "PAY_SUCCESS", "data": "{}"}).encode("utf-8")
        assert provider.verify_webhook(headers, body) is True

    def test_missing_header_webhook_verification(self):
        provider = _make_binancepay_provider()
        # Missing signature header
        headers = {
            "BinancePay-Timestamp": "1726800000000",
            "BinancePay-Nonce": "abcdef1234567890abcdef1234567890",
            "BinancePay-Certificate-SN": "test_api_key",
        }
        body = json.dumps({"bizStatus": "PAY_SUCCESS"}).encode("utf-8")
        assert provider.verify_webhook(headers, body) is False

    def test_invalid_json_webhook_verification(self):
        provider = _make_binancepay_provider()
        headers = {
            "BinancePay-Timestamp": "1726800000000",
            "BinancePay-Nonce": "abcdef1234567890abcdef1234567890",
            "BinancePay-Certificate-SN": "test_api_key",
            "BinancePay-Signature": "SIG",
        }
        body = b"not-json-content"
        assert provider.verify_webhook(headers, body) is False


class TestBinancePayWebhookProcessing:
    """Test webhook processing for Binance Pay in payment_service."""

    @pytest.mark.asyncio
    async def test_binancepay_webhook_marks_order_paid(
        self, session: AsyncSession, sample_data
    ):
        provider = _make_binancepay_provider()
        sample_user = sample_data["user"]
        sample_product = sample_data["product"]

        order_res = await order_service.create_order(session, sample_user.id, sample_product.id)
        order = order_res["order"]

        prepay_id = "binance_prepay_123456"
        merchant_trade_no = order.public_order_id.replace("-", "")

        # Create payment record
        await payment_repo.create(
            session,
            order_id=order.id,
            provider="binancepay",
            requested_amount=order.amount,
            provider_payment_id=prepay_id,
            provider_invoice_id=prepay_id,
        )

        # Simulate Binance Pay webhook payload
        inner_data = json.dumps({
            "merchantTradeNo": merchant_trade_no,
            "prepayId": prepay_id,
            "totalFee": float(order.amount),
            "currency": "USDT",
            "status": "PAID",
        })
        webhook_data = {
            "bizType": "PAY",
            "bizStatus": "PAY_SUCCESS",
            "data": inner_data,
        }

        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        assert result is not None
        assert result["order"].id == order.id

        # Verify payment status
        payment = await payment_repo.get_by_order_id(session, order.id)
        assert payment.status == PaymentStatus.FINISHED
        assert payment.received_amount == Decimal(str(float(order.amount)))
        assert payment.payment_currency == "USDT"

    @pytest.mark.asyncio
    async def test_binancepay_webhook_idempotency(
        self, session: AsyncSession, sample_data
    ):
        provider = _make_binancepay_provider()
        sample_user = sample_data["user"]
        sample_product = sample_data["product"]

        order_res = await order_service.create_order(session, sample_user.id, sample_product.id)
        order = order_res["order"]

        prepay_id = "binance_prepay_idempotent_1"
        merchant_trade_no = order.public_order_id.replace("-", "")

        payment = await payment_repo.create(
            session,
            order_id=order.id,
            provider="binancepay",
            requested_amount=order.amount,
            provider_payment_id=prepay_id,
            provider_invoice_id=prepay_id,
        )

        inner_data = json.dumps({
            "merchantTradeNo": merchant_trade_no,
            "prepayId": prepay_id,
            "status": "PAID",
        })
        webhook_data = {
            "bizType": "PAY",
            "bizStatus": "PAY_SUCCESS",
            "data": inner_data,
        }

        # First call: processes
        res1 = await payment_service.process_webhook(session, provider, webhook_data)
        assert res1 is not None

        # Second call: skipped
        res2 = await payment_service.process_webhook(session, provider, webhook_data)
        assert res2 is not None
        assert res2["action"] == "skipped"


class TestBinancePayEndpoint:
    """Test the FastAPI webhook endpoint for Binance Pay."""

    @pytest.mark.asyncio
    async def test_endpoint_success_response(self):
        from httpx import ASGITransport, AsyncClient
        from app.api.main import create_api
        from app.database.database import close_db, get_engine, init_db
        from app.database.models import Base

        await init_db()
        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            app = create_api()
            headers = {
                "BinancePay-Timestamp": "1726800000000",
                "BinancePay-Nonce": "abcdef1234567890abcdef1234567890",
                "BinancePay-Certificate-SN": "test_api_key",
                "BinancePay-Signature": "SIG12345",
            }
            body = {
                "bizType": "PAY",
                "bizStatus": "PAY_SUCCESS",
                "data": json.dumps({"merchantTradeNo": "CDNONEXISTENT", "prepayId": "999"}),
            }

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhooks/crypto/binancepay",
                    json=body,
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["returnCode"] == "SUCCESS"
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_endpoint_missing_headers_fail(self):
        from httpx import ASGITransport, AsyncClient
        from app.api.main import create_api

        app = create_api()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhooks/crypto/binancepay",
                json={"bizStatus": "PAY_SUCCESS"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["returnCode"] == "FAIL"

