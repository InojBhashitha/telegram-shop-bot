"""Top-up repository."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TopUp, TopUpStatus


async def create(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    provider: str,
    currency: str = "USD",
    provider_invoice_id: Optional[str] = None,
    payment_url: Optional[str] = None,
) -> TopUp:
    """Create a new top-up record."""
    topup = TopUp(
        user_id=user_id,
        amount=amount,
        currency=currency,
        provider=provider,
        provider_invoice_id=provider_invoice_id,
        payment_url=payment_url,
        status=TopUpStatus.PENDING,
    )
    session.add(topup)
    await session.flush()
    return topup


async def get_by_id(session: AsyncSession, topup_id: int) -> Optional[TopUp]:
    """Get a top-up by ID."""
    stmt = select(TopUp).where(TopUp.id == topup_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_provider_invoice_id(
    session: AsyncSession, provider: str, provider_invoice_id: str
) -> Optional[TopUp]:
    """Get a top-up by provider invoice ID."""
    stmt = (
        select(TopUp)
        .where(TopUp.provider == provider)
        .where(TopUp.provider_invoice_id == provider_invoice_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    topup_id: int,
    status: TopUpStatus,
    **extra_fields,
) -> Optional[TopUp]:
    """Update a top-up status."""
    stmt = select(TopUp).where(TopUp.id == topup_id)
    result = await session.execute(stmt)
    topup = result.scalar_one_or_none()
    if topup is None:
        return None
    topup.status = status
    for key, value in extra_fields.items():
        if hasattr(topup, key):
            setattr(topup, key, value)
    await session.flush()
    return topup


async def get_user_topups(
    session: AsyncSession,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> list[TopUp]:
    """Get top-up history for a user."""
    stmt = (
        select(TopUp)
        .where(TopUp.user_id == user_id)
        .order_by(TopUp.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
