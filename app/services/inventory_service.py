"""Inventory service — stock management with concurrency protection."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory
from app.database.repositories import inventory_repo

logger = logging.getLogger(__name__)


async def add_stock(
    session: AsyncSession,
    product_id: int,
    items: list[str],
) -> int:
    """Add inventory items for a product.

    Args:
        items: List of deliverable content strings.

    Returns:
        Number of items added.
    """
    created = await inventory_repo.add_items(session, product_id, items)
    count = len(created)
    logger.info("Inventory added: product_id=%s count=%s", product_id, count)
    return count


async def reserve_item(
    session: AsyncSession, product_id: int
) -> Optional[Inventory]:
    """Atomically reserve one inventory item.

    Returns:
        The reserved item, or None if out of stock.
    """
    item = await inventory_repo.reserve_item(session, product_id)
    if item:
        logger.info("Inventory reserved: id=%s product_id=%s", item.id, product_id)
    else:
        logger.warning("No stock available: product_id=%s", product_id)
    return item


async def release_item(session: AsyncSession, inventory_id: int) -> None:
    """Release a reserved inventory item back to available."""
    await inventory_repo.release_item(session, inventory_id)
    logger.info("Inventory released: id=%s", inventory_id)


async def mark_sold(
    session: AsyncSession, inventory_id: int, order_id: int
) -> None:
    """Mark inventory as sold."""
    await inventory_repo.mark_sold(session, inventory_id, order_id)
    logger.info("Inventory sold: id=%s order_id=%s", inventory_id, order_id)


async def release_expired(session: AsyncSession, expiry_minutes: int = 30) -> int:
    """Release expired inventory reservations.

    Returns:
        Number of items released.
    """
    count = await inventory_repo.release_expired_reservations(session, expiry_minutes)
    if count > 0:
        logger.info("Released %s expired inventory reservations", count)
    return count


async def get_stock_count(session: AsyncSession, product_id: int) -> int:
    """Get available stock count for a product."""
    return await inventory_repo.get_stock_count(session, product_id)


async def get_stock_summary(session: AsyncSession, product_id: int) -> dict:
    """Get stock breakdown by status."""
    return await inventory_repo.get_stock_summary(session, product_id)
