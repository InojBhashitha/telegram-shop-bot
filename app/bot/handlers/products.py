"""Product browsing handlers — categories, products, buy flow with quantity selector."""

from __future__ import annotations

import logging
from decimal import Decimal

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
from app.database.repositories import inventory_repo
from app.services import order_service, payment_service, product_service

logger = logging.getLogger(__name__)


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show product categories."""
    query = update.callback_query
    if query is None:
        return
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
    """Show products in a selected category with live stock & price badges."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    category_id = int(query.data.split(":")[1])

    async with get_session() as session:
        category = await product_service.get_category(session, category_id)
        if category is None:
            await query.edit_message_text("❌ Category not found.")
            return

        products = await product_service.get_products_by_category(session, category_id)

        # Get stock counts for each product to show live badges
        stock_counts = {}
        for prod in products:
            stock_counts[prod.id] = await inventory_repo.get_stock_count(session, prod.id)

    if not products:
        await query.edit_message_text(
            f"☁️ *Cloud Deals*\n\n"
            f"📦 *{category.name}*\n\n"
            f"No products available in this category.",
            parse_mode="Markdown",
        )
        return

    icon = category.icon or "📁"
    text = (
        f"☁️ *Cloud Deals — Category Catalog*\n\n"
        f"{icon} *{category.name}*\n"
        f"_{category.description or 'Explore premium digital accounts below:'}_\n\n"
        f"Select a product:"
    )
    keyboard = products_keyboard(products, category_id, stock_counts)

    if category.image_url:
        try:
            from telegram import InputMediaPhoto
            await query.edit_message_media(
                media=InputMediaPhoto(media=category.image_url, caption=text, parse_mode="Markdown"),
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning("Category media edit failed: %s", e)

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def show_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show product details with stock count and quantity buy buttons."""
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None:
        return
    await query.answer()

    product_id = int(query.data.split(":")[1])

    async with get_session() as session:
        details = await product_service.get_product_details(session, product_id)
        if details is None:
            await query.edit_message_text("❌ Product not found.")
            return

        from app.database.repositories import cart_repo, user_repo
        db_user = await user_repo.get_by_telegram_id(session, query.from_user.id)
        cart_count = 0
        if db_user:
            cart_count = await cart_repo.get_cart_item_count(session, db_user.id)

    product = details["product"]
    stock = details["stock"]
    in_stock = stock > 0

    settings = get_settings()
    from app.bot.utils.ui import format_product_caption
    caption = format_product_caption(
        name=product.name,
        price=product.price,
        stock=stock,
        description=product.description,
        currency=product.currency,
        warranty_hours=settings.warranty_hours,
    )

    keyboard = product_detail_keyboard(
        product.id, in_stock, product.category_id, stock, cart_count
    )

    image_url = product.image_url or (product.category.image_url if product.category else None)

    if image_url:
        try:
            from telegram import InputMediaPhoto
            await query.edit_message_media(
                media=InputMediaPhoto(media=image_url, caption=caption, parse_mode="Markdown"),
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning("Media edit failed, fallback to text: %s", e)

    await query.edit_message_text(
        caption,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle buy button with quantity — create order and payment."""
    query = update.callback_query
    if query is None or query.data is None or query.from_user is None:
        return
    await query.answer()

    parts = query.data.split(":")
    product_id = int(parts[1])
    quantity = int(parts[2]) if len(parts) > 2 else 1

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

        # Create order with quantity
        try:
            order_result = await order_service.create_order(
                session, user_id=db_user.id, product_id=product_id, quantity=quantity
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

    qty_label = f" (×{quantity})" if quantity > 1 else ""
    discount_line = f"🎁 10% Channel Discount: -${order.discount_amount}\n" if order.discount_amount > Decimal("0.00") else ""

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"💳 *Payment Required*\n\n"
        f"📦 Order: `{order.public_order_id}`\n"
        f"🔢 Quantity: {quantity}{qty_label}\n"
        f"{discount_line}"
        f"💰 Total: ${order.amount}\n\n"
        f"🟡 Deposit → ⚪ Confirm → ⚪ Deliver\n\n"
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
        CallbackQueryHandler(buy_product, pattern=r"^buy:\d+"),
    ]
