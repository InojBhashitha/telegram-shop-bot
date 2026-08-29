"""Cart service — shopping cart management, stock validation, and unified cart checkout."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import CartItem, Inventory, Order, OrderStatus
from app.database.repositories import cart_repo, inventory_repo, order_repo, product_repo

logger = logging.getLogger(__name__)


class CartError(Exception):
    """Raised when a cart operation fails."""
    pass


async def add_to_cart(
    session: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int = 1,
) -> dict:
    """Add a product to the user's cart with live stock validation.

    Args:
        session: Async database session.
        user_id: User database ID.
        product_id: Product ID to add.
        quantity: Number of accounts to add.

    Returns:
        Dict with 'cart_item' and 'total_cart_items'.

    Raises:
        CartError: If product inactive, not found, or quantity exceeds stock.
    """
    if quantity < 1:
        raise CartError("Quantity must be at least 1")

    product = await product_repo.get_by_id(session, product_id)
    if product is None or not product.active:
        raise CartError("Product is not available")

    stock = await inventory_repo.get_stock_count(session, product_id)
    if stock == 0:
        raise CartError(f"Sorry, '{product.name}' is currently out of stock")

    existing_item = await cart_repo.get_cart_item(session, user_id, product_id)
    current_cart_qty = existing_item.quantity if existing_item else 0
    new_total_qty = current_cart_qty + quantity

    if new_total_qty > stock:
        if current_cart_qty > 0:
            raise CartError(
                f"Cannot add {quantity} more. Only {stock} in stock "
                f"(you already have {current_cart_qty} in your cart)."
            )
        raise CartError(f"Cannot add {quantity}. Only {stock} available in stock.")

    item = await cart_repo.add_or_update_item(session, user_id, product_id, quantity)
    total_items = await cart_repo.get_cart_item_count(session, user_id)

    logger.info("Cart updated: user=%s product=%s qty=%s", user_id, product.name, item.quantity)
    return {"cart_item": item, "total_cart_items": total_items, "product": product}


async def update_cart_quantity(
    session: AsyncSession,
    user_id: int,
    product_id: int,
    quantity: int,
) -> Optional[CartItem]:
    """Set the exact quantity of a product in the user's cart."""
    if quantity <= 0:
        await cart_repo.remove_item(session, user_id, product_id)
        return None

    stock = await inventory_repo.get_stock_count(session, product_id)
    if quantity > stock:
        raise CartError(f"Cannot set quantity to {quantity}. Only {stock} available in stock.")

    return await cart_repo.set_item_quantity(session, user_id, product_id, quantity)


async def remove_from_cart(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> bool:
    """Remove a product from the user's cart."""
    return await cart_repo.remove_item(session, user_id, product_id)


async def clear_cart(
    session: AsyncSession,
    user_id: int,
) -> int:
    """Empty the user's cart."""
    return await cart_repo.clear_cart(session, user_id)


async def get_cart_summary(
    session: AsyncSession,
    user_id: int,
) -> dict:
    """Get full cart details, subtotal, and stock validation status for each item.

    Returns:
        Dict with 'items', 'total_amount', 'total_count', 'is_valid', 'currency'.
    """
    raw_items = await cart_repo.get_user_cart(session, user_id)

    items_data = []
    total_amount = Decimal("0.00")
    total_count = 0
    is_valid = len(raw_items) > 0
    currency = "USD"

    for item in raw_items:
        product = item.product
        if not product:
            continue
        currency = product.currency
        subtotal = product.price * item.quantity
        total_amount += subtotal
        total_count += item.quantity

        stock = await inventory_repo.get_stock_count(session, product.id)
        has_stock = stock >= item.quantity and product.active
        if not has_stock:
            is_valid = False

        items_data.append({
            "cart_item_id": item.id,
            "product_id": product.id,
            "product_name": product.name,
            "unit_price": product.price,
            "quantity": item.quantity,
            "subtotal": subtotal,
            "stock": stock,
            "has_stock": has_stock,
            "active": product.active,
        })

    return {
        "items": items_data,
        "total_amount": total_amount,
        "total_count": total_count,
        "is_valid": is_valid,
        "currency": currency,
    }


async def checkout_cart(
    session: AsyncSession,
    user_id: int,
) -> dict:
    """Checkout all items in the user's cart.

    Steps:
    1. Validates cart is not empty.
    2. Validates stock for all items.
    3. Atomically reserves inventory items across all products.
    4. Creates master Order record for the total amount.
    5. Clears the cart.

    Returns:
        Dict with 'order' and 'inventory_items'.

    Raises:
        CartError: If cart empty or insufficient stock for any item.
    """
    summary = await get_cart_summary(session, user_id)
    items = summary["items"]

    if not items:
        raise CartError("Your cart is empty")

    if not summary["is_valid"]:
        # Find the offending item
        for item in items:
            if not item["has_stock"]:
                if not item["active"]:
                    raise CartError(f"'{item['product_name']}' is no longer available.")
                raise CartError(
                    f"Not enough stock for '{item['product_name']}'. "
                    f"Requested {item['quantity']}, but only {item['stock']} available."
                )

    # Atomically reserve inventory items across all products
    all_reserved: list[Inventory] = []
    try:
        for item in items:
            qty = item["quantity"]
            pid = item["product_id"]
            if qty == 1:
                reserved = await inventory_repo.reserve_item(session, pid)
                if not reserved:
                    raise CartError(f"Failed to reserve stock for '{item['product_name']}'.")
                all_reserved.append(reserved)
            else:
                reserved_list = await inventory_repo.reserve_items(session, pid, qty)
                if len(reserved_list) < qty:
                    # Release any partially reserved
                    for r in reserved_list:
                        await inventory_repo.release_item(session, r.id)
                    raise CartError(f"Failed to reserve stock for '{item['product_name']}'.")
                all_reserved.extend(reserved_list)

    except Exception:
        # Release all already reserved items on failure
        for r in all_reserved:
            await inventory_repo.release_item(session, r.id)
        raise

    # Create master order
    settings = get_settings()
    public_order_id = await order_repo.generate_public_order_id(session)
    warranty_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.warranty_hours)

    primary_product_id = items[0]["product_id"] if len(items) == 1 else None

    order = await order_repo.create(
        session,
        public_order_id=public_order_id,
        user_id=user_id,
        product_id=primary_product_id or items[0]["product_id"],
        inventory_id=all_reserved[0].id,
        amount=summary["total_amount"],
        currency=summary["currency"],
        quantity=summary["total_count"],
        warranty_expires_at=warranty_expires_at,
    )

    # Link all reserved inventory items to this master order
    for inv_item in all_reserved:
        inv_item.order_id = order.id
    await session.flush()

    # Clear user's cart on successful order creation
    await cart_repo.clear_cart(session, user_id)

    logger.info(
        "Cart checkout successful: order=%s items=%s total=%s",
        public_order_id, len(all_reserved), summary["total_amount"],
    )

    return {"order": order, "inventory_items": all_reserved, "summary": summary}
