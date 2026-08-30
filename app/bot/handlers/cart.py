"""Cart handlers — shopping cart browsing, custom quantity input, and multi-product checkout."""

from __future__ import annotations

import logging
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.keyboards.cart import (
    cart_added_keyboard,
    cart_item_edit_keyboard,
    cart_manage_keyboard,
    cart_view_keyboard,
)
from app.bot.keyboards.orders import payment_keyboard
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import cart_repo, inventory_repo, user_repo
from app.payments import get_payment_provider
from app.services import cart_service, order_service, payment_service, product_service, user_service

logger = logging.getLogger(__name__)

# Conversation state for custom quantity prompt
CUSTOM_QUANTITY_INPUT = 1


# ---------------------------------------------------------------------------
# View Cart
# ---------------------------------------------------------------------------

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user's shopping cart."""
    query = update.callback_query
    if query:
        await query.answer()

    user_tg = update.effective_user
    if user_tg is None:
        return

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        summary = await cart_service.get_cart_summary(session, db_user.id)

    items = summary["items"]
    total_amount = summary["total_amount"]
    total_count = summary["total_count"]
    is_valid = summary["is_valid"]

    if not items:
        text = (
            "☁️ *Cloud Deals*\n\n"
            "🛒 *Your Shopping Cart is Empty*\n\n"
            "Browse our categories and add products to your cart!"
        )
        reply_markup = cart_view_keyboard(has_items=False)
    else:
        lines = ["☁️ *Cloud Deals*\n\n🛒 *Your Shopping Cart:*\n"]
        for idx, item in enumerate(items, 1):
            stock_warning = ""
            if not item["has_stock"]:
                stock_warning = f" ⚠️ *(Only {item['stock']} in stock!)*" if item["active"] else " ⚠️ *(Unavailable)*"

            lines.append(
                f"*{idx}.* 📦 *{item['product_name']}*\n"
                f"   {item['quantity']} × ${item['unit_price']} = *${item['subtotal']}*{stock_warning}"
            )

        lines.append(f"\n───────────────────\n💰 *Total:* ${total_amount} ({total_count} accounts)")

        if not is_valid:
            lines.append("\n⚠️ *Please adjust quantities before checking out.*")

        text = "\n".join(lines)
        reply_markup = cart_view_keyboard(has_items=True, is_valid=is_valid)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Quick Add to Cart
# ---------------------------------------------------------------------------

async def handle_quick_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quick add to cart button (e.g. cart_add:3:1)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    product_id = int(parts[1])
    quantity = int(parts[2]) if len(parts) > 2 else 1

    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        try:
            result = await cart_service.add_to_cart(
                session, db_user.id, product_id, quantity
            )
        except cart_service.CartError as e:
            await query.answer(f"❌ {e}", show_alert=True)
            return

        product = result["product"]
        summary = await cart_service.get_cart_summary(session, db_user.id)

    subtotal = product.price * quantity
    qty_text = f"{quantity}× " if quantity > 1 else ""

    text = (
        "☁️ *Cloud Deals*\n\n"
        "✅ *Added to Cart!*\n\n"
        f"📦 {qty_text}*{product.name}* — ${subtotal}\n\n"
        f"🛒 *Cart Total:* ${summary['total_amount']} ({summary['total_count']} accounts)"
    )

    await query.edit_message_text(
        text,
        reply_markup=cart_added_keyboard(product.category_id),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Custom Quantity Input Flow (ConversationHandler)
# ---------------------------------------------------------------------------

async def start_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to enter exact quantity of accounts."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])
    context.user_data["custom_qty_product_id"] = product_id

    async with get_session() as session:
        product = await product_service.get_product(session, product_id)
        if product is None or not product.active:
            await query.edit_message_text("❌ Product not found.")
            return ConversationHandler.END

        stock = await inventory_repo.get_stock_count(session, product_id)

    if stock == 0:
        await query.answer("❌ This product is sold out.", show_alert=True)
        return ConversationHandler.END

    context.user_data["custom_qty_max_stock"] = stock
    context.user_data["custom_qty_cat_id"] = product.category_id

    cancel_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_custom_qty:{product_id}")]
    ])

    from app.bot.utils.ui import format_stock_bar
    stock_bar = format_stock_bar(stock)

    await query.edit_message_text(
        f"☁️ *Cloud Deals — Custom Quantity*\n\n"
        f"📦 *{product.name}*\n"
        f"💰 Price: ${product.price} each\n"
        f"📊 Stock: {stock_bar}\n\n"
        f"🔢 *How many accounts would you like to buy?*\n"
        f"Please send a number between *1* and *{stock}* (or /cancel):",
        reply_markup=cancel_kb,
        parse_mode="Markdown",
    )
    return CUSTOM_QUANTITY_INPUT


async def cancel_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel custom quantity input and return to product details."""
    query = update.callback_query
    if query:
        await query.answer()
        product_id = int(query.data.split(":")[1]) if ":" in query.data else None
        if product_id:
            from app.bot.handlers.products import show_product_detail
            query.data = f"prod:{product_id}"
            await show_product_detail(update, context)
            return ConversationHandler.END
    return ConversationHandler.END


async def recv_custom_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and validate custom quantity integer."""
    text = update.message.text.strip()
    product_id = context.user_data.get("custom_qty_product_id")
    max_stock = context.user_data.get("custom_qty_max_stock", 50)
    cat_id = context.user_data.get("custom_qty_cat_id", 0)

    if not product_id:
        await update.message.reply_text("❌ Session expired. Please try again.")
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            f"❌ Please enter a valid whole number between 1 and {max_stock} (or /cancel):"
        )
        return CUSTOM_QUANTITY_INPUT

    quantity = int(text)
    if quantity < 1:
        await update.message.reply_text("❌ Quantity must be at least 1. Please try again:")
        return CUSTOM_QUANTITY_INPUT

    if quantity > max_stock:
        await update.message.reply_text(
            f"❌ Only {max_stock} accounts are available in stock. Please enter a number up to {max_stock}:"
        )
        return CUSTOM_QUANTITY_INPUT

    user_tg = update.effective_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        try:
            result = await cart_service.add_to_cart(
                session, db_user.id, product_id, quantity
            )
        except cart_service.CartError as e:
            await update.message.reply_text(f"❌ {e}")
            return ConversationHandler.END

        product = result["product"]
        summary = await cart_service.get_cart_summary(session, db_user.id)

    subtotal = product.price * quantity
    context.user_data.pop("custom_qty_product_id", None)
    context.user_data.pop("custom_qty_max_stock", None)
    context.user_data.pop("custom_qty_cat_id", None)

    msg_text = (
        "☁️ *Cloud Deals*\n\n"
        "✅ *Added to Cart!*\n\n"
        f"📦 {quantity}× *{product.name}* — ${subtotal}\n\n"
        f"🛒 *Cart Total:* ${summary['total_amount']} ({summary['total_count']} accounts)"
    )

    await update.message.reply_text(
        msg_text,
        reply_markup=cart_added_keyboard(product.category_id),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cart Item Management & Editing
# ---------------------------------------------------------------------------

async def manage_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of items in cart for individual management."""
    query = update.callback_query
    await query.answer()

    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        summary = await cart_service.get_cart_summary(session, db_user.id)

    if not summary["items"]:
        await query.edit_message_text(
            "☁️ *Cloud Deals*\n\n🛒 Your cart is empty.",
            reply_markup=cart_view_keyboard(has_items=False),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        "☁️ *Cloud Deals — Manage Cart*\n\n"
        "Select an item below to edit its quantity or remove it:",
        reply_markup=cart_manage_keyboard(summary["items"]),
        parse_mode="Markdown",
    )


async def edit_cart_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show single item edit stepper."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])
    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        from app.database.repositories import cart_repo
        cart_item = await cart_repo.get_cart_item(session, db_user.id, product_id)
        if cart_item is None:
            await query.edit_message_text("❌ Item is no longer in your cart.")
            return

        stock = await inventory_repo.get_stock_count(session, product_id)
        product = cart_item.product

    await query.edit_message_text(
        f"☁️ *Cloud Deals — Edit Item*\n\n"
        f"📦 *{product.name}*\n"
        f"💰 Unit Price: ${product.price}\n"
        f"🟢 Available Stock: {stock}\n\n"
        f"Use buttons below to adjust quantity:",
        reply_markup=cart_item_edit_keyboard(product_id, cart_item.quantity, stock),
        parse_mode="Markdown",
    )


async def update_cart_item_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle increment/decrement on cart item."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    product_id = int(parts[1])
    new_qty = int(parts[2])
    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        try:
            await cart_service.update_cart_quantity(
                session, db_user.id, product_id, new_qty
            )
        except cart_service.CartError as e:
            await query.answer(f"❌ {e}", show_alert=True)
            return

    # Return to cart view
    await show_cart(update, context)


async def delete_cart_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove item from cart."""
    query = update.callback_query
    await query.answer("Item removed from cart")

    product_id = int(query.data.split(":")[1])
    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        await cart_service.remove_from_cart(session, db_user.id, product_id)

    await show_cart(update, context)


async def clear_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all items from user's cart."""
    query = update.callback_query
    await query.answer("Cart cleared")

    user_tg = query.from_user

    async with get_session() as session:
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        await cart_service.clear_cart(session, db_user.id)

    await show_cart(update, context)


# ---------------------------------------------------------------------------
# Cart Checkout
# ---------------------------------------------------------------------------

async def checkout_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Checkout all items in cart and generate crypto payment."""
    query = update.callback_query
    await query.answer()

    user_tg = query.from_user
    settings = get_settings()

    # Check provider configuration
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
        user_res = await user_service.get_or_create_user(
            session,
            telegram_id=user_tg.id,
            username=user_tg.username,
            first_name=user_tg.first_name,
        )
        db_user = user_res["user"]

        try:
            checkout_res = await cart_service.checkout_cart(session, db_user.id)
        except cart_service.CartError as e:
            await query.edit_message_text(
                f"☁️ *Cloud Deals*\n\n❌ {e}",
                reply_markup=cart_view_keyboard(has_items=True),
                parse_mode="Markdown",
            )
            return

        order = checkout_res["order"]

        # Create payment invoice
        try:
            provider = get_payment_provider()
            pay_result = await payment_service.create_payment_for_order(
                session, provider, order.id
            )
        except Exception as e:
            logger.error("Cart payment creation failed: %s", e)
            from app.services import order_service
            await order_service.cancel_order(session, order.id)
            await query.edit_message_text(
                "☁️ *Cloud Deals*\n\n"
                "❌ Failed to create crypto payment. Please try again.\n\n"
                "Your reserved items have been restored.",
                parse_mode="Markdown",
            )
            return

        payment_url = pay_result["payment_url"]

    discount_line = f"🎁 10% Channel Discount: -${order.discount_amount}\n" if order.discount_amount > Decimal("0.00") else ""

    await query.edit_message_text(
        f"☁️ *Cloud Deals*\n\n"
        f"💳 *Payment Required*\n\n"
        f"📦 Order: `{order.public_order_id}`\n"
        f"🔢 Total Accounts: {order.quantity}\n"
        f"{discount_line}"
        f"💰 Total Amount: ${order.amount}\n\n"
        f"🟡 Deposit → ⚪ Confirm → ⚪ Deliver\n\n"
        f"⏰ Payment expires in {settings.order_expiry_minutes} minutes.",
        reply_markup=payment_keyboard(payment_url, order.id),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Handlers Export
# ---------------------------------------------------------------------------

def get_handlers() -> list:
    """Return handlers for cart module."""
    custom_qty_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_custom_quantity, pattern=r"^cart_custom:\d+$"),
        ],
        states={
            CUSTOM_QUANTITY_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_custom_quantity),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_custom_quantity),
            CallbackQueryHandler(cancel_custom_quantity, pattern=r"^cancel_custom_qty:\d+$"),
        ],
        per_user=True,
        per_chat=True,
        per_message=False,
    )

    return [
        custom_qty_conv,
        CommandHandler("cart", show_cart),
        CallbackQueryHandler(show_cart, pattern="^cart$"),
        CallbackQueryHandler(handle_quick_add, pattern=r"^cart_add:\d+:\d+$"),
        CallbackQueryHandler(manage_cart, pattern="^cart_manage$"),
        CallbackQueryHandler(edit_cart_item, pattern=r"^cart_edit:\d+$"),
        CallbackQueryHandler(update_cart_item_qty, pattern=r"^cart_qty:\d+:\d+$"),
        CallbackQueryHandler(delete_cart_item, pattern=r"^cart_del:\d+$"),
        CallbackQueryHandler(clear_cart_handler, pattern="^cart_clear$"),
        CallbackQueryHandler(checkout_cart_handler, pattern="^cart_checkout$"),
    ]
