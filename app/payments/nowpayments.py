"""NOWPayments provider implementation.

API Reference (as of 2025):
  - Base URL (production): https://api.nowpayments.io/v1
  - Base URL (sandbox):    https://api-sandbox.nowpayments.io/v1
  - Auth: x-api-key header
  - Webhook sig: HMAC-SHA512 of sorted JSON body, key = IPN secret,
                 sent in x-nowpayments-sig header
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

# Timeout for outgoing API requests (connect, read)
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class NOWPaymentsProvider(PaymentProvider):
    """NOWPayments crypto payment provider."""

    def __init__(
        self,
        api_key: str,
        ipn_secret: str,
        sandbox: bool = True,
    ) -> None:
        self._api_key = api_key
        self._ipn_secret = ipn_secret
        self._sandbox = sandbox
        self._base_url = (
            "https://api-sandbox.nowpayments.io/v1"
            if sandbox
            else "https://api.nowpayments.io/v1"
        )

    @property
    def provider_name(self) -> str:
        return "nowpayments"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
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
        """Create a payment invoice via POST /v1/invoice.

        The customer is redirected to the returned invoice_url to pick
        their crypto currency and complete the payment.
        """
        payload: dict = {
            "price_amount": float(price_amount),
            "price_currency": price_currency.lower(),
            "order_id": order_id,
            "order_description": order_description,
            "ipn_callback_url": ipn_callback_url,
            "is_fee_paid_by_user": False,
        }
        if success_url:
            payload["success_url"] = success_url
        if cancel_url:
            payload["cancel_url"] = cancel_url

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/invoice",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        logger.info(
            "NOWPayments invoice created: id=%s order=%s",
            data.get("id"), order_id,
        )

        return InvoiceResult(
            invoice_id=str(data["id"]),
            payment_url=data["invoice_url"],
        )

    # ------------------------------------------------------------------
    # Get payment status
    # ------------------------------------------------------------------

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check payment status via GET /v1/payment/{payment_id}."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/payment/{payment_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        return PaymentStatusResult(
            payment_id=str(data.get("payment_id", payment_id)),
            status=data.get("payment_status", "unknown"),
            actually_paid=Decimal(str(data["actually_paid"])) if data.get("actually_paid") else None,
            pay_currency=data.get("pay_currency"),
        )

    # ------------------------------------------------------------------
    # Webhook verification
    # ------------------------------------------------------------------

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify NOWPayments IPN webhook using HMAC-SHA512.

        Process:
        1. Get x-nowpayments-sig from headers
        2. Parse body as JSON
        3. Sort keys alphabetically
        4. JSON-serialize the sorted object
        5. HMAC-SHA512 with IPN secret
        6. Compare to the received signature
        """
        if not self._ipn_secret:
            logger.error("IPN secret not configured — cannot verify webhook")
            return False

        # Get signature from headers (case-insensitive lookup)
        received_sig = None
        for key, value in headers.items():
            if key.lower() == "x-nowpayments-sig":
                received_sig = value
                break

        if not received_sig:
            logger.warning("Webhook missing x-nowpayments-sig header")
            return False

        try:
            # Parse and re-serialize with sorted keys
            payload = json.loads(body)
            sorted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))

            # Compute HMAC-SHA512
            computed = hmac.new(
                self._ipn_secret.encode("utf-8"),
                sorted_payload.encode("utf-8"),
                hashlib.sha512,
            ).hexdigest()

            is_valid = hmac.compare_digest(computed, received_sig)
            if not is_valid:
                logger.warning("Webhook signature mismatch")
            return is_valid

        except (json.JSONDecodeError, Exception) as e:
            logger.error("Webhook verification error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Available currencies
    # ------------------------------------------------------------------

    async def get_available_currencies(self) -> list[str]:
        """Get list of supported currencies via GET /v1/currencies."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/currencies",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        currencies = data.get("currencies", [])
        return [str(c).upper() for c in currencies]

    # ------------------------------------------------------------------
    # Minimum amount
    # ------------------------------------------------------------------

    async def get_minimum_amount(
        self, currency_from: str, currency_to: str
    ) -> Decimal:
        """Get minimum payment amount via GET /v1/min-amount."""
        params = {
            "currency_from": currency_from.lower(),
            "currency_to": currency_to.lower(),
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/min-amount",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        return Decimal(str(data.get("min_amount", 0)))


def get_provider() -> NOWPaymentsProvider:
    """Create a NOWPayments provider instance from application settings."""
    from app.config import get_settings
    settings = get_settings()
    return NOWPaymentsProvider(
        api_key=settings.nowpayments_api_key,
        ipn_secret=settings.nowpayments_ipn_secret,
        sandbox=settings.nowpayments_sandbox,
    )
