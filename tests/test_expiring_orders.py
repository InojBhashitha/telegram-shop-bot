"""Tests for expiring order recovery loop and warning notifications."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus
from app.services import order_service


@pytest.mark.asyncio
async def test_expiring_orders_warning_window(session: AsyncSession, sample_data: dict):
    """Orders approaching expiration (>= 20 mins old in a 30-min window) are identified for warning."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Order 1: Created 25 minutes ago (within warning window of 10 min before 30 min expiry)
    res1 = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order1 = res1["order"]
    order1.created_at = datetime.now(timezone.utc) - timedelta(minutes=25)

    # Order 2: Created 5 minutes ago (fresh, not in warning window)
    res2 = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order2 = res2["order"]
    order2.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    await session.commit()

    # Query expiring orders (warning_minutes_before=10, expiry_minutes=30) -> threshold 20 min
    expiring = await order_service.get_expiring_orders_for_warning(
        session, expiry_minutes=30, warning_minutes_before=10
    )

    expiring_ids = [o.id for o in expiring]
    assert order1.id in expiring_ids
    assert order2.id not in expiring_ids

    # Mark warned
    await order_service.mark_order_warned(session, order1.id)
    await session.commit()

    # Next check must not return order1 again
    expiring_after = await order_service.get_expiring_orders_for_warning(
        session, expiry_minutes=30, warning_minutes_before=10
    )
    assert order1.id not in [o.id for o in expiring_after]
