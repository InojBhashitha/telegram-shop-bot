"""Tests for stock alerts and restock notification dispatch."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Product, User
from app.services import stock_alert_service


@pytest.mark.asyncio
async def test_create_and_idempotent_stock_alert(session: AsyncSession, sample_data: dict):
    """Subscribing to out of stock alert works and is idempotent."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Subscribe once
    alert1 = await stock_alert_service.subscribe_stock_alert(session, user.id, product.id)
    await session.commit()
    assert alert1.id is not None
    assert alert1.notified_at is None

    # Subscribe second time
    alert2 = await stock_alert_service.subscribe_stock_alert(session, user.id, product.id)
    assert alert1.id == alert2.id


@pytest.mark.asyncio
async def test_notify_restocked_product(session: AsyncSession, sample_data: dict):
    """When a product is restocked, pending subscribers receive DM and are marked notified."""
    user = sample_data["user"]
    product = sample_data["product"]

    await stock_alert_service.subscribe_stock_alert(session, user.id, product.id)
    await session.commit()

    # Mock Telegram bot
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()

    count = await stock_alert_service.notify_restocked_product(
        session, product.id, new_stock_count=5, bot=mock_bot
    )
    await session.commit()

    assert count == 1
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == user.telegram_id
    assert product.name in call_kwargs["text"]
    assert "restocked" in call_kwargs["text"].lower()

    # Second notification run finds 0 pending alerts
    count2 = await stock_alert_service.notify_restocked_product(
        session, product.id, new_stock_count=5, bot=mock_bot
    )
    assert count2 == 0
