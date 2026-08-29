"""Payments package and provider factory."""

from __future__ import annotations

from typing import Optional

from app.config import get_settings
from app.payments.base import InvoiceResult, PaymentProvider, PaymentStatusResult
from app.payments.cryptomus import CryptomusProvider
from app.payments.nowpayments import NOWPaymentsProvider


def get_payment_provider(provider_name: Optional[str] = None) -> PaymentProvider:
    """Resolve and return configured PaymentProvider instance."""
    settings = get_settings()
    name = (provider_name or settings.crypto_provider).lower()

    if name == "cryptomus":
        return CryptomusProvider(
            merchant_id=settings.cryptomus_merchant_id,
            payment_key=settings.cryptomus_payment_key,
        )

    # Default to NOWPayments
    return NOWPaymentsProvider(
        api_key=settings.nowpayments_api_key,
        ipn_secret=settings.nowpayments_ipn_secret,
        sandbox=settings.nowpayments_sandbox,
    )


__all__ = [
    "PaymentProvider",
    "InvoiceResult",
    "PaymentStatusResult",
    "CryptomusProvider",
    "NOWPaymentsProvider",
    "get_payment_provider",
]
