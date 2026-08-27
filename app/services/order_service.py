"""Order service — order creation, fulfillment, and lifecycle management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory, Order, OrderStatus
from app.database.repositories import inventory_repo, order_repo, product_repo

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """Raised when an order operation fails."""
    pass


async def create_order(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> dict:
    """Create a new order with inventory reservation.

    This is the main purchase entry point. It:
    1. Validates the product is active
    2. Reserves an inventory item (atomic)
    3. Creates the order record

    Returns:
        Dict with 'order' and 'inventory_item'.

    Raises:
        OrderError: If product invalid, inactive, or out of stock.
    """
    # Validate product
    product = await product_repo.get_by_id(session, product_id)
    if product is None:
        raise OrderError("Product not found")
    if not product.active:
        raise OrderError("Product is not available")

    # Reserve inventory atomically
    item = await inventory_repo.reserve_item(session, product_id)
    if item is None:
        raise OrderError("Out of stock")

    # Generate unique order ID
    public_order_id = await order_repo.generate_public_order_id(session)

    # Create order
    order = await order_repo.create(
        session,
        public_order_id=public_order_id,
        user_id=user_id,
        product_id=product_id,
        inventory_id=item.id,
        amount=product.price,
        currency=product.currency,
    )

    # Link inventory to order
    item.order_id = order.id
    await session.flush()

    logger.info(
        "Order created: %s product=%s user_id=%s amount=%s",
        public_order_id, product.name, user_id, product.price,
    )

    return {"order": order, "inventory_item": item}


async def cancel_order(session: AsyncSession, order_id: int) -> Optional[Order]:
    """Cancel an order and release its inventory.

    Only PENDING_PAYMENT orders can be cancelled by user.
    """
    order = await order_repo.get_by_id(session, order_id)
    if order is None:
        return None

    if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
        raise OrderError(f"Cannot cancel order in status {order.status.value}")

    # Release inventory
    if order.inventory_id:
        await inventory_repo.release_item(session, order.inventory_id)

    order = await order_repo.update_status(
        session, order_id, OrderStatus.CANCELLED,
        cancelled_at=datetime.now(timezone.utc),
    )
    logger.info("Order cancelled: %s", order.public_order_id)
    return order


async def mark_paid(session: AsyncSession, order_id: int) -> Optional[Order]:
    """Mark an order as paid."""
    order = await order_repo.update_status(
        session, order_id, OrderStatus.PAID,
        paid_at=datetime.now(timezone.utc),
    )
    if order:
        logger.info("Order paid: %s", order.public_order_id)
    return order


async def fulfill_order(session: AsyncSession, order_id: int) -> Optional[dict]:
    """Fulfill a paid order — mark inventory SOLD and order FULFILLED.

    Returns:
        Dict with 'order' and 'content' (the delivered item content),
        or None if order not found.

    Raises:
        OrderError: If order is not in PAID status (prevents double delivery).
    """
    order = await order_repo.get_by_id(session, order_id)
    if order is None:
        return None

    # CRITICAL: Only fulfill PAID orders — prevents duplicate delivery
    if order.status != OrderStatus.PAID:
        raise OrderError(
            f"Cannot fulfill order in status {order.status.value} "
            f"(expected PAID)"
        )

    # Mark inventory as sold
    content = None
    if order.inventory_id:
        await inventory_repo.mark_sold(session, order.inventory_id, order.id)
        item = await inventory_repo.get_item_by_id(session, order.inventory_id)
        if item:
            content = item.content

    # Mark order fulfilled
    order = await order_repo.update_status(
        session, order_id, OrderStatus.FULFILLED,
        delivered_at=datetime.now(timezone.utc),
    )

    logger.info("Order fulfilled: %s", order.public_order_id)
    return {"order": order, "content": content}


async def expire_old_orders(session: AsyncSession, expiry_minutes: int = 30) -> int:
    """Expire old pending orders and release their inventory.

    Returns:
        Number of orders expired.
    """
    inventory_ids = await order_repo.expire_old_orders(session, expiry_minutes)

    # Release inventory for expired orders
    for inv_id in inventory_ids:
        await inventory_repo.release_item(session, inv_id)

    if inventory_ids:
        logger.info("Expired %s orders, released inventory", len(inventory_ids))

    return len(inventory_ids)


async def get_user_orders(
    session: AsyncSession, user_id: int, offset: int = 0, limit: int = 10
) -> list[Order]:
    """Get orders for a user."""
    return await order_repo.get_user_orders(session, user_id, offset, limit)


async def get_order_by_public_id(
    session: AsyncSession, public_order_id: str
) -> Optional[Order]:
    """Get an order by its public ID."""
    return await order_repo.get_by_public_id(session, public_order_id)


async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    """Get an order by internal ID."""
    return await order_repo.get_by_id(session, order_id)


async def get_order_stats(session: AsyncSession) -> dict:
    """Get order statistics (admin)."""
    return await order_repo.get_order_stats(session)
