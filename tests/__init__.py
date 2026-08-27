"""Pytest fixtures for Cloud Deals tests."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override env for tests BEFORE importing app modules
os.environ["BOT_TOKEN"] = "test:token"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["ADMIN_TELEGRAM_IDS"] = "111111"
os.environ["NOWPAYMENTS_API_KEY"] = "test_api_key"
os.environ["NOWPAYMENTS_IPN_SECRET"] = "test_ipn_secret"

from app.database.models import Base


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session with fresh schema."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_data(session: AsyncSession) -> dict:
    """Create sample test data: user, category, product, inventory."""
    from app.database.models import Category, Inventory, InventoryStatus, Product, User

    user = User(telegram_id=12345, username="testuser", first_name="Test")
    session.add(user)

    category = Category(name="Test Category", icon="🧪", active=True)
    session.add(category)
    await session.flush()

    product = Product(
        category_id=category.id,
        name="Test Product",
        description="A test product",
        price=Decimal("4.50"),
        currency="USD",
        active=True,
    )
    session.add(product)
    await session.flush()

    items = []
    for i in range(3):
        item = Inventory(
            product_id=product.id,
            content=f"TEST-ITEM-{i:03d}",
            status=InventoryStatus.AVAILABLE,
        )
        session.add(item)
        items.append(item)

    await session.flush()

    return {
        "user": user,
        "category": category,
        "product": product,
        "inventory_items": items,
    }
