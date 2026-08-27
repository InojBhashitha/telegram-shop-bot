"""Tests for order creation, fulfillment, and lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import InventoryStatus, OrderStatus
from app.database.repositories import inventory_repo, order_repo
from app.services import order_service


@pytest.mark.asyncio
async def test_create_order(session: AsyncSession, sample_data: dict):
    """Test order creation with inventory reservation."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id)
    order = result["order"]
    inv = result["inventory_item"]

    assert order.public_order_id.startswith("CD-")
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.amount == Decimal("4.50")
    assert order.inventory_id == inv.id
    assert inv.status == InventoryStatus.RESERVED


@pytest.mark.asyncio
async def test_create_order_out_of_stock(session: AsyncSession, sample_data: dict):
    """Test that creating an order fails when out of stock."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Reserve all 3 items
    for _ in range(3):
        await order_service.create_order(session, user.id, product.id)

    # 4th should fail
    with pytest.raises(order_service.OrderError, match="Out of stock"):
        await order_service.create_order(session, user.id, product.id)


@pytest.mark.asyncio
async def test_cancel_order_releases_inventory(session: AsyncSession, sample_data: dict):
    """Test that cancelling an order releases its inventory."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id)
    order = result["order"]

    # Stock should be 2 after reservation
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 2

    await order_service.cancel_order(session, order.id)

    # Stock should be 3 again
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3

    # Order should be cancelled
    cancelled = await order_repo.get_by_id(session, order.id)
    assert cancelled.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_fulfill_order(session: AsyncSession, sample_data: dict):
    """Test order fulfillment."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id)
    order = result["order"]

    # Mark as paid first
    await order_service.mark_paid(session, order.id)

    # Fulfill
    fulfill_result = await order_service.fulfill_order(session, order.id)
    assert fulfill_result is not None
    assert fulfill_result["content"].startswith("TEST-ITEM-")
    assert fulfill_result["order"].status == OrderStatus.FULFILLED


@pytest.mark.asyncio
async def test_duplicate_fulfillment_prevented(session: AsyncSession, sample_data: dict):
    """Test that an order cannot be fulfilled twice."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id)
    order = result["order"]

    await order_service.mark_paid(session, order.id)
    await order_service.fulfill_order(session, order.id)

    # Second fulfillment should fail
    with pytest.raises(order_service.OrderError, match="Cannot fulfill"):
        await order_service.fulfill_order(session, order.id)


@pytest.mark.asyncio
async def test_order_public_id_unique(session: AsyncSession, sample_data: dict):
    """Test that order public IDs are unique."""
    user = sample_data["user"]
    product = sample_data["product"]

    r1 = await order_service.create_order(session, user.id, product.id)
    r2 = await order_service.create_order(session, user.id, product.id)

    assert r1["order"].public_order_id != r2["order"].public_order_id


@pytest.mark.asyncio
async def test_inactive_product_cannot_be_ordered(session: AsyncSession, sample_data: dict):
    """Test that inactive products cannot be ordered."""
    user = sample_data["user"]
    product = sample_data["product"]
    product.active = False
    await session.flush()

    with pytest.raises(order_service.OrderError, match="not available"):
        await order_service.create_order(session, user.id, product.id)


@pytest.mark.asyncio
async def test_expire_old_orders(session: AsyncSession, sample_data: dict):
    """Test order expiration releases inventory."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id)

    # Expire with very short timeout (0 minutes = expire everything)
    expired = await order_service.expire_old_orders(session, expiry_minutes=0)
    assert expired == 1

    # Stock should be restored
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3
