"""Order repository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Order, OrderStatus


async def create(
    session: AsyncSession,
    public_order_id: str,
    user_id: int,
    product_id: int,
    inventory_id: int,
    amount: Decimal,
    currency: str = "USD",
) -> Order:
    """Create a new order."""
    order = Order(
        public_order_id=public_order_id,
        user_id=user_id,
        product_id=product_id,
        inventory_id=inventory_id,
        amount=amount,
        currency=currency,
        status=OrderStatus.PENDING_PAYMENT,
    )
    session.add(order)
    await session.flush()
    return order


async def get_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    """Get an order by internal ID."""
    stmt = select(Order).where(Order.id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_public_id(session: AsyncSession, public_order_id: str) -> Optional[Order]:
    """Get an order by its public order ID."""
    stmt = select(Order).where(Order.public_order_id == public_order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_orders(
    session: AsyncSession,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> list[Order]:
    """Get orders for a specific user."""
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_user_orders(session: AsyncSession, user_id: int) -> int:
    """Count total orders for a user."""
    stmt = select(func.count(Order.id)).where(Order.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one()


async def update_status(
    session: AsyncSession,
    order_id: int,
    status: OrderStatus,
    **extra_fields,
) -> Optional[Order]:
    """Update an order's status and optional extra fields."""
    stmt = select(Order).where(Order.id == order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        return None
    order.status = status
    for key, value in extra_fields.items():
        if hasattr(order, key):
            setattr(order, key, value)
    await session.flush()
    return order


async def expire_old_orders(
    session: AsyncSession,
    expiry_minutes: int = 30,
) -> list[int]:
    """Find and expire orders that have been pending beyond the time limit.

    Returns:
        List of inventory IDs that should be released.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=expiry_minutes)

    # Find orders to expire
    stmt = (
        select(Order)
        .where(Order.status == OrderStatus.PENDING_PAYMENT)
        .where(Order.created_at < cutoff)
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    inventory_ids: list[int] = []
    now = datetime.now(timezone.utc)
    for order in orders:
        order.status = OrderStatus.EXPIRED
        order.cancelled_at = now
        if order.inventory_id:
            inventory_ids.append(order.inventory_id)

    await session.flush()
    return inventory_ids


async def get_all_orders(
    session: AsyncSession,
    status: Optional[OrderStatus] = None,
    offset: int = 0,
    limit: int = 20,
) -> list[Order]:
    """List all orders with optional status filter (admin)."""
    stmt = select(Order)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_order_stats(session: AsyncSession) -> dict:
    """Get aggregated order statistics."""
    total = await session.execute(select(func.count(Order.id)))
    paid = await session.execute(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.FULFILLED])
        )
    )
    revenue = await session.execute(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.FULFILLED])
        )
    )
    cancelled = await session.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.CANCELLED)
    )
    expired_count = await session.execute(
        select(func.count(Order.id)).where(Order.status == OrderStatus.EXPIRED)
    )

    return {
        "total_orders": total.scalar_one(),
        "paid_orders": paid.scalar_one(),
        "revenue": Decimal(str(revenue.scalar_one())),
        "cancelled_orders": cancelled.scalar_one(),
        "expired_orders": expired_count.scalar_one(),
    }


async def generate_public_order_id(session: AsyncSession) -> str:
    """Generate a unique public order ID in format CD-YYYYMMDD-NNNNNN."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"CD-{today}-"

    # Count today's orders
    stmt = select(func.count(Order.id)).where(Order.public_order_id.like(f"{prefix}%"))
    result = await session.execute(stmt)
    count = result.scalar_one()

    return f"{prefix}{count + 1:06d}"
