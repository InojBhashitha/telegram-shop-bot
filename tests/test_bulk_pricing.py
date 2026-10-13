"""Tests for Bulk / Wholesale Volume Pricing Tier service and checkout flows."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.main import create_api
from app.database.database import close_db, get_session, init_db
from app.database.models import (
    Category,
    Coupon,
    CouponType,
    Inventory,
    InventoryStatus,
    Product,
)
from app.services import bulk_pricing_service, cart_service, order_service


def test_bulk_pricing_calculation_tiers():
    """Test calculating wholesale volume discounts across tier boundaries."""
    price = Decimal("20.00")

    # 1 pc -> 0% discount
    res1 = bulk_pricing_service.calculate_bulk_discount(price, 1)
    assert res1["discount_percent"] == 0.0
    assert res1["discount_amount"] == Decimal("0.00")
    assert res1["final_subtotal"] == Decimal("20.00")
    assert res1["effective_unit_price"] == Decimal("20.00")
    assert "Add 2 more" in res1["next_tier_hint"]

    # 2 pcs -> 0% discount
    res2 = bulk_pricing_service.calculate_bulk_discount(price, 2)
    assert res2["discount_percent"] == 0.0
    assert res2["discount_amount"] == Decimal("0.00")
    assert res2["final_subtotal"] == Decimal("40.00")
    assert "Add 1 more" in res2["next_tier_hint"]

    # 3 pcs -> Tier 1 (5% OFF)
    res3 = bulk_pricing_service.calculate_bulk_discount(price, 3)
    # raw: $60.00, 5% of 60.00 = $3.00, final: $57.00
    assert res3["discount_percent"] == 5.0
    assert res3["discount_amount"] == Decimal("3.00")
    assert res3["final_subtotal"] == Decimal("57.00")
    assert res3["effective_unit_price"] == Decimal("19.00")
    assert "Add 2 more" in res3["next_tier_hint"]

    # 5 pcs -> Tier 2 (10% OFF)
    res5 = bulk_pricing_service.calculate_bulk_discount(price, 5)
    # raw: $100.00, 10% of 100.00 = $10.00, final: $90.00
    assert res5["discount_percent"] == 10.0
    assert res5["discount_amount"] == Decimal("10.00")
    assert res5["final_subtotal"] == Decimal("90.00")
    assert res5["effective_unit_price"] == Decimal("18.00")
    assert "Add 5 more" in res5["next_tier_hint"]

    # 10 pcs -> Tier 3 (15% OFF)
    res10 = bulk_pricing_service.calculate_bulk_discount(price, 10)
    # raw: $200.00, 15% of 200.00 = $30.00, final: $170.00
    assert res10["discount_percent"] == 15.0
    assert res10["discount_amount"] == Decimal("30.00")
    assert res10["final_subtotal"] == Decimal("170.00")
    assert res10["effective_unit_price"] == Decimal("17.00")
    assert "VIP Wholesale" in res10["next_tier_hint"]

    # 25 pcs -> Tier 4 VIP Wholesale (20% OFF)
    res25 = bulk_pricing_service.calculate_bulk_discount(price, 25)
    # raw: $500.00, 20% of 500.00 = $100.00, final: $400.00
    assert res25["discount_percent"] == 20.0
    assert res25["discount_amount"] == Decimal("100.00")
    assert res25["final_subtotal"] == Decimal("400.00")
    assert res25["effective_unit_price"] == Decimal("16.00")
    assert "VIP Wholesale" in res25["tier_label"]
    assert res25["next_tier_hint"] == ""


def test_bulk_pricing_caption_formatting():
    """Test formatting telegram caption wholesale table."""
    caption = bulk_pricing_service.format_bulk_pricing_caption(Decimal("10.00"))
    assert "Wholesale Volume Pricing:" in caption
    assert "1–2 pcs" in caption
    assert "3–4 pcs" in caption
    assert "5–9 pcs" in caption
    assert "10–24 pcs" in caption
    assert "25+ pcs" in caption


@pytest.mark.asyncio
async def test_order_creation_with_bulk_discount(session: AsyncSession, sample_data: dict):
    """Test creating an order with bulk quantity automatically receives wholesale discount."""
    user = sample_data["user"]
    cat = sample_data["category"]

    # Create product with 10 available stock
    prod = Product(
        category_id=cat.id,
        name="Oracle Cloud Tier Product",
        price=Decimal("10.00"),
        currency="USD",
        active=True,
    )
    session.add(prod)
    await session.flush()

    for i in range(10):
        session.add(Inventory(product_id=prod.id, content=f"acc_{i}", status=InventoryStatus.AVAILABLE))
    await session.flush()

    # Buy 5 pcs -> Tier 2 (10% OFF)
    # Raw subtotal = 5 * 10 = $50.00, Discount = $5.00, Final = $45.00
    res = await order_service.create_order(session, user_id=user.id, product_id=prod.id, quantity=5)
    order = res["order"]

    assert res["subtotal"] == Decimal("50.00")
    assert res["bulk_discount"] == Decimal("5.00")
    assert res["bulk_percent"] == 10.0
    assert order.amount == Decimal("45.00")
    assert order.discount_amount == Decimal("5.00")
    assert order.quantity == 5


@pytest.mark.asyncio
async def test_order_bulk_discount_stacks_with_coupon(session: AsyncSession, sample_data: dict):
    """Test that valid promo coupons stack on top of wholesale bulk pricing."""
    user = sample_data["user"]
    cat = sample_data["category"]

    prod = Product(
        category_id=cat.id,
        name="AWS High Volume",
        price=Decimal("20.00"),
        currency="USD",
        active=True,
    )
    session.add(prod)

    # 10% coupon code
    coupon = Coupon(
        code="EXTRA10",
        discount_type=CouponType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        active=True,
    )
    session.add(coupon)
    await session.flush()

    for i in range(6):
        session.add(Inventory(product_id=prod.id, content=f"aws_{i}", status=InventoryStatus.AVAILABLE))
    await session.flush()

    # Buy 5 pcs:
    # Raw subtotal = 5 * $20.00 = $100.00
    # Bulk discount Tier 2 (10% OFF) = -$10.00 -> subtotal after bulk = $90.00
    # Coupon EXTRA10 (10% OFF on $90.00) = -$9.00
    # Total discount = $10.00 + $9.00 = $19.00
    # Final amount = $81.00
    res = await order_service.create_order(
        session,
        user_id=user.id,
        product_id=prod.id,
        quantity=5,
        coupon_code="EXTRA10",
    )
    order = res["order"]

    assert res["subtotal"] == Decimal("100.00")
    assert res["bulk_discount"] == Decimal("10.00")
    assert order.discount_amount == Decimal("19.00")
    assert order.amount == Decimal("81.00")


@pytest.mark.asyncio
async def test_cart_summary_and_checkout_bulk_discounts(session: AsyncSession, sample_data: dict):
    """Test cart summary calculates individual item volume discounts and checkout preserves them."""
    user = sample_data["user"]
    cat = sample_data["category"]

    p1 = Product(category_id=cat.id, name="Product A", price=Decimal("10.00"), currency="USD", active=True)
    p2 = Product(category_id=cat.id, name="Product B", price=Decimal("20.00"), currency="USD", active=True)
    session.add_all([p1, p2])
    await session.flush()

    for i in range(6):
        session.add(Inventory(product_id=p1.id, content=f"p1_{i}", status=InventoryStatus.AVAILABLE))
        session.add(Inventory(product_id=p2.id, content=f"p2_{i}", status=InventoryStatus.AVAILABLE))
    await session.flush()

    # Add 3 of p1 -> Tier 1 (5% OFF) -> raw: $30.00, discount: $1.50, final: $28.50
    # Add 5 of p2 -> Tier 2 (10% OFF) -> raw: $100.00, discount: $10.00, final: $90.00
    await cart_service.add_to_cart(session, user.id, p1.id, quantity=3)
    await cart_service.add_to_cart(session, user.id, p2.id, quantity=5)

    summary = await cart_service.get_cart_summary(session, user.id)
    assert summary["raw_amount"] == Decimal("130.00")
    assert summary["bulk_discount_amount"] == Decimal("11.50")
    assert summary["total_amount"] == Decimal("118.50")
    assert summary["total_count"] == 8

    # Checkout cart
    checkout_res = await cart_service.checkout_cart(session, user.id)
    order = checkout_res["order"]

    assert order.amount == Decimal("118.50")
    assert order.discount_amount == Decimal("11.50")
    assert checkout_res["bulk_discount"] == Decimal("11.50")
    assert checkout_res["subtotal"] == Decimal("130.00")


@pytest.mark.asyncio
async def test_webapp_api_bulk_pricing_endpoints():
    """Test WebApp API returns bulk pricing tiers and cart calculates volume discounts."""
    await init_db()
    from app.database.database import get_engine
    from app.database.models import Base
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    api = create_api()

    async with get_session() as session:
        cat = Category(name="Bulk Catalog Category", icon="📦", active=True)
        session.add(cat)
        await session.flush()

        prod = Product(
            category_id=cat.id,
            name="Bulk Server Instance",
            price=Decimal("15.00"),
            currency="USD",
            active=True,
        )
        session.add(prod)
        await session.flush()

        for i in range(10):
            session.add(Inventory(product_id=prod.id, content=f"bulk_{i}", status=InventoryStatus.AVAILABLE))
        await session.flush()

        prod_id = prod.id

    transport = ASGITransport(app=api)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Check /catalog has bulk_tiers
        cat_res = await client.get("/api/webapp/catalog")
        assert cat_res.status_code == 200
        p_data = cat_res.json()["products"][0]
        assert "bulk_tiers" in p_data
        assert len(p_data["bulk_tiers"]) >= 4

        # 2. Check /products/{id} has bulk_tiers
        p_res = await client.get(f"/api/webapp/products/{prod_id}")
        assert p_res.status_code == 200
        assert "bulk_tiers" in p_res.json()

        # 3. Add 5 items to cart (10% Tier 2 discount)
        tg_id = 112233
        await client.post(
            "/api/webapp/cart/add",
            json={"product_id": prod_id, "quantity": 5, "telegram_id": tg_id},
        )

        # 4. Check /cart returns bulk savings
        cart_res = await client.get(f"/api/webapp/cart?telegram_id={tg_id}")
        assert cart_res.status_code == 200
        cart = cart_res.json()
        assert cart["raw_subtotal"] == "75.00"
        assert cart["bulk_discount_amount"] == "7.50"
        assert cart["subtotal"] == "67.50"
        item = cart["items"][0]
        assert item["bulk_tier"] != ""
        assert item["bulk_discount"] == "7.50"

    await close_db()
