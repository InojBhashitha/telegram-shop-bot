"""Shopping cart keyboards — view cart, manage quantities, and checkout buttons."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def cart_view_keyboard(has_items: bool, is_valid: bool = True) -> InlineKeyboardMarkup:
    """Main shopping cart keyboard."""
    buttons = []
    if has_items:
        if is_valid:
            buttons.append([
                InlineKeyboardButton("💳 Checkout with Crypto", callback_data="cart_checkout")
            ])
        buttons.append([
            InlineKeyboardButton("✏️ Manage Items", callback_data="cart_manage"),
            InlineKeyboardButton("🗑️ Clear Cart", callback_data="cart_clear"),
        ])
        buttons.append([
            InlineKeyboardButton("🛍 Keep Shopping", callback_data="products")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("🛍 Browse Products", callback_data="products")
        ])
        buttons.append([
            InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")
        ])
    return InlineKeyboardMarkup(buttons)


def cart_manage_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard listing cart items for editing or removal."""
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton(
                f"📦 {item['product_name']} ({item['quantity']}x) — ${item['subtotal']}",
                callback_data=f"cart_edit:{item['product_id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Cart", callback_data="cart")
    ])
    return InlineKeyboardMarkup(buttons)


def cart_item_edit_keyboard(
    product_id: int, quantity: int, stock: int
) -> InlineKeyboardMarkup:
    """Item detail edit keyboard with increment/decrement steppers and remove."""
    row1 = []
    if quantity > 1:
        row1.append(InlineKeyboardButton("➖ 1", callback_data=f"cart_qty:{product_id}:{quantity - 1}"))
    row1.append(InlineKeyboardButton(f"🔢 {quantity} in cart", callback_data="noop"))
    if quantity < stock:
        row1.append(InlineKeyboardButton("➕ 1", callback_data=f"cart_qty:{product_id}:{quantity + 1}"))

    buttons = []
    if row1:
        buttons.append(row1)
    buttons.append([
        InlineKeyboardButton("🗑️ Remove from Cart", callback_data=f"cart_del:{product_id}")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ Back to Cart", callback_data="cart")
    ])
    return InlineKeyboardMarkup(buttons)


def cart_added_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown immediately after successfully adding an item to cart."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 View Cart", callback_data="cart"),
            InlineKeyboardButton("💳 Checkout Now", callback_data="cart_checkout"),
        ],
        [
            InlineKeyboardButton("🛍 Continue Shopping", callback_data=f"cat:{category_id}")
        ],
    ])
