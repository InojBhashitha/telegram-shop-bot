"""Product and category keyboards."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Category, Product


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
    products: list[Product], category_id: int
) -> InlineKeyboardMarkup:
    """Build keyboard with product buttons for a category."""
    buttons = []
    for prod in products:
        buttons.append([
            InlineKeyboardButton(
                f"📦 {prod.name} — ${prod.price}",
                callback_data=f"prod:{prod.id}",
            )
        ])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="products")])
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(
    product_id: int, in_stock: bool, category_id: int
) -> InlineKeyboardMarkup:
    """Product detail keyboard with Buy button."""
    buttons = []
    if in_stock:
        buttons.append([
            InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy:{product_id}")
        ])
    buttons.append([
        InlineKeyboardButton("⬅️ Back", callback_data=f"cat:{category_id}")
    ])
    return InlineKeyboardMarkup(buttons)
