"""Vouch service — automated verified purchase proofs and social proof broadcast."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Order, Payment, User
from app.database.repositories import category_repo, inventory_repo, payment_repo, product_repo, user_repo

logger = logging.getLogger(__name__)


def anonymize_buyer(user: Optional[User]) -> str:
    """Safely anonymize buyer username or name for public channel proof."""
    if user is None:
        return "Verified Customer"

    if user.username:
        u = user.username.strip().lstrip("@")
        if len(u) <= 2:
            return f"@{u[0]}*"
        elif len(u) <= 4:
            return f"@{u[0]}**{u[-1]}"
        else:
            return f"@{u[0]}***{u[-1]}"

    if user.first_name:
        fn = user.first_name.strip()
        if len(fn) <= 2:
            return f"{fn}*"
        return f"{fn[:2]}*** (Verified Customer)"

    if user.telegram_id:
        tid_str = str(user.telegram_id)
        return f"Customer #{tid_str[-4:]}"

    return "Verified Customer"


def format_payment_badge(payment: Optional[Payment]) -> str:
    """Format payment method and currency badge for the proof card."""
    if payment is None:
        return "✅ Verified Automated Payment"

    provider = (payment.provider or "").lower()
    curr = f" ({payment.payment_currency})" if payment.payment_currency else ""

    if provider == "cryptopay":
        return f"✅ Crypto Pay @CryptoBot{curr}"
    if provider == "oxapay":
        return f"✅ OxaPay Gateway{curr}"
    if provider == "binancepay":
        return f"✅ Binance Pay{curr}"
    if provider == "cryptomus":
        return f"✅ Cryptomus Gateway{curr}"
    if provider == "nowpayments":
        return f"✅ NOWPayments{curr}"
    if provider == "stars":
        return "⭐️ Telegram Stars"
    if provider == "balance":
        return "💳 Account Store Balance"

    return f"✅ {provider.title()}{curr}"


async def post_order_vouch_to_channel(
    bot: Optional[Bot],
    session: AsyncSession,
    order: Order,
    channel_id: Optional[str] = None,
) -> tuple[bool, str]:
    """Broadcast an automated verified purchase proof card to the public vouch channel.

    Note: This is an automated transaction proof and does NOT require any star rating.

    Returns:
        (success: bool, status_message: str)
    """
    if bot is None:
        return False, "Bot instance unavailable"

    settings = get_settings()
    target_channel = channel_id or settings.vouch_channel_id
    if not target_channel:
        return False, "No vouch channel configured in settings"

    # Resolve product
    product = None
    if order.product_id:
        product = await product_repo.get_by_id(session, order.product_id)

    prod_name = product.name if product else "Digital Account"
    prod_price = product.price if product else order.amount

    # Resolve category
    category = None
    if product and product.category_id:
        category = await category_repo.get_by_id(session, product.category_id)

    cat_icon = category.icon if category and category.icon else "☁️"
    cat_name = category.name if category and category.name else "Cloud Services"

    # Resolve user
    user = None
    if order.user_id:
        user = await user_repo.get_by_id(session, order.user_id)

    # Resolve payment
    payment = await payment_repo.get_by_order_id(session, order.id)

    # Count items
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    item_count = len(items) if items else (order.quantity or 1)

    buyer_display = anonymize_buyer(user)
    payment_badge = format_payment_badge(payment)
    order_hash = order.public_order_id[:8].upper()

    bot_user = (
        bot.username
        if hasattr(bot, "username") and bot.username
        else settings.support_username or "CloudDealsBot"
    )
    webapp_url = settings.effective_webapp_url or f"{settings.webhook_base_url}/webapp"

    caption = (
        f"🛡️ *VERIFIED PURCHASE PROOF | {settings.store_name.upper()}* 🛡️\n\n"
        f"📦 *Product:* {prod_name}\n"
        f"🏷 *Category:* {cat_icon} {cat_name}\n"
        f"🔢 *Quantity:* {item_count} account(s)\n"
        f"💵 *Amount Paid:* ${order.amount:.2f} {order.currency}\n"
        f"💳 *Payment:* {payment_badge}\n"
        f"👤 *Buyer:* {buyer_display}\n"
        f"🧾 *Order ID:* `#{order_hash}`\n"
        f"⚡ *Fulfillment:* Instant Automated Delivery (< 3s)\n"
        f"🛡️ *Warranty:* {settings.warranty_hours}h Replacement Coverage Active\n\n"
        f"🔒 _100% genuine credentials tested and delivered instantly!_"
    )

    buttons = []
    if product:
        buttons.append([
            InlineKeyboardButton(
                f"🛒 Buy in Bot (${prod_price:.2f})",
                url=f"https://t.me/{bot_user}?start=prod_{product.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("📱 Open Store (Mini App)", url=webapp_url)])
    keyboard = InlineKeyboardMarkup(buttons)

    # Check for local logo image
    photo_file = None
    if product and product.image_url and product.image_url.startswith("/webapp/"):
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
        logger.info("Order proof posted to %s for order %s", target_channel, order.public_order_id)
        return True, f"Published to {target_channel}"

    except TelegramError as e:
        logger.warning("Failed to post order vouch to %s: %s", target_channel, e)
        return False, str(e)
