"""Product service — business logic for products and categories."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DeliveryType
from app.database.repositories import category_repo, product_repo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def get_active_categories(session: AsyncSession) -> list:
    """Get all active categories."""
    return await category_repo.list_active(session)


async def get_category(session: AsyncSession, category_id: int):
    """Get a single category by ID."""
    return await category_repo.get_by_id(session, category_id)


async def create_category(
    session: AsyncSession,
    name: str,
    description: Optional[str] = None,
    icon: Optional[str] = None,
) -> object:
    """Create a new category."""
    cat = await category_repo.create(session, name, description, icon)
    logger.info("Category created: id=%s name=%s", cat.id, cat.name)
    return cat


async def update_category(session: AsyncSession, category_id: int, **kwargs) -> object:
    """Update a category."""
    cat = await category_repo.update_category(session, category_id, **kwargs)
    if cat:
        logger.info("Category updated: id=%s", category_id)
    return cat


async def deactivate_category(session: AsyncSession, category_id: int) -> None:
    """Soft-delete a category."""
    await category_repo.deactivate(session, category_id)
    logger.info("Category deactivated: id=%s", category_id)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

async def get_products_by_category(
    session: AsyncSession, category_id: int
) -> list:
    """Get active products in a category."""
    return await product_repo.list_by_category(session, category_id, active_only=True)


async def get_product_details(
    session: AsyncSession, product_id: int
) -> Optional[dict]:
    """Get product with stock count."""
    return await product_repo.get_product_with_stock(session, product_id)


async def create_product(
    session: AsyncSession,
    category_id: int,
    name: str,
    price: Decimal,
    currency: str = "USD",
    description: Optional[str] = None,
    delivery_type: str = "digital",
    active: bool = True,
) -> object:
    """Create a new product."""
    dt = DeliveryType(delivery_type)
    prod = await product_repo.create(
        session, category_id, name, price, currency, description, dt, active
    )
    logger.info("Product created: id=%s name=%s price=%s", prod.id, prod.name, prod.price)
    return prod


async def update_product(session: AsyncSession, product_id: int, **kwargs) -> object:
    """Update a product."""
    prod = await product_repo.update_product(session, product_id, **kwargs)
    if prod:
        logger.info("Product updated: id=%s", product_id)
    return prod


async def deactivate_product(session: AsyncSession, product_id: int) -> None:
    """Soft-delete a product."""
    await product_repo.deactivate(session, product_id)
    logger.info("Product deactivated: id=%s", product_id)
