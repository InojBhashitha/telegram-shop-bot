"""Product browsing handlers — categories, products, and buy flow."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from app.bot.keyboards.orders import payment_keyboard
from app.bot.keyboards.products import (
    categories_keyboard,
    product_detail_keyboard,
    products_keyboard,
)
from app.config import get_settings
from app.database.database import get_session
from app.payments.nowpayments import get_provider
from app.services import order_service, payment_service, product_service

logger = logging.getLogger(__name__)


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show product categories."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        categories = await product_service.get_active_categories(session)

    if not categories:
        await query.edit_message_text(
            "☁️ *Cloud Deals*\n\n"
            "📦 No categories available yet.\n\n"
            "Check back soon!",
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        "☁️ *Cloud Deals*\n\n"
        "📦 *Available Categories:*",
        reply_markup=categories_keyboard(categories),
        parse_mode="Markdown",
    )


async def show_category_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show products in a selected category."""
    query = update.callback_query
    await query.answer()

    category_id = int(query.data.split(":")[1])

    async with get_session() as session:
        category = await product_service.get_category(session, category_id)
        if category is None:
            await query.edit_message_text("❌ Category not found.")
            return

        products = await product_service.get_products_by_category(session, category_id)

    if not products:
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"📦 *{category.name}*\n\n"
            f"No products available in this category.",
            parse_mode="Markdown",
        )
        return

    icon = category.icon or "📁"
    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"{icon} *{category.name}*\n\n"
        f"Select a product:",
        reply_markup=products_keyboard(products, category_id),
        parse_mode="Markdown",
    )


async def show_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show product details with stock and buy button."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])

    async with get_session() as session:
        details = await product_service.get_product_details(session, product_id)

    if details is None:
        await query.edit_message_text("❌ Product not found.")
        return

    product = details["product"]
    stock = details["stock"]
    in_stock = stock > 0

    stock_text = f"📦 *Stock:* {stock} available" if in_stock else "❌ *OUT OF STOCK*"
    desc = product.description or "No description."

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"📦 *{product.name}*\n\n"
        f"{desc}\n\n"
        f"💰 *Price:* ${product.price}\n"
        f"{stock_text}",
        reply_markup=product_detail_keyboard(product.id, in_stock, product.category_id),
        parse_mode="Markdown",
    )


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle buy button — create order and payment."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])
    user = query.from_user
    settings = get_settings()

    # Check if active payment provider is configured
    from app.payments import get_payment_provider
    is_configured = False
    if settings.crypto_provider.lower() == "cryptomus":
        is_configured = bool(settings.cryptomus_merchant_id and settings.cryptomus_payment_key)
    else:
        is_configured = bool(settings.nowpayments_api_key)

    if not is_configured:
        await query.edit_message_text(
            "☁️ *Cloud Deals*\n\n"
            "❌ Payment system is not configured yet.\n\n"
            "Please contact support.",
            parse_mode="Markdown",
        )
        return

    async with get_session() as session:
        # Ensure user exists
        from app.services import user_service
        await user_service.get_or_create_user(
            session,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        # Get user from DB for internal ID
        from app.database.repositories import user_repo
        db_user = await user_repo.get_by_telegram_id(session, user.id)
        if db_user is None:
            await query.edit_message_text("❌ User not found. Please /start again.")
            return

        # Create order
        try:
            order_result = await order_service.create_order(
                session, user_id=db_user.id, product_id=product_id
            )
        except order_service.OrderError as e:
            await query.edit_message_text(
                f"☁️ *Cloud Deals*\n\n"
                f"❌ {e}",
                parse_mode="Markdown",
            )
            return

        order = order_result["order"]

        # Create crypto payment
        try:
            provider = get_payment_provider()
            pay_result = await payment_service.create_payment_for_order(
                session, provider, order.id
            )
        except Exception as e:
            logger.error("Payment creation failed: %s", e)
            # Cancel the order since payment couldn't be created
            await order_service.cancel_order(session, order.id)
            await query.edit_message_text(
                "☁️ *Cloud Deals*\n\n"
                "❌ Failed to create payment. Please try again later.\n\n"
                "Your order has been cancelled.",
                parse_mode="Markdown",
            )
            return

        payment_url = pay_result["payment_url"]

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"💳 *Payment Required*\n\n"
        f"📦 Order: `{order.public_order_id}`\n"
        f"💰 Amount: ${order.amount}\n\n"
        f"Complete your payment using the button below.\n\n"
        f"⏰ Payment expires in {settings.order_expiry_minutes} minutes.",
        reply_markup=payment_keyboard(payment_url, order.id),
        parse_mode="Markdown",
    )


def get_handlers() -> list:
    """Return handlers for this module."""
    return [
        CallbackQueryHandler(show_categories, pattern="^products$"),
        CallbackQueryHandler(show_category_products, pattern=r"^cat:\d+$"),
        CallbackQueryHandler(show_product_detail, pattern=r"^prod:\d+$"),
        CallbackQueryHandler(buy_product, pattern=r"^buy:\d+$"),
    ]
