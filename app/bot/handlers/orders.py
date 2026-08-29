"""Order handlers — check payment, cancel order, order history, warranty claims."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.keyboards.orders import (
    order_detail_keyboard,
    order_list_keyboard,
    payment_keyboard,
)
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import payment_repo, user_repo
from app.services import order_service, payment_service

logger = logging.getLogger(__name__)

ORDERS_PER_PAGE = 5

# Conversation states for warranty claim
WARRANTY_REASON = 100


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check payment status for an order with live status tracker."""
    query = update.callback_query
    await query.answer("Checking payment status...")

    order_id = int(query.data.split(":")[1])

    async with get_session() as session:
        order = await order_service.get_order_by_id(session, order_id)
        if order is None:
            await query.edit_message_text("❌ Order not found.")
            return

        # Access control
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None or order.user_id != user.id:
            await query.answer("❌ This is not your order.", show_alert=True)
            return

        status_text = order.status.value

        payment = await payment_repo.get_by_order_id(session, order.id)
        payment_url = payment.payment_url if payment else None

        from app.payments import get_payment_provider
        provider = get_payment_provider(payment.provider if payment else None)
        try:
            provider_status = await payment_service.check_payment_status(
                session, provider, order.id
            )
            if provider_status:
                status_text = provider_status
        except Exception:
            pass

    status_display = _format_status(status_text)
    from app.bot.keyboards.orders import _get_payment_steps
    steps = _get_payment_steps(status_text)

    if payment_url and status_text in ("waiting", "pending_payment"):
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"💳 *Payment Status*\n\n"
            f"📦 Order: `{order.public_order_id}`\n"
            f"💰 Amount: ${order.amount}\n\n"
            f"{steps}\n\n"
            f"Status: {status_display}\n\n"
            f"Complete your payment using the button below.",
            reply_markup=payment_keyboard(payment_url, order.id, status_text),
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"💳 *Payment Status*\n\n"
            f"📦 Order: `{order.public_order_id}`\n"
            f"💰 Amount: ${order.amount}\n\n"
            f"{steps}\n\n"
            f"Status: {status_display}",
            reply_markup=order_detail_keyboard(order, has_warranty=True),
            parse_mode="Markdown",
        )


async def cancel_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel a pending order."""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    async with get_session() as session:
        order = await order_service.get_order_by_id(session, order_id)
        if order is None:
            await query.edit_message_text("❌ Order not found.")
            return

        # Access control
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None or order.user_id != user.id:
            await query.answer("❌ This is not your order.", show_alert=True)
            return

        try:
            await order_service.cancel_order(session, order.id)
        except order_service.OrderError as e:
            await query.edit_message_text(
                f"☁️ *Cloud Deals*\n\n"
                f"❌ {e}",
                parse_mode="Markdown",
            )
            return

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"❌ *Order Cancelled*\n\n"
        f"📦 Order: `{order.public_order_id}`\n\n"
        f"Your order has been cancelled and the reserved item(s) have been released.",
        parse_mode="Markdown",
    )


async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's order history."""
    query = update.callback_query
    if query:
        await query.answer()

    user_tg = update.effective_user

    page = 0
    if query and query.data.startswith("orders_page:"):
        page = int(query.data.split(":")[1])

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if user is None:
            text = "❌ Please /start the bot first."
            if query:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        orders = await order_service.get_user_orders(
            session, user.id, offset=page * ORDERS_PER_PAGE, limit=ORDERS_PER_PAGE + 1
        )

    has_more = len(orders) > ORDERS_PER_PAGE
    display_orders = orders[:ORDERS_PER_PAGE]

    if not display_orders:
        text = (
            "☁️ *Cloud Deals*\n\n"
            "📦 *My Orders*\n\n"
            "You have no orders yet."
        )
    else:
        text = "☁️ *Cloud Deals*\n\n📦 *My Orders*\n"

    keyboard = order_list_keyboard(display_orders, page, has_more)

    if query:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def show_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show details of a specific order with warranty button if applicable."""
    query = update.callback_query
    await query.answer()

    public_id = query.data.split(":")[1]

    async with get_session() as session:
        order = await order_service.get_order_by_public_id(session, public_id)
        if order is None:
            await query.edit_message_text("❌ Order not found.")
            return

        # Access control
        user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        if user is None or order.user_id != user.id:
            await query.answer("❌ This is not your order.", show_alert=True)
            return

        product_name = order.product.name if order.product else "Unknown"
        status_icon = _status_icon(order.status.value)
        created = order.created_at.strftime("%d %b %Y %H:%M")
        qty_label = f"\n🔢 Quantity: {order.quantity}" if order.quantity > 1 else ""

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"📦 *Order {order.public_order_id}*\n\n"
        f"🏷 Product: {product_name}{qty_label}\n"
        f"💰 Amount: ${order.amount}\n"
        f"Status: {status_icon} {order.status.value.replace('_', ' ').title()}\n"
        f"📅 Date: {created}",
        reply_markup=order_detail_keyboard(order, has_warranty=True),
        parse_mode="Markdown",
    )


# -----------------------------------------------------------------------
# Warranty claim flow
# -----------------------------------------------------------------------

async def start_warranty_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start warranty claim — ask for reason."""
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])
    context.user_data["warranty_order_id"] = order_id

    await query.edit_message_text(
        "☁️ *Cloud Deals — Warranty Claim*\n\n"
        "🛡 Please describe the issue with your account.\n\n"
        "Example:\n"
        "• Account password doesn't work\n"
        "• Account was already used / not fresh\n"
        "• Wrong account type delivered\n\n"
        "Send your issue description (or /cancel):",
        parse_mode="Markdown",
    )
    return WARRANTY_REASON


async def recv_warranty_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive warranty claim reason and submit."""
    order_id = context.user_data.get("warranty_order_id")
    if not order_id:
        await update.message.reply_text("❌ Error. Please try again.")
        return ConversationHandler.END

    reason = update.message.text.strip()
    if len(reason) < 5:
        await update.message.reply_text("❌ Please provide a more detailed description.")
        return WARRANTY_REASON

    user = update.effective_user

    async with get_session() as session:
        db_user = await user_repo.get_by_telegram_id(session, user.id)
        if db_user is None:
            await update.message.reply_text("❌ Please /start the bot first.")
            return ConversationHandler.END

        from app.services import warranty_service
        try:
            result = await warranty_service.create_claim(
                session,
                order_id=order_id,
                user_id=db_user.id,
                reason=reason,
            )
        except warranty_service.WarrantyError as e:
            await update.message.reply_text(
                f"☁️ *Cloud Deals*\n\n❌ {e}",
                parse_mode="Markdown",
            )
            return ConversationHandler.END

    claim = result["claim"]
    context.user_data.pop("warranty_order_id", None)

    # Notify admin about the new claim
    settings = get_settings()
    try:
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
        if bot and settings.admin_ids_list:
            for admin_id in settings.admin_ids_list:
                await bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🛡 *New Warranty Claim*\n\n"
                        f"Claim ID: `{claim.id}`\n"
                        f"User: @{user.username or user.id}\n"
                        f"Reason: {reason}\n\n"
                        f"Use /admin → 🛡 Warranty Claims to review."
                    ),
                    parse_mode="Markdown",
                )
    except Exception as e:
        logger.error("Failed to notify admin about warranty claim: %s", e)

    await update.message.reply_text(
        "☁️ *Cloud Deals*\n\n"
        "✅ *Warranty Claim Submitted*\n\n"
        f"🛡 Claim ID: `{claim.id}`\n"
        f"📝 Reason: {reason}\n\n"
        "Our team will review your claim and you'll receive a replacement "
        "or notification shortly.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /orders command."""
    user_tg = update.effective_user

    async with get_session() as session:
        user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if user is None:
            await update.message.reply_text("❌ Please /start the bot first.")
            return

        orders = await order_service.get_user_orders(session, user.id, limit=ORDERS_PER_PAGE + 1)

    has_more = len(orders) > ORDERS_PER_PAGE
    display_orders = orders[:ORDERS_PER_PAGE]

    if not display_orders:
        text = "☁️ *Cloud Deals*\n\n📦 *My Orders*\n\nYou have no orders yet."
    else:
        text = "☁️ *Cloud Deals*\n\n📦 *My Orders*\n"

    keyboard = order_list_keyboard(display_orders, 0, has_more)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


def _format_status(status: str) -> str:
    """Format a payment status string for display."""
    icons = {
        "waiting": "⏳ Waiting for payment",
        "confirming": "🔄 Confirming transaction",
        "confirmed": "✅ Transaction confirmed",
        "sending": "📤 Processing payout",
        "finished": "✅ Payment complete",
        "partially_paid": "⚠️ Partially paid",
        "failed": "❌ Payment failed",
        "expired": "⏰ Payment expired",
        "refunded": "↩️ Refunded",
        "pending_payment": "⏳ Waiting for payment",
        "payment_processing": "🔄 Processing",
        "paid": "✅ Paid",
        "fulfilled": "✅ Delivered",
        "cancelled": "❌ Cancelled",
        # Cryptomus statuses
        "process": "🔄 Processing",
        "check": "🔄 Checking",
        "confirm_check": "🔄 Confirming",
    }
    return icons.get(status, f"ℹ️ {status}")


def _status_icon(status: str) -> str:
    icons = {
        "pending_payment": "⏳",
        "payment_processing": "🔄",
        "paid": "💰",
        "fulfilled": "✅",
        "cancelled": "❌",
        "expired": "⏰",
        "refunded": "↩️",
    }
    return icons.get(status, "📦")


def get_handlers() -> list:
    """Return handlers for this module."""
    warranty_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_warranty_claim, pattern=r"^warranty_claim:\d+$"),
        ],
        states={
            WARRANTY_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_warranty_reason),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END),
        ],
        per_user=True,
        per_chat=True,
    )

    return [
        warranty_conv,
        CommandHandler("orders", orders_command),
        CallbackQueryHandler(check_payment, pattern=r"^check_pay:\d+$"),
        CallbackQueryHandler(cancel_order_handler, pattern=r"^cancel_order:\d+$"),
        CallbackQueryHandler(show_orders, pattern=r"^orders$"),
        CallbackQueryHandler(show_orders, pattern=r"^orders_page:\d+$"),
        CallbackQueryHandler(show_order_detail, pattern=r"^order:CD-"),
    ]
