"""Crypto payment webhook endpoints (NOWPayments & Cryptomus IPN)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, Response

from app.database.database import get_session
from app.payments import get_payment_provider
from app.services import delivery_service, payment_service, topup_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/cryptomus")
async def cryptomus_webhook(request: Request) -> Response:
    """Handle Cryptomus payment webhook.

    This endpoint:
    1. Reads raw request body.
    2. Verifies the Cryptomus MD5+Base64 signature.
    3. Processes the payment notification idempotently.
    4. Triggers automatic product delivery when payment completes.
    """
    body = await request.body()
    headers = dict(request.headers)

    provider = get_payment_provider("cryptomus")

    # Verify webhook signature
    if not provider.verify_webhook(headers, body):
        logger.warning("Cryptomus webhook signature verification FAILED")
        return Response(status_code=200, content="signature_invalid")

    try:
        webhook_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Cryptomus webhook body is not valid JSON")
        return Response(status_code=200, content="invalid_json")

    logger.info(
        "Cryptomus webhook received: uuid=%s status=%s order=%s",
        webhook_data.get("uuid"),
        webhook_data.get("status") or webhook_data.get("payment_status"),
        webhook_data.get("order_id"),
    )

    order_id_str = str(webhook_data.get("order_id", ""))

    # Top-up payment check
    if order_id_str.startswith("TOPUP-"):
        await _handle_topup_webhook(webhook_data, provider)
        return Response(status_code=200, content="ok")

    # Order purchase payment
    async with get_session() as session:
        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        if result is None:
            logger.warning("Cryptomus webhook did not match any payment record")
            return Response(status_code=200, content="no_match")

        order = result["order"]
        action = result["action"]

        if action == "fulfilled":
            await _deliver_order(order, session)

        logger.info(
            "Cryptomus webhook processed: order=%s action=%s",
            order.public_order_id, action,
        )

    return Response(status_code=200, content="ok")


@router.post("/nowpayments")
async def nowpayments_webhook(request: Request) -> Response:
    """Handle NOWPayments IPN webhook.

    This endpoint:
    1. Reads the raw body for signature verification
    2. Verifies the HMAC-SHA512 signature
    3. Processes the payment notification idempotently
    4. Triggers delivery if payment is finished
    5. Always returns 200 to acknowledge receipt
    """
    body = await request.body()
    headers = dict(request.headers)

    provider = get_payment_provider("nowpayments")

    # Verify webhook signature
    if not provider.verify_webhook(headers, body):
        logger.warning("NOWPayments webhook signature verification FAILED")
        return Response(status_code=200, content="signature_invalid")

    # Parse webhook data
    try:
        webhook_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("NOWPayments webhook body is not valid JSON")
        return Response(status_code=200, content="invalid_json")

    logger.info(
        "NOWPayments webhook received: payment_id=%s status=%s order=%s",
        webhook_data.get("payment_id"),
        webhook_data.get("payment_status"),
        webhook_data.get("order_id"),
    )

    order_id_str = webhook_data.get("order_id", "")

    # Check if this is a top-up payment
    if order_id_str.startswith("TOPUP-"):
        await _handle_topup_webhook(webhook_data, provider)
        return Response(status_code=200, content="ok")

    # Process as order payment
    async with get_session() as session:
        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        if result is None:
            logger.warning("NOWPayments webhook did not match any payment record")
            return Response(status_code=200, content="no_match")

        order = result["order"]
        action = result["action"]

        # Trigger Telegram delivery for fulfilled orders
        if action == "fulfilled":
            await _deliver_order(order, session)

        logger.info(
            "NOWPayments webhook processed: order=%s action=%s",
            order.public_order_id, action,
        )

    return Response(status_code=200, content="ok")


async def _handle_topup_webhook(webhook_data: dict, provider) -> None:
    """Handle webhook for top-up payments."""
    async with get_session() as session:
        invoice_id = str(webhook_data.get("uuid") or webhook_data.get("invoice_id", ""))
        status = str(webhook_data.get("status") or webhook_data.get("payment_status", "")).lower()

        result = await topup_service.process_topup_webhook(
            session,
            provider_invoice_id=invoice_id,
            provider_name=provider.provider_name,
            status=status,
        )

        if result and result["action"] == "credited":
            # Notify user via Telegram
            topup = result["topup"]
            try:
                from app.bot.bot import get_bot_instance
                bot = get_bot_instance()
                if bot:
                    from app.database.repositories import user_repo
                    user = await user_repo.get_by_id(session, topup.user_id)
                    if user:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=(
                                f"✅ *Top-Up Confirmed!*\n\n"
                                f"💰 Amount: ${topup.amount}\n"
                                f"💳 New balance has been credited.\n\n"
                                f"Thank you! ☁️"
                            ),
                            parse_mode="Markdown",
                        )
            except Exception as e:
                logger.error("Failed to send top-up notification: %s", e)


async def _deliver_order(order, session) -> None:
    """Send the fulfilled order's product to the customer via Telegram."""
    try:
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
        if bot is None:
            logger.error("Bot instance not available for delivery")
            return

        from app.database.repositories import inventory_repo, user_repo
        user = await user_repo.get_by_id(session, order.user_id)
        if user is None:
            logger.error("User not found for delivery: order=%s", order.public_order_id)
            return

        # Get all inventory items linked to this order
        items = await inventory_repo.get_items_by_order_id(session, order.id)
        contents = [item.content for item in items if item.content]

        # Fallback to single inventory_id
        if not contents and order.inventory_id:
            item = await inventory_repo.get_item_by_id(session, order.inventory_id)
            if item:
                contents = [item.content]

        if not contents:
            logger.error("No delivery content for order=%s", order.public_order_id)
            return

        # Group inventory items by product
        items_by_product = {}
        for item in items:
            p_name = item.product.name if hasattr(item, 'product') and item.product else (order.product.name if order.product else "Product")
            items_by_product.setdefault(p_name, []).append(item.content)

        if len(items_by_product) > 1:
            await delivery_service.deliver_cart_order_to_user(
                bot, user.telegram_id, order, items_by_product
            )
        else:
            p_name = list(items_by_product.keys())[0] if items_by_product else (order.product.name if order.product else "Product")
            await delivery_service.deliver_bulk_to_user(
                bot, user.telegram_id, order, contents, p_name
            )

    except Exception as e:
        logger.error(
            "Delivery failed for order=%s: %s",
            order.public_order_id, e,
        )
