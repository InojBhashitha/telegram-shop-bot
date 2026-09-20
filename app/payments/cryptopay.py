"""Crypto Pay (@CryptoBot) payment provider implementation.

Official API Reference:
  - Base URL: https://pay.crypt.bot/api
  - Create Invoice: POST /api/createInvoice
  - Query Invoices: POST /api/getInvoices
  - Auth: Crypto-Pay-API-Token header
  - Webhook verification: HMAC-SHA256 signature using sha256(api_token) as key

Key advantages:
  - No company / entity account required (works for individual bot owners)
  - No KYC required
  - 0 network gas fees when customer pays from Telegram crypto balance
  - 1-tap checkout inside Telegram
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
_BASE_URL = "https://pay.crypt.bot/api"


class CryptoPayProvider(PaymentProvider):
    """Crypto Pay (@CryptoBot) payment provider."""

    def __init__(self, api_token: str) -> None:
        self._api_token = api_token

    @property
    def provider_name(self) -> str:
        return "cryptopay"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Crypto-Pay-API-Token": self._api_token,
        }

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
        """Create a Crypto Pay invoice.

        Supports fiat USD pricing with multiple cryptocurrency payment options.
        """
        payload = {
            "currency_type": "fiat",
            "fiat": price_currency.upper(),
            "amount": f"{price_amount:.2f}",
            "description": order_description[:1024],
            "payload": order_id,
            "paid_btn_name": "callback",
            "paid_btn_url": success_url or "https://t.me",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/createInvoice",
                headers=self._get_headers(),
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "Crypto Pay createInvoice failed: status=%s body=%s",
                    resp.status_code, resp.text,
                )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok"):
            error_msg = data.get("error", {}).get("name", "Unknown error")
            logger.error("Crypto Pay API error: %s", error_msg)
            raise RuntimeError(f"Crypto Pay error: {error_msg}")

        result = data.get("result", {})
        invoice_id = str(result.get("invoice_id", ""))
        bot_invoice_url = result.get("bot_invoice_url", "")
        mini_app_invoice_url = result.get("mini_app_invoice_url", "")
        web_invoice_url = result.get("web_invoice_url", "")

        payment_url = bot_invoice_url or mini_app_invoice_url or web_invoice_url

        logger.info(
            "Crypto Pay invoice created: invoice_id=%s order=%s url=%s",
            invoice_id, order_id, payment_url,
        )

        return InvoiceResult(
            invoice_id=invoice_id,
            payment_url=payment_url,
            payment_id=invoice_id,
        )

    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check payment status via POST /api/getInvoices."""
        try:
            inv_id = int(payment_id)
            payload = {"invoice_ids": [inv_id]}
        except (ValueError, TypeError):
            payload = {"invoice_ids": [payment_id]}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/getInvoices",
                headers=self._get_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok"):
            logger.warning("Crypto Pay getInvoices failed: %s", data.get("error"))
            return PaymentStatusResult(
                payment_id=payment_id,
                status="error",
            )

        items = data.get("result", {}).get("items", [])
        if not items:
            return PaymentStatusResult(payment_id=payment_id, status="not_found")

        invoice = items[0]
        status = invoice.get("status", "active").upper()
        paid_amount = invoice.get("paid_amount") or invoice.get("amount")
        paid_asset = invoice.get("paid_asset") or invoice.get("asset")

        return PaymentStatusResult(
            payment_id=payment_id,
            status=status,
            actually_paid=Decimal(str(paid_amount)) if paid_amount else None,
            pay_currency=paid_asset,
        )

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify Crypto Pay webhook signature.

        Header: crypto-pay-api-signature
        Formula: HMAC-SHA256(raw_body, sha256(api_token))
        """
        h = {k.lower(): v for k, v in headers.items()}
        signature = h.get("crypto-pay-api-signature")
        if not signature:
            logger.warning("Crypto Pay webhook missing signature header")
            return False

        secret = hashlib.sha256(self._api_token.encode("utf-8")).digest()
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()

        return hmac.compare_digest(expected.lower(), signature.lower())

    async def get_available_currencies(self) -> list[str]:
        return ["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"]

    async def get_minimum_amount(
        self, currency_from: str, currency_to: str
    ) -> Decimal:
        return Decimal("0.01")
