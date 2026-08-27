"""Delivery service — sends purchased digital products via Telegram."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from app.database.models import Order

logger = logging.getLogger(__name__)


async def deliver_to_user(
    bot: Bot,
    telegram_id: int,
    order: Order,
    content: str,
    product_name: str,
) -> bool:
    """Send the purchased product to the customer via Telegram.

    Args:
        bot: Telegram Bot instance.
        telegram_id: Customer's Telegram user ID.
        order: The fulfilled order.
        content: The deliverable content string.
        product_name: Name of the product.

    Returns:
        True if delivery succeeded, False if Telegram send failed.
    """
    message = (
        f"✅ *Payment Confirmed!*\n\n"
        f"📦 *Order:* `{order.public_order_id}`\n"
        f"🏷 *Product:* {product_name}\n\n"
        f"🎁 *Your product:*\n"
        f"```\n{content}\n```\n\n"
        f"Thank you for using Cloud Deals! ☁️"
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info(
            "Delivery sent: order=%s user=%s",
            order.public_order_id, telegram_id,
        )
        return True

    except TelegramError as e:
        logger.error(
            "Delivery failed: order=%s user=%s error=%s",
            order.public_order_id, telegram_id, e,
        )
        return False


async def send_payment_update(
    bot: Bot,
    telegram_id: int,
    order_public_id: str,
    status_text: str,
) -> bool:
    """Send a payment status update to the customer."""
    message = (
        f"💳 *Payment Update*\n\n"
        f"📦 Order: `{order_public_id}`\n"
        f"Status: {status_text}"
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode="Markdown",
        )
        return True
    except TelegramError as e:
        logger.error(
            "Payment update notification failed: order=%s error=%s",
            order_public_id, e,
        )
        return False
