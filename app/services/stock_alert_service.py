"""Stock alert service — customer restock subscriptions and automated notifications."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import StockAlert
from app.database.repositories import product_repo, stock_alert_repo

logger = logging.getLogger(__name__)


async def subscribe_user(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> tuple[StockAlert, bool]:
    """Subscribe a user to restock alerts for a product."""
    return await stock_alert_repo.subscribe(session, user_id, product_id)


async def subscribe_stock_alert(
    session: AsyncSession,
    user_id: int,
    product_id: int,
) -> StockAlert:
    """Subscribe a user to restock alerts and return the StockAlert model."""
    alert, _ = await stock_alert_repo.subscribe(session, user_id, product_id)
    return alert


async def notify_restocked_product(
    session: AsyncSession,
    product_id: int,
    new_stock_count: int = 1,
    bot: Optional[Bot] = None,
) -> int:
    """Convenience wrapper to notify subscribers of a restocked product."""
    return await notify_subscribers_of_restock(bot=bot, session=session, product_id=product_id)


async def notify_subscribers_of_restock(
    bot: Optional[Bot],
    session: AsyncSession,
    product_id: int,
) -> int:
    """Send restock notification to all users who subscribed to this product.

    Args:
        bot: Telegram Bot instance (if available).
        session: Database session.
        product_id: ID of the product that was restocked.

    Returns:
        Number of users notified.
    """
    alerts = await stock_alert_repo.get_pending_alerts_for_product(session, product_id)
    if not alerts:
        return 0

    product = await product_repo.get_by_id(session, product_id)
    if not product:
        return 0

    alert_ids: list[int] = []
    notified_count = 0

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📦 Buy {product.name}", callback_data=f"prod:{product.id}")],
        [InlineKeyboardButton("🏪 Open Store", callback_data="products")],
    ])

    text = (
        f"🔔 *Good News\\! Stock Restocked*\n\n"
        f"📦 *{product.name}* is back in stock\\!\n\n"
        f"💵 Price: `${product.price:.2f}`\n\n"
        f"Grab yours now before it sells out again\\! ⚡"
    )

    for alert in alerts:
        alert_ids.append(alert.id)
        if bot and alert.user and alert.user.telegram_id:
            try:
                await bot.send_message(
                    chat_id=alert.user.telegram_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                notified_count += 1
            except TelegramError as e:
                logger.warning(
                    "Could not send restock notification to user %s: %s",
                    alert.user.telegram_id, e,
                )

    await stock_alert_repo.mark_notified(session, alert_ids)
    logger.info("Restock notifications dispatched for product %s: %s users", product_id, notified_count)
    return notified_count
