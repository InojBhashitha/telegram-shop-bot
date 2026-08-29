"""Tests for new features: bulk ordering, warranty claims, delivery formatting, and UI badges."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main import main_reply_keyboard
from app.bot.keyboards.orders import _get_payment_steps
from app.bot.keyboards.products import _stock_badge
from app.database.models import InventoryStatus, OrderStatus, WarrantyClaimStatus
from app.database.repositories import inventory_repo
from app.services import delivery_service, order_service, warranty_service
from app.services.delivery_service import _format_credentials_for_copy


# ===========================================================================
# 1. Bulk Ordering Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_bulk_order_creation_and_amount(session: AsyncSession, sample_data: dict):
    """Test creating an order with quantity > 1 reserves multiple items and scales amount."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=2)
    order = result["order"]
    items = result["inventory_items"]

    assert len(items) == 2
    assert order.quantity == 2
    assert order.amount == Decimal("9.00")  # 4.50 * 2
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.warranty_expires_at is not None

    # Stock should be 1 remaining out of 3
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 1


@pytest.mark.asyncio
async def test_bulk_order_insufficient_stock(session: AsyncSession, sample_data: dict):
    """Test creating a bulk order with requested quantity > stock fails and rolls back."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Request 5 items when only 3 exist
    with pytest.raises(order_service.OrderError, match="Only 3 item"):
        await order_service.create_order(session, user.id, product.id, quantity=5)

    # Stock should remain untouched at 3
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3


@pytest.mark.asyncio
async def test_bulk_order_cancellation_releases_all(session: AsyncSession, sample_data: dict):
    """Test cancelling a bulk order releases all reserved inventory items."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=3)
    order = result["order"]

    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 0

    await order_service.cancel_order(session, order.id)

    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 3


@pytest.mark.asyncio
async def test_bulk_order_fulfillment_delivers_all(session: AsyncSession, sample_data: dict):
    """Test fulfilling a bulk order marks all items as sold and returns all contents."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=2)
    order = result["order"]

    await order_service.mark_paid(session, order.id)
    fulfill_result = await order_service.fulfill_order(session, order.id)

    assert fulfill_result is not None
    assert len(fulfill_result["contents"]) == 2
    assert fulfill_result["order"].status == OrderStatus.FULFILLED


# ===========================================================================
# 2. Warranty Claims System Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_warranty_claim_flow(session: AsyncSession, sample_data: dict):
    """Test full warranty claim lifecycle: create claim -> approve -> replacement delivered."""
    user = sample_data["user"]
    product = sample_data["product"]

    # 1. Create and fulfill an order (leaves 2 items in stock)
    result = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = result["order"]
    await order_service.mark_paid(session, order.id)
    await order_service.fulfill_order(session, order.id)

    # 2. User creates a warranty claim
    claim_res = await warranty_service.create_claim(
        session,
        order_id=order.id,
        user_id=user.id,
        reason="Password was incorrect on first login",
    )
    claim = claim_res["claim"]
    assert claim.id is not None
    assert claim.status == WarrantyClaimStatus.PENDING

    # 3. Admin approves claim and provides replacement
    appr_res = await warranty_service.approve_claim(session, claim.id, admin_notes="Verified issue")
    approved_claim = appr_res["claim"]
    assert approved_claim.status == WarrantyClaimStatus.APPROVED
    assert approved_claim.replacement_inventory_id is not None
    assert appr_res["replacement_content"].startswith("TEST-ITEM-")

    # Available stock should now be 1 (started with 3, 1 bought, 1 replacement used)
    stock = await inventory_repo.get_stock_count(session, product.id)
    assert stock == 1


@pytest.mark.asyncio
async def test_warranty_claim_reject_flow(session: AsyncSession, sample_data: dict):
    """Test rejecting a warranty claim."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = result["order"]
    await order_service.mark_paid(session, order.id)
    await order_service.fulfill_order(session, order.id)

    claim_res = await warranty_service.create_claim(
        session,
        order_id=order.id,
        user_id=user.id,
        reason="Invalid credentials",
    )
    claim = claim_res["claim"]

    rej_res = await warranty_service.reject_claim(session, claim.id, admin_notes="Account working fine")
    assert rej_res["claim"].status == WarrantyClaimStatus.REJECTED


@pytest.mark.asyncio
async def test_warranty_claim_unfulfilled_order_fails(session: AsyncSession, sample_data: dict):
    """Test that warranty claims cannot be created for pending / unpaid orders."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = result["order"]

    with pytest.raises(warranty_service.WarrantyError, match="delivered orders"):
        await warranty_service.create_claim(
            session, order_id=order.id, user_id=user.id, reason="Issue"
        )


@pytest.mark.asyncio
async def test_warranty_claim_duplicate_prevented(session: AsyncSession, sample_data: dict):
    """Test that multiple pending warranty claims for same order are blocked."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = result["order"]
    await order_service.mark_paid(session, order.id)
    await order_service.fulfill_order(session, order.id)

    await warranty_service.create_claim(
        session, order_id=order.id, user_id=user.id, reason="First claim"
    )

    with pytest.raises(warranty_service.WarrantyError, match="already have a pending"):
        await warranty_service.create_claim(
            session, order_id=order.id, user_id=user.id, reason="Second claim"
        )


@pytest.mark.asyncio
async def test_warranty_claim_expired_fails(session: AsyncSession, sample_data: dict):
    """Test that claims on expired warranties are rejected."""
    user = sample_data["user"]
    product = sample_data["product"]

    result = await order_service.create_order(session, user.id, product.id, quantity=1)
    order = result["order"]
    await order_service.mark_paid(session, order.id)
    await order_service.fulfill_order(session, order.id)

    # Artificially expire the warranty
    order.warranty_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session.flush()

    with pytest.raises(warranty_service.WarrantyError, match="expired"):
        await warranty_service.create_claim(
            session, order_id=order.id, user_id=user.id, reason="Late claim"
        )


# ===========================================================================
# 3. Delivery Formatting (1-Tap Copy) Tests
# ===========================================================================

def test_format_credentials_key_value():
    """Test formatting key:value account credentials with copyable backticks."""
    content = "Email: test@example.com\nPassword: secret_pass\nAccount Pass: 12345"
    formatted = _format_credentials_for_copy(content)

    assert "`test@example.com`" in formatted
    assert "`secret_pass`" in formatted
    assert "`12345`" in formatted
    assert "📧 *Email:*" in formatted
    assert "🔑 *Password:*" in formatted


def test_format_credentials_colon_delimited():
    """Test formatting combo string email:pass:accpass."""
    content = "user@domain.com:mypass123:accpin99"
    formatted = _format_credentials_for_copy(content)

    assert "`user@domain.com`" in formatted
    assert "`mypass123`" in formatted
    assert "`accpin99`" in formatted


# ===========================================================================
# 4. UI Badges & Keyboards Tests
# ===========================================================================

def test_stock_badges():
    """Test live stock badge visual indicators."""
    assert _stock_badge(0) == "🔴 Sold Out"
    assert "🟡" in _stock_badge(2)
    assert "🟢" in _stock_badge(5)
    assert _stock_badge(10) == "🟢 In Stock"


def test_payment_step_tracker():
    """Test visual payment status stepper."""
    waiting_steps = _get_payment_steps("waiting")
    assert "🟡 Deposit" in waiting_steps

    confirming_steps = _get_payment_steps("confirming")
    assert "🟢 Deposit" in confirming_steps
    assert "🟡 Confirm" in confirming_steps

    paid_steps = _get_payment_steps("paid")
    assert "🟢 Deposit" in paid_steps
    assert "🟢 Confirm" in paid_steps
    assert "🟢 Deliver" in paid_steps


def test_persistent_reply_keyboard():
    """Test persistent bottom reply keyboard structure."""
    kb = main_reply_keyboard()
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True
    button_texts = [btn.text for row in kb.keyboard for btn in row]
    assert "🛍 Browse Store" in button_texts
    assert "📦 My Orders" in button_texts
    assert "👤 My Profile" in button_texts
    assert "☎️ Support / FAQ" in button_texts
