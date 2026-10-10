"""Tests for credential export service (.txt and .csv file generation & delivery)."""

import csv
import io
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Inventory, InventoryStatus, Order, OrderStatus, Product, User
from app.services import credential_export_service, order_service
from app.services.credential_export_service import (
    generate_credentials_csv,
    generate_credentials_txt,
    parse_credential_fields,
)


def test_parse_credential_fields_multiline_kv():
    """Test parsing multi-line key:value credentials."""
    raw = "Email: user1@cloud.com\nPassword: secretPassword123!\nRecovery: backup@mail.com\nPIN: 4821"
    parsed = parse_credential_fields(raw)
    assert parsed["login"] == "user1@cloud.com"
    assert parsed["password"] == "secretPassword123!"
    assert "Recovery: backup@mail.com" in parsed["extra"]
    assert "Pin: 4821" in parsed["extra"]
    assert "user1@cloud.com:secretPassword123!" in parsed["combo"]


def test_parse_credential_fields_delimited():
    """Test parsing single line colon and pipe delimited combos."""
    raw_colon = "admin@site.org:pass1234:2FA_KEY_XYZ"
    parsed_colon = parse_credential_fields(raw_colon)
    assert parsed_colon["login"] == "admin@site.org"
    assert parsed_colon["password"] == "pass1234"
    assert parsed_colon["extra"] == "2FA_KEY_XYZ"
    assert parsed_colon["combo"] == raw_colon

    raw_pipe = "testuser | mypassword | token123"
    parsed_pipe = parse_credential_fields(raw_pipe)
    assert parsed_pipe["login"] == "testuser"
    assert parsed_pipe["password"] == "mypassword"
    assert parsed_pipe["extra"] == "token123"


def test_generate_credentials_txt():
    """Test generating structured .txt file with headers and raw combo section."""
    order = MagicMock(spec=Order)
    order.public_order_id = "CD9824AB"
    order.created_at = None
    order.product = MagicMock()
    order.product.name = "AWS $1000 Credit Account"

    items = [
        {"content": "user1@test.com:pass1:rec1", "product_name": "AWS $1000 Credit Account"},
        {"content": "user2@test.com:pass2:rec2", "product_name": "AWS $1000 Credit Account"},
    ]

    txt_bytes = generate_credentials_txt(order, items, store_name="Cloud Deals", warranty_hours=24)
    content = txt_bytes.decode("utf-8")

    assert "CLOUD DEALS — DIGITAL CREDENTIALS" in content
    assert "#CD9824AB" in content
    assert "Total Accounts:  2" in content
    assert "24 Hours Replacement Coverage" in content
    assert "[ACCOUNT #1]" in content
    assert "[ACCOUNT #2]" in content
    assert "RAW COMBO LIST" in content
    assert "user1@test.com:pass1:rec1" in content
    assert "user2@test.com:pass2:rec2" in content


def test_generate_credentials_csv():
    """Test generating standard RFC 4180 CSV export."""
    order = MagicMock(spec=Order)
    order.public_order_id = "CD9824AB"
    order.product = MagicMock()
    order.product.name = "AWS Account"

    items = [
        {"content": "user1@test.com:pass1:rec1", "product_name": "AWS Account"},
        {"content": "user2@test.com:pass2:rec2", "product_name": "AWS Account"},
    ]

    csv_bytes = generate_credentials_csv(order, items, store_name="Cloud Deals")
    reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8")))
    rows = list(reader)

    # Header row
    assert rows[0] == [
        "Account #",
        "Order ID",
        "Product Name",
        "Username / Email",
        "Password",
        "Additional Details",
        "Raw Credential String",
    ]

    # Data rows
    assert len(rows) == 3
    assert rows[1][0] == "1"
    assert rows[1][1] == "CD9824AB"
    assert rows[1][3] == "user1@test.com"
    assert rows[1][4] == "pass1"
    assert rows[1][5] == "rec1"

    assert rows[2][0] == "2"
    assert rows[2][3] == "user2@test.com"


@pytest.mark.asyncio
async def test_export_and_send_order_credentials_txt_and_csv(session: AsyncSession, sample_data: dict):
    """Test sending credentials document directly via Telegram bot."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Create and fulfill an order
    order_res = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order = order_res["order"]
    await order_service.order_repo.update_status(session, order.id, OrderStatus.PAID)
    await order_service.fulfill_order(session, order.id)
    await session.commit()

    mock_bot = MagicMock()
    mock_bot.send_document = AsyncMock()

    # 1. Export as .txt
    success_txt, filename_txt = await credential_export_service.export_and_send_order_credentials(
        bot=mock_bot,
        session=session,
        chat_id=user.telegram_id,
        order=order,
        file_format="txt",
    )

    assert success_txt is True
    assert filename_txt.endswith(".txt")
    mock_bot.send_document.assert_called_once()
    kwargs_txt = mock_bot.send_document.call_args.kwargs
    assert kwargs_txt["chat_id"] == user.telegram_id
    assert kwargs_txt["filename"] == filename_txt
    assert "Credentials File (.txt)" in kwargs_txt["caption"]

    # 2. Export as .csv
    mock_bot.reset_mock()
    success_csv, filename_csv = await credential_export_service.export_and_send_order_credentials(
        bot=mock_bot,
        session=session,
        chat_id=user.telegram_id,
        order=order,
        file_format="csv",
    )

    assert success_csv is True
    assert filename_csv.endswith(".csv")
    mock_bot.send_document.assert_called_once()
    kwargs_csv = mock_bot.send_document.call_args.kwargs
    assert kwargs_csv["chat_id"] == user.telegram_id
    assert kwargs_csv["filename"] == filename_csv
    assert "Accounts Export (.csv)" in kwargs_csv["caption"]
