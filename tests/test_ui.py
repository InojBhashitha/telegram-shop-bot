"""Tests for UI utilities, stock progress bars, and product captions."""

from __future__ import annotations

from decimal import Decimal

from app.bot.utils.ui import format_product_caption, format_stock_bar


def test_format_stock_bar_high_stock():
    """Test stock bar for high stock level (>= 10)."""
    res = format_stock_bar(15)
    assert "🟢" in res
    assert "High Stock" in res
    assert "(15 left)" in res
    assert "██████████" in res


def test_format_stock_bar_medium_stock():
    """Test stock bar for medium stock level (4-9)."""
    res = format_stock_bar(6)
    assert "🟡" in res
    assert "Medium Stock" in res
    assert "(6 left)" in res
    assert "█████" in res


def test_format_stock_bar_low_stock():
    """Test stock bar for low stock level (1-3)."""
    res = format_stock_bar(2)
    assert "⚠️" in res
    assert "Low Stock" in res
    assert "(2 left)" in res


def test_format_stock_bar_sold_out():
    """Test stock bar for sold out stock level (0)."""
    res = format_stock_bar(0)
    assert "🔴" in res
    assert "Sold Out" in res


def test_format_product_caption():
    """Test format_product_caption outputs formatted card."""
    caption = format_product_caption(
        name="DigitalOcean $100 Credit",
        price=Decimal("15.00"),
        stock=12,
        description="60-day promotional credit code",
        currency="USD",
        warranty_hours=24,
    )
    assert "Cloud Deals" in caption
    assert "DigitalOcean $100 Credit" in caption
    assert "$15.00 USD" in caption
    assert "High Stock" in caption
    assert "24 Hours Auto-Replacement" in caption
    assert "60-day promotional credit code" in caption
