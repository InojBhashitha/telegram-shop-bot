"""Cart repository — database operations for user shopping carts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import CartItem, Product


async def get_user_cart(session: AsyncSession, user_id: int) -> list[CartItem]:
    """Get all cart items for a user, ordered by created_at."""
    stmt = (
        select(CartItem)
        .options(selectinload(CartItem.product))
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_cart_item(
    session: AsyncSession, user_id: int, product_id: int
) -> Optional[CartItem]:
    """Get a specific cart item for a user and product."""
    stmt = (
        select(CartItem)
        .options(selectinload(CartItem.product))
        .where(CartItem.user_id == user_id)
        .where(CartItem.product_id == product_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def add_or_update_item(
    session: AsyncSession, user_id: int, product_id: int, quantity: int
) -> CartItem:
    """Add item to cart or increment quantity if already exists."""
    item = await get_cart_item(session, user_id, product_id)
    now = datetime.now(timezone.utc)
    if item:
        item.quantity += quantity
        item.updated_at = now
    else:
        item = CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            created_at=now,
            updated_at=now,
        )
        session.add(item)

    await session.flush()
    return item


async def set_item_quantity(
    session: AsyncSession, user_id: int, product_id: int, quantity: int
) -> Optional[CartItem]:
    """Set exact quantity for a cart item, or remove it if quantity <= 0."""
    item = await get_cart_item(session, user_id, product_id)
    if item is None:
        if quantity > 0:
            return await add_or_update_item(session, user_id, product_id, quantity)
        return None

    if quantity <= 0:
        await session.delete(item)
        await session.flush()
        return None

    item.quantity = quantity
    item.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return item


async def remove_item(
    session: AsyncSession, user_id: int, product_id: int
) -> bool:
    """Remove a product from the user's cart."""
    stmt = (
        delete(CartItem)
        .where(CartItem.user_id == user_id)
        .where(CartItem.product_id == product_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0


async def clear_cart(session: AsyncSession, user_id: int) -> int:
    """Clear all items in a user's cart."""
    stmt = delete(CartItem).where(CartItem.user_id == user_id)
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount


async def get_cart_item_count(session: AsyncSession, user_id: int) -> int:
    """Get the total sum of item quantities in user's cart."""
    stmt = select(func.coalesce(func.sum(CartItem.quantity), 0)).where(
        CartItem.user_id == user_id
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())
