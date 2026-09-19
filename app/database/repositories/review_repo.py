"""Review repository for product ratings and customer feedback."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import ProductReview


async def create_review(
    session: AsyncSession,
    order_id: int,
    product_id: int,
    user_id: int,
    rating: int,
    comment: Optional[str] = None,
) -> ProductReview:
    """Create or update a product review for a completed order."""
    # Ensure rating is between 1 and 5
    clamped_rating = max(1, min(5, rating))

    review = ProductReview(
        order_id=order_id,
        product_id=product_id,
        user_id=user_id,
        rating=clamped_rating,
        comment=comment.strip() if comment else None,
    )
    session.add(review)
    await session.flush()
    return review


async def get_by_order_id(
    session: AsyncSession,
    order_id: int,
) -> Optional[ProductReview]:
    """Get review for a specific order."""
    stmt = select(ProductReview).where(ProductReview.order_id == order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_product_rating_summary(
    session: AsyncSession,
    product_id: int,
) -> dict[str, Any]:
    """Compute average star rating and total review count for a product."""
    stmt = (
        select(
            func.avg(ProductReview.rating),
            func.count(ProductReview.id),
        )
        .where(ProductReview.product_id == product_id)
    )
    result = await session.execute(stmt)
    avg_val, count_val = result.one()
    avg_float = round(float(avg_val), 1) if avg_val is not None else 0.0
    cnt = int(count_val or 0)
    return {
        "average_rating": avg_float,
        "review_count": cnt,
        "average": avg_float,
        "count": cnt,
    }


async def get_product_reviews(
    session: AsyncSession,
    product_id: int,
    limit: int = 10,
) -> list[ProductReview]:
    """Get latest reviews for a product."""
    stmt = (
        select(ProductReview)
        .options(selectinload(ProductReview.user))
        .where(ProductReview.product_id == product_id)
        .order_by(ProductReview.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
