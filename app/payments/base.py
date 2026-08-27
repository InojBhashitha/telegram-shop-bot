"""Payment provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class InvoiceResult:
    """Result from creating a payment invoice."""
    invoice_id: str
    payment_url: str
    payment_id: Optional[str] = None
    payment_address: Optional[str] = None


@dataclass
class PaymentStatusResult:
    """Result from checking payment status."""
    payment_id: str
    status: str  # Provider-specific status string
    actually_paid: Optional[Decimal] = None
    pay_currency: Optional[str] = None


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""

    @abstractmethod
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
        """Create a payment invoice.

        Args:
            price_amount: Amount in fiat currency.
            price_currency: Fiat currency code (e.g. "usd").
            order_id: Internal order identifier.
            order_description: Human-readable description.
            ipn_callback_url: URL for payment notifications.
            success_url: Redirect URL after successful payment.
            cancel_url: Redirect URL if payment is cancelled.

        Returns:
            InvoiceResult with payment URL and IDs.
        """
        ...

    @abstractmethod
    async def get_payment_status(self, payment_id: str) -> PaymentStatusResult:
        """Check the current status of a payment.

        Args:
            payment_id: The provider's payment ID.

        Returns:
            PaymentStatusResult with current status.
        """
        ...

    @abstractmethod
    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify the authenticity of a webhook/IPN notification.

        Args:
            headers: HTTP headers from the webhook request.
            body: Raw request body bytes.

        Returns:
            True if the webhook is authentic.
        """
        ...

    @abstractmethod
    async def get_available_currencies(self) -> list[str]:
        """Get list of supported cryptocurrency symbols."""
        ...

    @abstractmethod
    async def get_minimum_amount(
        self, currency_from: str, currency_to: str
    ) -> Decimal:
        """Get the minimum payment amount for a currency pair."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier string."""
        ...
