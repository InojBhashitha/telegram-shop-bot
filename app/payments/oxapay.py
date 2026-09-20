"""OxaPay payment provider implementation.

Official API Reference:
  - Base URL: https://api.oxapay.com
  - Create Invoice: POST /merchants/request
  - Query Invoice:  POST /merchants/inquiry
  - Auth: Merchant API Key in payload
  - Webhook verification: HMAC-SHA512 signature in 'HMAC' header

Key advantages:
  - 0.4% fixed merchant fee (lowest in industry)
  - No corporate entity or KYC required
  - Supports low gas networks: BEP-20 (BSC), Polygon, Tron, TON, LTC
  - Automatic invoice expiration and status callbacks
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Optional

import httpx

from app.payments.base import InvoiceResult, PaymentProvider, PaymentStatusResult

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_BASE_URL = "https://api.oxapay.com"


class OxaPayProvider(PaymentProvider):
    """OxaPay cryptocurrency payment gateway (0.4% fee, no KYC)."""

    def __init__(self, merchant_key: str) -> None:
        self._merchant_key = merchant_key

    @property
    def provider_name(self) -> str:
        return "oxapay"

    async def create_invoice(
        self,
        price_amount: Decimal,
        price_currency: str,
        order_id: str,
        order_description: str,
        ipn_callback_url: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> InvoiceResult:
        """Create an OxaPay hosted payment invoice."""
        payload = {
            "merchant": self._merchant_key,
            "amount": float(price_amount),
            "currency": price_currency.upper(),
            "orderId": order_id,
            "description": order_description[:255],
            "callbackUrl": ipn_callback_url,
            "feePaidByPayer": 0,
        }

        if success_url:
            payload["returnUrl"] = success_url

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/merchants/request",
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "OxaPay create invoice failed: status=%s body=%s",
                    resp.status_code, resp.text,
                )
            resp.raise_for_status()
            data = resp.json()

        # OxaPay returns result=100 on success
        if data.get("result") != 100:
            error_msg = data.get("message", "Unknown error")
            logger.error("OxaPay API error: %s (result=%s)", error_msg, data.get("result"))
            raise RuntimeError(f"OxaPay error: {error_msg}")

        track_id = str(data.get("trackId", ""))
        pay_link = data.get("payLink", "")

        logger.info(
            "OxaPay invoice created: trackId=%s order=%s url=%s",
            track_id, order_id, pay_link,
        )

        return InvoiceResult(
            invoice_id=track_id,
            payment_url=pay_link,
            payment_id=track_id,
        )

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check payment status via POST /merchants/inquiry."""
        payload = {
            "merchant": self._merchant_key,
            "trackId": payment_id,
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/merchants/inquiry",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("result") != 100:
            logger.warning("OxaPay inquiry failed: %s", data.get("message"))
            return PaymentStatusResult(
                payment_id=payment_id,
                status="error",
            )

        status = str(data.get("status", "Waiting")).upper()
        amount = data.get("amount")
        currency = data.get("currency")

        return PaymentStatusResult(
            payment_id=payment_id,
            status=status,
            actually_paid=Decimal(str(amount)) if amount else None,
            pay_currency=currency,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify OxaPay webhook HMAC-SHA512 signature.

        Header: HMAC
        Secret: merchant_key
        """
        h = {k.lower(): v for k, v in headers.items()}
        signature = h.get("hmac")
        if not signature:
            logger.warning("OxaPay webhook missing HMAC header")
            return False

        expected = hmac.new(
            self._merchant_key.encode("utf-8"),
            body,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected.lower(), signature.lower())

    async def get_available_currencies(self) -> list[str]:
        return ["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "MATIC"]

    async def get_minimum_amount(
        self, currency_from: str, currency_to: str
    ) -> Decimal:
        return Decimal("0.01")
