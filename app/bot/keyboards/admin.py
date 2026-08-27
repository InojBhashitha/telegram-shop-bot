"""Admin panel keyboards."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Admin panel main menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Products", callback_data="adm:products"),
            InlineKeyboardButton("📁 Categories", callback_data="adm:categories"),
        ],
        [
            InlineKeyboardButton("📥 Inventory", callback_data="adm:inventory"),
            InlineKeyboardButton("💰 Orders", callback_data="adm:orders"),
        ],
        [
            InlineKeyboardButton("💳 Payments", callback_data="adm:payments"),
            InlineKeyboardButton("👥 Users", callback_data="adm:users"),
        ],
        [
            InlineKeyboardButton("📊 Statistics", callback_data="adm:stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
        ],
        [
            InlineKeyboardButton("🎫 Tickets", callback_data="adm:tickets"),
            InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings"),
        ],
        [InlineKeyboardButton("⬅️ Close", callback_data="main_menu")],
    ])


def admin_products_keyboard(products: list, include_add: bool = True) -> InlineKeyboardMarkup:
    """Admin product list keyboard."""
    buttons = []
    if include_add:
        buttons.append([InlineKeyboardButton("➕ Add Product", callback_data="adm:add_product")])
    for prod in products:
        status = "✅" if prod.active else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{status} {prod.name} — ${prod.price}",
                callback_data=f"adm:prod:{prod.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)


def admin_product_detail_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Admin product detail actions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"adm:edit_prod:{product_id}"),
            InlineKeyboardButton("📥 Stock", callback_data=f"adm:stock:{product_id}"),
        ],
        [
            InlineKeyboardButton(
                "🔴 Deactivate", callback_data=f"adm:deact_prod:{product_id}"
            ),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm:products")],
    ])


def admin_categories_keyboard(categories: list) -> InlineKeyboardMarkup:
    """Admin category list keyboard."""
    buttons = [
        [InlineKeyboardButton("➕ Add Category", callback_data="adm:add_cat")]
    ]
    for cat in categories:
        icon = cat.icon or "📁"
        status = "✅" if cat.active else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{status} {icon} {cat.name}",
                callback_data=f"adm:cat:{cat.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)


def admin_category_detail_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Admin category detail actions."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Product Here", callback_data=f"adm:selcat:{category_id}"),
            InlineKeyboardButton("🔴 Deactivate", callback_data=f"adm:deact_cat:{category_id}"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="adm:categories")],
    ])


def admin_category_select_keyboard(categories: list) -> InlineKeyboardMarkup:
    """Category selection keyboard for product creation."""
    buttons = []
    for cat in categories:
        icon = cat.icon or "📁"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {cat.name}",
                callback_data=f"adm:selcat:{cat.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="adm:products")])
    return InlineKeyboardMarkup(buttons)


def admin_orders_keyboard(orders: list, page: int = 0, has_more: bool = False) -> InlineKeyboardMarkup:
    """Admin orders list keyboard."""
    buttons = []
    for order in orders:
        from app.bot.keyboards.orders import _order_status_icon
        icon = _order_status_icon(order.status.value)
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {order.public_order_id} — ${order.amount}",
                callback_data=f"adm:order:{order.id}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm:orders_p:{page - 1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm:orders_p:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)


def admin_order_detail_keyboard(order_id: int, can_fulfill: bool = False) -> InlineKeyboardMarkup:
    """Admin order detail actions."""
    buttons = []
    if can_fulfill:
        buttons.append([
            InlineKeyboardButton("📦 Deliver", callback_data=f"adm:deliver:{order_id}"),
        ])
    buttons.append([
        InlineKeyboardButton("❌ Cancel", callback_data=f"adm:cancel_ord:{order_id}"),
    ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="adm:orders")])
    return InlineKeyboardMarkup(buttons)


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    """Admin settings keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔧 Maintenance Mode", callback_data="adm:toggle_maint")],
        [InlineKeyboardButton("📝 Edit Store Name", callback_data="adm:edit_store_name")],
        [InlineKeyboardButton("📝 Edit FAQ", callback_data="adm:edit_faq")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin")],
    ])
