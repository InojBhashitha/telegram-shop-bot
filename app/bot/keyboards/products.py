"""Product and category keyboards with live stock & price badges."""

from __future__ import annotations

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Category, Product


def _stock_badge(stock: int) -> str:
    """Generate a visual stock badge."""
    if stock == 0:
        return "🔴 Sold Out"
    elif stock <= 2:
        return f"🟡 {stock} left!"
    elif stock <= 5:
        return f"🟢 {stock} left"
    else:
        return "🟢 In Stock"


def categories_keyboard(categories: list[Category]) -> InlineKeyboardMarkup:
    """Build keyboard with category buttons."""
    buttons = []
    for cat in categories:
        icon = cat.icon or "📁"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {cat.name}",
                callback_data=f"cat:{cat.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def products_keyboard(
    products: list[Product],
    category_id: int,
    stock_counts: Optional[dict[int, int]] = None,
) -> InlineKeyboardMarkup:
    """Build keyboard with product buttons including live stock & price badges.

    Args:
        products: List of product models.
        category_id: Category ID for back button.
        stock_counts: Optional dict mapping product_id -> available stock count.
    """
    buttons = []
    for prod in products:
        stock = stock_counts.get(prod.id, 0) if stock_counts else None
        if stock is not None:
            badge = _stock_badge(stock)
            label = f"📦 {prod.name} — ${prod.price} ({badge})"
        else:
            label = f"📦 {prod.name} — ${prod.price}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"prod:{prod.id}")
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(
    product_id: int, in_stock: bool, category_id: int, stock: int = 0
) -> InlineKeyboardMarkup:
    """Product detail keyboard with Buy button and quantity options."""
    buttons = []
    if in_stock:
        buttons.append([
            InlineKeyboardButton("🛒 Buy Now (1x)", callback_data=f"buy:{product_id}:1")
        ])
        if stock >= 2:
            row2 = []
            if stock >= 2:
                row2.append(InlineKeyboardButton("2x", callback_data=f"buy:{product_id}:2"))
            if stock >= 5:
                row2.append(InlineKeyboardButton("5x", callback_data=f"buy:{product_id}:5"))
            if stock >= 10:
                row2.append(InlineKeyboardButton("10x", callback_data=f"buy:{product_id}:10"))
            if row2:
                buttons.append(row2)
    buttons.append([
        InlineKeyboardButton("⬅️ Back", callback_data=f"cat:{category_id}")
    ])
    return InlineKeyboardMarkup(buttons)
