"""Store settings repository (key-value configuration)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import FAQ, StoreSettings


# ---------------------------------------------------------------------------
# Store Settings (key-value)
# ---------------------------------------------------------------------------

async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    """Get a setting value by key."""
    stmt = select(StoreSettings.value).where(StoreSettings.key == key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    """Set a setting value (upsert)."""
    stmt = select(StoreSettings).where(StoreSettings.key == key)
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        setting = StoreSettings(key=key, value=value)
        session.add(setting)
    await session.flush()


async def get_all_settings(session: AsyncSession) -> dict[str, str]:
    """Get all settings as a dictionary."""
    stmt = select(StoreSettings)
    result = await session.execute(stmt)
    return {s.key: s.value for s in result.scalars().all()}


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------

async def list_active_faqs(session: AsyncSession) -> list[FAQ]:
    """List all active FAQ entries ordered by sort_order."""
    stmt = (
        select(FAQ)
        .where(FAQ.active == True)
        .order_by(FAQ.sort_order, FAQ.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_faq(
    session: AsyncSession,
    question: str,
    answer: str,
    sort_order: int = 0,
) -> FAQ:
    """Create a new FAQ entry."""
    faq = FAQ(question=question, answer=answer, sort_order=sort_order)
    session.add(faq)
    await session.flush()
    return faq


async def update_faq(
    session: AsyncSession,
    faq_id: int,
    **kwargs,
) -> Optional[FAQ]:
    """Update a FAQ entry."""
    stmt = select(FAQ).where(FAQ.id == faq_id)
    result = await session.execute(stmt)
    faq = result.scalar_one_or_none()
    if faq is None:
        return None
    for key, value in kwargs.items():
        if hasattr(faq, key):
            setattr(faq, key, value)
    await session.flush()
    return faq


async def delete_faq(session: AsyncSession, faq_id: int) -> None:
    """Deactivate a FAQ entry."""
    stmt = select(FAQ).where(FAQ.id == faq_id)
    result = await session.execute(stmt)
    faq = result.scalar_one_or_none()
    if faq:
        faq.active = False
        await session.flush()
