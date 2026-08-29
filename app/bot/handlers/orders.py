"""Order handlers — check payment, cancel order, order history."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from app.bot.keyboards.orders import (
    order_detail_keyboard,
    order_list_keyboard,
    payment_keyboard,
)
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import payment_repo, user_repo
from app.payments.nowpayments import get_provider
from app.services import order_service, payment_service

logger = logging.getLogger(__name__)

ORDERS_PER_PAGE = 5


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check payment status for an order."""
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

        settings = get_settings()
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

    if payment_url and status_text in ("waiting", "pending_payment"):
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"💳 *Payment Status*\n\n"
            f"📦 Order: `{order.public_order_id}`\n"
            f"💰 Amount: ${order.amount}\n"
            f"Status: {status_display}\n\n"
            f"Complete your payment using the button below.",
            reply_markup=payment_keyboard(payment_url, order.id),
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"💳 *Payment Status*\n\n"
            f"📦 Order: `{order.public_order_id}`\n"
            f"💰 Amount: ${order.amount}\n"
            f"Status: {status_display}",
            reply_markup=order_detail_keyboard(order.public_order_id),
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
        f"Your order has been cancelled and the reserved item has been released.",
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
    """Show details of a specific order."""
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

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"📦 *Order {order.public_order_id}*\n\n"
        f"🏷 Product: {product_name}\n"
        f"💰 Amount: ${order.amount}\n"
        f"Status: {status_icon} {order.status.value.replace('_', ' ').title()}\n"
        f"📅 Date: {created}",
        reply_markup=order_detail_keyboard(order.public_order_id),
        parse_mode="Markdown",
    )


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /orders command."""
    # Reuse the show_orders logic
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
    return [
        CommandHandler("orders", orders_command),
        CallbackQueryHandler(check_payment, pattern=r"^check_pay:\d+$"),
        CallbackQueryHandler(cancel_order_handler, pattern=r"^cancel_order:\d+$"),
        CallbackQueryHandler(show_orders, pattern=r"^orders$"),
        CallbackQueryHandler(show_orders, pattern=r"^orders_page:\d+$"),
        CallbackQueryHandler(show_order_detail, pattern=r"^order:CD-"),
    ]
