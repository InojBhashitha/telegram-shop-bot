"""Review service — customer ratings, feedback, and social proof broadcast."""

from __future__ import annotations

import logging
from typing import Any, Optional

from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import OrderStatus, ProductReview
from app.database.repositories import order_repo, product_repo, review_repo

logger = logging.getLogger(__name__)


class ReviewError(Exception):
    """Raised when review submission fails."""
    pass


async def submit_review(
    session: AsyncSession,
    user_id: int,
    rating: int,
    order_id: Optional[int] = None,
    product_id: Optional[int] = None,
    comment: Optional[str] = None,
    bot: Optional[Bot] = None,
) -> ProductReview:
    """Submit a rating & review for a fulfilled order or product."""
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise ReviewError("Rating must be an integer between 1 and 5")

    order = None
    if order_id is not None:
        order = await order_repo.get_by_id(session, order_id)
        if order is None:
            raise ReviewError("Order not found.")

        if order.user_id != user_id:
            raise ReviewError("You can only review your own orders.")

        if order.status != OrderStatus.FULFILLED:
            raise ReviewError("You can only review fulfilled orders.")

        existing = await review_repo.get_by_order_id(session, order_id)
        if existing:
            # Update existing review
            existing.rating = rating
            if comment is not None:
                existing.comment = comment.strip()
            await session.flush()
            return existing

        if not product_id:
            product_id = order.product_id
            if not product_id and order.inventory_item:
                product_id = order.inventory_item.product_id

    if not product_id:
        raise ReviewError("Product ID or associated Order is required.")

    review = await review_repo.create_review(
        session=session,
        order_id=order_id,
        product_id=product_id,
        user_id=user_id,
        rating=rating,
        comment=comment,
    )

    # Optional social proof broadcast to public vouch channel
    settings = get_settings()
    if bot and settings.vouch_channel_id:
        try:
            product = await product_repo.get_by_id(session, review.product_id)
            prod_name = product.name if product else "Digital Item"
            stars_visual = "⭐" * review.rating
            order_label = f"`{order.public_order_id[:8]}...`" if order else "Verified Buyer"
            vouch_text = (
                f"🌟 *Verified Customer Purchase*\n\n"
                f"📦 *Product:* {prod_name}\n"
                f"🏷 *Order ID:* {order_label}\n"
                f"⭐ *Rating:* {stars_visual} ({review.rating}/5)\n"
            )
            if review.comment:
                vouch_text += f"💬 *Review:* _{review.comment}_\n\n"
            else:
                vouch_text += "\n"
            vouch_text += "Thank you for trusting Cloud Deals! ☁️"

            await bot.send_message(
                chat_id=settings.vouch_channel_id,
                text=vouch_text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.warning("Could not broadcast vouch to channel %s: %s", settings.vouch_channel_id, e)

    return review


async def get_product_rating(
    session: AsyncSession,
    product_id: int,
) -> dict[str, Any]:
    """Get average rating and count for a product."""
    return await review_repo.get_product_rating_summary(session, product_id)


async def get_product_review_summary(
    session: AsyncSession,
    product_id: int,
) -> dict[str, Any]:
    """Alias for get_product_rating."""
    return await review_repo.get_product_rating_summary(session, product_id)
