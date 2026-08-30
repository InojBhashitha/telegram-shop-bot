"""UI utilities for rich visual elements, stock bars, and media cards."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


def format_stock_bar(stock_count: int, max_capacity: int = 10) -> str:
    """Format a 10-segment visual stock progress bar with status indicator.

    Examples:
        Stock 15 -> 🟢 [██████████] High Stock (15 left)
        Stock 5  -> 🟡 [█████░░░░░] Medium Stock (5 left)
        Stock 2  -> ⚠️ [██░░░░░░░░] Low Stock (2 left)
        Stock 0  -> 🔴 [░░░░░░░░░░] Sold Out
    """
    if stock_count <= 0:
        return "🔴 `[░░░░░░░░░░]` *Sold Out*"

    # Calculate filled blocks out of 10
    filled = min(10, max(1, round((stock_count / max_capacity) * 10)))
    empty = 10 - filled
    bar = f"`[{'█' * filled}{'░' * empty}]`"

    if stock_count >= 10:
        return f"🟢 {bar} *High Stock* ({stock_count} left)"
    elif stock_count >= 4:
        return f"🟡 {bar} *Medium Stock* ({stock_count} left)"
    else:
        return f"⚠️ {bar} *Low Stock* ({stock_count} left)"


def format_product_caption(
    name: str,
    price: Decimal,
    stock: int,
    description: Optional[str] = None,
    currency: str = "USD",
    warranty_hours: int = 24,
) -> str:
    """Format a high-end visual product detail card caption."""
    stock_bar = format_stock_bar(stock)
    desc_text = f"\n\n📝 *Description:*\n_{description}_" if description else ""

    return (
        f"☁️ *Cloud Deals — Digital Store*\n\n"
        f"📦 *{name}*\n\n"
        f"💰 *Price:* ${price} {currency}\n"
        f"📊 *Availability:* {stock_bar}\n"
        f"🛡 *Warranty:* {warranty_hours} Hours Auto-Replacement\n"
        f"{desc_text}\n\n"
        f"👇 Select quantity or checkout below:"
    )
