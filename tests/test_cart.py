"""Tests for shopping cart system, custom quantity input, and multi-product cart checkout."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.cart import (
    cart_added_keyboard,
    cart_item_edit_keyboard,
    cart_manage_keyboard,
    cart_view_keyboard,
)
from app.database.models import Inventory, InventoryStatus, OrderStatus, Product
from app.database.repositories import cart_repo, inventory_repo
from app.services import cart_service


@pytest.mark.asyncio
async def test_add_to_cart_and_increment(session: AsyncSession, sample_data: dict):
    """Test adding items to cart and incrementing quantity."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Add 1 item
    res1 = await cart_service.add_to_cart(session, user.id, product.id, quantity=1)
    assert res1["cart_item"].quantity == 1
    assert res1["total_cart_items"] == 1

    # Add 1 more item
    res2 = await cart_service.add_to_cart(session, user.id, product.id, quantity=1)
    assert res2["cart_item"].quantity == 2
    assert res2["total_cart_items"] == 2


@pytest.mark.asyncio
async def test_add_to_cart_exceeds_stock_prevented(session: AsyncSession, sample_data: dict):
    """Test that adding more items than available in stock raises CartError."""
    user = sample_data["user"]
    product = sample_data["product"]  # has 3 items in sample_data

    # Adding 5 when only 3 available
    with pytest.raises(cart_service.CartError, match="Only 3 available"):
        await cart_service.add_to_cart(session, user.id, product.id, quantity=5)

    # Add 2 items first
    await cart_service.add_to_cart(session, user.id, product.id, quantity=2)

    # Trying to add 2 more (total 4 > 3 stock)
    with pytest.raises(cart_service.CartError, match="Cannot add 2 more"):
        await cart_service.add_to_cart(session, user.id, product.id, quantity=2)


@pytest.mark.asyncio
async def test_update_cart_quantity(session: AsyncSession, sample_data: dict):
    """Test updating cart quantity or removing item when set to 0."""
    user = sample_data["user"]
    product = sample_data["product"]

    await cart_service.add_to_cart(session, user.id, product.id, quantity=1)

    # Update to 3
    updated = await cart_service.update_cart_quantity(session, user.id, product.id, quantity=3)
    assert updated is not None
    assert updated.quantity == 3

    # Update to 0 removes the item
    res = await cart_service.update_cart_quantity(session, user.id, product.id, quantity=0)
    assert res is None
    count = await cart_repo.get_cart_item_count(session, user.id)
    assert count == 0


@pytest.mark.asyncio
async def test_remove_from_cart_and_clear(session: AsyncSession, sample_data: dict):
    """Test removing specific items and clearing the cart."""
    user = sample_data["user"]
    product = sample_data["product"]

    await cart_service.add_to_cart(session, user.id, product.id, quantity=2)
    assert await cart_repo.get_cart_item_count(session, user.id) == 2

    # Remove item
    removed = await cart_service.remove_from_cart(session, user.id, product.id)
    assert removed is True
    assert await cart_repo.get_cart_item_count(session, user.id) == 0

    # Add again and clear cart
    await cart_service.add_to_cart(session, user.id, product.id, quantity=1)
    cleared = await cart_service.clear_cart(session, user.id)
    assert cleared == 1
    assert await cart_repo.get_cart_item_count(session, user.id) == 0


@pytest.mark.asyncio
async def test_get_cart_summary(session: AsyncSession, sample_data: dict):
    """Test computing cart summary breakdown and totals."""
    user = sample_data["user"]
    p1 = sample_data["product"]  # price: 4.50

    # Create second product
    p2 = Product(
        category_id=sample_data["category"].id,
        name="Product Two",
        price=Decimal("10.00"),
        currency="USD",
        active=True,
    )
    session.add(p2)
    await session.flush()

    for i in range(2):
        session.add(Inventory(product_id=p2.id, content=f"P2-{i}", status=InventoryStatus.AVAILABLE))
    await session.flush()

    # Add 2 of p1 ($9.00) and 1 of p2 ($10.00)
    await cart_service.add_to_cart(session, user.id, p1.id, quantity=2)
    await cart_service.add_to_cart(session, user.id, p2.id, quantity=1)

    summary = await cart_service.get_cart_summary(session, user.id)
    assert summary["total_amount"] == Decimal("19.00")
    assert summary["total_count"] == 3
    assert summary["is_valid"] is True
    assert len(summary["items"]) == 2


@pytest.mark.asyncio
async def test_cart_checkout_multi_product(session: AsyncSession, sample_data: dict):
    """Test checking out cart with multiple distinct products creates master order and clears cart."""
    user = sample_data["user"]
    p1 = sample_data["product"]  # price: 4.50

    # Create second product
    p2 = Product(
        category_id=sample_data["category"].id,
        name="Product Two",
        price=Decimal("10.00"),
        currency="USD",
        active=True,
    )
    session.add(p2)
    await session.flush()

    for i in range(2):
        session.add(Inventory(product_id=p2.id, content=f"P2-{i}", status=InventoryStatus.AVAILABLE))
    await session.flush()

    # Add to cart
    await cart_service.add_to_cart(session, user.id, p1.id, quantity=2)
    await cart_service.add_to_cart(session, user.id, p2.id, quantity=1)

    # Checkout
    checkout_res = await cart_service.checkout_cart(session, user.id)
    order = checkout_res["order"]
    reserved_items = checkout_res["inventory_items"]

    assert order.public_order_id.startswith("CD-")
    assert order.amount == Decimal("19.00")
    assert order.quantity == 3
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert len(reserved_items) == 3

    # All items should be linked to this order
    for item in reserved_items:
        assert item.order_id == order.id
        assert item.status == InventoryStatus.RESERVED

    # Cart should be empty
    count = await cart_repo.get_cart_item_count(session, user.id)
    assert count == 0


@pytest.mark.asyncio
async def test_cart_checkout_empty_fails(session: AsyncSession, sample_data: dict):
    """Test checking out an empty cart raises CartError."""
    user = sample_data["user"]
    with pytest.raises(cart_service.CartError, match="empty"):
        await cart_service.checkout_cart(session, user.id)


def test_cart_keyboards():
    """Test cart keyboard button generation."""
    kb_empty = cart_view_keyboard(has_items=False)
    assert any("Browse Products" in btn.text for row in kb_empty.inline_keyboard for btn in row)

    kb_items = cart_view_keyboard(has_items=True, is_valid=True)
    assert any("Checkout with Crypto" in btn.text for row in kb_items.inline_keyboard for btn in row)
    assert any("Manage Items" in btn.text for row in kb_items.inline_keyboard for btn in row)

    kb_added = cart_added_keyboard(category_id=1)
    assert any("View Cart" in btn.text for row in kb_added.inline_keyboard for btn in row)
    assert any("Checkout Now" in btn.text for row in kb_added.inline_keyboard for btn in row)
