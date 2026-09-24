"""Tests for Admin Bulk Inventory Upload (.txt file and text parsing)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from telegram import Document, Message, Update, User as TgUser
from telegram.ext import ConversationHandler

from app.bot.handlers.admin import ADD_STOCK_ITEMS, recv_stock_items
from app.database.database import close_db, get_engine, get_session, init_db
from app.database.models import Base
from app.database.repositories import inventory_repo
from app.services import stock_alert_service
from app.utils.crypto_vault import decrypt_content


from decimal import Decimal

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_db()


@pytest_asyncio.fixture
async def sample_test_data():
    """Seed test user and product in the active test database."""
    from app.database.models import Category, Product, User
    async with get_session() as s:
        user = User(telegram_id=12345, username="testuser", first_name="Test")
        s.add(user)
        cat = Category(name="Test Category", icon="🧪", active=True)
        s.add(cat)
        await s.flush()

        product = Product(
            category_id=cat.id,
            name="Test Product",
            description="A test product",
            price=Decimal("4.50"),
            currency="USD",
            active=True,
        )
        s.add(product)
        await s.flush()
        return {"user": user, "category": cat, "product": product}


def _make_update_with_text(text: str, user_id: int = 111111) -> Update:
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    user = MagicMock(spec=TgUser)
    user.id = user_id
    message.from_user = user
    message.text = text
    message.document = None
    message.reply_text = AsyncMock()
    update.message = message
    return update


def _make_update_with_document(
    file_bytes: bytes,
    file_name: str = "accounts.txt",
    user_id: int = 111111,
) -> Update:
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    user = MagicMock(spec=TgUser)
    user.id = user_id
    message.from_user = user
    message.text = None

    doc = MagicMock(spec=Document)
    doc.file_name = file_name
    doc.file_size = len(file_bytes)

    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(file_bytes))
    doc.get_file = AsyncMock(return_value=tg_file)

    message.document = doc
    message.reply_text = AsyncMock()
    update.message = message
    return update


class TestBulkInventoryUpload:
    """Test text and document parsing for bulk inventory restock."""

    @pytest.mark.asyncio
    async def test_bulk_add_stock_single_lines(self, sample_test_data):
        product = sample_test_data["product"]
        update = _make_update_with_text(
            "acc1@test.com:pass1\n"
            "acc2@test.com:pass2\n"
            "acc3@test.com:pass3\n"
        )
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = AsyncMock()

        res = await recv_stock_items(update, context)
        assert res == ConversationHandler.END

        # Verify added to database and encrypted
        async with get_session() as s:
            items = await inventory_repo.get_items_by_product_id(s, product.id)
            assert len(items) >= 3
            decrypted = [decrypt_content(it.content) for it in items]
            assert "acc1@test.com:pass1" in decrypted
            assert "acc2@test.com:pass2" in decrypted
            assert "acc3@test.com:pass3" in decrypted

        # Verify reply message contains summary
        call_args = update.message.reply_text.call_args[0][0]
        assert "+3" in call_args
        assert "Total In Stock" in call_args

    @pytest.mark.asyncio
    async def test_bulk_add_stock_multiline_blocks(self, sample_test_data):
        product = sample_test_data["product"]
        content = (
            "Email: user1@gmail.com\n"
            "Pass: secret123\n"
            "Pin: 9999\n"
            "---\n"
            "Email: user2@gmail.com\n"
            "Pass: secret456\n"
            "Pin: 8888\n"
        )
        update = _make_update_with_text(content)
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = AsyncMock()

        res = await recv_stock_items(update, context)
        assert res == ConversationHandler.END

        async with get_session() as s:
            items = await inventory_repo.get_items_by_product_id(s, product.id)
            decrypted = [decrypt_content(it.content) for it in items]
            assert any("user1@gmail.com" in d and "Pin: 9999" in d for d in decrypted)
            assert any("user2@gmail.com" in d and "Pin: 8888" in d for d in decrypted)

    @pytest.mark.asyncio
    async def test_bulk_add_stock_comments_and_deduplication(self, sample_test_data):
        product = sample_test_data["product"]
        content = (
            "# This is a comment line\n"
            "// Another comment line\n"
            "license_key_AAA\n"
            "license_key_BBB\n"
            "license_key_AAA\n"  # Duplicate
            "\n"  # Empty line
        )
        update = _make_update_with_text(content)
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = AsyncMock()

        res = await recv_stock_items(update, context)
        assert res == ConversationHandler.END

        call_args = update.message.reply_text.call_args[0][0]
        # 2 unique items added, 1 duplicate skipped
        assert "+2" in call_args
        assert "Duplicates Skipped" in call_args
        assert "1" in call_args

    @pytest.mark.asyncio
    async def test_bulk_add_stock_txt_document(self, sample_test_data):
        product = sample_test_data["product"]
        file_content = (
            "key1-xxxx-yyyy\n"
            "key2-xxxx-yyyy\n"
            "key3-xxxx-yyyy\n"
            "key4-xxxx-yyyy\n"
        ).encode("utf-8")

        update = _make_update_with_document(file_content, file_name="keys_batch.txt")
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = AsyncMock()

        res = await recv_stock_items(update, context)
        assert res == ConversationHandler.END

        call_args = update.message.reply_text.call_args[0][0]
        assert "keys_batch.txt" in call_args
        assert "+4" in call_args

        async with get_session() as s:
            items = await inventory_repo.get_items_by_product_id(s, product.id)
            decrypted = [decrypt_content(it.content) for it in items]
            assert "key1-xxxx-yyyy" in decrypted
            assert "key4-xxxx-yyyy" in decrypted

    @pytest.mark.asyncio
    async def test_bulk_add_stock_rejects_invalid_file_type(self, sample_test_data):
        product = sample_test_data["product"]
        update = _make_update_with_document(b"fake binary content", file_name="malicious.exe")
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = AsyncMock()

        res = await recv_stock_items(update, context)
        # Should stay in state and reply with invalid format error
        assert res == ADD_STOCK_ITEMS
        call_args = update.message.reply_text.call_args[0][0]
        assert "Invalid file format" in call_args

    @pytest.mark.asyncio
    async def test_bulk_add_stock_triggers_subscribers_alert(self, sample_test_data):
        product = sample_test_data["product"]
        user = sample_test_data["user"]

        # Subscribe user to restock alert
        async with get_session() as s:
            await stock_alert_service.subscribe_user(s, user.id, product.id)

        update = _make_update_with_text("new_netflix_account:pass123")
        mock_bot = AsyncMock()
        context = MagicMock()
        context.user_data = {"stock_product_id": product.id}
        context.bot = mock_bot

        res = await recv_stock_items(update, context)
        assert res == ConversationHandler.END

        # Bot should have sent restock alert to the subscribed user
        assert mock_bot.send_message.called
        call_kwargs = mock_bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == user.telegram_id
        assert "Stock Restocked" in call_kwargs["text"]
