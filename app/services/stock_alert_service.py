"""Stock alert service — customer restock subscriptions and automated notifications."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import StockAlert
from app.database.repositories import category_repo, product_repo, stock_alert_repo

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
        f"🔔 *Stock Restocked!*\n\n"
        f"📦 *{product.name}* is back in stock!\n\n"
        f"💵 Price: `${product.price:.2f}`\n\n"
        f"⚡ Automated instant delivery upon payment.\n"
        f"Grab yours now before it sells out again! ⚡"
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


async def post_restock_to_channel(
    bot: Optional[Bot],
    session: AsyncSession,
    product_id: int,
    added_count: int = 1,
    channel_id: Optional[str] = None,
) -> tuple[bool, str]:
    """Broadcast an automated restock announcement to the public channel.

    Returns:
        (success: bool, status_message: str)
    """
    if bot is None:
        return False, "Bot instance unavailable"

    settings = get_settings()
    target_channel = channel_id or settings.restock_channel_id or settings.force_channel_id
    if not target_channel:
        return False, "No restock channel configured in settings"

    product = await product_repo.get_by_id(session, product_id)
    if not product:
        return False, "Product not found"

    category = await category_repo.get_by_id(session, product.category_id) if product.category_id else None
    cat_icon = category.icon if category and category.icon else "☁️"
    cat_name = category.name if category and category.name else "Cloud Services"

    stock_count = await product_repo.get_stock_count(session, product_id)
    bot_user = (
        bot.username
        if hasattr(bot, "username") and bot.username
        else settings.support_username or "CloudDealsBot"
    )
    webapp_url = settings.webapp_url or f"{settings.webhook_base_url}/webapp"

    caption = (
        f"⚡️ *RESTOCK ALERT | {settings.store_name.upper()}* ⚡️\n\n"
        f"📦 *Product:* {product.name}\n"
        f"🏷 *Category:* {cat_icon} {cat_name}\n"
        f"💰 *Price:* ${product.price:.2f} {product.currency}\n"
        f"📥 *Newly Restocked:* +{added_count} accounts\n"
        f"📊 *Current Stock:* {stock_count} available\n\n"
        f"⚡️ *Instant Automated Key Delivery*\n"
        f"🛡️ *{settings.warranty_hours}h Replacement Warranty*\n"
        f"🔒 *100% Tested Working Credentials*\n\n"
        f"🚀 _Tap below to secure your accounts before they sell out!_"
    )

    buttons = [
        [InlineKeyboardButton(f"🛒 Buy in Bot (${product.price:.2f})", url=f"https://t.me/{bot_user}?start=prod_{product.id}")],
        [InlineKeyboardButton("📱 Open Store (Mini App)", url=webapp_url)],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    photo_file = None
    if product.image_url and product.image_url.startswith("/webapp/"):
        candidate_path = Path("app") / product.image_url.lstrip("/")
        if candidate_path.exists() and candidate_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            photo_file = candidate_path

    try:
        if photo_file:
            with open(photo_file, "rb") as f:
                await bot.send_photo(
                    chat_id=target_channel,
                    photo=f,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
        else:
            await bot.send_message(
                chat_id=target_channel,
                text=caption,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        logger.info("Restock announcement published to %s for product %s", target_channel, product_id)
        return True, f"Published to {target_channel}"
    except TelegramError as e:
        logger.warning("Failed to post restock announcement to %s: %s", target_channel, e)
        return False, str(e)


async def handle_restock_event(
    bot: Optional[Bot],
    session: AsyncSession,
    product_id: int,
    added_count: int = 1,
    channel_id: Optional[str] = None,
) -> dict:
    """Execute complete automated restock pipeline:
    1. Notify subscribed users (1-on-1 private DM).
    2. Broadcast announcement to public restock channel.

    Returns:
        Dict with keys:
            - product_id: int
            - subscribers_notified: int
            - channel_posted: bool
            - channel_status: str
    """
    notified_subscribers = await notify_subscribers_of_restock(
        bot=bot,
        session=session,
        product_id=product_id,
    )

    channel_posted, channel_status = await post_restock_to_channel(
        bot=bot,
        session=session,
        product_id=product_id,
        added_count=added_count,
        channel_id=channel_id,
    )

    return {
        "product_id": product_id,
        "subscribers_notified": notified_subscribers,
        "channel_posted": channel_posted,
        "channel_status": channel_status,
    }
