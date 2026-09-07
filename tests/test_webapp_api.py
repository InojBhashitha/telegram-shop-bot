"""Tests for Telegram Mini App (TMA) API endpoints and initData validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import create_api
from app.api.webapp import validate_telegram_init_data
from app.database.database import close_db, get_session, init_db
from app.database.models import Category, Inventory, InventoryStatus, Product, User
from app.services import user_service


def make_telegram_init_data(user_dict: dict, bot_token: str, auth_date: int = 1700000000) -> str:
    """Helper to generate a valid Telegram WebApp initData query string."""
    user_str = json.dumps(user_dict, separators=(",", ":"))
    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_str,
    }
    items = sorted(params.items(), key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    params["hash"] = sig
    return urllib.parse.urlencode(params)


class TestInitDataValidation:
    """Test cryptographic validation of Telegram initData."""

    def test_valid_signature_passes(self):
        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        user_info = {"id": 888777, "first_name": "Alice", "username": "alice_tma"}
        init_data = make_telegram_init_data(user_info, token)

        result = validate_telegram_init_data(init_data, token)
        assert result is not None
        assert result["user_data"]["id"] == 888777
        assert result["user_data"]["username"] == "alice_tma"
        assert result["user_data"]["first_name"] == "Alice"

    def test_tampered_data_rejected(self):
        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        user_info = {"id": 888777, "first_name": "Alice"}
        init_data = make_telegram_init_data(user_info, token)

        # Tamper user ID
        tampered = init_data.replace("888777", "999999")
        result = validate_telegram_init_data(tampered, token)
        assert result is None

    def test_empty_or_malformed_rejected(self):
        token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert validate_telegram_init_data("", token) is None
        assert validate_telegram_init_data("not_a_valid_query", token) is None
        assert validate_telegram_init_data("user=123", token) is None


@pytest_asyncio.fixture
async def test_app_client():
    """Create a test client with initialized database and created tables."""
    await init_db()
    from app.database.database import get_engine
    from app.database.models import Base
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    api = create_api()

    # Pre-seed test category, product, and inventory in database
    async with get_session() as session:
        # Check if already exists
        cat = Category(name="Cloud Accounts", icon="☁️", active=True)
        session.add(cat)
        await session.flush()

        prod = Product(
            category_id=cat.id,
            name="Vite Cloud VPS",
            description="Ultra-fast cloud compute instance.",
            price=Decimal("12.50"),
            currency="USD",
            active=True,
        )
        session.add(prod)
        await session.flush()

        inv1 = Inventory(
            product_id=prod.id,
            content="root:secretpass123:ip10.0.0.1",
            status=InventoryStatus.AVAILABLE,
        )
        inv2 = Inventory(
            product_id=prod.id,
            content="root:secretpass456:ip10.0.0.2",
            status=InventoryStatus.AVAILABLE,
        )
        session.add_all([inv1, inv2])
        await session.flush()

    transport = ASGITransport(app=api)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await close_db()


@pytest.mark.asyncio
async def test_webapp_static_files(test_app_client: AsyncClient):
    """Test that static files (index.html, style.css, app.js) are served properly."""
    res_html = await test_app_client.get("/webapp/")
    assert res_html.status_code == 200
    assert "Cloud Deals" in res_html.text
    assert "bottom-dock" in res_html.text

    res_css = await test_app_client.get("/webapp/style.css")
    assert res_css.status_code == 200
    assert "--font-heading" in res_css.text

    res_js = await test_app_client.get("/webapp/app.js")
    assert res_js.status_code == 200
    assert "Telegram" in res_js.text


@pytest.mark.asyncio
async def test_webapp_auth_and_user_profile(test_app_client: AsyncClient):
    """Test /api/webapp/auth endpoint."""
    res = await test_app_client.post(
        "/api/webapp/auth",
        json={"dev_telegram_id": 777123, "dev_username": "cloud_tester", "dev_first_name": "Tester"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["user"]["telegram_id"] == 777123
    assert data["user"]["username"] == "cloud_tester"
    assert "balance" in data["user"]
    assert "store" in data


@pytest.mark.asyncio
async def test_webapp_catalog_and_product_detail(test_app_client: AsyncClient):
    """Test /api/webapp/catalog and /api/webapp/products/{id} endpoints."""
    res = await test_app_client.get("/api/webapp/catalog")
    assert res.status_code == 200
    data = res.json()
    assert len(data["categories"]) >= 1
    assert len(data["products"]) >= 1

    first_prod = data["products"][0]
    assert first_prod["stock"] >= 2
    assert float(first_prod["price"]) > 0

    # Test single product detail
    detail_res = await test_app_client.get(f"/api/webapp/products/{first_prod['id']}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["name"] == first_prod["name"]
    assert detail["stock"] >= 2


@pytest.mark.asyncio
async def test_webapp_cart_lifecycle_and_checkout_balance(test_app_client: AsyncClient):
    """Test adding to cart, updating quantity, removing, and instant checkout with store balance."""
    tg_id = 998811

    # 1. Add balance to user first
    async with get_session() as session:
        u_res = await user_service.get_or_create_user(session, telegram_id=tg_id, username="rich_user")
        db_u = u_res["user"]
        db_u.balance = Decimal("50.00")
        await session.flush()

    # Get product ID
    cat_res = await test_app_client.get("/api/webapp/catalog")
    prod_id = cat_res.json()["products"][0]["id"]

    # 2. Add to cart
    add_res = await test_app_client.post(
        "/api/webapp/cart/add",
        json={"product_id": prod_id, "quantity": 1, "telegram_id": tg_id},
    )
    assert add_res.status_code == 200
    assert add_res.json()["success"] is True

    # 3. View cart
    cart_res = await test_app_client.get(f"/api/webapp/cart?telegram_id={tg_id}")
    assert cart_res.status_code == 200
    cart = cart_res.json()
    assert cart["total_items"] == 1
    assert len(cart["items"]) == 1

    # 4. Update quantity to 2
    up_res = await test_app_client.post(
        "/api/webapp/cart/update",
        json={"product_id": prod_id, "quantity": 2, "telegram_id": tg_id},
    )
    assert up_res.status_code == 200

    cart_res2 = await test_app_client.get(f"/api/webapp/cart?telegram_id={tg_id}")
    assert cart_res2.json()["total_items"] == 2

    # 5. Checkout with store balance
    checkout_res = await test_app_client.post(
        "/api/webapp/checkout",
        json={"payment_method": "balance", "telegram_id": tg_id},
    )
    assert checkout_res.status_code == 200
    co_data = checkout_res.json()
    assert co_data["payment_method"] == "balance"
    assert co_data["status"] == "fulfilled"
    assert len(co_data["credentials"]) == 2

    # 6. Verify credentials delivered and cart emptied
    empty_cart_res = await test_app_client.get(f"/api/webapp/cart?telegram_id={tg_id}")
    assert empty_cart_res.json()["total_items"] == 0

    # 7. Check orders history
    orders_res = await test_app_client.get(f"/api/webapp/orders?telegram_id={tg_id}")
    assert orders_res.status_code == 200
    orders = orders_res.json()["orders"]
    assert len(orders) >= 1
    assert orders[0]["status"] == "fulfilled"
    assert len(orders[0]["delivered_items"]) == 2


@pytest.mark.asyncio
async def test_webapp_first_order_discount(test_app_client: AsyncClient):
    """Test claiming 10% first-order discount."""
    tg_id = 998822
    claim_res = await test_app_client.post(
        "/api/webapp/discount/claim",
        json={"telegram_id": tg_id},
    )
    assert claim_res.status_code == 200
    data = claim_res.json()
    assert data["success"] is True
    assert data["claimed"] is True
