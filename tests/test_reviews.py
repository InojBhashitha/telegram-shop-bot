"""Tests for product reviews, ratings, and vouch channel broadcast."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus
from app.services import order_service, review_service
from app.services.review_service import ReviewError


@pytest.mark.asyncio
async def test_submit_review_and_aggregation(session: AsyncSession, sample_data: dict):
    """Submit reviews and check average rating aggregation."""
    user = sample_data["user"]
    product = sample_data["product"]

    # Create & fulfill an order first
    order_res = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order = order_res["order"]
    await order_service.order_repo.update_status(session, order.id, OrderStatus.PAID)
    await order_service.fulfill_order(session, order.id)
    await session.commit()

    # Submit 5-star review
    rev = await review_service.submit_review(
        session,
        user_id=user.id,
        product_id=product.id,
        order_id=order.id,
        rating=5,
        comment="Fast delivery and works perfectly!",
    )
    await session.commit()

    assert rev.id is not None
    assert rev.rating == 5
    assert rev.comment == "Fast delivery and works perfectly!"

    # Check aggregation
    summary = await review_service.get_product_review_summary(session, product.id)
    assert summary["count"] == 1
    assert summary["average"] == 5.0


@pytest.mark.asyncio
async def test_invalid_rating_rejected(session: AsyncSession, sample_data: dict):
    """Ratings outside 1-5 range are rejected."""
    user = sample_data["user"]
    product = sample_data["product"]

    with pytest.raises(ReviewError, match="Rating must be an integer between 1 and 5"):
        await review_service.submit_review(
            session, user_id=user.id, product_id=product.id, rating=6
        )

    with pytest.raises(ReviewError, match="Rating must be an integer between 1 and 5"):
        await review_service.submit_review(
            session, user_id=user.id, product_id=product.id, rating=0
        )


@pytest.mark.asyncio
async def test_update_existing_review(session: AsyncSession, sample_data: dict):
    """Re-submitting for the same order updates the existing review instead of duplicating."""
    user = sample_data["user"]
    product = sample_data["product"]

    order_res = await order_service.create_order(session, user_id=user.id, product_id=product.id)
    order = order_res["order"]
    await order_service.order_repo.update_status(session, order.id, OrderStatus.PAID)
    await order_service.fulfill_order(session, order.id)
    await session.commit()

    # Submit initial 4-star review
    await review_service.submit_review(
        session, user_id=user.id, product_id=product.id, order_id=order.id, rating=4
    )
    await session.commit()

    # Update to 5-star review
    rev2 = await review_service.submit_review(
        session, user_id=user.id, product_id=product.id, order_id=order.id, rating=5, comment="Upgraded!"
    )
    await session.commit()

    summary = await review_service.get_product_review_summary(session, product.id)
    assert summary["count"] == 1
    assert summary["average"] == 5.0
    assert rev2.comment == "Upgraded!"
