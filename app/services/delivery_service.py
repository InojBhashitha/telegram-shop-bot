"""Delivery service — sends purchased digital products via Telegram with 1-tap copy."""

from __future__ import annotations

import logging
import re
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Order

logger = logging.getLogger(__name__)


def _review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Build interactive 1-5 star review rating keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 ⭐", callback_data=f"review:{order_id}:1"),
            InlineKeyboardButton("2 ⭐", callback_data=f"review:{order_id}:2"),
            InlineKeyboardButton("3 ⭐", callback_data=f"review:{order_id}:3"),
            InlineKeyboardButton("4 ⭐", callback_data=f"review:{order_id}:4"),
            InlineKeyboardButton("5 ⭐", callback_data=f"review:{order_id}:5"),
        ]
    ])


def _format_credentials_for_copy(content: str) -> str:
    """Format credentials into individual 1-tap copyable monospace fields.

    Detects common patterns:
    - Key: Value lines → formatted as 📧 Key: `Value`
    - email:pass:accpass → formatted as individual fields
    - email | pass | accpass → formatted as individual fields
    """
    lines = [l.strip() for l in content.strip().split("\n") if l.strip()]

    # Check if it's a key:value format (e.g. "Email: user@gmail.com")
    kv_pattern = re.compile(r'^(.+?):\s+(.+)$')
    kv_lines = [kv_pattern.match(line) for line in lines]
    if all(m is not None for m in kv_lines) and len(lines) >= 2:
        formatted = []
        icons = {
            "email": "📧", "mail": "📧", "e-mail": "📧",
            "password": "🔑", "pass": "🔑", "pwd": "🔑",
            "mail password": "🔑", "mail pass": "🔑",
            "account password": "🔒", "account pass": "🔒", "acc pass": "🔒",
            "recovery": "🔐", "recovery email": "🔐", "backup": "🔐",
            "login": "🌐", "url": "🌐", "link": "🌐",
            "username": "👤", "user": "👤",
            "pin": "📌", "code": "📌",
        }
        for m in kv_lines:
            key = m.group(1).strip()
            value = m.group(2).strip()
            icon = icons.get(key.lower(), "📋")
            formatted.append(f"{icon} *{key}:* `{value}`")
        return "\n".join(formatted)

    # Check if it's single-line combo format (email:pass:accpass or email|pass|accpass)
    if len(lines) == 1:
        line = lines[0]
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif line.count(":") >= 2:
            parts = [p.strip() for p in line.split(":")]
        else:
            # Just a single value; wrap in code block
            return f"`{line}`"

        labels = ["📧 Email", "🔑 Password", "🔒 Account Pass", "🔐 Recovery", "📋 Extra"]
        formatted = []
        for i, part in enumerate(parts):
            label = labels[i] if i < len(labels) else f"📋 Field {i+1}"
            # Check if part has its own label (e.g. "MailPass: secret123")
            kv = kv_pattern.match(part)
            if kv:
                formatted.append(f"📋 *{kv.group(1).strip()}:* `{kv.group(2).strip()}`")
            else:
                formatted.append(f"{label}: `{part}`")
        return "\n".join(formatted)

    # Fallback: wrap in code block
    return f"```\n{content}\n```"


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
        content: The deliverable content string (or multi-content joined).
        product_name: Name of the product.

    Returns:
        True if delivery succeeded, False if Telegram send failed.
    """
    formatted = _format_credentials_for_copy(content)

    message = (
        f"✅ *Payment Confirmed\\!*\n\n"
        f"📦 *Order:* `{order.public_order_id}`\n"
        f"🏷 *Product:* {product_name}\n\n"
        f"🎁 *Your product:*\n"
        f"{formatted}\n\n"
        f"Thank you for using Cloud Deals\\! ☁️\n\n"
        f"⭐ *Rate your purchase below:*"
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            reply_markup=_review_keyboard(order.id),
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


async def deliver_bulk_to_user(
    bot: Bot,
    telegram_id: int,
    order: Order,
    contents: list[str],
    product_name: str,
) -> bool:
    """Send multiple purchased accounts to the customer.

    Each account is formatted as a numbered block with 1-tap copy fields.
    """
    if len(contents) == 1:
        return await deliver_to_user(bot, telegram_id, order, contents[0], product_name)

    blocks = []
    for i, content in enumerate(contents, 1):
        formatted = _format_credentials_for_copy(content)
        blocks.append(f"🎁 *Account #{i}:*\n{formatted}")

    all_accounts = "\n\n".join(blocks)

    message = (
        f"✅ *Payment Confirmed\\!*\n\n"
        f"📦 *Order:* `{order.public_order_id}`\n"
        f"🏷 *Product:* {product_name}\n"
        f"🔢 *Quantity:* {len(contents)}\n\n"
        f"{all_accounts}\n\n"
        f"Thank you for using Cloud Deals\\! ☁️\n\n"
        f"⭐ *Rate your purchase below:*"
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            reply_markup=_review_keyboard(order.id),
            parse_mode="Markdown",
        )
        logger.info(
            "Bulk delivery sent: order=%s qty=%s user=%s",
            order.public_order_id, len(contents), telegram_id,
        )
        return True

    except TelegramError as e:
        logger.error(
            "Bulk delivery failed: order=%s user=%s error=%s",
            order.public_order_id, telegram_id, e,
        )
        return False


async def deliver_cart_order_to_user(
    bot: Bot,
    telegram_id: int,
    order: Order,
    items_by_product: dict[str, list[str]],
) -> bool:
    """Send multi-product purchased accounts to the customer.

    Args:
        bot: Telegram Bot instance.
        telegram_id: Customer Telegram user ID.
        order: The fulfilled order.
        items_by_product: Dict mapping product_name -> list of content strings.
    """
    sections = []
    total_qty = sum(len(c) for c in items_by_product.values())

    for prod_name, contents in items_by_product.items():
        prod_header = f"🏷 *{prod_name}* ({len(contents)}x):"
        blocks = []
        for i, content in enumerate(contents, 1):
            formatted = _format_credentials_for_copy(content)
            if len(contents) > 1:
                blocks.append(f"🎁 *Account #{i}:*\n{formatted}")
            else:
                blocks.append(f"🎁 *Account:*\n{formatted}")
        sections.append(f"{prod_header}\n" + "\n\n".join(blocks))

    all_delivery = "\n\n───────────────────\n\n".join(sections)

    message = (
        f"✅ *Payment Confirmed\\!*\n\n"
        f"📦 *Order:* `{order.public_order_id}`\n"
        f"🔢 *Total Items:* {total_qty}\n\n"
        f"{all_delivery}\n\n"
        f"Thank you for using Cloud Deals\\! ☁️\n\n"
        f"⭐ *Rate your purchase below:*"
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=message,
            reply_markup=_review_keyboard(order.id),
            parse_mode="Markdown",
        )
        logger.info(
            "Cart delivery sent: order=%s items=%s user=%s",
            order.public_order_id, total_qty, telegram_id,
        )
        return True
    except TelegramError as e:
        logger.error(
            "Cart delivery failed: order=%s user=%s error=%s",
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


async def deliver_order_if_fulfilled(
    session: AsyncSession,
    order: Order,
    bot: Optional[Bot] = None,
) -> bool:
    """Send fulfilled digital order credentials to customer and notify admin."""
    if bot is None:
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
    if bot is None:
        logger.error("Bot instance not available for delivery")
        return False

    from app.database.repositories import inventory_repo, user_repo
    user = await user_repo.get_by_id(session, order.user_id)
    if user is None:
        logger.error("User not found for delivery: order=%s", order.public_order_id)
        return False

    # Get all inventory items linked to this order
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    contents = [item.content for item in items if item.content]

    # Fallback to single inventory_id
    if not contents and order.inventory_id:
        item = await inventory_repo.get_item_by_id(session, order.inventory_id)
        if item:
            contents = [item.content]

    if not contents:
        logger.error("No delivery content for order=%s", order.public_order_id)
        return False

    # Decrypt contents if encrypted
    from app.utils.crypto_vault import decrypt_content
    decrypted_contents = [decrypt_content(c) for c in contents]

    # Group inventory items by product
    items_by_product: dict[str, list[str]] = {}
    for i, item in enumerate(items):
        p_name = item.product.name if hasattr(item, 'product') and item.product else (order.product.name if order.product else "Product")
        content_val = decrypted_contents[i] if i < len(decrypted_contents) else decrypt_content(item.content)
        items_by_product.setdefault(p_name, []).append(content_val)

    if len(items_by_product) > 1:
        success = await deliver_cart_order_to_user(
            bot, user.telegram_id, order, items_by_product
        )
    else:
        p_name = list(items_by_product.keys())[0] if items_by_product else (order.product.name if order.product else "Product")
        success = await deliver_bulk_to_user(
            bot, user.telegram_id, order, decrypted_contents, p_name
        )

    # Notify admin(s) if configured
    if success:
        try:
            from app.config import get_settings
            admin_ids_str = get_settings().admin_telegram_ids
            if admin_ids_str:
                p_display = order.product.name if order.product else f"{len(contents)} item(s)"
                user_display = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
                admin_msg = (
                    f"🎉 *New Sale Confirmed\\!*\n\n"
                    f"📦 *Order:* `{order.public_order_id}`\n"
                    f"💰 *Amount:* ${order.amount:.2f}\n"
                    f"🏷 *Product:* {p_display}\n"
                    f"👤 *Customer:* {user_display}\n"
                    f"💳 *Status:* ✅ Fulfilled & Delivered"
                )
                for aid in admin_ids_str.split(","):
                    aid = aid.strip()
                    if aid.isdigit():
                        try:
                            await bot.send_message(
                                chat_id=int(aid),
                                text=admin_msg,
                                parse_mode="Markdown",
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Failed to send admin sale notification: %s", e)

    return success

