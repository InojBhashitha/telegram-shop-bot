"""Profile handler — user profile, balance, top-up, referrals."""

from __future__ import annotations

import logging
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import user_repo
from app.services import topup_service, user_service

logger = logging.getLogger(__name__)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user profile."""
    user_tg = update.effective_user
    if user_tg is None:
        return

    query = update.callback_query
    if query:
        await query.answer()

    async with get_session() as session:
        profile = await user_service.get_profile(session, user_tg.id)

    if profile is None:
        text = "❌ Please /start the bot first."
        if query:
            await query.edit_message_text(text)
        elif update.message:
            await update.message.reply_text(text)
        return

    user = profile["user"]
    username = f"@{user.username}" if user.username else user.first_name or "User"

    promo_status = "🎁 First Order Promo: *10% OFF Active*\n" if user.channel_discount_claimed and not user.channel_discount_used else ""

    text = (
        f"☁️ *Cloud Deals*\n\n"
        f"👤 *Profile*\n\n"
        f"User: {username}\n"
        f"💰 Balance: ${user.balance}\n"
        f"📦 Orders: {profile['order_count']}\n"
        f"💸 Total Spent: ${profile['total_spent']}\n"
        f"{promo_status}"
        f"🎁 Referrals: {profile['referral_count']}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 My Orders", callback_data="orders")],
        [InlineKeyboardButton("💰 Balance & Top-up", callback_data="topup")],
        [InlineKeyboardButton("🎁 Referral", callback_data="referral")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")],
    ])

    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def show_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top-up options."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        balance = user.balance if user else Decimal("0")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+ $5", callback_data="topup_amt:5"),
            InlineKeyboardButton("+ $10", callback_data="topup_amt:10"),
        ],
        [
            InlineKeyboardButton("+ $20", callback_data="topup_amt:20"),
            InlineKeyboardButton("+ $50", callback_data="topup_amt:50"),
        ],
        [InlineKeyboardButton("+ $100", callback_data="topup_amt:100")],
        [InlineKeyboardButton("⬅️ Back", callback_data="profile")],
    ])

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"💳 *Top-Up Balance*\n\n"
        f"Current balance: ${balance}\n\n"
        f"Select an amount to add:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def process_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a top-up payment."""
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None:
        return
    await query.answer()

    amount = Decimal(query.data.split(":")[1])
    settings = get_settings()

    from app.payments import get_payment_provider
    is_configured = False
    if settings.crypto_provider.lower() == "cryptopay":
        is_configured = bool(settings.cryptopay_api_token)
    elif settings.crypto_provider.lower() == "oxapay":
        is_configured = bool(settings.oxapay_merchant_key)
    elif settings.crypto_provider.lower() == "binancepay":
        is_configured = bool(settings.binance_pay_api_key and settings.binance_pay_secret_key)
    elif settings.crypto_provider.lower() == "cryptomus":
        is_configured = bool(settings.cryptomus_merchant_id and settings.cryptomus_payment_key)
    else:
        is_configured = bool(settings.nowpayments_api_key)

    if not is_configured:
        await query.edit_message_text(
            "☁️ *Cloud Deals*\n\n"
            "❌ Payment system is not configured yet.",
            parse_mode="Markdown",
        )
        return

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None:
            await query.edit_message_text("❌ Please /start the bot first.")
            return

        try:
            provider = get_payment_provider()
            result = await topup_service.create_topup(
                session, provider, user.id, amount
            )
        except Exception as e:
            logger.error("Top-up creation failed: %s", e)
            await query.edit_message_text(
                "☁️ *Cloud Deals*\n\n"
                "❌ Failed to create top-up payment. Please try again.",
                parse_mode="Markdown",
            )
            return

        payment_url = result["payment_url"]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay with Crypto", url=payment_url)],
        [InlineKeyboardButton("⬅️ Back", callback_data="topup")],
    ])

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"💳 *Top-Up Payment*\n\n"
        f"💰 Amount: ${amount}\n\n"
        f"Complete your payment using the button below.\n"
        f"Your balance will be credited automatically after confirmation.",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show referral information."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None:
            await query.edit_message_text("❌ Please /start the bot first.")
            return
        from app.services import referral_service
        summary = await referral_service.get_referral_summary(session, user.id)

    settings = get_settings()
    bot_username = context.bot.username if context.bot and context.bot.username else "bot"
    ref_code = user.referral_code or f"ref_{user.telegram_id}"
    referral_link = f"https://t.me/{bot_username}?start={ref_code}"

    import urllib.parse
    share_text = f"🔥 Check out {settings.store_name} for instant cloud accounts, keys & subscriptions!"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(referral_link)}&text={urllib.parse.quote(share_text)}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share with Friends", url=share_url)],
        [InlineKeyboardButton("📋 Commission History", callback_data="ref_history")],
        [InlineKeyboardButton("⬅️ Back to Profile", callback_data="profile")],
    ])

    await query.edit_message_text(
        f"☁️ *{settings.store_name} — Referral Program*\n\n"
        f"Invite your friends and earn *{summary['commission_rate']:.1f}% commission* in wallet credits on every purchase they make\\!\n\n"
        f"🔗 *Your Referral Link:*\n`{referral_link}`\n\n"
        f"👥 *Invited Friends:* {summary['referral_count']}\n"
        f"💰 *Total Earned:* `${summary['total_earned']:.2f}`\n"
        f"💼 *Wallet Balance:* `${user.balance:.2f}`\n\n"
        f"Tap *Share with Friends* below or copy your link to start earning\\!",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def show_referral_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent referral commission payouts."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None:
            return
        from app.services import referral_service
        summary = await referral_service.get_referral_summary(session, user.id)

    recent = summary["recent_commissions"]
    if not recent:
        text = (
            "📋 *Referral Commission History*\n\n"
            "You haven't earned any referral commissions yet.\n\n"
            "Share your referral link with friends to start earning instant commissions when they make purchases!"
        )
    else:
        lines = ["📋 *Recent Commission Earnings*\n"]
        for comm in recent:
            order_name = comm.order.public_order_id if comm.order else f"#{comm.order_id}"
            dt_str = comm.created_at.strftime("%d %b %H:%M")
            lines.append(
                f"• `{dt_str}` — *+${comm.commission_amount:.2f}* "
                f"({comm.commission_rate:.1f}% on ${comm.order_amount:.2f} order `{order_name}`)"
            )
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Referral", callback_data="referral")],
    ])

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile command."""
    await show_profile(update, context)


def get_handlers() -> list:
    """Return handlers for this module."""
    return [
        CommandHandler("profile", profile_command),
        CallbackQueryHandler(show_profile, pattern="^profile$"),
        CallbackQueryHandler(show_topup, pattern="^topup$"),
        CallbackQueryHandler(process_topup, pattern=r"^topup_amt:\d+$"),
        CallbackQueryHandler(show_referral, pattern="^referral$"),
        CallbackQueryHandler(show_referral_history, pattern="^ref_history$"),
    ]
