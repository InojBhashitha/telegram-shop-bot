"""Tests for Merchant Admin Suite API endpoints (/api/webapp/admin/*)."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.auth import create_access_token
from app.api.main import create_api
from app.database.database import close_db, get_session, init_db
from app.database.models import (
    Category,
    Coupon,
    CouponType,
    DeliveryType,
    Inventory,
    InventoryStatus,
    Order,
    OrderStatus,
    Product,
    StockAlert,
    User,
)
from app.services import user_service
from app.utils.crypto_vault import encrypt_content


@pytest_asyncio.fixture
async def admin_test_client():
    """Create a test client with initialized database and sample store data."""
    await init_db()
    from app.database.database import get_engine
    from app.database.models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    api = create_api()

    # Pre-seed test admin, customer, category, product, and stock
    async with get_session() as session:
        # Admin user (111111 is in ADMIN_TELEGRAM_IDS)
        admin_res = await user_service.get_or_create_user(
            session, telegram_id=111111, username="store_owner", first_name="Owner"
        )
        admin_user = admin_res["user"]

        # Regular customer user
        cust_res = await user_service.get_or_create_user(
            session, telegram_id=222222, username="regular_buyer", first_name="Buyer"
        )
        cust_user = cust_res["user"]
        cust_user.balance = Decimal("10.00")

        cat = Category(name="VPN Services", icon="🛡️", active=True)
        session.add(cat)
        await session.flush()

        prod = Product(
            category_id=cat.id,
            name="NordVPN Premium 1Y",
            description="High speed VPN subscription key.",
            price=Decimal("15.00"),
            currency="USD",
            delivery_type=DeliveryType.DIGITAL,
            active=True,
        )
        session.add(prod)
        await session.flush()

        inv1 = Inventory(
            product_id=prod.id,
            content=encrypt_content("nord:user1:key12345"),
            status=InventoryStatus.AVAILABLE,
        )
        session.add(inv1)

        # Create a paid order
        order = Order(
            user_id=cust_user.id,
            product_id=prod.id,
            public_order_id="CD-TEST001",
            amount=Decimal("15.00"),
            currency="USD",
            status=OrderStatus.PAID,
        )
        session.add(order)
        await session.flush()

        inv_delivered = Inventory(
            product_id=prod.id,
            order_id=order.id,
            content=encrypt_content("nord:delivered:secret_pass"),
            status=InventoryStatus.SOLD,
        )
        session.add(inv_delivered)
        await session.commit()

    transport = ASGITransport(app=api)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await close_db()


@pytest.mark.asyncio
async def test_admin_analytics_access_control(admin_test_client: AsyncClient):
    """Test that non-admins are rejected with 403 and admins can access analytics."""
    # 1. Non-admin request
    res_non_admin = await admin_test_client.get(
        "/api/webapp/admin/analytics",
        headers={"X-Dev-Telegram-Id": "222222"},
    )
    assert res_non_admin.status_code == 403
    assert "Administrative privileges required" in res_non_admin.json()["detail"]

    # 2. Admin request using dev header
    res_admin = await admin_test_client.get(
        "/api/webapp/admin/analytics",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "overview" in data
    assert "top_products" in data
    assert "low_stock_alerts" in data
    assert data["overview"]["active_products"] >= 1


@pytest.mark.asyncio
async def test_admin_jwt_authentication(admin_test_client: AsyncClient):
    """Test authenticating to admin portal using signed JWT Bearer token."""
    token = create_access_token(user_id=1, telegram_id=111111, is_admin=True)

    res = await admin_test_client.get(
        "/api/webapp/admin/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["overview"]["total_available_stock"] >= 1


@pytest.mark.asyncio
async def test_admin_list_and_create_products(admin_test_client: AsyncClient):
    """Test listing products and creating a new product with initial stock."""
    # List products
    res_list = await admin_test_client.get(
        "/api/webapp/admin/products",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_list.status_code == 200
    data = res_list.json()
    assert len(data["products"]) >= 1
    assert len(data["categories"]) >= 1
    cat_id = data["categories"][0]["id"]

    # Create new product with seed stock
    res_create = await admin_test_client.post(
        "/api/webapp/admin/products",
        headers={"X-Dev-Telegram-Id": "111111"},
        json={
            "category_id": cat_id,
            "name": "ExpressVPN 1 Year Key",
            "price": 24.99,
            "description": "Premium tier VPN",
            "initial_stock": "express:key1\nexpress:key2\nexpress:key3",
            "active": True,
        },
    )
    assert res_create.status_code == 200
    create_data = res_create.json()
    assert create_data["success"] is True
    assert create_data["initial_stock"] == 3
    new_pid = create_data["product_id"]

    # Toggle product visibility
    res_toggle = await admin_test_client.patch(
        f"/api/webapp/admin/products/{new_pid}/toggle",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_toggle.status_code == 200
    assert res_toggle.json()["active"] is False


@pytest.mark.asyncio
async def test_admin_restock_and_stock_alert_notification(admin_test_client: AsyncClient):
    """Test restocking credentials to a product and clearing customer stock alerts."""
    # Get product ID
    res_list = await admin_test_client.get(
        "/api/webapp/admin/products",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    pid = res_list.json()["products"][0]["id"]

    # Add a stock alert for customer
    async with get_session() as session:
        cust = (await session.execute(User.__table__.select().where(User.telegram_id == 222222))).first()
        assert cust is not None
        alert = StockAlert(user_id=cust.id, product_id=pid)
        session.add(alert)
        await session.commit()

    # Admin restocks credentials
    res_restock = await admin_test_client.post(
        "/api/webapp/admin/products/stock",
        headers={"X-Dev-Telegram-Id": "111111"},
        json={
            "product_id": pid,
            "content": "key_fresh_101\nkey_fresh_102",
        },
    )
    assert res_restock.status_code == 200
    restock_data = res_restock.json()
    assert restock_data["success"] is True
    assert restock_data["added_count"] == 2
    assert restock_data["subscribers_notified"] == 1


@pytest.mark.asyncio
async def test_admin_coupons_lifecycle(admin_test_client: AsyncClient):
    """Test creating, listing, and deleting promo codes."""
    # 1. Create coupon
    res_create = await admin_test_client.post(
        "/api/webapp/admin/coupons",
        headers={"X-Dev-Telegram-Id": "111111"},
        json={
            "code": "CYBER50",
            "discount_type": "percent",
            "discount_value": 50.0,
            "max_uses": 100,
            "expires_in_days": 14,
        },
    )
    assert res_create.status_code == 200
    c_id = res_create.json()["coupon"]["id"]

    # 2. List coupons
    res_list = await admin_test_client.get(
        "/api/webapp/admin/coupons",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_list.status_code == 200
    coupons = res_list.json()["coupons"]
    assert any(c["code"] == "CYBER50" for c in coupons)

    # 3. Delete coupon
    res_del = await admin_test_client.delete(
        f"/api/webapp/admin/coupons/{c_id}",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True


@pytest.mark.asyncio
async def test_admin_order_vault_and_refund(admin_test_client: AsyncClient):
    """Test order vault inspection and 1-click customer support balance refund."""
    # 1. Inspect orders
    res_orders = await admin_test_client.get(
        "/api/webapp/admin/orders",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_orders.status_code == 200
    orders = res_orders.json()["orders"]
    assert len(orders) >= 1

    target_order = orders[0]
    order_id = target_order["id"]
    # Check that delivered credentials was decrypted properly in vault view
    assert "nord:delivered:secret_pass" in target_order["delivered_credentials"]

    # 2. Refund order
    res_refund = await admin_test_client.post(
        f"/api/webapp/admin/orders/{order_id}/refund",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_refund.status_code == 200
    refund_data = res_refund.json()
    assert refund_data["success"] is True
    # Customer initial balance was 10.00 + 15.00 refund = 25.00
    assert refund_data["new_balance"] == 25.0

    # 3. Double refund attempt fails
    res_double = await admin_test_client.post(
        f"/api/webapp/admin/orders/{order_id}/refund",
        headers={"X-Dev-Telegram-Id": "111111"},
    )
    assert res_double.status_code == 400
    assert "already been refunded" in res_double.json()["detail"]


@pytest.mark.asyncio
async def test_admin_broadcast_announcement(admin_test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Test dispatching broadcast announcements to registered customers."""
    from unittest.mock import AsyncMock, MagicMock

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)

    monkeypatch.setattr("app.bot.bot.get_bot_instance", lambda: mock_bot)

    res_broadcast = await admin_test_client.post(
        "/api/webapp/admin/broadcast",
        headers={"X-Dev-Telegram-Id": "111111"},
        json={"message": "🔥 Flash Sale! Use code FLASH20 for 20% off all items!"},
    )
    assert res_broadcast.status_code == 200
    data = res_broadcast.json()
    assert data["success"] is True
    assert data["sent_count"] >= 1
    assert mock_bot.send_message.called

