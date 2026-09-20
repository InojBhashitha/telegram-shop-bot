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


@router.post("/binancepay")
async def binancepay_webhook(request: Request) -> Response:
    """Handle Binance Pay IPN webhook.

    This endpoint:
    1. Reads raw request body and headers
    2. Validates Binance Pay webhook notification
    3. Parses the notification data payload
    4. Processes payment updates and triggers order fulfillment
    5. Returns {"returnCode": "SUCCESS", "returnMessage": null} as required by Binance
    """
    body = await request.body()
    headers = dict(request.headers)

    provider = get_payment_provider("binancepay")

    # Verify webhook headers and format
    if not provider.verify_webhook(headers, body):
        logger.warning("Binance Pay webhook verification FAILED")
        fail_body = json.dumps({"returnCode": "FAIL", "returnMessage": "verification_failed"})
        return Response(status_code=200, content=fail_body, media_type="application/json")

    try:
        webhook_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Binance Pay webhook body is not valid JSON")
        fail_body = json.dumps({"returnCode": "FAIL", "returnMessage": "invalid_json"})
        return Response(status_code=200, content=fail_body, media_type="application/json")

    # Parse inner data if stringified JSON
    data_raw = webhook_data.get("data", {})
    if isinstance(data_raw, str):
        try:
            data_obj = json.loads(data_raw)
        except Exception:
            data_obj = {}
    elif isinstance(data_raw, dict):
        data_obj = data_raw
    else:
        data_obj = {}

    merchant_trade_no = str(data_obj.get("merchantTradeNo", ""))
    biz_status = webhook_data.get("bizStatus")
    prepay_id = str(data_obj.get("prepayId") or webhook_data.get("bizId", ""))

    logger.info(
        "Binance Pay webhook received: tradeNo=%s prepayId=%s bizStatus=%s",
        merchant_trade_no, prepay_id, biz_status,
    )

    success_resp = json.dumps({"returnCode": "SUCCESS", "returnMessage": None})

    # Check if this is a top-up payment
    if merchant_trade_no.upper().startswith("TOPUP"):
        topup_data = {
            "invoice_id": prepay_id,
            "prepay_id": prepay_id,
            "uuid": prepay_id,
            "status": data_obj.get("status") or biz_status or "",
        }
        await _handle_topup_webhook(topup_data, provider)
        return Response(status_code=200, content=success_resp, media_type="application/json")

    # Process as order payment
    async with get_session() as session:
        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        if result is None:
            logger.warning("Binance Pay webhook did not match any payment record")
            return Response(status_code=200, content=success_resp, media_type="application/json")

        order = result["order"]
        action = result["action"]

        # Trigger Telegram delivery for fulfilled orders
        if action == "fulfilled":
            await _deliver_order(order, session)

        logger.info(
            "Binance Pay webhook processed: order=%s action=%s",
            order.public_order_id, action,
        )

    return Response(status_code=200, content=success_resp, media_type="application/json")


@router.post("/cryptopay")
async def cryptopay_webhook(request: Request) -> Response:
    """Handle Crypto Pay (@CryptoBot) webhook notification."""
    body = await request.body()
    headers = dict(request.headers)

    provider = get_payment_provider("cryptopay")

    if not provider.verify_webhook(headers, body):
        logger.warning("Crypto Pay webhook signature verification FAILED")
        return Response(status_code=400, content="signature_invalid")

    try:
        webhook_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Crypto Pay webhook body is not valid JSON")
        return Response(status_code=400, content="invalid_json")

    p_data = webhook_data.get("payload") if isinstance(webhook_data.get("payload"), dict) else webhook_data
    invoice_id = str(p_data.get("invoice_id") or "")
    order_id_str = str(p_data.get("payload") or "")
    status = str(p_data.get("status") or "").lower()

    logger.info(
        "Crypto Pay webhook received: invoice=%s order=%s status=%s",
        invoice_id, order_id_str, status,
    )

    if order_id_str.startswith("TOPUP"):
        topup_data = {
            "invoice_id": invoice_id,
            "uuid": invoice_id,
            "status": status,
        }
        await _handle_topup_webhook(topup_data, provider)
        return Response(status_code=200, content="ok")

    async with get_session() as session:
        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        if result is None:
            logger.warning("Crypto Pay webhook did not match any payment record")
            return Response(status_code=200, content="no_match")

        order = result["order"]
        action = result["action"]

        if action == "fulfilled":
            await _deliver_order(order, session)

        logger.info(
            "Crypto Pay webhook processed: order=%s action=%s",
            order.public_order_id, action,
        )

    return Response(status_code=200, content="ok")


@router.post("/oxapay")
async def oxapay_webhook(request: Request) -> Response:
    """Handle OxaPay IPN callback webhook."""
    body = await request.body()
    headers = dict(request.headers)

    provider = get_payment_provider("oxapay")

    if not provider.verify_webhook(headers, body):
        logger.warning("OxaPay webhook signature verification FAILED")
        return Response(status_code=400, content="signature_invalid")

    try:
        webhook_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("OxaPay webhook body is not valid JSON")
        return Response(status_code=400, content="invalid_json")

    track_id = str(webhook_data.get("trackId") or "")
    order_id_str = str(webhook_data.get("orderId") or "")
    status = str(webhook_data.get("status") or "").lower()

    logger.info(
        "OxaPay webhook received: trackId=%s order=%s status=%s",
        track_id, order_id_str, status,
    )

    if order_id_str.startswith("TOPUP"):
        topup_data = {
            "invoice_id": track_id,
            "uuid": track_id,
            "status": status,
        }
        await _handle_topup_webhook(topup_data, provider)
        return Response(status_code=200, content="ok")

    async with get_session() as session:
        result = await payment_service.process_webhook(
            session, provider, webhook_data
        )

        if result is None:
            logger.warning("OxaPay webhook did not match any payment record")
            return Response(status_code=200, content="no_match")

        order = result["order"]
        action = result["action"]

        if action == "fulfilled":
            await _deliver_order(order, session)

        logger.info(
            "OxaPay webhook processed: order=%s action=%s",
            order.public_order_id, action,
        )

    return Response(status_code=200, content="ok")


async def _handle_topup_webhook(webhook_data: dict, provider) -> None:
    """Handle webhook for top-up payments."""
    async with get_session() as session:
        invoice_id = str(
            webhook_data.get("uuid")
            or webhook_data.get("invoice_id")
            or webhook_data.get("prepayId")
            or webhook_data.get("prepay_id")
            or ""
        )
        status = str(
            webhook_data.get("status")
            or webhook_data.get("payment_status")
            or webhook_data.get("bizStatus")
            or ""
        ).lower()

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
