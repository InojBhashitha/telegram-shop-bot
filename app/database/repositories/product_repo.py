"""Product repository."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    DeliveryType,
    Inventory,
    InventoryStatus,
    Product,
)


async def create(
    session: AsyncSession,
    category_id: int,
    name: str,
    price: Decimal,
    currency: str = "USD",
    description: Optional[str] = None,
    delivery_type: DeliveryType = DeliveryType.DIGITAL,
    active: bool = True,
) -> Product:
    """Create a new product."""
    product = Product(
        category_id=category_id,
        name=name,
        description=description,
        price=price,
        currency=currency,
        delivery_type=delivery_type,
        active=active,
    )
    session.add(product)
    await session.flush()
    return product


async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
    """Get a product by ID."""
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_category(
    session: AsyncSession, category_id: int, active_only: bool = True
) -> list[Product]:
    """List products in a category."""
    stmt = select(Product).where(Product.category_id == category_id)
    if active_only:
        stmt = stmt.where(Product.active == True)
    stmt = stmt.order_by(Product.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_active(session: AsyncSession) -> list[Product]:
    """List all active products."""
    stmt = select(Product).where(Product.active == True).order_by(Product.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_stock_count(session: AsyncSession, product_id: int) -> int:
    """Count available inventory for a product."""
    stmt = (
        select(func.count(Inventory.id))
        .where(Inventory.product_id == product_id)
        .where(Inventory.status == InventoryStatus.AVAILABLE)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def update_product(
    session: AsyncSession,
    product_id: int,
    **kwargs,
) -> Optional[Product]:
    """Update a product's fields."""
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        return None
    for key, value in kwargs.items():
        if hasattr(product, key):
            setattr(product, key, value)
    await session.flush()
    return product


async def deactivate(session: AsyncSession, product_id: int) -> None:
    """Soft-delete a product by marking it inactive."""
    stmt = update(Product).where(Product.id == product_id).values(active=False)
    await session.execute(stmt)


async def get_product_with_stock(
    session: AsyncSession, product_id: int
) -> Optional[dict]:
    """Get product details including stock count."""
    product = await get_by_id(session, product_id)
    if product is None:
        return None
    stock = await get_stock_count(session, product_id)
    return {
        "product": product,
        "stock": stock,
    }
