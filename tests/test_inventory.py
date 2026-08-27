"""Tests for inventory reservation and concurrency protection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory, InventoryStatus
from app.database.repositories import inventory_repo


@pytest.mark.asyncio
async def test_reserve_item(session: AsyncSession, sample_data: dict):
    """Test that reserve_item returns an item and marks it RESERVED."""
    product = sample_data["product"]

    item = await inventory_repo.reserve_item(session, product.id)
    assert item is not None
    assert item.status == InventoryStatus.RESERVED
    assert item.reserved_at is not None


@pytest.mark.asyncio
async def test_reserve_reduces_stock(session: AsyncSession, sample_data: dict):
    """Test that reserving items reduces available stock."""
    product = sample_data["product"]

    initial = await inventory_repo.get_stock_count(session, product.id)
    assert initial == 3

    await inventory_repo.reserve_item(session, product.id)
    remaining = await inventory_repo.get_stock_count(session, product.id)
    assert remaining == 2


@pytest.mark.asyncio
async def test_reserve_all_items(session: AsyncSession, sample_data: dict):
    """Test reserving all items returns None when exhausted."""
    product = sample_data["product"]

    for _ in range(3):
        item = await inventory_repo.reserve_item(session, product.id)
        assert item is not None

    # No more stock
    item = await inventory_repo.reserve_item(session, product.id)
    assert item is None


@pytest.mark.asyncio
async def test_release_item(session: AsyncSession, sample_data: dict):
    """Test releasing a reserved item makes it available again."""
    product = sample_data["product"]

    item = await inventory_repo.reserve_item(session, product.id)
    assert item is not None

    await inventory_repo.release_item(session, item.id)

    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3  # All 3 available again


@pytest.mark.asyncio
async def test_mark_sold(session: AsyncSession, sample_data: dict):
    """Test marking an item as sold."""
    product = sample_data["product"]

    item = await inventory_repo.reserve_item(session, product.id)
    await inventory_repo.mark_sold(session, item.id, order_id=1)

    updated = await inventory_repo.get_item_by_id(session, item.id)
    assert updated.status == InventoryStatus.SOLD
    assert updated.sold_at is not None


@pytest.mark.asyncio
async def test_sold_item_not_available(session: AsyncSession, sample_data: dict):
    """Test that sold items don't count as available stock."""
    product = sample_data["product"]

    item = await inventory_repo.reserve_item(session, product.id)
    await inventory_repo.mark_sold(session, item.id, order_id=1)

    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 2  # Only 2 of 3 remain


@pytest.mark.asyncio
async def test_release_expired_reservations(session: AsyncSession, sample_data: dict):
    """Test that expired reservations are released."""
    product = sample_data["product"]

    item = await inventory_repo.reserve_item(session, product.id)
    assert item is not None

    # Backdate the reservation
    old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
    stmt = (
        update(Inventory)
        .where(Inventory.id == item.id)
        .values(reserved_at=old_time)
    )
    await session.execute(stmt)

    released = await inventory_repo.release_expired_reservations(session, expiry_minutes=30)
    assert released == 1

    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3


@pytest.mark.asyncio
async def test_stock_summary(session: AsyncSession, sample_data: dict):
    """Test stock summary by status."""
    product = sample_data["product"]

    await inventory_repo.reserve_item(session, product.id)
    summary = await inventory_repo.get_stock_summary(session, product.id)

    assert summary["available"] == 2
    assert summary["reserved"] == 1
    assert summary["sold"] == 0
