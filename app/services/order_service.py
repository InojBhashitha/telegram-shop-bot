"""Order service — order creation, fulfillment, and lifecycle management."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Inventory, Order, OrderStatus
from app.database.repositories import inventory_repo, order_repo, product_repo

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """Raised when an order operation fails."""
    pass


def compute_first_order_discount(user: Optional[User], raw_amount: Decimal) -> Decimal:
    """Compute 10% discount capped at $10.00 for channel member's first order."""
    if user and user.channel_discount_claimed and not user.channel_discount_used:
        discount = (raw_amount * Decimal("0.10")).quantize(Decimal("0.01"))
        return min(discount, Decimal("10.00"))
    return Decimal("0.00")


from app.database.repositories import coupon_repo, inventory_repo, order_repo, product_repo, user_repo
from app.services import coupon_service
from app.utils.crypto_vault import decrypt_content


async def create_order(
    session: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int = 1,
    coupon_code: Optional[str] = None,
    coupon_id: Optional[int] = None,
) -> dict:
    """Create a new order with inventory reservation (supports bulk quantity & discounts).

    This is the main purchase entry point. It:
    1. Validates the product is active
    2. Reserves `quantity` inventory items (atomic)
    3. Calculates coupon discount or 10% first-order discount
    4. Creates the order record with total amount = (price × quantity) - discount

    Returns:
        Dict with 'order', 'inventory_items', 'discount', and 'subtotal'.

    Raises:
        OrderError: If product invalid, inactive, or out of stock.
    """
    # Validate product
    product = await product_repo.get_by_id(session, product_id)
    if product is None:
        raise OrderError("Product not found")
    if not product.active:
        raise OrderError("Product is not available")

    # Validate quantity
    if quantity < 1 or quantity > 50:
        raise OrderError("Quantity must be between 1 and 50")

    # Check stock
    available = await inventory_repo.get_stock_count(session, product_id)
    if available < quantity:
        if available == 0:
            raise OrderError("Out of stock")
        raise OrderError(f"Only {available} item(s) in stock (requested {quantity})")

    # Reserve inventory atomically
    if quantity == 1:
        item = await inventory_repo.reserve_item(session, product_id)
        if item is None:
            raise OrderError("Out of stock")
        reserved_items = [item]
    else:
        reserved_items = await inventory_repo.reserve_items(session, product_id, quantity)
        if len(reserved_items) < quantity:
            # Release any partially reserved items
            for ri in reserved_items:
                await inventory_repo.release_item(session, ri.id)
            raise OrderError(f"Not enough stock available (only {len(reserved_items)})")

    # Calculate subtotal, discount, and warranty expiry
    subtotal = product.price * quantity
    user = await user_repo.get_by_id(session, user_id)

    applied_coupon_id: Optional[int] = None
    discount = Decimal("0.00")

    if coupon_code and coupon_code.strip():
        try:
            coupon_res = await coupon_service.validate_and_calculate_discount(
                session=session,
                code=coupon_code.strip(),
                subtotal=subtotal,
                user_id=user_id,
            )
            discount = coupon_res["discount_amount"]
            applied_coupon_id = coupon_res["coupon_id"]
            await coupon_repo.increment_uses(session, applied_coupon_id)
        except coupon_service.CouponError as e:
            # Release reserved items before raising
            for ri in reserved_items:
                await inventory_repo.release_item(session, ri.id)
            raise OrderError(str(e))
    elif coupon_id is not None:
        coupon_obj = await coupon_repo.get_by_id(session, coupon_id)
        if coupon_obj:
            try:
                coupon_res = await coupon_service.validate_and_calculate_discount(
                    session=session,
                    code=coupon_obj.code,
                    subtotal=subtotal,
                    user_id=user_id,
                )
                discount = coupon_res["discount_amount"]
                applied_coupon_id = coupon_obj.id
                await coupon_repo.increment_uses(session, applied_coupon_id)
            except coupon_service.CouponError as e:
                for ri in reserved_items:
                    await inventory_repo.release_item(session, ri.id)
                raise OrderError(str(e))
    else:
        discount = compute_first_order_discount(user, subtotal)
        if discount > Decimal("0.00") and user:
            user.channel_discount_used = True

    final_amount = max(subtotal - discount, Decimal("0.01"))

    settings = get_settings()
    warranty_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.warranty_hours)

    # Generate unique order ID
    public_order_id = await order_repo.generate_public_order_id(session)

    # Create order (inventory_id = first item for backward compatibility)
    order = await order_repo.create(
        session,
        public_order_id=public_order_id,
        user_id=user_id,
        product_id=product_id,
        inventory_id=reserved_items[0].id,
        amount=final_amount,
        discount_amount=discount,
        currency=product.currency,
        quantity=quantity,
        warranty_expires_at=warranty_expires_at,
        coupon_id=applied_coupon_id,
    )

    # Link all inventory items to this order
    for item in reserved_items:
        item.order_id = order.id
    await session.flush()

    logger.info(
        "Order created: %s product=%s user_id=%s qty=%s subtotal=%s discount=%s amount=%s coupon_id=%s",
        public_order_id, product.name, user_id, quantity, subtotal, discount, final_amount, coupon_id,
    )

    return {
        "order": order,
        "inventory_items": reserved_items,
        "subtotal": subtotal,
        "discount": discount,
    }


async def cancel_order(session: AsyncSession, order_id: int) -> Optional[Order]:
    """Cancel an order, release its inventory, and restore first-order discount if applied.

    Only PENDING_PAYMENT orders can be cancelled by user.
    """
    order = await order_repo.get_by_id(session, order_id)
    if order is None:
        return None

    if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
        raise OrderError(f"Cannot cancel order in status {order.status.value}")

    # Release all inventory items linked to this order
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    for item in items:
        await inventory_repo.release_item(session, item.id)

    # Also release the primary inventory_id if not covered
    if order.inventory_id and not any(i.id == order.inventory_id for i in items):
        await inventory_repo.release_item(session, order.inventory_id)

    # Restore channel discount if order had discount applied
    if order.discount_amount and order.discount_amount > Decimal("0.00"):
        from app.database.repositories import user_repo
        user = await user_repo.get_by_id(session, order.user_id)
        if user:
            user.channel_discount_used = False

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
        Dict with 'order' and 'contents' (list of delivered item contents),
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

    # Mark all inventory items as sold and collect decrypted contents
    contents = []
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    for item in items:
        await inventory_repo.mark_sold(session, item.id, order.id)
        contents.append(decrypt_content(item.content))

    # Fallback: if no items found via order_id, try inventory_id
    if not contents and order.inventory_id:
        await inventory_repo.mark_sold(session, order.inventory_id, order.id)
        item = await inventory_repo.get_item_by_id(session, order.inventory_id)
        if item:
            contents.append(decrypt_content(item.content))

    # Mark order fulfilled
    order = await order_repo.update_status(
        session, order_id, OrderStatus.FULFILLED,
        delivered_at=datetime.now(timezone.utc),
    )

    # Credit affiliate commission if order used an affiliate coupon
    try:
        await coupon_service.credit_affiliate_for_order(session, order)
    except Exception as e:
        logger.warning("Error crediting affiliate commission for order %s: %s", order.public_order_id, e)

    logger.info("Order fulfilled: %s (%d items)", order.public_order_id, len(contents))
    return {"order": order, "contents": contents, "content": contents[0] if contents else None}


async def get_expiring_orders_for_warning(
    session: AsyncSession,
    expiry_minutes: int = 30,
    warning_minutes_before: int = 10,
) -> list[Order]:
    """Find pending orders that have <= warning_minutes_before remaining before expiration."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    threshold_minutes = max(1, expiry_minutes - warning_minutes_before)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    stmt = (
        select(Order)
        .options(selectinload(Order.user), selectinload(Order.product))
        .where(Order.status == OrderStatus.PENDING_PAYMENT)
        .where(Order.created_at <= cutoff)
        .where(Order.expiry_warned == False)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_order_warned(session: AsyncSession, order_id: int) -> None:
    """Mark order as having received the expiry warning."""
    from sqlalchemy import update
    stmt = update(Order).where(Order.id == order_id).values(expiry_warned=True)
    await session.execute(stmt)
    await session.flush()


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
