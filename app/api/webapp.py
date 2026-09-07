"""Telegram Mini App (TMA) API router.

Provides REST endpoints for:
- Telegram initData cryptographic authentication (with dev/preview fallback)
- User profile & balance information
- Category and product catalog with live stock counts
- Cart operations (get, add, update, remove, clear)
- Checkout with Crypto (Cryptomus / NOWPayments) or Store Balance
- Live order status tracking, polling & digital credentials vault
- 10% First-Order Discount claiming
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database.database import get_session
from app.database.models import OrderStatus, PaymentStatus, User
from app.database.repositories import (
    cart_repo,
    category_repo,
    inventory_repo,
    order_repo,
    payment_repo,
    product_repo,
    user_repo,
)
from app.payments import get_payment_provider
from app.services import (
    cart_service,
    delivery_service,
    order_service,
    payment_service,
    user_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Cryptographic Validation of Telegram initData
# ---------------------------------------------------------------------------

def validate_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict[str, Any]]:
    """Validate Telegram WebApp initData string using HMAC-SHA256 signature verification.

    Specification:
    1. Parse query string into key-value pairs.
    2. Extract 'hash'.
    3. Sort remaining keys alphabetically and concatenate as 'key=value\n...'.
    4. secret_key = HMAC_SHA256(b"WebAppData", bot_token)
    5. calc_hash = HMAC_SHA256(secret_key, data_check_string).hexdigest()
    6. Verify calc_hash == hash in constant time.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Build data check string
        items = sorted(parsed.items(), key=lambda x: x[0])
        data_check_string = "\n".join(f"{k}={v}" for k, v in items)

        # Telegram secret key
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calc_hash, received_hash):
            logger.warning("Telegram initData hash mismatch")
            return None

        # Parse user JSON if present
        user_raw = parsed.get("user")
        user_data = json.loads(user_raw) if user_raw else {}
        parsed["user_data"] = user_data
        return parsed

    except Exception as e:
        logger.warning("Error parsing Telegram initData: %s", e)
        return None


# ---------------------------------------------------------------------------
# User Resolution Helper
# ---------------------------------------------------------------------------

async def resolve_user(
    session: AsyncSession,
    init_data: Optional[str] = None,
    telegram_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> User:
    """Resolve or create database user from Telegram initData or dev parameters."""
    settings = get_settings()

    tg_id: Optional[int] = None
    uname: Optional[str] = username
    fname: Optional[str] = first_name
    lname: Optional[str] = None

    # Try validating initData first
    if init_data:
        validated = validate_telegram_init_data(init_data, settings.bot_token)
        if validated and "user_data" in validated:
            ud = validated["user_data"]
            tg_id = ud.get("id")
            uname = ud.get("username", uname)
            fname = ud.get("first_name", fname)
            lname = ud.get("last_name")

    # Fallback to direct telegram_id (for dev mode or preview when running locally)
    if tg_id is None and telegram_id:
        tg_id = telegram_id

    # Fallback to demo user if no user specified
    if tg_id is None:
        tg_id = 999001
        uname = uname or "DemoUser"
        fname = fname or "Cloud"
        lname = lname or "Customer"

    res = await user_service.get_or_create_user(
        session,
        telegram_id=tg_id,
        username=uname,
        first_name=fname,
        last_name=lname,
    )
    return res["user"]


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class AuthRequest(BaseModel):
    init_data: Optional[str] = None
    dev_telegram_id: Optional[int] = None
    dev_username: Optional[str] = None
    dev_first_name: Optional[str] = None


class CartItemActionRequest(BaseModel):
    product_id: int
    quantity: int = 1
    init_data: Optional[str] = None
    telegram_id: Optional[int] = None


class CartUpdateQuantityRequest(BaseModel):
    product_id: int
    quantity: int
    init_data: Optional[str] = None
    telegram_id: Optional[int] = None


class CartRemoveRequest(BaseModel):
    product_id: int
    init_data: Optional[str] = None
    telegram_id: Optional[int] = None


class CheckoutRequest(BaseModel):
    payment_method: str = "crypto"  # "crypto" or "balance"
    init_data: Optional[str] = None
    telegram_id: Optional[int] = None


class ClaimDiscountRequest(BaseModel):
    init_data: Optional[str] = None
    telegram_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Authentication & User Profile Endpoints
# ---------------------------------------------------------------------------

@router.post("/auth")
async def auth_user(req: AuthRequest):
    """Authenticate Telegram WebApp user, returning user profile and state."""
    async with get_session() as session:
        user = await resolve_user(
            session,
            init_data=req.init_data,
            telegram_id=req.dev_telegram_id,
            username=req.dev_username,
            first_name=req.dev_first_name,
        )

        cart_count = await cart_repo.get_cart_item_count(session, user.id)
        settings = get_settings()

        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "balance": str(user.balance),
                "channel_discount_claimed": user.channel_discount_claimed,
                "channel_discount_used": user.channel_discount_used,
                "is_admin": settings.is_admin(user.telegram_id),
                "referral_code": user.referral_code,
            },
            "store": {
                "name": settings.store_name,
                "force_channel": settings.force_channel_id,
                "warranty_hours": settings.warranty_hours,
                "support_username": settings.support_username,
            },
            "cart_count": cart_count,
        }


@router.get("/user")
async def get_user_profile(
    init_data: Optional[str] = Query(None),
    telegram_id: Optional[int] = Query(None),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Get current user details and balance."""
    raw_init = init_data or x_telegram_init_data
    async with get_session() as session:
        user = await resolve_user(session, init_data=raw_init, telegram_id=telegram_id)
        cart_count = await cart_repo.get_cart_item_count(session, user.id)
        settings = get_settings()

        return {
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "balance": str(user.balance),
                "channel_discount_claimed": user.channel_discount_claimed,
                "channel_discount_used": user.channel_discount_used,
                "is_admin": settings.is_admin(user.telegram_id),
            },
            "cart_count": cart_count,
        }


# ---------------------------------------------------------------------------
# Catalog Endpoints (Categories & Products with Stock)
# ---------------------------------------------------------------------------

@router.get("/catalog")
async def get_catalog(category_id: Optional[int] = Query(None)):
    """Get all active categories and products with live stock counts."""
    async with get_session() as session:
        categories = await category_repo.list_active(session)
        products = await product_repo.list_active(session)

        # Build category map and calculate stock
        cat_list = []
        for cat in categories:
            cat_list.append({
                "id": cat.id,
                "name": cat.name,
                "description": cat.description or "",
                "icon": cat.icon or "📦",
                "image_url": cat.image_url,
                "sort_order": cat.sort_order,
            })

        prod_list = []
        for prod in products:
            if category_id is not None and prod.category_id != category_id:
                continue

            stock = await inventory_repo.get_stock_count(session, prod.id)
            cat_name = prod.category.name if prod.category else "Other"
            cat_icon = prod.category.icon if prod.category else "📦"

            prod_list.append({
                "id": prod.id,
                "category_id": prod.category_id,
                "category_name": cat_name,
                "category_icon": cat_icon,
                "name": prod.name,
                "description": prod.description or "",
                "price": str(prod.price),
                "currency": prod.currency,
                "delivery_type": prod.delivery_type.value,
                "stock": stock,
                "in_stock": stock > 0,
                "image_url": prod.image_url,
            })

        return {
            "categories": cat_list,
            "products": prod_list,
        }


@router.get("/products/{product_id}")
async def get_product_detail(product_id: int):
    """Get single product details with live stock."""
    async with get_session() as session:
        prod_data = await product_repo.get_product_with_stock(session, product_id)
        if not prod_data:
            raise HTTPException(status_code=404, detail="Product not found")

        prod = prod_data["product"]
        stock = prod_data["stock"]

        return {
            "id": prod.id,
            "category_id": prod.category_id,
            "category_name": prod.category.name if prod.category else "Other",
            "category_icon": prod.category.icon if prod.category else "📦",
            "name": prod.name,
            "description": prod.description or "",
            "price": str(prod.price),
            "currency": prod.currency,
            "delivery_type": prod.delivery_type.value,
            "stock": stock,
            "in_stock": stock > 0,
            "active": prod.active,
            "image_url": prod.image_url,
        }


# ---------------------------------------------------------------------------
# Shopping Cart Endpoints
# ---------------------------------------------------------------------------

@router.get("/cart")
async def get_cart(
    init_data: Optional[str] = Query(None),
    telegram_id: Optional[int] = Query(None),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Get current user's cart summary, items, and calculated discount."""
    raw_init = init_data or x_telegram_init_data
    async with get_session() as session:
        user = await resolve_user(session, init_data=raw_init, telegram_id=telegram_id)
        summary = await cart_service.get_cart_summary(session, user.id)

        from app.services.order_service import compute_first_order_discount
        discount = compute_first_order_discount(user, summary["total_amount"])
        final_amount = max(summary["total_amount"] - discount, Decimal("0.00"))

        return {
            "items": [
                {
                    "cart_item_id": item["cart_item_id"],
                    "product_id": item["product_id"],
                    "product_name": item["product_name"],
                    "unit_price": str(item["unit_price"]),
                    "quantity": item["quantity"],
                    "subtotal": str(item["subtotal"]),
                    "stock": item["stock"],
                    "has_stock": item["has_stock"],
                    "active": item["active"],
                }
                for item in summary["items"]
            ],
            "total_items": summary["total_count"],
            "subtotal": str(summary["total_amount"]),
            "discount_eligible": user.channel_discount_claimed and not user.channel_discount_used,
            "discount_amount": str(discount),
            "final_amount": str(final_amount),
            "currency": summary["currency"],
            "is_valid": summary["is_valid"],
            "user_balance": str(user.balance),
        }


@router.post("/cart/add")
async def add_to_cart(req: CartItemActionRequest):
    """Add a product to cart with live stock check."""
    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)
        try:
            result = await cart_service.add_to_cart(
                session, user.id, req.product_id, req.quantity
            )
            return {
                "success": True,
                "message": "Added to cart",
                "total_cart_items": result["total_cart_items"],
            }
        except cart_service.CartError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/cart/update")
async def update_cart_item(req: CartUpdateQuantityRequest):
    """Update item quantity in cart."""
    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)
        try:
            await cart_service.update_cart_quantity(
                session, user.id, req.product_id, req.quantity
            )
            return {"success": True, "message": "Cart updated"}
        except cart_service.CartError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/cart/remove")
async def remove_from_cart(req: CartRemoveRequest):
    """Remove product from cart."""
    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)
        await cart_service.remove_from_cart(session, user.id, req.product_id)
        return {"success": True, "message": "Item removed"}


@router.post("/cart/clear")
async def clear_cart(req: ClaimDiscountRequest):
    """Clear all items from cart."""
    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)
        await cart_service.clear_cart(session, user.id)
        return {"success": True, "message": "Cart cleared"}


# ---------------------------------------------------------------------------
# Checkout & Payment Endpoints
# ---------------------------------------------------------------------------

@router.post("/checkout")
async def checkout(req: CheckoutRequest):
    """Checkout cart items via Crypto payment invoice or Account Balance."""
    settings = get_settings()

    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)

        # 1. Validate and execute cart checkout
        try:
            checkout_res = await cart_service.checkout_cart(session, user.id)
        except cart_service.CartError as e:
            raise HTTPException(status_code=400, detail=str(e))

        order = checkout_res["order"]
        subtotal = checkout_res["subtotal"]
        discount = checkout_res["discount"]

        # --- OPTION A: STORE BALANCE CHECKOUT ---
        if req.payment_method.lower() == "balance":
            if user.balance < order.amount:
                # Cancel the order to release reserved inventory
                await order_service.cancel_order(session, order.id)
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient balance (${user.balance}). Order total is ${order.amount}.",
                )

            # Deduct balance
            user.balance -= order.amount
            await session.flush()

            # Mark order as PAID
            await order_service.mark_paid(session, order.id)

            # Auto-fulfill and deliver credentials
            fulfill_res = await order_service.fulfill_order(session, order.id)
            credentials = fulfill_res["contents"] if fulfill_res else []

            # Trigger bot message if bot instance is available
            from app.bot.bot import get_bot_instance
            bot = get_bot_instance()
            if bot and fulfill_res and fulfill_res.get("content"):
                try:
                    product_name = order.product.name if order.product else "Cloud Deals Items"
                    await delivery_service.deliver_to_user(
                        bot=bot,
                        telegram_id=user.telegram_id,
                        order=order,
                        content="\n".join(credentials),
                        product_name=product_name,
                    )
                except Exception as e:
                    logger.warning("Bot delivery notification skipped: %s", e)

            return {
                "success": True,
                "payment_method": "balance",
                "status": "fulfilled",
                "public_order_id": order.public_order_id,
                "amount": str(order.amount),
                "discount": str(discount),
                "subtotal": str(subtotal),
                "credentials": credentials,
                "message": "Order paid with store balance and fulfilled instantly!",
            }

        # --- OPTION B: CRYPTO INVOICE CHECKOUT (Cryptomus / NOWPayments) ---
        provider = get_payment_provider()
        try:
            pay_result = await payment_service.create_payment_for_order(
                session, provider, order.id
            )
        except Exception as e:
            logger.error("Mini App payment generation failed: %s", e)
            await order_service.cancel_order(session, order.id)
            raise HTTPException(
                status_code=500,
                detail=f"Payment provider error: {e}",
            )

        payment = pay_result["payment"]

        return {
            "success": True,
            "payment_method": "crypto",
            "status": order.status.value,
            "order_id": order.id,
            "public_order_id": order.public_order_id,
            "amount": str(order.amount),
            "subtotal": str(subtotal),
            "discount": str(discount),
            "payment_url": payment.payment_url,
            "payment_address": payment.payment_address,
            "payment_provider": payment.provider,
            "created_at": order.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Order History & Live Status Polling Endpoints
# ---------------------------------------------------------------------------

@router.get("/orders")
async def list_orders(
    init_data: Optional[str] = Query(None),
    telegram_id: Optional[int] = Query(None),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """List customer orders with status and delivered credentials."""
    raw_init = init_data or x_telegram_init_data
    async with get_session() as session:
        user = await resolve_user(session, init_data=raw_init, telegram_id=telegram_id)
        orders = await order_repo.get_user_orders(session, user.id, limit=30)

        orders_data = []
        for o in orders:
            delivered = []
            if o.status == OrderStatus.FULFILLED:
                items = await inventory_repo.get_items_by_order_id(session, o.id)
                delivered = [i.content for i in items if i.content]
                if not delivered and o.inventory_item:
                    delivered = [o.inventory_item.content]

            payment = await payment_repo.get_by_order_id(session, o.id)
            payment_url = payment.payment_url if payment else None

            prod_name = "Cloud Deals Item"
            if o.product_id:
                p = await product_repo.get_by_id(session, o.product_id)
                if p:
                    prod_name = p.name
            orders_data.append({
                "id": o.id,
                "public_order_id": o.public_order_id,
                "product_name": prod_name,
                "quantity": o.quantity,
                "amount": str(o.amount),
                "discount_amount": str(o.discount_amount),
                "status": o.status.value,
                "payment_url": payment_url,
                "created_at": o.created_at.isoformat(),
                "delivered_items": delivered,
            })

        return {"orders": orders_data}


@router.get("/orders/{order_id}")
async def get_order_status(
    order_id: int,
    init_data: Optional[str] = Query(None),
    telegram_id: Optional[int] = Query(None),
    x_telegram_init_data: Optional[str] = Header(None),
):
    """Get live status of order; checks payment provider if pending."""
    raw_init = init_data or x_telegram_init_data
    async with get_session() as session:
        user = await resolve_user(session, init_data=raw_init, telegram_id=telegram_id)
        order = await order_service.get_order_by_id(session, order_id)

        if not order or order.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")

        # If pending, check with provider
        payment = await payment_repo.get_by_order_id(session, order.id)
        if payment and payment.provider and order.status in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_PROCESSING):
            try:
                provider = get_payment_provider(payment.provider)
                await payment_service.check_payment_status(session, provider, order.id)
                # Reload refreshed order
                order = await order_service.get_order_by_id(session, order_id)
            except Exception as e:
                logger.warning("Error checking order status with provider: %s", e)

        # Retrieve delivered items if fulfilled
        delivered = []
        if order.status == OrderStatus.FULFILLED:
            items = await inventory_repo.get_items_by_order_id(session, order.id)
            delivered = [i.content for i in items if i.content]
            if not delivered and order.inventory_item:
                delivered = [order.inventory_item.content]

        return {
            "id": order.id,
            "public_order_id": order.public_order_id,
            "amount": str(order.amount),
            "status": order.status.value,
            "payment_url": payment.payment_url if payment else None,
            "delivered_credentials": delivered,
            "created_at": order.created_at.isoformat(),
        }


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    req: ClaimDiscountRequest,
):
    """Cancel pending order and release reserved inventory."""
    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)
        order = await order_service.get_order_by_id(session, order_id)

        if not order or order.user_id != user.id:
            raise HTTPException(status_code=404, detail="Order not found")

        try:
            await order_service.cancel_order(session, order.id)
            return {"success": True, "message": "Order cancelled and stock released"}
        except order_service.OrderError as e:
            raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Channel Discount Claim Endpoint
# ---------------------------------------------------------------------------

@router.post("/discount/claim")
async def claim_channel_discount(req: ClaimDiscountRequest):
    """Check membership in required channel and activate 10% first-order discount."""
    settings = get_settings()

    async with get_session() as session:
        user = await resolve_user(session, init_data=req.init_data, telegram_id=req.telegram_id)

        if user.channel_discount_used:
            return {
                "success": False,
                "message": "First order discount has already been used.",
                "claimed": False,
            }

        if user.channel_discount_claimed:
            return {
                "success": True,
                "message": "10% First order discount is already active!",
                "claimed": True,
            }

        # Check channel membership if bot instance is available
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
        channel = settings.force_channel_id

        is_member = True
        if bot and channel:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user.telegram_id)
                is_member = member.status in ("member", "administrator", "creator")
            except Exception as e:
                logger.warning("Channel membership check failed for WebApp user: %s", e)
                is_member = True

        if not is_member:
            return {
                "success": False,
                "message": f"Please join {channel} first to claim your 10% discount.",
                "claimed": False,
            }

        user.channel_discount_claimed = True
        await session.flush()

        return {
            "success": True,
            "message": "🎉 10% First-Order Discount activated! Applied automatically at checkout.",
            "claimed": True,
        }
