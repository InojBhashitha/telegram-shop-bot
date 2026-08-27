"""Start handler — /start, /help, main menu navigation, and maintenance check."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.bot.keyboards.main import main_menu_keyboard
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import settings_repo
from app.services import user_service

logger = logging.getLogger(__name__)


async def _is_maintenance(session) -> bool:
    """Check if maintenance mode is enabled."""
    val = await settings_repo.get_setting(session, "maintenance_mode")
    return val == "true"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command. Creates user and shows main menu."""
    user = update.effective_user
    if user is None:
        return

    async with get_session() as session:
        # Check maintenance mode
        if await _is_maintenance(session):
            settings = get_settings()
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

        if result["is_new"]:
            logger.info("New user registered: %s (@%s)", user.id, user.username)

    await update.message.reply_text(
        "☁️ *Cloud Deals*\n\n"
        "👋 Welcome!\n\n"
        "Choose an option below:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
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
    await query.answer()

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


def get_handlers() -> list:
    """Return handlers for this module."""
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
    ]
