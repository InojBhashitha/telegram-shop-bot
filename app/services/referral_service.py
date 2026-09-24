"""Referral service — customer invitations, commissions, and notifications."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Order, ReferralCommission, User
from app.database.repositories import referral_repo, user_repo

logger = logging.getLogger(__name__)


def _get_active_bot(bot: Optional[Bot] = None) -> Optional[Bot]:
    """Helper to retrieve Telegram bot instance."""
    if bot:
        return bot
    try:
        from app.bot.bot import get_bot_instance
        return get_bot_instance()
    except Exception:
        return None


async def bind_referral(
    session: AsyncSession,
    new_user: User,
    referral_code: str,
    bot: Optional[Bot] = None,
) -> Optional[User]:
    """Bind a newly registered user to their referrer and notify the referrer.

    Args:
        session: Database session.
        new_user: The user who just started the bot.
        referral_code: The referral token or ref_<telegram_id> string.
        bot: Optional Telegram Bot instance for sending notifications.

    Returns:
        The referrer User object if successfully linked, otherwise None.
    """
    if not referral_code or not referral_code.strip():
        return None

    # User already has a referrer
    if new_user.referred_by is not None:
        return None

    referrer = await user_repo.get_by_referral_code(session, referral_code.strip())
    if referrer is None or referrer.id == new_user.id:
        return None

    # Check if a referral record already exists
    existing = await referral_repo.get_referral_by_referred_id(session, new_user.id)
    if existing:
        return None

    new_user.referred_by = referrer.id
    await referral_repo.create_referral(
        session,
        referrer_user_id=referrer.id,
        referred_user_id=new_user.id,
    )
    await session.flush()

    logger.info(
        "Referral linked: user %s (%s) referred by %s (%s)",
        new_user.id, new_user.telegram_id, referrer.id, referrer.telegram_id,
    )

    # Dispatch celebration notification to referrer
    active_bot = _get_active_bot(bot)
    if active_bot and referrer.telegram_id:
        settings = get_settings()
        rate = settings.referral_commission_percent
        friend_name = f"@{new_user.username}" if new_user.username else f"User {new_user.telegram_id}"
        text = (
            f"🎉 *New Referral Joined!*\n\n"
            f"A friend just joined Cloud Deals using your referral link:\n"
            f"👤 *{friend_name}*\n\n"
            f"🎁 You will automatically earn *{rate:.1f}% commission* in wallet credits on all their purchases!\n\n"
            f"Keep sharing to earn more! 🚀"
        )
        try:
            await active_bot.send_message(
                chat_id=referrer.telegram_id,
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("Could not send referral join notification to %s: %s", referrer.telegram_id, e)

    return referrer


async def process_order_commission(
    session: AsyncSession,
    order: Order,
    bot: Optional[Bot] = None,
) -> Optional[Decimal]:
    """Calculate and credit referral commission upon order fulfillment.

    Args:
        session: Database session.
        order: The fulfilled Order object.
        bot: Optional Telegram Bot instance for sending notifications.

    Returns:
        Commission Decimal amount credited, or None.
    """
    # Check if ordering user has a referrer
    user = await user_repo.get_by_id(session, order.user_id)
    if not user or not user.referred_by:
        return None

    referrer = await user_repo.get_by_id(session, user.referred_by)
    if not referrer:
        return None

    # Idempotency check: don't process twice for the same order
    stmt = select(ReferralCommission).where(ReferralCommission.order_id == order.id)
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is not None:
        logger.info("Referral commission already processed for order %s", order.id)
        return None

    settings = get_settings()
    rate = Decimal(str(settings.referral_commission_percent))
    if rate <= Decimal("0.00"):
        return None

    commission = (order.amount * (rate / Decimal("100"))).quantize(Decimal("0.01"))
    if commission <= Decimal("0.00"):
        return None

    # Credit referrer wallet balance
    updated_referrer = await user_repo.update_balance(session, referrer.id, commission)

    # Record commission audit trail
    await referral_repo.record_commission(
        session=session,
        referrer_user_id=referrer.id,
        referred_user_id=user.id,
        order_id=order.id,
        order_amount=order.amount,
        commission_rate=rate,
        commission_amount=commission,
    )

    logger.info(
        "Referral commission credited: $%s to user %s (order %s, buyer %s)",
        commission, referrer.telegram_id, order.public_order_id, user.telegram_id,
    )

    # Notify referrer of earned commission
    active_bot = _get_active_bot(bot)
    if active_bot and referrer.telegram_id:
        text = (
            f"💰 *Referral Commission Earned!*\n\n"
            f"Your referral completed an order!\n"
            f"📦 *Order:* `{order.public_order_id}`\n"
            f"💵 *Order Total:* `${order.amount:.2f}`\n"
            f"🎁 *Commission (+{rate:.1f}%):* `+${commission:.2f}`\n\n"
            f"💼 *Your Balance:* `${updated_referrer.balance:.2f}`\n\n"
            f"Your wallet credits are ready to spend in the store anytime! ⚡"
        )
        try:
            await active_bot.send_message(
                chat_id=referrer.telegram_id,
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("Could not send referral commission alert to %s: %s", referrer.telegram_id, e)

    return commission


async def get_referral_summary(session: AsyncSession, user_id: int) -> dict:
    """Retrieve full referral dashboard stats for a user."""
    settings = get_settings()
    count = await referral_repo.count_referrals(session, user_id)
    total_earned = await referral_repo.get_total_commissions_earned(session, user_id)
    recent = await referral_repo.get_recent_commissions(session, user_id, limit=5)

    return {
        "referral_count": count,
        "total_earned": total_earned,
        "commission_rate": settings.referral_commission_percent,
        "recent_commissions": recent,
    }
