"""Referral repository for managing referrals and commission records."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Referral, ReferralCommission


async def create_referral(
    session: AsyncSession,
    referrer_user_id: int,
    referred_user_id: int,
    reward_amount: Decimal = Decimal("0.00"),
) -> Referral:
    """Record a new referral link between two users."""
    referral = Referral(
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        reward_amount=reward_amount,
    )
    session.add(referral)
    await session.flush()
    return referral


async def get_referral_by_referred_id(
    session: AsyncSession,
    referred_user_id: int,
) -> Optional[Referral]:
    """Get the referral record for a referred user."""
    stmt = select(Referral).where(Referral.referred_user_id == referred_user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def count_referrals(session: AsyncSession, user_id: int) -> int:
    """Count how many users a given user has referred."""
    stmt = select(func.count(Referral.id)).where(Referral.referrer_user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one()


async def record_commission(
    session: AsyncSession,
    referrer_user_id: int,
    referred_user_id: int,
    order_id: int,
    order_amount: Decimal,
    commission_rate: Decimal,
    commission_amount: Decimal,
) -> ReferralCommission:
    """Record a paid commission for an order."""
    record = ReferralCommission(
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        order_id=order_id,
        order_amount=order_amount,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
    )
    session.add(record)

    # Also update cumulative reward_amount on the Referral table
    stmt = (
        update(Referral)
        .where(Referral.referred_user_id == referred_user_id)
        .values(reward_amount=Referral.reward_amount + commission_amount)
    )
    await session.execute(stmt)
    await session.flush()
    return record


async def get_total_commissions_earned(
    session: AsyncSession,
    user_id: int,
) -> Decimal:
    """Get sum of all commissions earned by a user."""
    stmt = select(func.coalesce(func.sum(ReferralCommission.commission_amount), Decimal("0.00"))).where(
        ReferralCommission.referrer_user_id == user_id
    )
    result = await session.execute(stmt)
    return Decimal(str(result.scalar_one()))


async def get_recent_commissions(
    session: AsyncSession,
    user_id: int,
    limit: int = 5,
) -> list[ReferralCommission]:
    """Get recent commissions earned by user with order details."""
    stmt = (
        select(ReferralCommission)
        .options(selectinload(ReferralCommission.referred), selectinload(ReferralCommission.order))
        .where(ReferralCommission.referrer_user_id == user_id)
        .order_by(ReferralCommission.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
