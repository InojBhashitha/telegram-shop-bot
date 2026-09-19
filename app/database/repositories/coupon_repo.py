"""Coupon repository for promo codes and affiliate tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Coupon, CouponType


async def get_by_code(session: AsyncSession, code: str) -> Optional[Coupon]:
    """Look up a coupon by its case-insensitive code."""
    stmt = select(Coupon).where(Coupon.code == code.strip().upper())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, coupon_id: int) -> Optional[Coupon]:
    """Look up a coupon by its primary key ID."""
    stmt = select(Coupon).where(Coupon.id == coupon_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    code: str,
    discount_type: CouponType,
    discount_value: Decimal,
    min_order_amount: Decimal = Decimal("0.00"),
    max_discount: Optional[Decimal] = None,
    max_uses: Optional[int] = None,
    expiry_at: Optional[datetime] = None,
    affiliate_user_id: Optional[int] = None,
    affiliate_commission_pct: Decimal = Decimal("0.00"),
) -> Coupon:
    """Create a new coupon."""
    coupon = Coupon(
        code=code.strip().upper(),
        discount_type=discount_type,
        discount_value=discount_value,
        min_order_amount=min_order_amount,
        max_discount=max_discount,
        max_uses=max_uses,
        expiry_at=expiry_at,
        affiliate_user_id=affiliate_user_id,
        affiliate_commission_pct=affiliate_commission_pct,
        active=True,
    )
    session.add(coupon)
    await session.flush()
    return coupon


async def increment_uses(session: AsyncSession, coupon_id: int) -> None:
    """Increment the usage counter of a coupon."""
    stmt = (
        update(Coupon)
        .where(Coupon.id == coupon_id)
        .values(current_uses=Coupon.current_uses + 1)
    )
    await session.execute(stmt)
    await session.flush()


async def list_all(session: AsyncSession, active_only: bool = False) -> list[Coupon]:
    """List all coupons, optionally filtered by active status."""
    stmt = select(Coupon).order_by(Coupon.created_at.desc())
    if active_only:
        stmt = stmt.where(Coupon.active == True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_active(session: AsyncSession, coupon_id: int, active: bool) -> Optional[Coupon]:
    """Activate or deactivate a coupon."""
    coupon = await get_by_id(session, coupon_id)
    if coupon:
        coupon.active = active
        await session.flush()
    return coupon
