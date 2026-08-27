"""Support and FAQ handlers."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import settings_repo, support_repo, user_repo

logger = logging.getLogger(__name__)

# Conversation states for ticket creation
TICKET_SUBJECT, TICKET_MESSAGE = range(2)


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show support menu."""
    query = update.callback_query
    if query:
        await query.answer()

    settings = get_settings()
    support_text = (
        f"@{settings.support_username}" if settings.support_username
        else "our support team"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Create Ticket", callback_data="create_ticket")],
        [InlineKeyboardButton("📋 My Tickets", callback_data="my_tickets")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
    ])

    text = (
        f"☁️ *Cloud Deals*\n\n"
        f"☎️ *Support*\n\n"
        f"Need help? Contact {support_text} or create a support ticket."
    )

    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def start_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start ticket creation — ask for subject."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "☁️ *Cloud Deals*\n\n"
        "🎫 *Create Support Ticket*\n\n"
        "Please type the *subject* of your issue:",
        parse_mode="Markdown",
    )
    return TICKET_SUBJECT


async def receive_ticket_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ticket subject, ask for message."""
    context.user_data["ticket_subject"] = update.message.text.strip()

    await update.message.reply_text(
        "☁️ *Cloud Deals*\n\n"
        "🎫 Now describe your issue in detail:",
        parse_mode="Markdown",
    )
    return TICKET_MESSAGE


async def receive_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive ticket message and create the ticket."""
    subject = context.user_data.get("ticket_subject", "No subject")
    message = update.message.text.strip()
    user_tg = update.effective_user

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if user is None:
            await update.message.reply_text("❌ Please /start the bot first.")
            return ConversationHandler.END

        ticket = await support_repo.create(
            session, user_id=user.id, subject=subject, message=message
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Support", callback_data="support")],
    ])

    await update.message.reply_text(
        f"☁️ *Cloud Deals*\n\n"
        f"✅ *Ticket Created!*\n\n"
        f"🎫 Ticket #{ticket.id}\n"
        f"📝 Subject: {subject}\n\n"
        f"We'll get back to you as soon as possible.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    context.user_data.pop("ticket_subject", None)
    return ConversationHandler.END


async def cancel_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel ticket creation."""
    context.user_data.pop("ticket_subject", None)
    await update.message.reply_text("❌ Ticket creation cancelled.")
    return ConversationHandler.END


async def show_my_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's support tickets."""
    query = update.callback_query
    await query.answer()

    user_tg = query.from_user

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if user is None:
            await query.edit_message_text("❌ Please /start the bot first.")
            return

        tickets = await support_repo.get_user_tickets(session, user.id, limit=10)

    if not tickets:
        await query.edit_message_text(
            "☁️ *Cloud Deals*\n\n"
            "📋 *My Tickets*\n\n"
            "You have no tickets.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="support")],
            ]),
            parse_mode="Markdown",
        )
        return

    lines = ["☁️ *Cloud Deals*\n\n📋 *My Tickets*\n"]
    for t in tickets:
        status_icon = {"open": "🟡", "replied": "🟢", "closed": "⚫"}.get(t.status.value, "❓")
        lines.append(f"{status_icon} *#{t.id}* — {t.subject}")
        if t.admin_reply:
            lines.append(f"   ↪️ Reply: {t.admin_reply[:60]}...")

    buttons = [[InlineKeyboardButton("⬅️ Back", callback_data="support")]]

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def show_faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show FAQ entries."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        faqs = await settings_repo.list_active_faqs(session)

    if not faqs:
        settings = get_settings()
        support = f"@{settings.support_username}" if settings.support_username else "support"

        # Show default FAQ
        text = (
            "☁️ *Cloud Deals*\n\n"
            "❓ *FAQ*\n\n"
            "*What payment methods are supported?*\n"
            "Crypto payments through our payment provider.\n\n"
            "*How long does delivery take?*\n"
            "Usually automatic after confirmed payment.\n\n"
            "*What happens if payment fails?*\n"
            "The order is not fulfilled and your reserved item is released.\n\n"
            f"Contact: {support}"
        )
    else:
        lines = ["☁️ *Cloud Deals*\n\n❓ *FAQ*\n"]
        for faq in faqs:
            lines.append(f"*{faq.question}*")
            lines.append(f"{faq.answer}\n")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
    ])

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /support command."""
    await show_support(update, context)


def get_handlers() -> list:
    """Return handlers for this module."""
    ticket_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_ticket, pattern="^create_ticket$"),
        ],
        states={
            TICKET_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket_subject),
            ],
            TICKET_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket_message),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_ticket),
        ],
        per_message=False,
    )

    return [
        CommandHandler("support", support_command),
        ticket_conv,
        CallbackQueryHandler(show_support, pattern="^support$"),
        CallbackQueryHandler(show_my_tickets, pattern="^my_tickets$"),
        CallbackQueryHandler(show_faq, pattern="^faq$"),
    ]
