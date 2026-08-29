"""Top-up service — balance credit via crypto payment."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

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

    order_id = f"TOPUP-{user_id}-{int(datetime.now(timezone.utc).timestamp())}"

    bot_username = settings.support_username or "CloudDeals"
    return_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me"

    result = await provider.create_invoice(
        price_amount=amount,
        price_currency=currency.upper() if provider.provider_name == "cryptomus" else currency.lower(),
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


async def process_topup_webhook(
    session: AsyncSession,
    provider_invoice_id: str,
    provider_name: str,
    status: str,
) -> Optional[dict]:
    """Process a top-up payment webhook.

    Returns:
        Dict with 'topup' and 'action', or None if not a top-up.
    """
    topup = await topup_repo.get_by_provider_invoice_id(
        session, provider_name, provider_invoice_id
    )
    if topup is None:
        return None

    # Already credited
    if topup.status == TopUpStatus.PAID:
        return {"topup": topup, "action": "skipped"}

    if status in ("finished", "paid", "paid_over"):
        topup = await topup_repo.update_status(
            session, topup.id, TopUpStatus.PAID,
            confirmed_at=datetime.now(timezone.utc),
        )
        # Credit balance
        await user_service.credit_balance(session, topup.user_id, topup.amount)
        logger.info("Top-up completed: user_id=%s amount=%s", topup.user_id, topup.amount)
        return {"topup": topup, "action": "credited"}

    elif status in ("expired", "failed", "cancel", "fail", "system_fail"):
        await topup_repo.update_status(session, topup.id, TopUpStatus.EXPIRED)
        return {"topup": topup, "action": "expired"}

    return {"topup": topup, "action": "updated"}
