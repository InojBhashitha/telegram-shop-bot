"""Tests for Sales Analytics, Daily Digest, and CSV Data Exports."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.bot.handlers.admin import (
    admin_export_customers,
    admin_export_inventory,
    admin_export_orders,
    admin_send_digest_now,
    admin_stats,
)
from app.database.database import close_db, get_engine, get_session, init_db
from app.database.models import (
    Base,
    Category,
    Inventory,
    InventoryStatus,
    Order,
    OrderStatus,
    Product,
    TopUp,
    TopUpStatus,
    User,
)
from app.services import analytics_service, order_service


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_db()


@pytest_asyncio.fixture
async def sample_analytics_data():
    """Seed test database with users, products, orders, and topups for analytics testing."""
    async with get_session() as s:
        admin_user = User(telegram_id=111111, username="admin_user", first_name="Admin")
        customer1 = User(telegram_id=222001, username="buyer_one", first_name="Alice", balance=Decimal("15.00"))
        customer2 = User(telegram_id=222002, username="buyer_two", first_name="Bob", balance=Decimal("0.00"))
        s.add_all([admin_user, customer1, customer2])
        await s.flush()

        cat = Category(name="Streaming Subscriptions", icon="🎬", active=True)
        s.add(cat)
        await s.flush()

        prod_netflix = Product(
            category_id=cat.id,
            name="Netflix 4K UHD",
            description="Ultra HD 1-Month",
            price=Decimal("10.00"),
            currency="USD",
            active=True,
        )
        prod_vpn = Product(
            category_id=cat.id,
            name="NordVPN 1-Year",
            description="Fast secure VPN",
            price=Decimal("25.00"),
            currency="USD",
            active=True,
        )
        s.add_all([prod_netflix, prod_vpn])
        await s.flush()

        # Add 2 inventory items for Netflix (low stock alert <= 3)
        for i in range(2):
            inv = Inventory(
                product_id=prod_netflix.id,
                content=f"netflix_acc_{i}:pass123",
                status=InventoryStatus.AVAILABLE,
            )
            s.add(inv)

        # VPN has 0 stock (out of stock alert)
        await s.flush()

        # Create paid order for customer1 (Netflix)
        order_res1 = await order_service.create_order(
            s, user_id=customer1.id, product_id=prod_netflix.id, quantity=1
        )
        order1 = order_res1["order"]
        await order_service.mark_paid(s, order1.id)
        await order_service.fulfill_order(s, order1.id)

        # Create paid topup for customer2 ($50.00)
        topup = TopUp(
            user_id=customer2.id,
            amount=Decimal("50.00"),
            currency="USD",
            status=TopUpStatus.PAID,
            provider="cryptopay",
            provider_invoice_id="inv_test_999",
        )
        s.add(topup)
        await s.flush()

        return {
            "admin": admin_user,
            "customer1": customer1,
            "customer2": customer2,
            "prod_netflix": prod_netflix,
            "prod_vpn": prod_vpn,
            "order": order1,
        }


class TestAnalyticsService:
    """Test analytics aggregation, message formatting, and CSV exports."""

    @pytest.mark.asyncio
    async def test_get_analytics_summary(self, sample_analytics_data):
        async with get_session() as s:
            summary = await analytics_service.get_analytics_summary(s, hours=24)

            assert summary["revenue"] == Decimal("10.00")
            assert summary["completed_orders"] == 1
            assert summary["new_users"] >= 3
            assert summary["topup_revenue"] == Decimal("50.00")
            assert summary["topup_count"] == 1

            # Top products
            assert len(summary["top_products"]) == 1
            assert summary["top_products"][0]["name"] == "Netflix 4K UHD"
            assert summary["top_products"][0]["units"] == 1
            assert summary["top_products"][0]["revenue"] == Decimal("10.00")

            # Low stock products (Netflix has 1 remaining available, VPN has 0)
            low_stocks = {item["name"]: item["available"] for item in summary["low_stock_products"]}
            assert "Netflix 4K UHD" in low_stocks
            assert "NordVPN 1-Year" in low_stocks
            assert low_stocks["NordVPN 1-Year"] == 0

    @pytest.mark.asyncio
    async def test_format_digest_message(self, sample_analytics_data):
        async with get_session() as s:
            summary = await analytics_service.get_analytics_summary(s, hours=24)
            msg = analytics_service.format_digest_message(summary, hours=24)

            assert "Daily Sales Digest" in msg
            assert "$10.00" in msg
            assert "Completed Orders" in msg
            assert "Netflix 4K UHD" in msg
            assert "OUT OF STOCK" in msg or "only" in msg
            assert "All-Time Store Totals" in msg

    @pytest.mark.asyncio
    async def test_send_digest_to_admins(self, sample_analytics_data):
        mock_bot = AsyncMock()
        async with get_session() as s:
            sent_count = await analytics_service.send_digest_to_admins(s, bot=mock_bot, hours=24)

            assert sent_count >= 1
            assert mock_bot.send_message.called
            call_kwargs = mock_bot.send_message.call_args[1]
            assert call_kwargs["chat_id"] == 111111
            assert "Daily Sales Digest" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_export_orders_csv(self, sample_analytics_data):
        async with get_session() as s:
            csv_bytes = await analytics_service.export_orders_csv(s)

            content = csv_bytes.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            assert len(rows) >= 2  # Header + at least 1 order
            headers = rows[0]
            assert "Order ID" in headers
            assert "Telegram ID" in headers
            assert "Product Name" in headers
            assert "Amount ($)" in headers
            assert "Status" in headers

            # Check order row
            order_row = rows[1]
            assert "Netflix 4K UHD" in order_row
            assert "10.00" in order_row

    @pytest.mark.asyncio
    async def test_export_inventory_csv(self, sample_analytics_data):
        async with get_session() as s:
            csv_bytes = await analytics_service.export_inventory_csv(s)

            content = csv_bytes.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            assert len(rows) >= 3  # Header + 2 products
            headers = rows[0]
            assert "Product ID" in headers
            assert "Product Name" in headers
            assert "Available Stock" in headers
            assert "Sold Count" in headers

            prod_names = [r[2] for r in rows[1:]]
            assert "Netflix 4K UHD" in prod_names
            assert "NordVPN 1-Year" in prod_names

    @pytest.mark.asyncio
    async def test_export_customers_csv(self, sample_analytics_data):
        async with get_session() as s:
            csv_bytes = await analytics_service.export_customers_csv(s)

            content = csv_bytes.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            rows = list(reader)

            assert len(rows) >= 4  # Header + 3 users
            headers = rows[0]
            assert "User ID" in headers
            assert "Telegram ID" in headers
            assert "Username" in headers
            assert "Balance ($)" in headers
            assert "Total Spent ($)" in headers

            usernames = [r[2] for r in rows[1:]]
            assert "buyer_one" in usernames
            assert "buyer_two" in usernames


class TestAdminAnalyticsBotHandlers:
    """Test admin stats menu and on-demand CSV and digest callback triggers."""

    @pytest.mark.asyncio
    async def test_admin_stats_menu_renders_options(self, sample_analytics_data):
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 111111
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
        context = MagicMock()

        await admin_stats(update, context)

        assert query.edit_message_text.called
        call_kwargs = query.edit_message_text.call_args[1]
        text = query.edit_message_text.call_args[0][0]
        assert "Sales Analytics & Exports" in text
        assert "$10.00" in text

        # Check action buttons present
        kb = call_kwargs["reply_markup"]
        btn_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Export Orders" in t for t in btn_texts)
        assert any("Export Inventory" in t for t in btn_texts)
        assert any("Export Customers" in t for t in btn_texts)
        assert any("Send Daily Digest" in t for t in btn_texts)

    @pytest.mark.asyncio
    async def test_admin_export_orders_sends_document(self, sample_analytics_data):
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 111111
        query.answer = AsyncMock()
        update.callback_query = query

        context = MagicMock()
        context.bot.send_document = AsyncMock()

        await admin_export_orders(update, context)

        assert context.bot.send_document.called
        call_kwargs = context.bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 111111
        assert "orders_export_" in call_kwargs["filename"]
        assert call_kwargs["filename"].endswith(".csv")
        assert "Orders Export" in call_kwargs["caption"]

    @pytest.mark.asyncio
    async def test_admin_export_inventory_sends_document(self, sample_analytics_data):
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 111111
        query.answer = AsyncMock()
        update.callback_query = query

        context = MagicMock()
        context.bot.send_document = AsyncMock()

        await admin_export_inventory(update, context)

        assert context.bot.send_document.called
        call_kwargs = context.bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 111111
        assert "inventory_export_" in call_kwargs["filename"]
        assert call_kwargs["filename"].endswith(".csv")

    @pytest.mark.asyncio
    async def test_admin_export_customers_sends_document(self, sample_analytics_data):
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 111111
        query.answer = AsyncMock()
        update.callback_query = query

        context = MagicMock()
        context.bot.send_document = AsyncMock()

        await admin_export_customers(update, context)

        assert context.bot.send_document.called
        call_kwargs = context.bot.send_document.call_args[1]
        assert call_kwargs["chat_id"] == 111111
        assert "customers_export_" in call_kwargs["filename"]
        assert call_kwargs["filename"].endswith(".csv")

    @pytest.mark.asyncio
    async def test_admin_send_digest_now_sends_message(self, sample_analytics_data):
        update = MagicMock()
        query = MagicMock()
        query.from_user.id = 111111
        query.answer = AsyncMock()
        update.callback_query = query

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        await admin_send_digest_now(update, context)

        assert context.bot.send_message.called
        call_kwargs = context.bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 111111
        assert "Daily Sales Digest" in call_kwargs["text"]
