"""Order and payment keyboards with live status tracker and warranty button."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Order, OrderStatus


def payment_keyboard(
    payment_url: str,
    order_id: int,
    order_status: str = "pending_payment",
    amount: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Payment keyboard with crypto checkout URL and live status tracker."""
    # Status step indicators
    steps = _get_payment_steps(order_status)

    buttons = [
        [InlineKeyboardButton(f"💳 Pay with Crypto", url=payment_url)],
        [InlineKeyboardButton(steps, callback_data="noop")],
        [
            InlineKeyboardButton("🔄 Check Payment", callback_data=f"check_pay:{order_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_order:{order_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def _get_payment_steps(status: str) -> str:
    """Generate visual step progress bar for payment status."""
    steps_map = {
        "pending_payment": ("🟡", "⚪", "⚪"),
        "waiting": ("🟡", "⚪", "⚪"),
        "confirming": ("🟢", "🟡", "⚪"),
        "payment_processing": ("🟢", "🟡", "⚪"),
        "confirmed": ("🟢", "🟡", "⚪"),
        "sending": ("🟢", "🟢", "🟡"),
        "paid": ("🟢", "🟢", "🟢"),
        "finished": ("🟢", "🟢", "🟢"),
        "fulfilled": ("🟢", "🟢", "🟢"),
        "failed": ("🔴", "🔴", "🔴"),
        "expired": ("🔴", "🔴", "🔴"),
        "cancelled": ("🔴", "🔴", "🔴"),
    }
    s1, s2, s3 = steps_map.get(status, ("⚪", "⚪", "⚪"))
    return f"{s1} Deposit → {s2} Confirm → {s3} Deliver"


def order_list_keyboard(
    orders: list[Order],
    page: int = 0,
    has_more: bool = False,
) -> InlineKeyboardMarkup:
    """Order history list keyboard."""
    buttons = []
    for order in orders:
        status_icon = _order_status_icon(order.status.value)
        qty_label = f" ×{order.quantity}" if hasattr(order, 'quantity') and order.quantity > 1 else ""
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {order.public_order_id}{qty_label} — ${order.amount}",
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


def order_detail_keyboard(
    order: Order,
    has_warranty: bool = False,
) -> InlineKeyboardMarkup:
    """Order detail keyboard with optional warranty claim button."""
    buttons = []

    # Warranty button for fulfilled orders within warranty period
    if has_warranty and order.status == OrderStatus.FULFILLED:
        now = datetime.now(timezone.utc)
        if order.warranty_expires_at and now < order.warranty_expires_at:
            buttons.append([
                InlineKeyboardButton(
                    "🛡 Report Issue / Request Replacement",
                    callback_data=f"warranty_claim:{order.id}",
                )
            ])

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="orders")])
    return InlineKeyboardMarkup(buttons)


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
