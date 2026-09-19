"""Coupon service — coupon validation, discount computation, and affiliate rewards."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Coupon, CouponType, Order
from app.database.repositories import coupon_repo, user_repo

logger = logging.getLogger(__name__)


class CouponError(Exception):
    """Raised when coupon validation fails."""
    pass


async def create_coupon(
    session: AsyncSession,
    code: str,
    discount_type: CouponType,
    discount_value: Decimal,
    min_order_amount: Decimal = Decimal("0.00"),
    max_discount: Optional[Decimal] = None,
    max_uses: Optional[int] = None,
    expiry_at: Optional[datetime] = None,
    affiliate_user_id: Optional[int] = None,
    affiliate_commission_pct: Decimal = Decimal("0.00"),
    **kwargs,
) -> Coupon:
    """Create a new coupon code in the system."""
    if "min_spend" in kwargs:
        min_order_amount = kwargs["min_spend"]
    if "expires_at" in kwargs:
        expiry_at = kwargs["expires_at"]
    if "affiliate_reward_percent" in kwargs:
        affiliate_commission_pct = kwargs["affiliate_reward_percent"]

    return await coupon_repo.create(
        session=session,
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        min_order_amount=min_order_amount,
        max_discount=max_discount,
        max_uses=max_uses,
        expiry_at=expiry_at,
        affiliate_user_id=affiliate_user_id,
        affiliate_commission_pct=affiliate_commission_pct,
    )


async def validate_and_apply_coupon(
    session: AsyncSession,
    code: str,
    cart_subtotal: Decimal,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Validate a coupon code and return its discount info."""
    res = await validate_and_calculate_discount(session, code, cart_subtotal, user_id)
    return {
        "valid": True,
        "discount_amount": res["discount_amount"],
        "final_subtotal": res["final_amount"],
        "coupon": res["coupon"],
        "code": res["code"],
    }


async def validate_and_calculate_discount(
    session: AsyncSession,
    code: str,
    subtotal: Decimal,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Validate a coupon code and calculate its applicable discount.

    Args:
        session: Database session.
        code: Promo code string.
        subtotal: Order amount before discounts.
        user_id: Optional user attempting to redeem.

    Returns:
        Dict with 'coupon', 'discount_amount', 'final_amount', 'code'.

    Raises:
        CouponError: If coupon is invalid, inactive, expired, or min spend not met.
    """
    if not code or not code.strip():
        raise CouponError("Promo code cannot be empty.")

    coupon = await coupon_repo.get_by_code(session, code.strip())
    if coupon is None:
        raise CouponError(f"Promo code '{code.strip().upper()}' is not valid.")

    if not coupon.active:
        raise CouponError(f"Promo code '{coupon.code}' is no longer active.")

    now = datetime.now(timezone.utc)
    if coupon.expiry_at is not None:
        expiry = coupon.expiry_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < now:
            raise CouponError(f"Promo code '{coupon.code}' has expired.")

    if coupon.max_uses is not None and coupon.current_uses >= coupon.max_uses:
        raise CouponError(f"Promo code '{coupon.code}' has reached its maximum usage limit.")

    if subtotal < coupon.min_order_amount:
        raise CouponError(
            f"Promo code '{coupon.code}' requires a minimum order of ${coupon.min_order_amount:.2f}."
        )

    # Cannot use own affiliate coupon code
    if user_id and coupon.affiliate_user_id == user_id:
        raise CouponError("You cannot use your own affiliate promo code.")

    # Calculate discount amount
    if coupon.discount_type == CouponType.PERCENTAGE:
        raw_discount = subtotal * (coupon.discount_value / Decimal("100"))
        if coupon.max_discount is not None:
            discount = min(raw_discount, coupon.max_discount)
        else:
            discount = raw_discount
    else:  # FIXED
        discount = min(coupon.discount_value, subtotal)

    discount = discount.quantize(Decimal("0.01"))
    final_amount = max(subtotal - discount, Decimal("0.00"))

    return {
        "coupon": coupon,
        "coupon_id": coupon.id,
        "code": coupon.code,
        "discount_amount": discount,
        "final_amount": final_amount,
        "affiliate_user_id": coupon.affiliate_user_id,
    }


async def credit_affiliate_for_order(
    session: AsyncSession,
    order: Order,
) -> Optional[Decimal]:
    """Credit affiliate commission to referrer balance upon order completion."""
    if not order.coupon_id:
        return None

    coupon = await coupon_repo.get_by_id(session, order.coupon_id)
    if not coupon or not coupon.affiliate_user_id:
        return None

    if coupon.affiliate_commission_pct <= Decimal("0.00"):
        return None

    commission = (order.amount * (coupon.affiliate_commission_pct / Decimal("100"))).quantize(Decimal("0.01"))
    if commission <= Decimal("0.00"):
        return None

    affiliate = await user_repo.get_by_id(session, coupon.affiliate_user_id)
    if affiliate:
        await user_repo.update_balance(session, affiliate.id, commission)
        logger.info(
            "Affiliate commission credited: $%s to user %s (order %s, code %s)",
            commission, affiliate.telegram_id, order.public_order_id, coupon.code,
        )
        return commission

    return None
