"""Inventory repository with concurrency-safe reservation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory, InventoryStatus


async def add_items(
    session: AsyncSession,
    product_id: int,
    contents: list[str],
) -> list[Inventory]:
    """Add multiple inventory items for a product.

    Args:
        contents: List of deliverable content strings (one per item).

    Returns:
        List of created Inventory objects.
    """
    items = []
    for content in contents:
        item = Inventory(
            product_id=product_id,
            content=content.strip(),
            status=InventoryStatus.AVAILABLE,
        )
        session.add(item)
        items.append(item)
    await session.flush()
    return items


async def reserve_item(
    session: AsyncSession,
    product_id: int,
) -> Optional[Inventory]:
    """Atomically reserve one inventory item for a product.

    Uses SELECT ... FOR UPDATE (PostgreSQL) or immediate locking (SQLite)
    to prevent double-reservation under concurrent access.

    Returns:
        The reserved Inventory item, or None if no stock available.
    """
    # Select the first available item with row-level lock
    stmt = (
        select(Inventory)
        .where(Inventory.product_id == product_id)
        .where(Inventory.status == InventoryStatus.AVAILABLE)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        return None

    item.status = InventoryStatus.RESERVED
    item.reserved_at = datetime.now(timezone.utc)
    await session.flush()
    return item


async def release_item(session: AsyncSession, inventory_id: int) -> None:
    """Release a reserved inventory item back to available."""
    stmt = (
        update(Inventory)
        .where(Inventory.id == inventory_id)
        .where(Inventory.status == InventoryStatus.RESERVED)
        .values(
            status=InventoryStatus.AVAILABLE,
            reserved_at=None,
            order_id=None,
        )
    )
    await session.execute(stmt)


async def mark_sold(
    session: AsyncSession,
    inventory_id: int,
    order_id: int,
) -> None:
    """Mark a reserved inventory item as sold."""
    stmt = (
        update(Inventory)
        .where(Inventory.id == inventory_id)
        .where(Inventory.status == InventoryStatus.RESERVED)
        .values(
            status=InventoryStatus.SOLD,
            sold_at=datetime.now(timezone.utc),
            order_id=order_id,
        )
    )
    await session.execute(stmt)


async def release_expired_reservations(
    session: AsyncSession,
    expiry_minutes: int = 30,
) -> int:
    """Release inventory items that have been reserved beyond the expiry time.

    Returns:
        Number of items released.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=expiry_minutes)
    stmt = (
        update(Inventory)
        .where(Inventory.status == InventoryStatus.RESERVED)
        .where(Inventory.reserved_at < cutoff)
        .values(
            status=InventoryStatus.AVAILABLE,
            reserved_at=None,
            order_id=None,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount


async def get_stock_count(session: AsyncSession, product_id: int) -> int:
    """Count available inventory for a product."""
    stmt = (
        select(func.count(Inventory.id))
        .where(Inventory.product_id == product_id)
        .where(Inventory.status == InventoryStatus.AVAILABLE)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_stock_summary(session: AsyncSession, product_id: int) -> dict:
    """Get inventory counts grouped by status for a product."""
    stmt = (
        select(Inventory.status, func.count(Inventory.id))
        .where(Inventory.product_id == product_id)
        .group_by(Inventory.status)
    )
    result = await session.execute(stmt)
    summary = {s.value: 0 for s in InventoryStatus}
    for status, count in result.all():
        summary[status.value if isinstance(status, InventoryStatus) else status] = count
    return summary


async def get_item_by_id(session: AsyncSession, inventory_id: int) -> Optional[Inventory]:
    """Get an inventory item by ID."""
    stmt = select(Inventory).where(Inventory.id == inventory_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
