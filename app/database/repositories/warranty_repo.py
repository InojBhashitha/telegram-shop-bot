"""Warranty claim repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WarrantyClaim, WarrantyClaimStatus


async def create(
    session: AsyncSession,
    order_id: int,
    user_id: int,
    inventory_id: int,
    reason: str,
) -> WarrantyClaim:
    """Create a warranty claim."""
    claim = WarrantyClaim(
        order_id=order_id,
        user_id=user_id,
        inventory_id=inventory_id,
        reason=reason,
        status=WarrantyClaimStatus.PENDING,
    )
    session.add(claim)
    await session.flush()
    return claim


async def get_by_id(session: AsyncSession, claim_id: int) -> Optional[WarrantyClaim]:
    """Get a warranty claim by ID."""
    stmt = select(WarrantyClaim).where(WarrantyClaim.id == claim_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pending_claims(session: AsyncSession) -> list[WarrantyClaim]:
    """Get all pending warranty claims (for admin)."""
    stmt = (
        select(WarrantyClaim)
        .where(WarrantyClaim.status == WarrantyClaimStatus.PENDING)
        .order_by(WarrantyClaim.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_claims_for_order(
    session: AsyncSession, order_id: int
) -> list[WarrantyClaim]:
    """Get all warranty claims for a specific order."""
    stmt = (
        select(WarrantyClaim)
        .where(WarrantyClaim.order_id == order_id)
        .order_by(WarrantyClaim.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_status(
    session: AsyncSession,
    claim_id: int,
    status: WarrantyClaimStatus,
    replacement_inventory_id: Optional[int] = None,
    admin_notes: Optional[str] = None,
) -> Optional[WarrantyClaim]:
    """Update a claim's status."""
    claim = await get_by_id(session, claim_id)
    if claim is None:
        return None
    claim.status = status
    claim.resolved_at = datetime.now(timezone.utc)
    if replacement_inventory_id is not None:
        claim.replacement_inventory_id = replacement_inventory_id
    if admin_notes is not None:
        claim.admin_notes = admin_notes
    await session.flush()
    return claim
