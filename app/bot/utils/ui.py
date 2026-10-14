"""UI utilities for rich visual elements, stock bars, and media cards."""

from __future__ import annotations

from decimal import Decimal


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
    description: str | None = None,
    currency: str = "USD",
    warranty_hours: int = 24,
) -> str:
    from telegram.helpers import escape_markdown
    safe_name = escape_markdown(name, version=1)
    stock_bar = format_stock_bar(stock)
    desc_text = f"\n\n📝 *Description:*\n{description}" if description else ""
    bulk_text = ""
    try:
        from app.services.bulk_pricing_service import format_bulk_pricing_caption
        bulk_caption = format_bulk_pricing_caption(price)
        if bulk_caption:
            bulk_text = f"\n\n{bulk_caption}"
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Bulk caption error: %s", e)

    return (
        f"☁️ *Cloud Deals — Digital Store*\n\n"
        f"📦 *{safe_name}*\n\n"
        f"💰 *Price:* ${price} {currency}\n"
        f"📊 *Availability:* {stock_bar}\n"
        f"🛡 *Warranty:* {warranty_hours} Hours Auto-Replacement\n"
        f"{desc_text}"
        f"{bulk_text}\n\n"
        f"👇 Select quantity or checkout below:"
    )

