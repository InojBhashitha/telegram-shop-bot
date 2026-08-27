"""Support ticket repository."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SupportTicket, TicketStatus


async def create(
    session: AsyncSession,
    user_id: int,
    subject: str,
    message: str,
) -> SupportTicket:
    """Create a new support ticket."""
    ticket = SupportTicket(
        user_id=user_id,
        subject=subject,
        message=message,
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def get_by_id(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
    """Get a ticket by ID."""
    stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_tickets(
    session: AsyncSession,
    user_id: int,
    offset: int = 0,
    limit: int = 10,
) -> list[SupportTicket]:
    """List tickets for a user."""
    stmt = (
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_all(
    session: AsyncSession,
    status: Optional[TicketStatus] = None,
    offset: int = 0,
    limit: int = 20,
) -> list[SupportTicket]:
    """List all tickets (admin), optionally filtered by status."""
    stmt = select(SupportTicket)
    if status is not None:
        stmt = stmt.where(SupportTicket.status == status)
    stmt = stmt.order_by(SupportTicket.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def reply(
    session: AsyncSession,
    ticket_id: int,
    admin_reply: str,
) -> Optional[SupportTicket]:
    """Admin replies to a ticket."""
    stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        return None
    ticket.admin_reply = admin_reply
    ticket.status = TicketStatus.REPLIED
    await session.flush()
    return ticket


async def close_ticket(session: AsyncSession, ticket_id: int) -> None:
    """Close a ticket."""
    stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket:
        ticket.status = TicketStatus.CLOSED
        await session.flush()


async def count_open(session: AsyncSession) -> int:
    """Count open tickets."""
    stmt = select(func.count(SupportTicket.id)).where(
        SupportTicket.status == TicketStatus.OPEN
    )
    result = await session.execute(stmt)
    return result.scalar_one()
