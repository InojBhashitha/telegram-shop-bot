"""Category repository."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Category


async def create(
    session: AsyncSession,
    name: str,
    description: Optional[str] = None,
    icon: Optional[str] = None,
    sort_order: int = 0,
) -> Category:
    """Create a new product category."""
    cat = Category(
        name=name,
        description=description,
        icon=icon,
        sort_order=sort_order,
    )
    session.add(cat)
    await session.flush()
    return cat


async def get_by_id(session: AsyncSession, category_id: int) -> Optional[Category]:
    """Get a category by ID."""
    stmt = select(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_active(session: AsyncSession) -> list[Category]:
    """List all active categories ordered by sort_order."""
    stmt = (
        select(Category)
        .where(Category.active == True)
        .order_by(Category.sort_order, Category.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_all(session: AsyncSession) -> list[Category]:
    """List all categories including inactive ones."""
    stmt = select(Category).order_by(Category.sort_order, Category.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_category(
    session: AsyncSession,
    category_id: int,
    **kwargs,
) -> Optional[Category]:
    """Update a category's fields."""
    stmt = select(Category).where(Category.id == category_id)
    result = await session.execute(stmt)
    cat = result.scalar_one_or_none()
    if cat is None:
        return None
    for key, value in kwargs.items():
        if hasattr(cat, key):
            setattr(cat, key, value)
    await session.flush()
    return cat


async def deactivate(session: AsyncSession, category_id: int) -> None:
    """Soft-delete a category by marking it inactive."""
    stmt = update(Category).where(Category.id == category_id).values(active=False)
    await session.execute(stmt)
