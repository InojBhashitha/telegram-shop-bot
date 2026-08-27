"""Order and payment keyboards."""

from __future__ import annotations

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Order


def payment_keyboard(
    payment_url: str,
    order_id: int,
) -> InlineKeyboardMarkup:
    """Payment keyboard with crypto checkout URL button."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay with Crypto", url=payment_url)],
        [
            InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_pay:{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_order:{order_id}"),
        ],
    ])


def order_list_keyboard(
    orders: list[Order],
    page: int = 0,
    has_more: bool = False,
) -> InlineKeyboardMarkup:
    """Order history list keyboard."""
    buttons = []
    for order in orders:
        status_icon = _order_status_icon(order.status.value)
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {order.public_order_id} — ${order.amount}",
                callback_data=f"order:{order.public_order_id}",
            )
        ])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"orders_page:{page - 1}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"orders_page:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="profile")])
    return InlineKeyboardMarkup(buttons)


def order_detail_keyboard(public_order_id: str) -> InlineKeyboardMarkup:
    """Order detail keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="orders")],
    ])


def _order_status_icon(status: str) -> str:
    """Map order status to an emoji icon."""
    icons = {
        "pending_payment": "⏳",
        "payment_processing": "🔄",
        "paid": "💰",
        "fulfilled": "✅",
        "cancelled": "❌",
        "expired": "⏰",
        "refunded": "↩️",
    }
    return icons.get(status, "📦")
