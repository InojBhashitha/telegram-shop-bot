"""Top-up service — balance credit via crypto payment."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import TopUpStatus
from app.database.repositories import topup_repo
from app.payments.base import PaymentProvider
from app.services import user_service

logger = logging.getLogger(__name__)


async def create_topup(
    session: AsyncSession,
    provider: PaymentProvider,
    user_id: int,
    amount: Decimal,
    currency: str = "USD",
) -> dict:
    """Create a top-up payment.

    Returns:
        Dict with 'topup' model and 'payment_url'.
    """
    settings = get_settings()
    ipn_url = f"{settings.webhook_base_url}/webhooks/crypto/{provider.provider_name}"

    order_id = f"TOPUP-{user_id}-{int(datetime.now(UTC).timestamp())}"

    bot_username = settings.support_username or "CloudDeals"
    return_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me"

    result = await provider.create_invoice(
        price_amount=amount,
        price_currency=currency.upper() if provider.provider_name in ("cryptomus", "binancepay", "cryptopay", "oxapay") else currency.lower(),
        order_id=order_id,
        order_description=f"Cloud Deals Top-Up ${amount}",
        ipn_callback_url=ipn_url,
        success_url=return_url,
        cancel_url=return_url,
    )

    topup = await topup_repo.create(
        session,
        user_id=user_id,
        amount=amount,
        provider=provider.provider_name,
        currency=currency,
        provider_invoice_id=result.invoice_id,
        payment_url=result.payment_url,
    )

    logger.info("Top-up created: user_id=%s amount=%s", user_id, amount)

    return {"topup": topup, "payment_url": result.payment_url}


def calculate_deposit_bonus(amount: Decimal | float) -> tuple[Decimal, float, str]:
    """Calculate deposit bonus amount, bonus percentage, and tier label based on deposit amount.

    Tiers:
    - $100+ : +15.0% (VIP Bonus)
    - $50+  : +10.0% (Mega Bonus)
    - $20+  : +7.5%  (Pro Bonus)
    - $10+  : +5.0%  (Starter Bonus)
    - <$10  : 0%

    Returns:
        (bonus_amount, bonus_percent, tier_label)
    """
    settings = get_settings()
    if not settings.deposit_bonus_enabled:
        return Decimal("0.00"), 0.0, ""

    amt = Decimal(str(amount))
    t4_min = Decimal(str(settings.deposit_bonus_tier4_min))
    t3_min = Decimal(str(settings.deposit_bonus_tier3_min))
    t2_min = Decimal(str(settings.deposit_bonus_tier2_min))
    t1_min = Decimal(str(settings.deposit_bonus_tier1_min))

    if amt >= t4_min:
        pct = settings.deposit_bonus_tier4_percent
        label = "VIP Bonus"
    elif amt >= t3_min:
        pct = settings.deposit_bonus_tier3_percent
        label = "Mega Bonus"
    elif amt >= t2_min:
        pct = settings.deposit_bonus_tier2_percent
        label = "Pro Bonus"
    elif amt >= t1_min:
        pct = settings.deposit_bonus_tier1_percent
        label = "Starter Bonus"
    else:
        pct = 0.0
        label = ""

    if pct > 0:
        bonus = (amt * Decimal(str(pct)) / Decimal(100)).quantize(Decimal("0.01"))
    else:
        bonus = Decimal("0.00")

    return bonus, pct, label


def get_deposit_bonus_tiers() -> list[dict]:
    """Return active deposit bonus tiers for UI display."""
    settings = get_settings()
    if not settings.deposit_bonus_enabled:
        return []
    return [
        {
            "min_amount": settings.deposit_bonus_tier1_min,
            "percent": settings.deposit_bonus_tier1_percent,
            "label": "Starter Bonus",
            "badge": f"+{settings.deposit_bonus_tier1_percent:g}%",
        },
        {
            "min_amount": settings.deposit_bonus_tier2_min,
            "percent": settings.deposit_bonus_tier2_percent,
            "label": "Pro Bonus",
            "badge": f"+{settings.deposit_bonus_tier2_percent:g}%",
        },
        {
            "min_amount": settings.deposit_bonus_tier3_min,
            "percent": settings.deposit_bonus_tier3_percent,
            "label": "Mega Bonus",
            "badge": f"+{settings.deposit_bonus_tier3_percent:g}%",
        },
        {
            "min_amount": settings.deposit_bonus_tier4_min,
            "percent": settings.deposit_bonus_tier4_percent,
            "label": "VIP Bonus",
            "badge": f"+{settings.deposit_bonus_tier4_percent:g}%",
        },
    ]


async def process_topup_webhook(
    session: AsyncSession,
    provider_invoice_id: str,
    provider_name: str,
    status: str,
) -> dict | None:
    """Process a top-up payment webhook.

    Returns:
        Dict with 'topup', 'action', and bonus details, or None if not a top-up.
    """
    topup = await topup_repo.get_by_provider_invoice_id(
        session, provider_name, provider_invoice_id
    )
    if topup is None:
        return None

    # Already credited
    if topup.status == TopUpStatus.PAID:
        return {"topup": topup, "action": "skipped"}

    status_lower = status.lower()
    if status_lower in ("finished", "paid", "paid_over", "pay_success", "success"):
        topup = await topup_repo.update_status(
            session, topup.id, TopUpStatus.PAID,
            confirmed_at=datetime.now(UTC),
        )
        # Calculate deposit bonus
        bonus_amount, bonus_percent, tier_label = calculate_deposit_bonus(topup.amount)
        total_credit = (topup.amount + bonus_amount).quantize(Decimal("0.01"))

        # Credit total to user balance
        await user_service.credit_balance(session, topup.user_id, total_credit)
        logger.info(
            "Top-up completed: user_id=%s deposit=%s bonus=%s total_credited=%s",
            topup.user_id,
            topup.amount,
            bonus_amount,
            total_credit,
        )
        return {
            "topup": topup,
            "action": "credited",
            "deposit_amount": topup.amount,
            "bonus_amount": bonus_amount,
            "bonus_percent": bonus_percent,
            "tier_label": tier_label,
            "total_credit": total_credit,
        }

    elif status_lower in ("expired", "failed", "cancel", "fail", "system_fail", "pay_closed", "canceled", "cancelled"):
        await topup_repo.update_status(session, topup.id, TopUpStatus.EXPIRED)
        return {"topup": topup, "action": "expired"}

    return {"topup": topup, "action": "updated"}
