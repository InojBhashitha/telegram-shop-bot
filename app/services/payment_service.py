"""Payment service — payment creation, webhook processing, and fulfillment orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import OrderStatus, PaymentStatus
from app.database.repositories import order_repo, payment_repo
from app.payments.base import PaymentProvider
from app.services import order_service

logger = logging.getLogger(__name__)


# Mapping from NOWPayments status strings to internal PaymentStatus
_NOWPAYMENTS_STATUS_MAP: dict[str, PaymentStatus] = {
    "waiting": PaymentStatus.WAITING,
    "confirming": PaymentStatus.CONFIRMING,
    "confirmed": PaymentStatus.CONFIRMED,
    "sending": PaymentStatus.SENDING,
    "finished": PaymentStatus.FINISHED,
    "partially_paid": PaymentStatus.PARTIALLY_PAID,
    "failed": PaymentStatus.FAILED,
    "expired": PaymentStatus.EXPIRED,
    "refunded": PaymentStatus.REFUNDED,
}

# Mapping from Cryptomus status strings to internal PaymentStatus
_CRYPTOMUS_STATUS_MAP: dict[str, PaymentStatus] = {
    "check": PaymentStatus.CONFIRMING,
    "process": PaymentStatus.CONFIRMING,
    "confirm_check": PaymentStatus.CONFIRMING,
    "paid": PaymentStatus.FINISHED,
    "paid_over": PaymentStatus.FINISHED,
    "fail": PaymentStatus.FAILED,
    "cancel": PaymentStatus.FAILED,
    "system_fail": PaymentStatus.FAILED,
    "wrong_amount": PaymentStatus.PARTIALLY_PAID,
    "refund_process": PaymentStatus.REFUNDED,
    "refund_fail": PaymentStatus.REFUNDED,
    "refund_paid": PaymentStatus.REFUNDED,
}

# Internal payment statuses that map to order becoming PAID
_PAID_STATUSES = {PaymentStatus.FINISHED}

# Internal payment statuses that indicate processing
_PROCESSING_STATUSES = {PaymentStatus.CONFIRMING, PaymentStatus.CONFIRMED, PaymentStatus.SENDING}

# Terminal statuses — no further transitions expected
_TERMINAL_STATUSES = {
    PaymentStatus.FINISHED,
    PaymentStatus.FAILED,
    PaymentStatus.EXPIRED,
    PaymentStatus.REFUNDED,
}


async def create_payment_for_order(
    session: AsyncSession,
    provider: PaymentProvider,
    order_id: int,
) -> dict:
    """Create a crypto payment for an existing order.

    Returns:
        Dict with 'payment' model and 'payment_url'.
    """
    order = await order_repo.get_by_id(session, order_id)
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    settings = get_settings()
    ipn_url = f"{settings.webhook_base_url}/webhooks/crypto/{provider.provider_name}"

    bot_username = settings.support_username or "CloudDeals"
    return_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me"

    # Create invoice via payment provider
    result = await provider.create_invoice(
        price_amount=order.amount,
        price_currency=order.currency.upper() if provider.provider_name == "cryptomus" else order.currency.lower(),
        order_id=order.public_order_id,
        order_description=f"Cloud Deals Order {order.public_order_id}",
        ipn_callback_url=ipn_url,
        success_url=return_url,
        cancel_url=return_url,
    )

    # Save payment record
    payment = await payment_repo.create(
        session,
        order_id=order.id,
        provider=provider.provider_name,
        requested_amount=order.amount,
        provider_invoice_id=result.invoice_id,
        provider_payment_id=result.payment_id,
        payment_url=result.payment_url,
        payment_address=result.payment_address,
    )

    logger.info(
        "Payment created: provider=%s order=%s invoice_id=%s",
        provider.provider_name, order.public_order_id, result.invoice_id,
    )

    return {"payment": payment, "payment_url": result.payment_url}


async def process_webhook(
    session: AsyncSession,
    provider: PaymentProvider,
    webhook_data: dict,
) -> Optional[dict]:
    """Process a payment webhook/IPN notification.

    This is the CRITICAL idempotent handler that:
    1. Finds the payment by provider payment ID or order ID
    2. Checks if already processed (idempotency)
    3. Updates payment status
    4. Updates order status
    5. Triggers fulfillment if payment is finished

    Returns:
        Dict with 'order', 'action' ('fulfilled', 'updated', 'skipped'),
        or None if payment not found.
    """
    if provider.provider_name == "cryptomus":
        provider_payment_id = str(webhook_data.get("uuid") or webhook_data.get("payment_id", ""))
        provider_status = str(webhook_data.get("payment_status") or webhook_data.get("status", "")).lower()
        order_id_str = webhook_data.get("order_id", "")
        actually_paid = webhook_data.get("payment_amount") or webhook_data.get("payer_amount")
        pay_currency = webhook_data.get("payer_currency") or webhook_data.get("currency")
        internal_status = _CRYPTOMUS_STATUS_MAP.get(provider_status, PaymentStatus.WAITING)
    else:
        provider_payment_id = str(webhook_data.get("payment_id", ""))
        provider_status = str(webhook_data.get("payment_status", "")).lower()
        order_id_str = webhook_data.get("order_id", "")
        actually_paid = webhook_data.get("actually_paid")
        pay_currency = webhook_data.get("pay_currency")
        internal_status = _NOWPAYMENTS_STATUS_MAP.get(provider_status, PaymentStatus.WAITING)

    if not provider_payment_id and not order_id_str:
        logger.warning("Webhook missing payment_id and order_id")
        return None

    # Find payment by invoice/order
    payment = None
    if order_id_str:
        order = await order_repo.get_by_public_id(session, order_id_str)
        if order:
            payment = await payment_repo.get_by_order_id(session, order.id)

    # Also try by provider payment ID
    if payment is None:
        payment = await payment_repo.get_by_provider_payment_id(
            session, provider.provider_name, provider_payment_id
        )

    if payment is None:
        logger.warning(
            "Webhook for unknown payment: provider_id=%s order=%s",
            provider_payment_id, order_id_str,
        )
        return None

    # Get the associated order
    order = await order_repo.get_by_id(session, payment.order_id)
    if order is None:
        logger.error("Payment %s has no associated order", payment.id)
        return None

    # --- IDEMPOTENCY CHECK ---
    # If payment is already in a terminal state, skip processing
    if payment.status in _TERMINAL_STATUSES:
        logger.info(
            "Webhook skipped (already terminal): order=%s status=%s",
            order.public_order_id, payment.status.value,
        )
        return {"order": order, "action": "skipped"}

    # Update provider payment ID if not yet set
    if not payment.provider_payment_id:
        payment.provider_payment_id = provider_payment_id
        await session.flush()

    # Update payment status
    extra = {}
    if actually_paid is not None:
        extra["received_amount"] = Decimal(str(actually_paid))
    if pay_currency:
        extra["payment_currency"] = str(pay_currency)
    if internal_status in _PAID_STATUSES:
        extra["confirmed_at"] = datetime.now(timezone.utc)

    await payment_repo.update_status(
        session, payment.id, internal_status, **extra
    )

    logger.info(
        "Payment updated: order=%s status=%s→%s",
        order.public_order_id, payment.status.value, internal_status.value,
    )

    # --- ORDER STATUS TRANSITIONS ---
    action = "updated"

    if internal_status in _PROCESSING_STATUSES:
        if order.status == OrderStatus.PENDING_PAYMENT:
            await order_repo.update_status(
                session, order.id, OrderStatus.PAYMENT_PROCESSING
            )

    elif internal_status in _PAID_STATUSES:
        # Verify amount matches (prevent underpayment fraud)
        if actually_paid is not None:
            received = Decimal(str(actually_paid))
            # Note: received is in crypto, requested is in fiat
            # The provider handles conversion; we trust "finished" status
            # but log for audit
            logger.info(
                "Payment amount: requested=%s %s, received=%s %s",
                payment.requested_amount, order.currency,
                received, pay_currency,
            )

        # Mark order paid
        if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
            await order_service.mark_paid(session, order.id)

            # Attempt fulfillment
            try:
                result = await order_service.fulfill_order(session, order.id)
                if result:
                    action = "fulfilled"
                    logger.info("Order auto-fulfilled: %s", order.public_order_id)
            except order_service.OrderError as e:
                logger.error(
                    "Auto-fulfillment failed for %s: %s",
                    order.public_order_id, e,
                )
                action = "paid_not_fulfilled"

    elif internal_status == PaymentStatus.EXPIRED:
        if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
            await order_service.cancel_order(session, order.id)
            action = "expired"

    elif internal_status == PaymentStatus.FAILED:
        if order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
            await order_service.cancel_order(session, order.id)
            action = "failed"

    # Reload order to get final state
    order = await order_repo.get_by_id(session, order.id)
    return {"order": order, "action": action}


async def check_payment_status(
    session: AsyncSession,
    provider: PaymentProvider,
    order_id: int,
) -> Optional[str]:
    """Poll the provider for current payment status.

    This is for the "Check Payment" button — it queries the provider
    but does NOT update order status (that's only done via webhook).

    Returns:
        The provider status string, or None if payment not found.
    """
    payment = await payment_repo.get_by_order_id(session, order_id)
    if payment is None or not payment.provider_payment_id:
        return payment.status.value if payment else None

    try:
        result = await provider.get_payment_status(payment.provider_payment_id)
        return result.status
    except Exception as e:
        logger.warning("Failed to check payment status: %s", e)
        return payment.status.value
