"""Start handler — /start, /help, main menu, force-subscribe gate, persistent keyboard routing."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.keyboards.main import main_menu_keyboard, main_reply_keyboard
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import settings_repo
from app.services import user_service

logger = logging.getLogger(__name__)


async def _is_maintenance(session) -> bool:
    """Check if maintenance mode is enabled."""
    val = await settings_repo.get_setting(session, "maintenance_mode")
    return val == "true"


async def _check_channel_membership(bot, user_id: int) -> bool:
    """Check if user is a member of the required channel.

    Returns True if no channel is configured or user is a member.
    """
    settings = get_settings()
    channel = settings.force_channel_id
    if not channel:
        return True  # No channel configured, allow access

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.warning("Channel membership check failed for %s: %s", user_id, e)
        return True  # If check fails, don't block users


async def _show_discount_offer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the optional 10% discount welcome offer with join, claim, and skip buttons."""
    settings = get_settings()
    channel = settings.force_channel_id

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel.lstrip('@')}")],
        [InlineKeyboardButton("🎁 Verify & Claim 10% OFF", callback_data="claim_channel_discount")],
        [InlineKeyboardButton("🛍 Skip & Start Shopping", callback_data="skip_channel_discount")],
    ])

    text = (
        "☁️ *Welcome to Cloud Deals!*\n\n"
        "🎁 *EXCLUSIVE NEW CUSTOMER OFFER:*\n"
        "Join our official channel and get *10% OFF* on your first order\\! *(Max $10 discount)*\n\n"
        f"📢 *Channel:* {channel}\n\n"
        "Join now to claim your instant discount, or continue to browse:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=keyboard, parse_mode="Markdown",
        )
    elif update.message:
        await update.message.reply_text(
            text, reply_markup=keyboard, parse_mode="Markdown",
        )


async def claim_channel_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verify channel membership and activate 10% first-order discount."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    is_member = await _check_channel_membership(context.bot, query.from_user.id)
    if not is_member:
        await query.answer(
            "❌ You haven't joined the channel yet! Please join first to claim your 10% discount.",
            show_alert=True,
        )
        return

    cart_count = 0
    async with get_session() as session:
        from app.database.repositories import cart_repo, user_repo
        db_user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if db_user:
            db_user.channel_discount_claimed = True
            await session.flush()
            cart_count = await cart_repo.get_cart_item_count(session, db_user.id)

    await query.edit_message_text(
        "☁️ *Cloud Deals*\n\n"
        "🎉 *10% First-Order Discount Activated!*\n\n"
        "Your *10% discount* (up to $10.00 max) will be automatically applied at checkout.\n\n"
        "Choose an option below:",
        reply_markup=main_menu_keyboard(cart_count),
        parse_mode="Markdown",
    )


async def skip_channel_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skip discount offer and proceed to main menu."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    cart_count = 0
    async with get_session() as session:
        from app.database.repositories import cart_repo, user_repo
        db_user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if db_user:
            cart_count = await cart_repo.get_cart_item_count(session, db_user.id)

    await query.edit_message_text(
        "☁️ *Cloud Deals*\n\n"
        "👋 Welcome!\n\n"
        "Choose an option below:",
        reply_markup=main_menu_keyboard(cart_count),
        parse_mode="Markdown",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command. Creates user, offers 10% discount, and shows main menu."""
    user = update.effective_user
    if user is None or update.message is None:
        return

    settings = get_settings()

    async with get_session() as session:
        # Check maintenance mode
        if await _is_maintenance(session):
            if not settings.is_admin(user.id):
                await update.message.reply_text(
                    "☁️ *Cloud Deals*\n\n"
                    "🔧 The store is currently under maintenance.\n\n"
                    "Please try again later.",
                    parse_mode="Markdown",
                )
                return

        # Parse referral code from deep link
        referral_code = None
        if context.args and context.args[0].startswith("ref_"):
            referral_code = context.args[0]

        result = await user_service.get_or_create_user(
            session,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            referral_code=referral_code,
        )

        db_user = result["user"]
        if result["is_new"]:
            logger.info("New user registered: %s (@%s)", user.id, user.username)

        from app.database.repositories import cart_repo
        cart_count = await cart_repo.get_cart_item_count(session, db_user.id)

        # Check if user is already a channel member and auto-claim
        if settings.force_channel_id and not db_user.channel_discount_claimed and not db_user.channel_discount_used:
            is_member = await _check_channel_membership(context.bot, user.id)
            if is_member:
                db_user.channel_discount_claimed = True
                await session.flush()

    # Send persistent bottom keyboard
    await update.message.reply_text(
        "☁️",
        reply_markup=main_reply_keyboard(),
    )

    # If channel configured and discount not yet claimed or used, show welcome offer
    if settings.force_channel_id and not db_user.channel_discount_claimed and not db_user.channel_discount_used:
        await _show_discount_offer(update, context)
        return

    promo_banner = "🎁 *10% First Order Discount Active!*\n\n" if db_user.channel_discount_claimed and not db_user.channel_discount_used else ""

    await update.message.reply_text(
        f"☁️ *Cloud Deals*\n\n"
        f"👋 Welcome!\n\n"
        f"{promo_banner}"
        f"Choose an option below:",
        reply_markup=main_menu_keyboard(cart_count),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if update.message is None:
        return
    settings = get_settings()
    support = f"@{settings.support_username}" if settings.support_username else "the support menu"

    await update.message.reply_text(
        "☁️ *Cloud Deals — Help*\n\n"
        "🎁 *Browse products* — View categories and products\n"
        "💳 *Top-up* — Add balance to your account\n"
        "👤 *Profile* — View your account and orders\n"
        "☎️ *Support* — Contact us for help\n"
        "❓ *FAQ* — Frequently asked questions\n\n"
        f"For assistance, contact {support}.",
        parse_mode="Markdown",
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'main_menu' callback — return to main menu."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    # Force-subscribe gate check
    is_member = await _check_channel_membership(context.bot, query.from_user.id)
    if not is_member:
        await _show_join_required(update, context)
        return

    async with get_session() as session:
        if await _is_maintenance(session):
            settings = get_settings()
            if not settings.is_admin(query.from_user.id):
                await query.edit_message_text(
                    "☁️ *Cloud Deals*\n\n"
                    "🔧 The store is currently under maintenance.\n\n"
                    "Please try again later.",
                    parse_mode="Markdown",
                )
                return

    await query.edit_message_text(
        "☁️ *Cloud Deals*\n\n"
        "👋 Welcome!\n\n"
        "Choose an option below:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


# -----------------------------------------------------------------------
# Persistent reply keyboard button handlers
# -----------------------------------------------------------------------

async def _handle_reply_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle '🛍 Browse Store' reply keyboard button."""
    if update.effective_user is None or update.message is None:
        return
    from app.bot.handlers.products import show_categories
    # Force-subscribe gate check
    is_member = await _check_channel_membership(context.bot, update.effective_user.id)
    if not is_member:
        await _show_join_required(update, context)
        return

    async with get_session() as session:
        from app.services import product_service
        categories = await product_service.get_active_categories(session)

    if not categories:
        await update.message.reply_text(
            "☁️ *Cloud Deals*\n\n"
            "📦 No categories available yet.\n\n"
            "Check back soon!",
            parse_mode="Markdown",
        )
        return

    from app.bot.keyboards.products import categories_keyboard
    await update.message.reply_text(
        "☁️ *Cloud Deals*\n\n"
        "📦 *Available Categories:*",
        reply_markup=categories_keyboard(categories),
        parse_mode="Markdown",
    )


async def _handle_reply_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle '📦 My Orders' reply keyboard button."""
    from app.bot.handlers.orders import orders_command
    await orders_command(update, context)


async def _handle_reply_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle '👤 My Profile' reply keyboard button."""
    if update.effective_user is None or update.message is None:
        return
    user_tg = update.effective_user
    async with get_session() as session:
        from app.database.repositories import user_repo
        from decimal import Decimal
        user = await user_repo.get_by_telegram_id(session, user_tg.id)
        balance = user.balance if user else Decimal("0")
        order_count = 0
        if user:
            from app.database.repositories import order_repo
            order_count = await order_repo.count_user_orders(session, user.id)

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 My Orders", callback_data="orders"),
            InlineKeyboardButton("💳 Top-up", callback_data="topup"),
        ],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")],
    ])

    await update.message.reply_text(
        f"☁️ *Cloud Deals*\n\n"
        f"👤 *Profile*\n\n"
        f"🆔 ID: `{user_tg.id}`\n"
        f"👤 Username: @{user_tg.username or 'N/A'}\n"
        f"💰 Balance: ${balance}\n"
        f"📦 Orders: {order_count}",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _handle_reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle '☎️ Support / FAQ' reply keyboard button."""
    if update.message is None:
        return
    settings = get_settings()
    support = f"@{settings.support_username}" if settings.support_username else "the support menu"

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("☎️ Support", callback_data="support")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")],
    ])

    await update.message.reply_text(
        f"☁️ *Cloud Deals*\n\n"
        f"☎️ *Support & FAQ*\n\n"
        f"Contact: {support}\n\n"
        f"Select an option:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def _handle_reply_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle '🛒 My Cart' reply keyboard button."""
    if update.effective_user is None:
        return
    from app.bot.handlers.cart import show_cart
    # Force-subscribe gate check
    is_member = await _check_channel_membership(context.bot, update.effective_user.id)
    if not is_member:
        await _show_join_required(update, context)
        return
    await show_cart(update, context)


def get_handlers() -> list:
    """Return handlers for this module."""
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
        CallbackQueryHandler(claim_channel_discount, pattern="^claim_channel_discount$"),
        CallbackQueryHandler(skip_channel_discount, pattern="^skip_channel_discount$"),
        # noop callback for status tracker button
        CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"),
        # Persistent reply keyboard button handlers
        MessageHandler(filters.Regex("^🛍 Browse Store$"), _handle_reply_browse),
        MessageHandler(filters.Regex("^🛒 My Cart$"), _handle_reply_cart),
        MessageHandler(filters.Regex("^📦 My Orders$"), _handle_reply_orders),
        MessageHandler(filters.Regex("^👤 My Profile$"), _handle_reply_profile),
        MessageHandler(filters.Regex("^☎️ Support / FAQ$"), _handle_reply_support),
    ]
