"""Tests for coupon & promo code engine and affiliate rewards."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Coupon, CouponType, User, Order, OrderStatus
from app.services import coupon_service, order_service
from app.services.coupon_service import CouponError


@pytest.mark.asyncio
async def test_percentage_coupon_discount(session: AsyncSession, sample_data: dict):
    """Test 20% discount on $50 subtotal yields $10 discount."""
    coupon = await coupon_service.create_coupon(
        session,
        code="SAVE20",
        discount_type=CouponType.PERCENTAGE,
        discount_value=Decimal("20.00"),
    )
    await session.commit()

    val = await coupon_service.validate_and_apply_coupon(
        session, code="save20", cart_subtotal=Decimal("50.00")
    )

    assert val["valid"] is True
    assert val["discount_amount"] == Decimal("10.00")
    assert val["final_subtotal"] == Decimal("40.00")


@pytest.mark.asyncio
async def test_fixed_coupon_discount(session: AsyncSession):
    """Test $5 fixed discount on $20 subtotal yields $5 discount."""
    await coupon_service.create_coupon(
        session,
        code="TAKE5",
        discount_type=CouponType.FIXED,
        discount_value=Decimal("5.00"),
    )
    await session.commit()

    val = await coupon_service.validate_and_apply_coupon(
        session, code="TAKE5", cart_subtotal=Decimal("20.00")
    )

    assert val["valid"] is True
    assert val["discount_amount"] == Decimal("5.00")
    assert val["final_subtotal"] == Decimal("15.00")


@pytest.mark.asyncio
async def test_fixed_discount_caps_at_subtotal(session: AsyncSession):
    """Fixed discount larger than subtotal caps at subtotal."""
    await coupon_service.create_coupon(
        session,
        code="HUGE50",
        discount_type=CouponType.FIXED,
        discount_value=Decimal("50.00"),
    )
    await session.commit()

    val = await coupon_service.validate_and_apply_coupon(
        session, code="HUGE50", cart_subtotal=Decimal("15.00")
    )

    assert val["discount_amount"] == Decimal("15.00")
    assert val["final_subtotal"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_coupon_min_spend_requirement(session: AsyncSession):
    """Coupon with min spend raises CouponError if cart is below threshold."""
    await coupon_service.create_coupon(
        session,
        code="VIP100",
        discount_type=CouponType.PERCENTAGE,
        discount_value=Decimal("15.00"),
        min_spend=Decimal("30.00"),
    )
    await session.commit()

    with pytest.raises(CouponError, match="requires a minimum order of"):
        await coupon_service.validate_and_apply_coupon(
            session, code="VIP100", cart_subtotal=Decimal("20.00")
        )

    # Above min_spend should succeed
    val = await coupon_service.validate_and_apply_coupon(
        session, code="VIP100", cart_subtotal=Decimal("40.00")
    )
    assert val["valid"] is True


@pytest.mark.asyncio
async def test_coupon_max_uses_limit(session: AsyncSession):
    """Coupon reaches max uses limit and rejects further attempts."""
    coupon = await coupon_service.create_coupon(
        session,
        code="LIMITED",
        discount_type=CouponType.FIXED,
        discount_value=Decimal("2.00"),
        max_uses=1,
    )
    coupon.current_uses = 1
    await session.commit()

    with pytest.raises(CouponError, match="maximum usage limit"):
        await coupon_service.validate_and_apply_coupon(
            session, code="LIMITED", cart_subtotal=Decimal("10.00")
        )


@pytest.mark.asyncio
async def test_expired_coupon(session: AsyncSession):
    """Expired coupon raises CouponError."""
    past_date = datetime.now(timezone.utc) - timedelta(days=2)
    await coupon_service.create_coupon(
        session,
        code="EXPIRED",
        discount_type=CouponType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        expires_at=past_date,
    )
    await session.commit()

    with pytest.raises(CouponError, match="has expired"):
        await coupon_service.validate_and_apply_coupon(
            session, code="EXPIRED", cart_subtotal=Decimal("10.00")
        )


@pytest.mark.asyncio
async def test_affiliate_commission_crediting(session: AsyncSession, sample_data: dict):
    """Affiliate partner receives balance credit when order with affiliate coupon is fulfilled."""
    affiliate = User(telegram_id=999999, username="affiliate_boss", first_name="Boss", balance=Decimal("0.00"))
    session.add(affiliate)
    await session.flush()

    coupon = await coupon_service.create_coupon(
        session,
        code="BOSS10",
        discount_type=CouponType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        affiliate_user_id=affiliate.id,
        affiliate_reward_percent=Decimal("5.00"),  # 5% of order final amount
    )
    await session.commit()

    buyer = sample_data["user"]
    product = sample_data["product"]

    order_res = await order_service.create_order(
        session,
        user_id=buyer.id,
        product_id=product.id,
        coupon_id=coupon.id,
    )
    order = order_res["order"]
    await session.commit()

    # Mark paid and fulfill
    await order_service.order_repo.update_status(session, order.id, OrderStatus.PAID)
    await order_service.fulfill_order(session, order.id)
    await session.commit()

    # Verify affiliate received credit (5% of order.amount)
    from app.database.repositories import user_repo
    updated_affiliate = await user_repo.get_by_id(session, affiliate.id)
    expected_commission = (order.amount * Decimal("5.00") / Decimal("100")).quantize(Decimal("0.01"))
    assert updated_affiliate.balance == expected_commission
    assert updated_affiliate.balance > Decimal("0.00")
