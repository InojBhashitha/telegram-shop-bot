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


@pytest.mark.asyncio
async def test_post_restock_to_channel_success(session: AsyncSession, sample_data: dict):
    """Test broadcasting restock announcement to public channel."""
    product = sample_data["product"]

    mock_bot = MagicMock()
    mock_bot.username = "CloudDealsBot"
    mock_bot.send_message = AsyncMock()
    mock_bot.send_photo = AsyncMock()

    success, msg = await stock_alert_service.post_restock_to_channel(
        bot=mock_bot,
        session=session,
        product_id=product.id,
        added_count=5,
        channel_id="@TestRestockChannel",
    )

    assert success is True
    assert "Published to @TestRestockChannel" in msg

    # Either send_photo or send_message was called
    called_method = mock_bot.send_photo if mock_bot.send_photo.called else mock_bot.send_message
    assert called_method.called
    kwargs = called_method.call_args.kwargs
    assert kwargs["chat_id"] == "@TestRestockChannel"
    caption_or_text = kwargs.get("caption") or kwargs.get("text")
    assert product.name in caption_or_text
    assert "+5 accounts" in caption_or_text
    assert "RESTOCK ALERT" in caption_or_text

    # Verify buttons
    reply_markup = kwargs["reply_markup"]
    buttons = reply_markup.inline_keyboard
    buy_button = buttons[0][0]
    assert f"start=prod_{product.id}" in buy_button.url


@pytest.mark.asyncio
async def test_post_restock_to_channel_no_channel(session: AsyncSession, sample_data: dict, monkeypatch):
    """When no channel is configured, returns False gracefully."""
    product = sample_data["product"]
    mock_bot = MagicMock()

    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "restock_channel_id", "")
    monkeypatch.setattr(settings, "force_channel_id", "")

    success, msg = await stock_alert_service.post_restock_to_channel(
        bot=mock_bot,
        session=session,
        product_id=product.id,
        added_count=2,
        channel_id=None,
    )

    assert success is False
    assert "No restock channel configured" in msg


@pytest.mark.asyncio
async def test_handle_restock_event_complete_pipeline(session: AsyncSession, sample_data: dict):
    """Test unified restock pipeline notifying private subscribers and public channel."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Subscribe user to product
    await stock_alert_service.subscribe_stock_alert(session, user.id, product.id)
    await session.commit()

    mock_bot = MagicMock()
    mock_bot.username = "CloudDealsBot"
    mock_bot.send_message = AsyncMock()
    mock_bot.send_photo = AsyncMock()

    result = await stock_alert_service.handle_restock_event(
        bot=mock_bot,
        session=session,
        product_id=product.id,
        added_count=10,
        channel_id="@RestockChannel",
    )

    assert result["product_id"] == product.id
    assert result["subscribers_notified"] == 1
    assert result["channel_posted"] is True

    # User received 1-on-1 DM
    mock_bot.send_message.assert_any_call(
        chat_id=user.telegram_id,
        text=mock_bot.send_message.call_args_list[0].kwargs["text"],
        reply_markup=mock_bot.send_message.call_args_list[0].kwargs["reply_markup"],
        parse_mode="Markdown",
    )
