"""User repository."""

from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Order, OrderStatus, Referral, User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> User:
    """Get existing user or create a new one.

    Returns:
        The User object (new or existing).
    """
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        # Update profile info if changed
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if last_name is not None and user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if changed:
            await session.flush()
        return user

    # Create new user
    referral_code = f"ref_{secrets.token_hex(6)}"
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        referral_code=referral_code,
    )
    session.add(user)
    await session.flush()
    return user


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """Get a user by their Telegram ID."""
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by their internal ID."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_referral_code(session: AsyncSession, code: str) -> Optional[User]:
    """Find a user by their referral code."""
    stmt = select(User).where(User.referral_code == code)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_balance(
    session: AsyncSession, user_id: int, amount: Decimal
) -> User:
    """Atomically update a user's balance.

    Args:
        amount: Positive to credit, negative to debit.

    Raises:
        ValueError: If the resulting balance would be negative.
    """
    stmt = select(User).where(User.id == user_id).with_for_update()
    result = await session.execute(stmt)
    user = result.scalar_one()

    new_balance = user.balance + amount
    if new_balance < Decimal("0"):
        raise ValueError("Insufficient balance")

    user.balance = new_balance
    await session.flush()
    return user


async def list_users(
    session: AsyncSession, offset: int = 0, limit: int = 20
) -> list[User]:
    """List users with pagination."""
    stmt = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_users(session: AsyncSession) -> int:
    """Count total registered users."""
    stmt = select(func.count(User.id))
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_user_stats(session: AsyncSession, user_id: int) -> dict:
    """Get aggregated stats for a user."""
    # Order count
    order_count_stmt = select(func.count(Order.id)).where(Order.user_id == user_id)
    order_result = await session.execute(order_count_stmt)
    order_count = order_result.scalar_one()

    # Total spent
    spent_stmt = (
        select(func.coalesce(func.sum(Order.amount), 0))
        .where(Order.user_id == user_id)
        .where(Order.status.in_([OrderStatus.PAID, OrderStatus.FULFILLED]))
    )
    spent_result = await session.execute(spent_stmt)
    total_spent = spent_result.scalar_one()

    return {
        "order_count": order_count,
        "total_spent": Decimal(str(total_spent)),
    }


async def set_blocked(session: AsyncSession, user_id: int, blocked: bool) -> None:
    """Block or unblock a user."""
    stmt = update(User).where(User.id == user_id).values(is_blocked=blocked)
    await session.execute(stmt)


async def set_admin(session: AsyncSession, user_id: int, is_admin: bool) -> None:
    """Grant or revoke admin status."""
    stmt = update(User).where(User.id == user_id).values(is_admin=is_admin)
    await session.execute(stmt)


async def create_referral(
    session: AsyncSession,
    referrer_user_id: int,
    referred_user_id: int,
    reward_amount: Decimal = Decimal("0.00"),
) -> Referral:
    """Record a referral relationship."""
    referral = Referral(
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        reward_amount=reward_amount,
    )
    session.add(referral)
    await session.flush()
    return referral


async def count_referrals(session: AsyncSession, user_id: int) -> int:
    """Count how many users a given user has referred."""
    stmt = select(func.count(Referral.id)).where(Referral.referrer_user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one()
