"""Bulk & Wholesale Volume Pricing Tier service.

Calculates automatic quantity-based discounts to reward bulk and wholesale buyers,
multiplying Average Order Value (AOV).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_bulk_pricing_tiers() -> list[dict]:
    """Return active bulk volume pricing tiers configuration."""
    settings = get_settings()
    if not settings.bulk_pricing_enabled:
        return []

    return [
        {
            "min_qty": settings.bulk_tier1_min_qty,
            "discount_percent": settings.bulk_tier1_discount_percent,
            "label": f"{settings.bulk_tier1_min_qty}+ pcs",
            "badge": f"-{settings.bulk_tier1_discount_percent:g}%",
        },
        {
            "min_qty": settings.bulk_tier2_min_qty,
            "discount_percent": settings.bulk_tier2_discount_percent,
            "label": f"{settings.bulk_tier2_min_qty}+ pcs",
            "badge": f"-{settings.bulk_tier2_discount_percent:g}%",
        },
        {
            "min_qty": settings.bulk_tier3_min_qty,
            "discount_percent": settings.bulk_tier3_discount_percent,
            "label": f"{settings.bulk_tier3_min_qty}+ pcs",
            "badge": f"-{settings.bulk_tier3_discount_percent:g}%",
        },
        {
            "min_qty": settings.bulk_tier4_min_qty,
            "discount_percent": settings.bulk_tier4_discount_percent,
            "label": f"{settings.bulk_tier4_min_qty}+ pcs (VIP Wholesale)",
            "badge": f"-{settings.bulk_tier4_discount_percent:g}%",
        },
    ]


def calculate_bulk_discount(unit_price: Decimal | float | int, quantity: int) -> dict:
    """Calculate wholesale volume discount for a given unit price and quantity.

    Tiers:
    - Tier 4: 25+ pcs  -> 20% OFF (VIP Wholesale)
    - Tier 3: 10+ pcs  -> 15% OFF
    - Tier 2: 5+ pcs   -> 10% OFF
    - Tier 1: 3+ pcs   -> 5% OFF
    - Below 3 pcs      -> 0% OFF

    Returns:
        Dict with discount details, savings, final subtotal, and next tier upsell hint.
    """
    settings = get_settings()
    price = Decimal(str(unit_price))
    qty = max(1, int(quantity))
    raw_subtotal = (price * qty).quantize(Decimal("0.01"))

    if not settings.bulk_pricing_enabled:
        return {
            "quantity": qty,
            "unit_price": price,
            "raw_subtotal": raw_subtotal,
            "discount_percent": 0.0,
            "discount_amount": Decimal("0.00"),
            "final_subtotal": raw_subtotal,
            "effective_unit_price": price,
            "tier_label": "",
            "next_tier_hint": "",
        }

    t4_qty = settings.bulk_tier4_min_qty
    t4_pct = settings.bulk_tier4_discount_percent

    t3_qty = settings.bulk_tier3_min_qty
    t3_pct = settings.bulk_tier3_discount_percent

    t2_qty = settings.bulk_tier2_min_qty
    t2_pct = settings.bulk_tier2_discount_percent

    t1_qty = settings.bulk_tier1_min_qty
    t1_pct = settings.bulk_tier1_discount_percent

    discount_percent = 0.0
    tier_label = ""
    next_tier_hint = ""

    if qty >= t4_qty:
        discount_percent = t4_pct
        tier_label = f"VIP Wholesale ({t4_pct:g}% OFF)"
    elif qty >= t3_qty:
        discount_percent = t3_pct
        tier_label = f"Tier 3 ({t3_pct:g}% OFF)"
        needed = t4_qty - qty
        next_tier_hint = f"Add {needed} more for {t4_pct:g}% VIP Wholesale!"
    elif qty >= t2_qty:
        discount_percent = t2_pct
        tier_label = f"Tier 2 ({t2_pct:g}% OFF)"
        needed = t3_qty - qty
        next_tier_hint = f"Add {needed} more for {t3_pct:g}% OFF!"
    elif qty >= t1_qty:
        discount_percent = t1_pct
        tier_label = f"Tier 1 ({t1_pct:g}% OFF)"
        needed = t2_qty - qty
        next_tier_hint = f"Add {needed} more for {t2_pct:g}% OFF!"
    else:
        needed = t1_qty - qty
        next_tier_hint = f"Add {needed} more for {t1_pct:g}% Wholesale Discount!"

    if discount_percent > 0:
        discount_amount = (raw_subtotal * Decimal(str(discount_percent)) / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount_amount = Decimal("0.00")

    final_subtotal = max(raw_subtotal - discount_amount, Decimal("0.01"))
    effective_unit_price = (final_subtotal / Decimal(qty)).quantize(Decimal("0.01"))

    return {
        "quantity": qty,
        "unit_price": price,
        "raw_subtotal": raw_subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "final_subtotal": final_subtotal,
        "effective_unit_price": effective_unit_price,
        "tier_label": tier_label,
        "next_tier_hint": next_tier_hint,
    }


def get_product_bulk_pricing(unit_price: Decimal | float | int) -> list[dict]:
    """Generate display tiers with calculated unit prices for a specific product."""
    settings = get_settings()
    if not settings.bulk_pricing_enabled:
        return []

    price = Decimal(str(unit_price))
    tiers = [
        {
            "min_qty": 1,
            "unit_price": f"${price:.2f}",
            "discount_percent": 0.0,
            "badge": "Standard",
        },
        {
            "min_qty": settings.bulk_tier1_min_qty,
            "unit_price": f"${(price * (1 - Decimal(str(settings.bulk_tier1_discount_percent)) / Decimal('100'))):.2f}",
            "discount_percent": settings.bulk_tier1_discount_percent,
            "badge": f"-{settings.bulk_tier1_discount_percent:g}%",
        },
        {
            "min_qty": settings.bulk_tier2_min_qty,
            "unit_price": f"${(price * (1 - Decimal(str(settings.bulk_tier2_discount_percent)) / Decimal('100'))):.2f}",
            "discount_percent": settings.bulk_tier2_discount_percent,
            "badge": f"-{settings.bulk_tier2_discount_percent:g}% 🔥",
        },
        {
            "min_qty": settings.bulk_tier3_min_qty,
            "unit_price": f"${(price * (1 - Decimal(str(settings.bulk_tier3_discount_percent)) / Decimal('100'))):.2f}",
            "discount_percent": settings.bulk_tier3_discount_percent,
            "badge": f"-{settings.bulk_tier3_discount_percent:g}% 🚀",
        },
        {
            "min_qty": settings.bulk_tier4_min_qty,
            "unit_price": f"${(price * (1 - Decimal(str(settings.bulk_tier4_discount_percent)) / Decimal('100'))):.2f}",
            "discount_percent": settings.bulk_tier4_discount_percent,
            "badge": f"-{settings.bulk_tier4_discount_percent:g}% VIP 💎",
        },
    ]
    return tiers


def format_bulk_pricing_caption(unit_price: Decimal | float | int) -> str:
    """Format markdown text displaying wholesale volume discounts."""
    settings = get_settings()
    if not settings.bulk_pricing_enabled:
        return ""

    tiers = get_product_bulk_pricing(unit_price)
    if not tiers or len(tiers) <= 1:
        return ""

    lines = ["📉 *Wholesale Volume Pricing:*"]
    for t in tiers:
        if t["min_qty"] == 1:
            lines.append(f"• `1–{settings.bulk_tier1_min_qty - 1} pcs`: {t['unit_price']}/ea")
        elif t["min_qty"] == settings.bulk_tier1_min_qty:
            lines.append(f"• `{settings.bulk_tier1_min_qty}–{settings.bulk_tier2_min_qty - 1} pcs`: {t['unit_price']}/ea *({t['badge']})*")
        elif t["min_qty"] == settings.bulk_tier2_min_qty:
            lines.append(f"• `{settings.bulk_tier2_min_qty}–{settings.bulk_tier3_min_qty - 1} pcs`: {t['unit_price']}/ea *({t['badge']})*")
        elif t["min_qty"] == settings.bulk_tier3_min_qty:
            lines.append(f"• `{settings.bulk_tier3_min_qty}–{settings.bulk_tier4_min_qty - 1} pcs`: {t['unit_price']}/ea *({t['badge']})*")
        else:
            lines.append(f"• `{settings.bulk_tier4_min_qty}+ pcs`: {t['unit_price']}/ea *({t['badge']})*")

    return "\n".join(lines)
