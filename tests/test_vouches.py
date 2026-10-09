"""Tests for automated public vouch and purchase proof broadcasting."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Order, OrderStatus, Payment, PaymentStatus, Product, User
from app.services import order_service, vouch_service
from app.services.vouch_service import anonymize_buyer, format_payment_badge


def test_anonymize_buyer():
    """Verify buyer details are properly anonymized for customer privacy."""
    # Username formatting
    u1 = MagicMock(spec=User)
    u1.username = "alex_smith"
    u1.first_name = "Alex"
    u1.telegram_id = 123456789
    assert anonymize_buyer(u1) == "@a***h"

    # Short username
    u2 = MagicMock(spec=User)
    u2.username = "jo"
    u2.first_name = "Joe"
    u2.telegram_id = 123456789
    assert anonymize_buyer(u2) == "@j*"

    # First name fallback
    u3 = MagicMock(spec=User)
    u3.username = None
    u3.first_name = "Samantha"
    u3.telegram_id = 123456789
    assert anonymize_buyer(u3) == "Sa*** (Verified Customer)"

    # Telegram ID fallback
    u4 = MagicMock(spec=User)
    u4.username = None
    u4.first_name = None
    u4.telegram_id = 987654321
    assert anonymize_buyer(u4) == "Customer #4321"

    # None user
    assert anonymize_buyer(None) == "Verified Customer"


def test_format_payment_badge():
    """Verify payment badges are formatted with provider and asset."""
    p_crypto = MagicMock(spec=Payment)
    p_crypto.provider = "cryptopay"
    p_crypto.payment_currency = "USDT"
    assert format_payment_badge(p_crypto) == "✅ Crypto Pay @CryptoBot (USDT)"

    p_binance = MagicMock(spec=Payment)
    p_binance.provider = "binancepay"
    p_binance.payment_currency = "BUSD"
    assert format_payment_badge(p_binance) == "✅ Binance Pay (BUSD)"

    p_stars = MagicMock(spec=Payment)
    p_stars.provider = "stars"
    p_stars.payment_currency = None
    assert format_payment_badge(p_stars) == "⭐️ Telegram Stars"

    assert format_payment_badge(None) == "✅ Verified Automated Payment"


@pytest.mark.asyncio
async def test_post_order_vouch_no_channel(session: AsyncSession, sample_data: dict, monkeypatch):
    """Gracefully returns False when no vouch channel is configured."""
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "vouch_channel_id", "")

    user = sample_data["user"]
    product = sample_data["product"]

    order_res = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order = order_res["order"]

    mock_bot = MagicMock()
    success, msg = await vouch_service.post_order_vouch_to_channel(
        bot=mock_bot,
        session=session,
        order=order,
        channel_id=None,
    )

    assert success is False
    assert "No vouch channel configured" in msg


@pytest.mark.asyncio
async def test_post_order_vouch_success(session: AsyncSession, sample_data: dict):
    """Successfully broadcasts automated verified purchase proof to public channel."""
    user = sample_data["user"]
    product = sample_data["product"]

    order_res = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order = order_res["order"]
    await order_service.order_repo.update_status(session, order.id, OrderStatus.PAID)
    await order_service.fulfill_order(session, order.id)
    await session.commit()

    mock_bot = MagicMock()
    mock_bot.username = "CloudDealsBot"
    mock_bot.send_message = AsyncMock()
    mock_bot.send_photo = AsyncMock()

    success, msg = await vouch_service.post_order_vouch_to_channel(
        bot=mock_bot,
        session=session,
        order=order,
        channel_id="@CloudDealsVouches",
    )

    assert success is True
    assert "Published to @CloudDealsVouches" in msg

    called_method = mock_bot.send_photo if mock_bot.send_photo.called else mock_bot.send_message
    assert called_method.called
    kwargs = called_method.call_args.kwargs
    assert kwargs["chat_id"] == "@CloudDealsVouches"

    caption_or_text = kwargs.get("caption") or kwargs.get("text")
    assert caption_or_text is not None

    # Check that it's a verified purchase proof WITHOUT star rating
    assert "VERIFIED PURCHASE PROOF" in caption_or_text
    assert product.name in caption_or_text
    assert f"${order.amount:.2f}" in caption_or_text
    assert "Instant Automated Delivery" in caption_or_text
    # Ensure no star rating system is included
    assert "/5" not in caption_or_text
    assert "Rate your purchase" not in caption_or_text

    # Verify inline buttons (buy in bot & Mini App)
    reply_markup = kwargs["reply_markup"]
    buttons = reply_markup.inline_keyboard
    buy_btn = buttons[0][0]
    assert f"start=prod_{product.id}" in buy_btn.url
    store_btn = buttons[1][0]
    assert "webapp" in store_btn.url.lower()
