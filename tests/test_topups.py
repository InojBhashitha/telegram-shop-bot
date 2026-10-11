"""Tests for top-up balance service and tiered deposit bonuses."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import TopUp, TopUpStatus, User
from app.database.repositories import topup_repo
from app.services import topup_service


def test_calculate_deposit_bonus_tiers():
    """Test deposit bonus calculation across different deposit amounts."""
    # Under $10: No bonus
    b5, pct5, label5 = topup_service.calculate_deposit_bonus(Decimal("5.00"))
    assert b5 == Decimal("0.00")
    assert pct5 == 0.0
    assert label5 == ""

    # $10 - $19: +5% Starter Bonus
    b10, pct10, label10 = topup_service.calculate_deposit_bonus(Decimal("10.00"))
    assert b10 == Decimal("0.50")
    assert pct10 == 5.0
    assert "Starter" in label10

    # $20 - $49: +7.5% Pro Bonus
    b20, pct20, label20 = topup_service.calculate_deposit_bonus(Decimal("20.00"))
    assert b20 == Decimal("1.50")
    assert pct20 == 7.5
    assert "Pro" in label20

    # $50 - $99: +10% Mega Bonus
    b50, pct50, label50 = topup_service.calculate_deposit_bonus(Decimal("50.00"))
    assert b50 == Decimal("5.00")
    assert pct50 == 10.0
    assert "Mega" in label50

    # $100+: +15% VIP Bonus
    b100, pct100, label100 = topup_service.calculate_deposit_bonus(Decimal("100.00"))
    assert b100 == Decimal("15.00")
    assert pct100 == 15.0
    assert "VIP" in label100

    b200, pct200, label200 = topup_service.calculate_deposit_bonus(Decimal("200.00"))
    assert b200 == Decimal("30.00")
    assert pct200 == 15.0


def test_calculate_deposit_bonus_disabled(monkeypatch):
    """Test that bonus returns zero when deposit bonuses are disabled."""
    settings = get_settings()
    monkeypatch.setattr(settings, "deposit_bonus_enabled", False)

    b100, pct100, label100 = topup_service.calculate_deposit_bonus(Decimal("100.00"))
    assert b100 == Decimal("0.00")
    assert pct100 == 0.0
    assert label100 == ""

    tiers = topup_service.get_deposit_bonus_tiers()
    assert tiers == []


def test_get_deposit_bonus_tiers():
    """Test retrieving active bonus tiers."""
    tiers = topup_service.get_deposit_bonus_tiers()
    assert len(tiers) == 4
    assert tiers[0]["min_amount"] == 10.0
    assert tiers[0]["badge"] == "+5%"
    assert tiers[3]["min_amount"] == 100.0
    assert tiers[3]["badge"] == "+15%"


@pytest.mark.asyncio
async def test_create_topup(session: AsyncSession, sample_data: dict):
    """Test creating a top-up invoice."""
    user = sample_data["user"]

    mock_provider = MagicMock()
    mock_provider.provider_name = "oxapay"
    mock_result = MagicMock()
    mock_result.invoice_id = "inv_test_123"
    mock_result.payment_url = "https://oxapay.com/pay/inv_test_123"
    mock_provider.create_invoice = AsyncMock(return_value=mock_result)

    res = await topup_service.create_topup(
        session, mock_provider, user_id=user.id, amount=Decimal("20.00")
    )
    assert res["payment_url"] == "https://oxapay.com/pay/inv_test_123"
    assert res["topup"].user_id == user.id
    assert res["topup"].amount == Decimal("20.00")
    assert res["topup"].status == TopUpStatus.PENDING


@pytest.mark.asyncio
async def test_process_topup_webhook_with_bonus(session: AsyncSession, sample_data: dict):
    """Test top-up webhook processing applies deposit bonus to user balance."""
    user = sample_data["user"]
    assert user.balance == Decimal("0.00")

    # Create a topup of $50 (Mega Bonus: +10% = $5.00)
    topup = await topup_repo.create(
        session,
        user_id=user.id,
        amount=Decimal("50.00"),
        provider="oxapay",
        currency="USD",
        provider_invoice_id="inv_50",
        payment_url="https://pay.example.com/50",
    )

    # Process successful payment webhook
    res = await topup_service.process_topup_webhook(
        session,
        provider_invoice_id="inv_50",
        provider_name="oxapay",
        status="paid",
    )

    assert res is not None
    assert res["action"] == "credited"
    assert res["deposit_amount"] == Decimal("50.00")
    assert res["bonus_amount"] == Decimal("5.00")
    assert res["bonus_percent"] == 10.0
    assert res["total_credit"] == Decimal("55.00")

    # Verify user received deposit + bonus
    await session.refresh(user)
    assert user.balance == Decimal("55.00")

    # Verify idempotency — processing again skips
    repeat_res = await topup_service.process_topup_webhook(
        session,
        provider_invoice_id="inv_50",
        provider_name="oxapay",
        status="paid",
    )
    assert repeat_res["action"] == "skipped"
    await session.refresh(user)
    assert user.balance == Decimal("55.00")  # Balance unchanged


@pytest.mark.asyncio
async def test_process_topup_webhook_expired(session: AsyncSession, sample_data: dict):
    """Test top-up webhook processing handles expiration."""
    user = sample_data["user"]
    topup = await topup_repo.create(
        session,
        user_id=user.id,
        amount=Decimal("10.00"),
        provider="oxapay",
        currency="USD",
        provider_invoice_id="inv_expired",
        payment_url="https://pay.example.com/expired",
    )

    res = await topup_service.process_topup_webhook(
        session,
        provider_invoice_id="inv_expired",
        provider_name="oxapay",
        status="expired",
    )
    assert res["action"] == "expired"
    assert res["topup"].status == TopUpStatus.EXPIRED

    await session.refresh(user)
    assert user.balance == Decimal("0.00")
