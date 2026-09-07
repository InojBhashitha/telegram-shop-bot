"""Main navigation keyboards — inline menu + persistent reply keyboard."""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import get_settings


def main_menu_keyboard(cart_count: int = 0) -> InlineKeyboardMarkup:
    """Main menu keyboard shown after /start with prominent Mini App launcher."""
    settings = get_settings()
    webapp_url = settings.effective_webapp_url
    cart_btn = f"🛒 My Cart ({cart_count})" if cart_count > 0 else "🛒 My Cart"

    rows: list[list[InlineKeyboardButton]] = []
    if webapp_url and webapp_url.startswith("https://"):
        rows.append([InlineKeyboardButton("🚀 Launch Mini App Store", web_app=WebAppInfo(url=webapp_url))])

    rows.extend([
        [InlineKeyboardButton("🎁 View all products", callback_data="products")],
        [
            InlineKeyboardButton("🔥 Buy Now", callback_data="products"),
            InlineKeyboardButton(cart_btn, callback_data="cart"),
        ],
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("💳 Top-up", callback_data="topup"),
        ],
        [
            InlineKeyboardButton("☎️ Support", callback_data="support"),
            InlineKeyboardButton("❓ FAQ", callback_data="faq"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom reply keyboard for quick navigation with Mini App button."""
    settings = get_settings()
    webapp_url = settings.effective_webapp_url

    rows: list[list[KeyboardButton]] = []
    if webapp_url and webapp_url.startswith("https://"):
        rows.append([KeyboardButton("🚀 Open Store (Mini App)", web_app=WebAppInfo(url=webapp_url))])

    rows.extend([
        [KeyboardButton("🛍 Browse Store"), KeyboardButton("🛒 My Cart")],
        [KeyboardButton("📦 My Orders"), KeyboardButton("👤 My Profile")],
        [KeyboardButton("☎️ Support / FAQ")],
    ])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def back_button(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """Single back button keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data=callback_data)],
    ])


def confirm_cancel_keyboard(
    confirm_data: str,
    cancel_data: str = "main_menu",
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel",
) -> InlineKeyboardMarkup:
    """Confirm/Cancel keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(confirm_text, callback_data=confirm_data),
            InlineKeyboardButton(cancel_text, callback_data=cancel_data),
        ],
    ])
