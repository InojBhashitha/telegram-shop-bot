"""Admin panel handler — product, category, inventory, order, user management."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.keyboards.admin import (
    admin_categories_keyboard,
    admin_category_select_keyboard,
    admin_main_keyboard,
    admin_order_detail_keyboard,
    admin_orders_keyboard,
    admin_product_detail_keyboard,
    admin_products_keyboard,
    admin_settings_keyboard,
)
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import (
    category_repo,
    inventory_repo,
    order_repo,
    payment_repo,
    settings_repo,
    support_repo,
    user_repo,
)
from app.services import (
    inventory_service,
    order_service,
    product_service,
)

logger = logging.getLogger(__name__)

# Conversation states
(
    ADD_CAT_NAME, ADD_CAT_ICON, ADD_CAT_DESC,
    ADD_PROD_CAT, ADD_PROD_NAME, ADD_PROD_DESC, ADD_PROD_PRICE,
    ADD_STOCK_ITEMS,
    EDIT_PROD_FIELD, EDIT_PROD_VALUE,
    BROADCAST_MSG,
    EDIT_STORE_NAME,
    TICKET_REPLY_MSG,
) = range(13)


def _is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return get_settings().is_admin(user_id)


# ---------------------------------------------------------------------------
# Admin panel entry
# ---------------------------------------------------------------------------

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command."""
    user = update.effective_user
    if not _is_admin(user.id):
        await update.message.reply_text("❌ Access denied.")
        return

    await update.message.reply_text(
        "⚙️ *Cloud Deals Admin*",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin panel (callback)."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_text(
        "⚙️ *Cloud Deals Admin*",
        reply_markup=admin_main_keyboard(),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

async def admin_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all categories (admin)."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        cats = await category_repo.list_all(session)

    await query.edit_message_text(
        "⚙️ *Categories*",
        reply_markup=admin_categories_keyboard(cats),
        parse_mode="Markdown",
    )


async def admin_category_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category detail (admin)."""
    query = update.callback_query
    await query.answer()
    category_id = int(query.data.split(":")[2])

    async with get_session() as session:
        cat = await category_repo.get_by_id(session, category_id)
        if cat is None:
            await query.edit_message_text("❌ Category not found.")
            return
        products = await product_service.get_products_by_category(session, category_id)

    icon = cat.icon or "📁"
    status = "Active ✅" if cat.active else "Inactive ❌"

    from app.bot.keyboards.admin import admin_category_detail_keyboard
    await query.edit_message_text(
        f"⚙️ *Category: {icon} {cat.name}*\n\n"
        f"📝 Description: {cat.description or 'None'}\n"
        f"Status: {status}\n"
        f"📦 Products count: {len(products)}",
        reply_markup=admin_category_detail_keyboard(cat.id),
        parse_mode="Markdown",
    )


async def deactivate_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deactivate a category."""
    query = update.callback_query
    await query.answer()
    category_id = int(query.data.split(":")[2])

    async with get_session() as session:
        await product_service.deactivate_category(session, category_id)

    await query.edit_message_text(
        "✅ Category deactivated.",
        reply_markup=admin_main_keyboard(),
    )


async def start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add category conversation."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text("📁 Enter *category name*:", parse_mode="Markdown")
    return ADD_CAT_NAME


async def recv_cat_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["cat_name"] = update.message.text.strip()
    await update.message.reply_text("Enter *icon* (emoji, e.g. 🌊):", parse_mode="Markdown")
    return ADD_CAT_ICON


async def recv_cat_icon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["cat_icon"] = update.message.text.strip()
    await update.message.reply_text("Enter *description* (or /skip):", parse_mode="Markdown")
    return ADD_CAT_DESC


async def recv_cat_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = None if update.message.text.strip() == "/skip" else update.message.text.strip()

    async with get_session() as session:
        await product_service.create_category(
            session,
            name=context.user_data["cat_name"],
            icon=context.user_data.get("cat_icon"),
            description=desc,
        )

    context.user_data.pop("cat_name", None)
    context.user_data.pop("cat_icon", None)

    await update.message.reply_text(
        "✅ Category created!",
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all products (admin)."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        from app.database.repositories import product_repo
        products = await product_repo.list_active(session)
        # Also get inactive for admin view
        from sqlalchemy import select
        from app.database.models import Product
        stmt = select(Product).order_by(Product.name)
        result = await session.execute(stmt)
        all_products = list(result.scalars().all())

    await query.edit_message_text(
        "⚙️ *Products*",
        reply_markup=admin_products_keyboard(all_products),
        parse_mode="Markdown",
    )


async def admin_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show product detail (admin)."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split(":")[2])

    async with get_session() as session:
        details = await product_service.get_product_details(session, product_id)
        stock_summary = await inventory_service.get_stock_summary(session, product_id)

    if details is None:
        await query.edit_message_text("❌ Product not found.")
        return

    product = details["product"]
    stock = details["stock"]

    await query.edit_message_text(
        f"⚙️ *Product: {product.name}*\n\n"
        f"💰 Price: ${product.price}\n"
        f"📦 Available: {stock_summary.get('available', 0)}\n"
        f"🔒 Reserved: {stock_summary.get('reserved', 0)}\n"
        f"✅ Sold: {stock_summary.get('sold', 0)}\n"
        f"Active: {'✅' if product.active else '❌'}\n"
        f"Category ID: {product.category_id}",
        reply_markup=admin_product_detail_keyboard(product.id),
        parse_mode="Markdown",
    )


async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add product conversation."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    # If triggered directly with a category selected (adm:selcat:{id})
    if query.data.startswith("adm:selcat:"):
        cat_id = int(query.data.split(":")[2])
        context.user_data["prod_cat_id"] = cat_id
        await query.edit_message_text("Enter *product name*:", parse_mode="Markdown")
        return ADD_PROD_NAME

    async with get_session() as session:
        cats = await category_repo.list_active(session)

    if not cats:
        await query.edit_message_text("❌ Create a category first.")
        return ConversationHandler.END

    await query.edit_message_text(
        "📦 Select *category* for new product:",
        reply_markup=admin_category_select_keyboard(cats),
        parse_mode="Markdown",
    )
    return ADD_PROD_CAT


async def recv_prod_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive category selection for new product."""
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split(":")[2])
    context.user_data["prod_cat_id"] = cat_id
    await query.edit_message_text("Enter *product name*:", parse_mode="Markdown")
    return ADD_PROD_NAME


async def recv_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["prod_name"] = update.message.text.strip()
    await update.message.reply_text("Enter *description* (or /skip):", parse_mode="Markdown")
    return ADD_PROD_DESC


async def recv_prod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["prod_desc"] = None if text == "/skip" else text
    await update.message.reply_text("Enter *price* (e.g. 4.50):", parse_mode="Markdown")
    return ADD_PROD_PRICE


async def recv_prod_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = Decimal(update.message.text.strip())
    except InvalidOperation:
        await update.message.reply_text("❌ Invalid price. Enter a number (e.g. 4.50):")
        return ADD_PROD_PRICE

    async with get_session() as session:
        await product_service.create_product(
            session,
            category_id=context.user_data["prod_cat_id"],
            name=context.user_data["prod_name"],
            price=price,
            description=context.user_data.get("prod_desc"),
        )

    for key in ("prod_cat_id", "prod_name", "prod_desc"):
        context.user_data.pop(key, None)

    await update.message.reply_text(
        "✅ Product created!",
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


async def deactivate_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deactivate a product."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split(":")[2])

    async with get_session() as session:
        await product_service.deactivate_product(session, product_id)

    await query.edit_message_text(
        "✅ Product deactivated.",
        reply_markup=admin_main_keyboard(),
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

async def admin_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show inventory overview."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        from app.database.repositories import product_repo
        products = await product_repo.list_active(session)

    buttons = []
    for prod in products:
        buttons.append([
            InlineKeyboardButton(
                f"📦 {prod.name}",
                callback_data=f"adm:stock:{prod.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin")])

    await query.edit_message_text(
        "⚙️ *Inventory — Select Product*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def show_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show stock for a product."""
    query = update.callback_query
    await query.answer()
    product_id = int(query.data.split(":")[2])

    async with get_session() as session:
        from app.database.repositories import product_repo
        product = await product_repo.get_by_id(session, product_id)
        summary = await inventory_service.get_stock_summary(session, product_id)

    if product is None:
        await query.edit_message_text("❌ Product not found.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Stock", callback_data=f"adm:addstock:{product_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm:inventory")],
    ])

    await query.edit_message_text(
        f"⚙️ *Inventory: {product.name}*\n\n"
        f"📦 Available: {summary.get('available', 0)}\n"
        f"🔒 Reserved: {summary.get('reserved', 0)}\n"
        f"✅ Sold: {summary.get('sold', 0)}",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def start_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding stock items."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    product_id = int(query.data.split(":")[2])
    context.user_data["stock_product_id"] = product_id
    await query.edit_message_text(
        "📥 *Add Inventory / Account Stock*\n\n"
        "You can send accounts in either format:\n\n"
        "🔹 *Option 1: One line per account*\n"
        "`mail1@gmail.com:mailpass1:accpass1`\n"
        "`mail2@gmail.com:mailpass2:accpass2`\n\n"
        "🔹 *Option 2: Multi-line blocks (separated by `---`)*\n"
        "```\n"
        "Email: user1@gmail.com\n"
        "Mail Password: mailpass1\n"
        "Account Password: accpass1\n"
        "---\n"
        "Email: user2@gmail.com\n"
        "Mail Password: mailpass2\n"
        "Account Password: accpass2\n"
        "```\n\n"
        "Send your accounts now (or /cancel):",
        parse_mode="Markdown",
    )
    return ADD_STOCK_ITEMS


async def recv_stock_items(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and add inventory items (single-line or multi-line blocks)."""
    product_id = context.user_data.get("stock_product_id")
    if not product_id:
        await update.message.reply_text("❌ Error. Please try again.")
        return ConversationHandler.END

    raw_text = update.message.text.strip()
    if "---" in raw_text:
        items = [item.strip() for item in raw_text.split("---") if item.strip()]
    else:
        items = [item.strip() for item in raw_text.split("\n") if item.strip()]

    if not items:
        await update.message.reply_text("❌ No valid items found. Please try again or /cancel.")
        return ADD_STOCK_ITEMS

    async with get_session() as session:
        count = await inventory_service.add_stock(session, product_id, items)

    context.user_data.pop("stock_product_id", None)
    await update.message.reply_text(
        f"✅ Added {count} account(s) to stock successfully!",
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Orders (Admin)
# ---------------------------------------------------------------------------

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show orders (admin)."""
    query = update.callback_query
    await query.answer()

    page = 0
    if "orders_p:" in query.data:
        page = int(query.data.split(":")[2])

    async with get_session() as session:
        orders = await order_repo.get_all_orders(session, offset=page * 10, limit=11)

    has_more = len(orders) > 10
    display = orders[:10]

    await query.edit_message_text(
        "⚙️ *Orders*",
        reply_markup=admin_orders_keyboard(display, page, has_more),
        parse_mode="Markdown",
    )


async def admin_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show order details (admin)."""
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[2])

    async with get_session() as session:
        order = await order_repo.get_by_id(session, order_id)
        if order is None:
            await query.edit_message_text("❌ Order not found.")
            return

        payment = await payment_repo.get_by_order_id(session, order.id)
        user = await user_repo.get_by_id(session, order.user_id)

    username = f"@{user.username}" if user and user.username else f"ID:{order.user_id}"
    product_name = order.product.name if order.product else "Unknown"
    pay_status = payment.status.value if payment else "N/A"

    can_fulfill = order.status.value == "paid"

    await query.edit_message_text(
        f"⚙️ *Order: {order.public_order_id}*\n\n"
        f"👤 User: {username}\n"
        f"📦 Product: {product_name}\n"
        f"💰 Amount: ${order.amount}\n"
        f"📋 Status: {order.status.value}\n"
        f"💳 Payment: {pay_status}\n"
        f"📅 Created: {order.created_at.strftime('%d %b %Y %H:%M')}",
        reply_markup=admin_order_detail_keyboard(order.id, can_fulfill),
        parse_mode="Markdown",
    )


async def admin_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin manually deliver an order."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])

    async with get_session() as session:
        try:
            result = await order_service.fulfill_order(session, order_id)
            if result:
                order = result["order"]
                content = result["content"]

                # Try to deliver via Telegram
                user = await user_repo.get_by_id(session, order.user_id)
                if user and content:
                    from app.bot.bot import get_bot_instance
                    bot = get_bot_instance()
                    if bot:
                        from app.services import delivery_service
                        product_name = order.product.name if order.product else "Product"
                        await delivery_service.deliver_to_user(
                            bot, user.telegram_id, order, content, product_name
                        )

                await query.edit_message_text(
                    f"✅ Order {order.public_order_id} delivered.",
                    reply_markup=admin_main_keyboard(),
                )
            else:
                await query.edit_message_text("❌ Could not fulfill order.")
        except order_service.OrderError as e:
            await query.edit_message_text(f"❌ {e}")


async def admin_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin cancel an order."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])

    async with get_session() as session:
        try:
            await order_service.cancel_order(session, order_id)
            await query.edit_message_text(
                "✅ Order cancelled.",
                reply_markup=admin_main_keyboard(),
            )
        except order_service.OrderError as e:
            await query.edit_message_text(f"❌ {e}")


# ---------------------------------------------------------------------------
# Payments (Admin)
# ---------------------------------------------------------------------------

async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent payments (admin)."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        payments = await payment_repo.list_payments(session, limit=10)

    if not payments:
        await query.edit_message_text(
            "⚙️ *Payments*\n\nNo payments yet.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
            ]),
            parse_mode="Markdown",
        )
        return

    lines = ["⚙️ *Recent Payments*\n"]
    for p in payments:
        lines.append(
            f"💳 `{p.provider_payment_id or p.provider_invoice_id or 'N/A'}`\n"
            f"   Order: {p.order_id} | {p.status.value} | ${p.requested_amount}"
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
        ]),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Users (Admin)
# ---------------------------------------------------------------------------

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show users (admin)."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        users = await user_repo.list_users(session, limit=15)
        total = await user_repo.count_users(session)

    lines = [f"⚙️ *Users* ({total} total)\n"]
    for u in users:
        username = f"@{u.username}" if u.username else u.first_name or "?"
        lines.append(f"👤 {username} (ID: {u.telegram_id})")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
        ]),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show statistics."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        user_count = await user_repo.count_users(session)
        order_stats = await order_service.get_order_stats(session)
        open_tickets = await support_repo.count_open(session)

    await query.edit_message_text(
        f"⚙️ *Statistics*\n\n"
        f"👥 Total Users: {user_count}\n\n"
        f"📦 Total Orders: {order_stats['total_orders']}\n"
        f"✅ Paid/Fulfilled: {order_stats['paid_orders']}\n"
        f"❌ Cancelled: {order_stats['cancelled_orders']}\n"
        f"⏰ Expired: {order_stats['expired_orders']}\n\n"
        f"💰 Revenue: ${order_stats['revenue']}\n\n"
        f"🎫 Open Tickets: {open_tickets}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
        ]),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start broadcast."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text(
        "📢 *Broadcast*\n\nType the message to send to all users\n(or /cancel):",
        parse_mode="Markdown",
    )
    return BROADCAST_MSG


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send broadcast message to all users."""
    message_text = update.message.text.strip()

    async with get_session() as session:
        users = await user_repo.list_users(session, limit=10000)

    sent = 0
    failed = 0
    status_msg = await update.message.reply_text("📢 Broadcasting... 0 sent, 0 failed")

    for i, user in enumerate(users):
        if user.is_blocked:
            failed += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=user.telegram_id,
                text=message_text,
            )
            sent += 1
        except TelegramError:
            failed += 1

        # Rate limiting: 30 messages per second
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)
            try:
                await status_msg.edit_text(f"📢 Broadcasting... {sent} sent, {failed} failed")
            except TelegramError:
                pass

    await status_msg.edit_text(
        f"📢 *Broadcast Complete*\n\n✅ Sent: {sent}\n❌ Failed: {failed}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Tickets (Admin)
# ---------------------------------------------------------------------------

async def admin_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show open support tickets (admin)."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        tickets = await support_repo.list_all(session, limit=15)

    if not tickets:
        await query.edit_message_text(
            "⚙️ *Support Tickets*\n\nNo tickets.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
            ]),
            parse_mode="Markdown",
        )
        return

    buttons = []
    for t in tickets:
        icon = {"open": "🟡", "replied": "🟢", "closed": "⚫"}.get(t.status.value, "❓")
        buttons.append([
            InlineKeyboardButton(
                f"{icon} #{t.id} — {t.subject[:30]}",
                callback_data=f"adm:ticket:{t.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin")])

    await query.edit_message_text(
        "⚙️ *Support Tickets*",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def admin_ticket_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show ticket detail (admin)."""
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(":")[2])

    async with get_session() as session:
        ticket = await support_repo.get_by_id(session, ticket_id)

    if ticket is None:
        await query.edit_message_text("❌ Ticket not found.")
        return

    reply_text = f"\n\n↪️ Reply: {ticket.admin_reply}" if ticket.admin_reply else ""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"adm:reply_ticket:{ticket_id}")],
        [InlineKeyboardButton("🔒 Close", callback_data=f"adm:close_ticket:{ticket_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm:tickets")],
    ])

    await query.edit_message_text(
        f"⚙️ *Ticket #{ticket.id}*\n\n"
        f"📝 Subject: {ticket.subject}\n"
        f"💬 Message: {ticket.message}\n"
        f"Status: {ticket.status.value}{reply_text}",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def start_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start replying to a ticket."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    ticket_id = int(query.data.split(":")[2])
    context.user_data["reply_ticket_id"] = ticket_id
    await query.edit_message_text("💬 Type your reply:", parse_mode="Markdown")
    return TICKET_REPLY_MSG


async def recv_ticket_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and save ticket reply."""
    ticket_id = context.user_data.get("reply_ticket_id")
    if not ticket_id:
        await update.message.reply_text("❌ Error.")
        return ConversationHandler.END

    reply_text = update.message.text.strip()

    async with get_session() as session:
        ticket = await support_repo.reply(session, ticket_id, reply_text)

        # Notify user
        if ticket:
            user = await user_repo.get_by_id(session, ticket.user_id)
            if user:
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=(
                            f"💬 *Support Reply*\n\n"
                            f"🎫 Ticket #{ticket.id}: {ticket.subject}\n\n"
                            f"↪️ {reply_text}"
                        ),
                        parse_mode="Markdown",
                    )
                except TelegramError:
                    pass

    context.user_data.pop("reply_ticket_id", None)
    await update.message.reply_text(
        "✅ Reply sent.",
        reply_markup=admin_main_keyboard(),
    )
    return ConversationHandler.END


async def close_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Close a ticket."""
    query = update.callback_query
    await query.answer()
    ticket_id = int(query.data.split(":")[2])

    async with get_session() as session:
        await support_repo.close_ticket(session, ticket_id)

    await query.edit_message_text(
        "✅ Ticket closed.",
        reply_markup=admin_main_keyboard(),
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin settings."""
    query = update.callback_query
    await query.answer()

    async with get_session() as session:
        maint = await settings_repo.get_setting(session, "maintenance_mode")

    maint_status = "🟢 OFF" if maint != "true" else "🔴 ON"

    await query.edit_message_text(
        f"⚙️ *Settings*\n\n"
        f"🔧 Maintenance Mode: {maint_status}",
        reply_markup=admin_settings_keyboard(),
        parse_mode="Markdown",
    )


async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle maintenance mode."""
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("❌ Access denied.", show_alert=True)
        return
    await query.answer()

    async with get_session() as session:
        current = await settings_repo.get_setting(session, "maintenance_mode")
        new_val = "false" if current == "true" else "true"
        await settings_repo.set_setting(session, "maintenance_mode", new_val)

    status = "🔴 ON" if new_val == "true" else "🟢 OFF"
    await query.edit_message_text(
        f"✅ Maintenance mode: {status}",
        reply_markup=admin_main_keyboard(),
    )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

def get_handlers() -> list:
    """Return all admin handlers."""
    add_cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_category, pattern="^adm:add_cat$")],
        states={
            ADD_CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_cat_name)],
            ADD_CAT_ICON: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_cat_icon)],
            ADD_CAT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_cat_desc),
                CommandHandler("skip", recv_cat_desc),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    add_prod_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_product, pattern="^adm:add_product$"),
            CallbackQueryHandler(start_add_product, pattern=r"^adm:selcat:\d+$"),
        ],
        states={
            ADD_PROD_CAT: [
                CallbackQueryHandler(recv_prod_category, pattern=r"^adm:selcat:\d+$"),
            ],
            ADD_PROD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_prod_name),
            ],
            ADD_PROD_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_prod_desc),
                CommandHandler("skip", recv_prod_desc),
            ],
            ADD_PROD_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_prod_price),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    add_stock_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_stock, pattern=r"^adm:addstock:\d+$"),
        ],
        states={
            ADD_STOCK_ITEMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_stock_items),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_broadcast, pattern="^adm:broadcast$")],
        states={
            BROADCAST_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    ticket_reply_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_ticket_reply, pattern=r"^adm:reply_ticket:\d+$"),
        ],
        states={
            TICKET_REPLY_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_ticket_reply),
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_message=False,
    )

    return [
        CommandHandler("admin", admin_command),
        add_cat_conv,
        add_prod_conv,
        add_stock_conv,
        broadcast_conv,
        ticket_reply_conv,
        CallbackQueryHandler(admin_panel, pattern="^admin$"),
        CallbackQueryHandler(admin_categories, pattern="^adm:categories$"),
        CallbackQueryHandler(admin_category_detail, pattern=r"^adm:cat:\d+$"),
        CallbackQueryHandler(deactivate_category_handler, pattern=r"^adm:deact_cat:\d+$"),
        CallbackQueryHandler(admin_products, pattern="^adm:products$"),
        CallbackQueryHandler(admin_product_detail, pattern=r"^adm:prod:\d+$"),
        CallbackQueryHandler(deactivate_product, pattern=r"^adm:deact_prod:\d+$"),
        CallbackQueryHandler(admin_inventory, pattern="^adm:inventory$"),
        CallbackQueryHandler(show_stock, pattern=r"^adm:stock:\d+$"),
        CallbackQueryHandler(admin_orders, pattern="^adm:orders$"),
        CallbackQueryHandler(admin_orders, pattern=r"^adm:orders_p:\d+$"),
        CallbackQueryHandler(admin_order_detail, pattern=r"^adm:order:\d+$"),
        CallbackQueryHandler(admin_deliver, pattern=r"^adm:deliver:\d+$"),
        CallbackQueryHandler(admin_cancel_order, pattern=r"^adm:cancel_ord:\d+$"),
        CallbackQueryHandler(admin_payments, pattern="^adm:payments$"),
        CallbackQueryHandler(admin_users, pattern="^adm:users$"),
        CallbackQueryHandler(admin_stats, pattern="^adm:stats$"),
        CallbackQueryHandler(admin_tickets, pattern="^adm:tickets$"),
        CallbackQueryHandler(admin_ticket_detail, pattern=r"^adm:ticket:\d+$"),
        CallbackQueryHandler(close_ticket_handler, pattern=r"^adm:close_ticket:\d+$"),
        CallbackQueryHandler(admin_settings, pattern="^adm:settings$"),
        CallbackQueryHandler(toggle_maintenance, pattern="^adm:toggle_maint$"),
    ]
