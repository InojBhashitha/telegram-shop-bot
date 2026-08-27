"""Tests for database models and basic CRUD."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Category,
    InventoryStatus,
    Order,
    OrderStatus,
    Product,
    User,
)
from app.database.repositories import (
    category_repo,
    product_repo,
    user_repo,
)


@pytest.mark.asyncio
async def test_create_user(session: AsyncSession):
    """Test user creation and retrieval."""
    user = await user_repo.get_or_create_user(
        session, telegram_id=99999, username="newuser", first_name="New"
    )
    assert user.id is not None
    assert user.telegram_id == 99999
    assert user.username == "newuser"
    assert user.balance == Decimal("0.00")
    assert user.referral_code is not None


@pytest.mark.asyncio
async def test_get_or_create_user_idempotent(session: AsyncSession):
    """Test that get_or_create returns the same user on second call."""
    user1 = await user_repo.get_or_create_user(session, telegram_id=88888)
    user2 = await user_repo.get_or_create_user(session, telegram_id=88888)
    assert user1.id == user2.id


@pytest.mark.asyncio
async def test_create_category(session: AsyncSession):
    """Test category creation."""
    cat = await category_repo.create(
        session, name="Digital", description="Digital products", icon="💻"
    )
    assert cat.id is not None
    assert cat.name == "Digital"
    assert cat.active is True


@pytest.mark.asyncio
async def test_list_active_categories(session: AsyncSession):
    """Test listing active categories."""
    await category_repo.create(session, name="Active Cat")
    cat2 = await category_repo.create(session, name="Inactive Cat")
    await category_repo.deactivate(session, cat2.id)

    active = await category_repo.list_active(session)
    names = [c.name for c in active]
    assert "Active Cat" in names
    assert "Inactive Cat" not in names


@pytest.mark.asyncio
async def test_create_product(session: AsyncSession):
    """Test product creation."""
    cat = await category_repo.create(session, name="Test")
    prod = await product_repo.create(
        session,
        category_id=cat.id,
        name="Test Product",
        price=Decimal("9.99"),
    )
    assert prod.id is not None
    assert prod.price == Decimal("9.99")
    assert prod.active is True


@pytest.mark.asyncio
async def test_product_stock_count(session: AsyncSession, sample_data: dict):
    """Test stock counting for products."""
    product = sample_data["product"]
    stock = await product_repo.get_stock_count(session, product.id)
    assert stock == 3  # 3 items created in sample_data


@pytest.mark.asyncio
async def test_user_balance_operations(session: AsyncSession):
    """Test balance credit and debit."""
    user = await user_repo.get_or_create_user(session, telegram_id=77777)
    assert user.balance == Decimal("0.00")

    user = await user_repo.update_balance(session, user.id, Decimal("50.00"))
    assert user.balance == Decimal("50.00")

    user = await user_repo.update_balance(session, user.id, Decimal("-20.00"))
    assert user.balance == Decimal("30.00")

    with pytest.raises(ValueError, match="Insufficient balance"):
        await user_repo.update_balance(session, user.id, Decimal("-100.00"))
