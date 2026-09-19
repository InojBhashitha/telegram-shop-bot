"""Stock alert repository for product restock notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import StockAlert, User


async def get_active_subscription(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> Optional[StockAlert]:
    """Check if user has an un-notified restock alert for this product."""
    stmt = (
        select(StockAlert)
        .where(StockAlert.user_id == user_id)
        .where(StockAlert.product_id == product_id)
        .where(StockAlert.notified_at.is_(None))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def subscribe(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> tuple[StockAlert, bool]:
    """Subscribe a user to restock alerts.

    Returns:
        tuple (StockAlert, created: bool)
    """
    existing = await get_active_subscription(session, user_id, product_id)
    if existing:
        return existing, False

    alert = StockAlert(
        user_id=user_id,
        product_id=product_id,
    )
    session.add(alert)
    await session.flush()
    return alert, True


async def get_pending_alerts_for_product(
    session: AsyncSession,
    product_id: int,
) -> list[StockAlert]:
    """Get all pending (un-notified) alerts for a product, loading user and product."""
    stmt = (
        select(StockAlert)
        .options(selectinload(StockAlert.user), selectinload(StockAlert.product))
        .where(StockAlert.product_id == product_id)
        .where(StockAlert.notified_at.is_(None))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_notified(
    session: AsyncSession,
    alert_ids: list[int],
) -> None:
    """Mark alerts as notified with the current timestamp."""
    if not alert_ids:
        return

    now = datetime.now(timezone.utc)
    stmt = (
        update(StockAlert)
        .where(StockAlert.id.in_(alert_ids))
        .values(notified_at=now)
    )
    await session.execute(stmt)
    await session.flush()
