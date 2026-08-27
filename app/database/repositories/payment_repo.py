"""Payment repository."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Payment, PaymentStatus


async def create(
    session: AsyncSession,
    order_id: int,
    provider: str,
    requested_amount: Decimal,
    provider_payment_id: Optional[str] = None,
    provider_invoice_id: Optional[str] = None,
    payment_currency: Optional[str] = None,
    payment_url: Optional[str] = None,
    payment_address: Optional[str] = None,
) -> Payment:
    """Create a new payment record."""
    payment = Payment(
        order_id=order_id,
        provider=provider,
        provider_payment_id=provider_payment_id,
        provider_invoice_id=provider_invoice_id,
        requested_amount=requested_amount,
        payment_currency=payment_currency,
        payment_url=payment_url,
        payment_address=payment_address,
        status=PaymentStatus.WAITING,
    )
    session.add(payment)
    await session.flush()
    return payment


async def get_by_order_id(session: AsyncSession, order_id: int) -> Optional[Payment]:
    """Get a payment by its order ID."""
    stmt = select(Payment).where(Payment.order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_provider_payment_id(
    session: AsyncSession, provider: str, provider_payment_id: str
) -> Optional[Payment]:
    """Get a payment by provider + provider_payment_id (for idempotency)."""
    stmt = (
        select(Payment)
        .where(Payment.provider == provider)
        .where(Payment.provider_payment_id == provider_payment_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_provider_invoice_id(
    session: AsyncSession, provider: str, provider_invoice_id: str
) -> Optional[Payment]:
    """Get a payment by provider + provider_invoice_id."""
    stmt = (
        select(Payment)
        .where(Payment.provider == provider)
        .where(Payment.provider_invoice_id == provider_invoice_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    payment_id: int,
    status: PaymentStatus,
    **extra_fields,
) -> Optional[Payment]:
    """Update a payment's status and optional extra fields."""
    stmt = select(Payment).where(Payment.id == payment_id)
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    if payment is None:
        return None
    payment.status = status
    for key, value in extra_fields.items():
        if hasattr(payment, key):
            setattr(payment, key, value)
    await session.flush()
    return payment


async def list_payments(
    session: AsyncSession,
    offset: int = 0,
    limit: int = 20,
) -> list[Payment]:
    """List all payments (admin)."""
    stmt = select(Payment).order_by(Payment.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
