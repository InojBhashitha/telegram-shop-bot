"""Warranty service — warranty claim creation, approval, and replacement delivery."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import OrderStatus, WarrantyClaimStatus
from app.database.repositories import inventory_repo, order_repo, warranty_repo

logger = logging.getLogger(__name__)


class WarrantyError(Exception):
    """Raised when a warranty operation fails."""
    pass


async def create_claim(
    session: AsyncSession,
    order_id: int,
    user_id: int,
    reason: str,
) -> dict:
    """Create a warranty claim for a fulfilled order.

    Validates:
    - Order exists and belongs to user
    - Order is fulfilled
    - Warranty period has not expired
    - No existing pending claim for this order

    Returns:
        Dict with 'claim' model.
    """
    order = await order_repo.get_by_id(session, order_id)
    if order is None:
        raise WarrantyError("Order not found")
    if order.user_id != user_id:
        raise WarrantyError("This is not your order")
    if order.status != OrderStatus.FULFILLED:
        raise WarrantyError("Warranty is only available for delivered orders")

    # Check warranty expiry
    now = datetime.now(timezone.utc)
    if order.warranty_expires_at and now > order.warranty_expires_at:
        raise WarrantyError("Warranty period has expired for this order")

    # Check for existing pending claim
    existing = await warranty_repo.get_claims_for_order(session, order_id)
    pending = [c for c in existing if c.status == WarrantyClaimStatus.PENDING]
    if pending:
        raise WarrantyError("You already have a pending warranty claim for this order")

    # Get inventory item(s) for the order
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    if not items:
        raise WarrantyError("No inventory item found for this order")

    # Create claim (using the first inventory item)
    claim = await warranty_repo.create(
        session,
        order_id=order_id,
        user_id=user_id,
        inventory_id=items[0].id,
        reason=reason,
    )

    logger.info(
        "Warranty claim created: claim_id=%s order=%s user_id=%s",
        claim.id, order.public_order_id, user_id,
    )
    return {"claim": claim}


async def approve_claim(
    session: AsyncSession,
    claim_id: int,
    admin_notes: Optional[str] = None,
) -> dict:
    """Approve a warranty claim and auto-replace with fresh stock.

    Steps:
    1. Validate claim is pending
    2. Reserve a new inventory item from the same product
    3. Mark the claim as approved with the replacement item ID
    4. Return the replacement content for delivery

    Returns:
        Dict with 'claim', 'replacement_content', 'order'.
    """
    claim = await warranty_repo.get_by_id(session, claim_id)
    if claim is None:
        raise WarrantyError("Claim not found")
    if claim.status != WarrantyClaimStatus.PENDING:
        raise WarrantyError("Claim is not pending")

    order = await order_repo.get_by_id(session, claim.order_id)
    if order is None:
        raise WarrantyError("Associated order not found")

    # Reserve a replacement item from same product
    replacement = await inventory_repo.reserve_item(session, order.product_id)
    if replacement is None:
        raise WarrantyError(
            "No replacement stock available. Please restock and try again."
        )

    # Mark replacement as sold
    await inventory_repo.mark_sold(session, replacement.id, order.id)

    # Approve claim
    claim = await warranty_repo.update_status(
        session,
        claim_id,
        WarrantyClaimStatus.APPROVED,
        replacement_inventory_id=replacement.id,
        admin_notes=admin_notes or "Replacement sent automatically",
    )

    logger.info(
        "Warranty claim approved: claim_id=%s replacement_id=%s",
        claim_id, replacement.id,
    )
    return {
        "claim": claim,
        "replacement_content": replacement.content,
        "order": order,
    }


async def reject_claim(
    session: AsyncSession,
    claim_id: int,
    admin_notes: Optional[str] = None,
) -> dict:
    """Reject a warranty claim."""
    claim = await warranty_repo.get_by_id(session, claim_id)
    if claim is None:
        raise WarrantyError("Claim not found")
    if claim.status != WarrantyClaimStatus.PENDING:
        raise WarrantyError("Claim is not pending")

    claim = await warranty_repo.update_status(
        session,
        claim_id,
        WarrantyClaimStatus.REJECTED,
        admin_notes=admin_notes or "Claim rejected by admin",
    )

    logger.info("Warranty claim rejected: claim_id=%s", claim_id)
    return {"claim": claim}


async def get_pending_claims(session: AsyncSession) -> list:
    """Get all pending warranty claims."""
    return await warranty_repo.get_pending_claims(session)
