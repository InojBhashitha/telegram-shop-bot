"""User service — business logic for user management."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import user_repo

logger = logging.getLogger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    referral_code: Optional[str] = None,
    bot: Optional[Any] = None,
) -> dict:
    """Get or create a user, optionally processing a referral code.

    Returns:
        Dict with 'user' and 'is_new' flag.
    """
    existing = await user_repo.get_by_telegram_id(session, telegram_id)
    is_new = existing is None

    user = await user_repo.get_or_create_user(
        session, telegram_id, username, first_name, last_name
    )

    # Process referral for new users
    if is_new and referral_code:
        from app.services import referral_service
        await referral_service.bind_referral(
            session=session,
            new_user=user,
            referral_code=referral_code,
            bot=bot,
        )

    return {"user": user, "is_new": is_new}


async def get_profile(session: AsyncSession, telegram_id: int) -> Optional[dict]:
    """Get complete user profile with stats."""
    user = await user_repo.get_by_telegram_id(session, telegram_id)
    if user is None:
        return None

    stats = await user_repo.get_user_stats(session, user.id)
    referral_count = await user_repo.count_referrals(session, user.id)

    return {
        "user": user,
        "order_count": stats["order_count"],
        "total_spent": stats["total_spent"],
        "referral_count": referral_count,
    }


async def credit_balance(
    session: AsyncSession, user_id: int, amount: Decimal
) -> Decimal:
    """Credit a user's balance. Returns the new balance."""
    if amount <= 0:
        raise ValueError("Credit amount must be positive")
    user = await user_repo.update_balance(session, user_id, amount)
    logger.info("Balance credited: user_id=%s amount=%s new_balance=%s",
                user_id, amount, user.balance)
    return user.balance


async def debit_balance(
    session: AsyncSession, user_id: int, amount: Decimal
) -> Decimal:
    """Debit a user's balance. Returns the new balance.

    Raises:
        ValueError: If insufficient balance.
    """
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    user = await user_repo.update_balance(session, user_id, -amount)
    logger.info("Balance debited: user_id=%s amount=%s new_balance=%s",
                user_id, amount, user.balance)
    return user.balance
