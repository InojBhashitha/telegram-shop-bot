"""Tests for 10% first-order channel member discount system."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory, InventoryStatus, Product
from app.database.repositories import user_repo
from app.services import cart_service, order_service


@pytest.mark.asyncio
async def test_channel_discount_applied_first_order(session: AsyncSession, sample_data: dict):
    """Test that a claimed channel discount applies 10% off to the first order."""
    user = sample_data["user"]
    product = sample_data["product"]  # price 4.50

    # User claims discount
    user.channel_discount_claimed = True
    user.channel_discount_used = False
    await session.flush()

    # Buy 2 items ($9.00 subtotal)
    res = await order_service.create_order(session, user.id, product.id, quantity=2)
    order = res["order"]

    # 10% of 9.00 = 0.90
    assert order.discount_amount == Decimal("0.90")
    assert order.amount == Decimal("8.10")  # 9.00 - 0.90

    # Verify user state
    db_user = await user_repo.get_by_id(session, user.id)
    assert db_user.channel_discount_used is True


@pytest.mark.asyncio
async def test_channel_discount_capped_at_10_dollars(session: AsyncSession, sample_data: dict):
    """Test that discount is capped at a maximum of $10.00."""
    user = sample_data["user"]

    # Create expensive product ($150.00)
    p_expensive = Product(
        category_id=sample_data["category"].id,
        name="Enterprise Bundle",
        price=Decimal("150.00"),
        currency="USD",
        active=True,
    )
    session.add(p_expensive)
    await session.flush()

    session.add(Inventory(product_id=p_expensive.id, content="EXP-01", status=InventoryStatus.AVAILABLE))
    await session.flush()

    user.channel_discount_claimed = True
    user.channel_discount_used = False
    await session.flush()

    res = await order_service.create_order(session, user.id, p_expensive.id, quantity=1)
    order = res["order"]

    # 10% of 150.00 is $15.00, but cap is $10.00
    assert order.discount_amount == Decimal("10.00")
    assert order.amount == Decimal("140.00")  # 150.00 - 10.00


@pytest.mark.asyncio
async def test_second_order_does_not_get_discount(session: AsyncSession, sample_data: dict):
    """Test that discount only applies to the first order."""
    user = sample_data["user"]
    product = sample_data["product"]

    user.channel_discount_claimed = True
    user.channel_discount_used = False
    await session.flush()

    # First order gets discount
    r1 = await order_service.create_order(session, user.id, product.id, quantity=1)
    assert r1["order"].discount_amount == Decimal("0.45")

    # Second order gets NO discount
    r2 = await order_service.create_order(session, user.id, product.id, quantity=1)
    assert r2["order"].discount_amount == Decimal("0.00")
    assert r2["order"].amount == Decimal("4.50")


@pytest.mark.asyncio
async def test_cancelling_order_restores_discount(session: AsyncSession, sample_data: dict):
    """Test that cancelling an unpaid order restores first-order discount eligibility."""
    user = sample_data["user"]
    product = sample_data["product"]

    user.channel_discount_claimed = True
    user.channel_discount_used = False
    await session.flush()

    # Create order
    r1 = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = r1["order"]
    assert order.discount_amount == Decimal("0.45")

    db_user = await user_repo.get_by_id(session, user.id)
    assert db_user.channel_discount_used is True

    # Cancel order
    await order_service.cancel_order(session, order.id)

    # Discount should be restored
    db_user = await user_repo.get_by_id(session, user.id)
    assert db_user.channel_discount_used is False

    # Next order can use the discount again
    r2 = await order_service.create_order(session, user.id, product.id, quantity=1)
    assert r2["order"].discount_amount == Decimal("0.45")


@pytest.mark.asyncio
async def test_cart_checkout_applies_channel_discount(session: AsyncSession, sample_data: dict):
    """Test that cart checkout applies the 10% discount on total cart subtotal."""
    user = sample_data["user"]
    p1 = sample_data["product"]  # price 4.50

    user.channel_discount_claimed = True
    user.channel_discount_used = False
    await session.flush()

    # Add 2 items to cart ($9.00 total)
    await cart_service.add_to_cart(session, user.id, p1.id, quantity=2)

    # Checkout cart
    checkout_res = await cart_service.checkout_cart(session, user.id)
    order = checkout_res["order"]

    assert order.discount_amount == Decimal("0.90")
    assert order.amount == Decimal("8.10")  # 9.00 - 0.90
