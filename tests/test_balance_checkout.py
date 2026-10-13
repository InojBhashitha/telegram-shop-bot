"""Tests for bot 0-second balance checkout and top-up UI."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import orders as orders_handler
from app.bot.keyboards.orders import order_detail_keyboard, payment_keyboard
from app.database.models import OrderStatus
from app.services import order_service


def test_payment_keyboard_with_balance():
    """Test payment keyboard contains instant balance payment button when balance is provided."""
    kb = payment_keyboard(
        payment_url="https://pay.example.com",
        order_id=42,
        user_balance=Decimal("25.50"),
    )
    # Check first row has balance payment button
    first_btn = kb.inline_keyboard[0][0]
    assert "⚡ Pay with Store Balance ($25.50)" in first_btn.text
    assert first_btn.callback_data == "pay_balance:42"

    # Second row has crypto payment url
    second_btn = kb.inline_keyboard[1][0]
    assert second_btn.url == "https://pay.example.com"


def test_payment_keyboard_without_balance():
    """Test payment keyboard does not include balance button if user_balance is None."""
    kb = payment_keyboard(
        payment_url="https://pay.example.com",
        order_id=42,
        user_balance=None,
    )
    first_btn = kb.inline_keyboard[0][0]
    assert first_btn.url == "https://pay.example.com"


def test_order_detail_keyboard_pending_balance():
    """Test order detail keyboard includes balance payment button when pending."""
    mock_order = MagicMock()
    mock_order.id = 99
    mock_order.status = OrderStatus.PENDING_PAYMENT
    mock_order.warranty_expires_at = None

    kb = order_detail_keyboard(mock_order, user_balance=Decimal("15.00"))
    balance_btn = kb.inline_keyboard[0][0]
    assert "⚡ Pay with Store Balance ($15.00)" in balance_btn.text
    assert balance_btn.callback_data == "pay_balance:99"


@pytest.mark.asyncio
async def test_pay_balance_callback_insufficient(session: AsyncSession, sample_data: dict):
    """Test paying with insufficient balance displays shortfall and top-up option."""
    user = sample_data["user"]
    product = sample_data["product"]
    user.balance = Decimal("2.00")
    await session.flush()

    order_res = await order_service.create_order(
        session, user_id=user.id, product_id=product.id, quantity=1
    )
    order = order_res["order"]
    assert order.amount == Decimal("4.50")

    # Mock Telegram Update & CallbackQuery
    query = MagicMock()
    query.data = f"pay_balance:{order.id}"
    query.from_user.id = user.telegram_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    context = MagicMock()

    with patch("app.bot.handlers.orders.get_session") as mock_get_sess:
        mock_get_sess.return_value.__aenter__.return_value = session
        await orders_handler.pay_balance_callback(update, context)

    # Verify message says insufficient balance
    query.edit_message_text.assert_called_once()
    call_args = query.edit_message_text.call_args[0][0]
    assert "Insufficient Store Balance" in call_args
    assert "Shortfall: `$2.50`" in call_args

    # Check topup button is present in reply markup
    reply_markup = query.edit_message_text.call_args[1]["reply_markup"]
    btn_callbacks = [btn.callback_data for row in reply_markup.inline_keyboard for btn in row]
    assert "topup" in btn_callbacks


@pytest.mark.asyncio
async def test_pay_balance_callback_success(session: AsyncSession, sample_data: dict):
    """Test successful 0-second balance payment debits balance and fulfills order."""
    user = sample_data["user"]
    product = sample_data["product"]
    user.balance = Decimal("20.00")
    await session.flush()

    order_res = await order_service.create_order(
        session, user_id=user.id, product_id=product.id, quantity=1
    )
    order = order_res["order"]
    assert order.amount == Decimal("4.50")
    assert order.status == OrderStatus.PENDING_PAYMENT

    query = MagicMock()
    query.data = f"pay_balance:{order.id}"
    query.from_user.id = user.telegram_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    context = MagicMock()

    with patch("app.bot.handlers.orders.get_session") as mock_get_sess, \
         patch("app.services.delivery_service.deliver_order_if_fulfilled", new_callable=AsyncMock) as mock_deliver:
        mock_get_sess.return_value.__aenter__.return_value = session
        await orders_handler.pay_balance_callback(update, context)

    # Verify debit
    await session.refresh(user)
    assert user.balance == Decimal("15.50")

    # Verify order is fulfilled
    await session.refresh(order)
    assert order.status == OrderStatus.FULFILLED

    # Verify delivery hook called
    mock_deliver.assert_called_once()

    # Verify Telegram edit message confirmed 0-second checkout
    query.edit_message_text.assert_called_once()
    call_text = query.edit_message_text.call_args[0][0]
    assert "0-Second Balance Checkout Complete!" in call_text
    assert "Remaining Balance: `$15.50`" in call_text
