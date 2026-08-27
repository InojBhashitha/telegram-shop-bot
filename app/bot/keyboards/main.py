"""Main navigation keyboards."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard shown after /start."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 View all products", callback_data="products")],
        [
            InlineKeyboardButton("🔥 Buy Now", callback_data="products"),
            InlineKeyboardButton("💳 Top-up", callback_data="topup"),
        ],
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("☎️ Support", callback_data="support"),
        ],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
    ])


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
