"""Cryptomus payment provider implementation.

Official API Reference:
  - Base URL: https://api.cryptomus.com/v1
  - Auth Headers:
      merchant: <merchant_uuid>
      sign: md5(base64_encode(json_data) + payment_key)
"""

from __future__ import annotations

import base64
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


class CryptomusProvider(PaymentProvider):
    """Cryptomus cryptocurrency payment provider."""

    def __init__(
        self,
        merchant_id: str,
        payment_key: str,
    ) -> None:
        self._merchant_id = merchant_id
        self._payment_key = payment_key
        self._base_url = "https://api.cryptomus.com/v1"

    @property
    def provider_name(self) -> str:
        return "cryptomus"

    def _generate_signature(self, payload: dict) -> str:
        """Generate Cryptomus MD5 signature for API requests.

        Formula: md5(base64_encode(json_encode(payload)) + payment_key)
        """
        json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("\\/", "/")
        b64_str = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
        return hashlib.md5((b64_str + self._payment_key).encode("utf-8")).hexdigest()

    def _headers(self, payload: dict) -> dict[str, str]:
        """Build authenticated headers for Cryptomus API."""
        return {
            "merchant": self._merchant_id,
            "sign": self._generate_signature(payload),
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Create invoice (hosted checkout page)
    # ------------------------------------------------------------------

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
        """Create a hosted checkout payment via POST /v1/payment."""
        payload: dict = {
            "amount": f"{price_amount:.2f}",
            "currency": price_currency.upper(),
            "order_id": order_id,
            "url_callback": ipn_callback_url,
            "is_payment_multiple": False,
            "lifetime": 1800,  # 30 minutes
        }
        if success_url:
            payload["url_return"] = success_url

        headers = self._headers(payload)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/payment",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        result = data.get("result", {})
        invoice_uuid = str(result.get("uuid", ""))
        payment_url = result.get("url", "")

        logger.info(
            "Cryptomus invoice created: uuid=%s order=%s url=%s",
            invoice_uuid, order_id, payment_url,
        )

        return InvoiceResult(
            invoice_id=invoice_uuid,
            payment_url=payment_url,
            payment_id=invoice_uuid,
        )

    # ------------------------------------------------------------------
    # Get payment status
    # ------------------------------------------------------------------

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check payment status via POST /v1/payment/info."""
        payload = {"uuid": payment_id}
        headers = self._headers(payload)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/payment/info",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        result = data.get("result", {})
        status = result.get("payment_status", "unknown")
        payer_amount = result.get("payment_amount") or result.get("payer_amount")

        return PaymentStatusResult(
            payment_id=str(result.get("uuid", payment_id)),
            status=status,
            actually_paid=Decimal(str(payer_amount)) if payer_amount else None,
            pay_currency=result.get("payer_currency"),
        )

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify Cryptomus webhook signature.

        Steps:
          1. Parse JSON body.
          2. Extract and remove the `sign` field.
          3. Base64 encode the remaining JSON without escaped slashes.
          4. Compute md5(base64_str + payment_key).
          5. Compare with received signature.
        """
        if not self._payment_key:
            logger.error("Cryptomus payment key not configured — cannot verify webhook")
            return False

        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                return False

            received_sign = payload.get("sign")
            if not received_sign:
                logger.warning("Cryptomus webhook missing 'sign' field")
                return False

            # Exclude sign key
            payload_without_sign = {k: v for k, v in payload.items() if k != "sign"}

            # Serialize without unescaped slashes
            json_str = json.dumps(
                payload_without_sign,
                ensure_ascii=False,
                separators=(",", ":"),
            ).replace("\\/", "/")

            b64_str = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
            computed_sign = hashlib.md5(
                (b64_str + self._payment_key).encode("utf-8")
            ).hexdigest()

            is_valid = hmac.compare_digest(computed_sign, received_sign)
            if not is_valid:
                logger.warning("Cryptomus webhook signature mismatch")
            return is_valid

        except Exception as e:
            logger.error("Cryptomus webhook verification error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Available currencies
    # ------------------------------------------------------------------

    async def get_available_currencies(self) -> list[str]:
        """Get supported currencies list."""
        payload = {}
        headers = self._headers(payload)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/payment/services",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                services = data.get("result", [])
                return [s.get("currency", "").upper() for s in services if s.get("currency")]
        return ["USDT", "BTC", "ETH", "LTC", "TON", "TRX", "SOL", "BNB"]

    # ------------------------------------------------------------------
    # Minimum amount
    # ------------------------------------------------------------------

    async def get_minimum_amount(
        self, currency_from: str, currency_to: str
    ) -> Decimal:
        """Return minimum accepted amount."""
        return Decimal("1.00")
