"""Admin Portal API — Executive management suite for store owners.

Provides real-time revenue analytics, inventory restock, product creation,
coupon generation, order vault with customer support refunds, and broadcasts.
Protected by administrative JWT role verification.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.webapp import resolve_user
from app.config import get_settings
from app.database.database import get_session
from app.database.models import (
    Category,
    Coupon,
    CouponType,
    DeliveryType,
    Inventory,
    InventoryStatus,
    Order,
    OrderStatus,
    Product,
    StockAlert,
    User,
)
from app.database.repositories import inventory_repo
from app.database.repositories.inventory_repo import add_items
from app.services import analytics_service
from app.utils.crypto_vault import decrypt_content

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Administrative Dependency & Security Guard
# ---------------------------------------------------------------------------

async def require_admin(
    authorization: str | None = Header(None),
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    x_dev_telegram_id: str | None = Header(None, alias="X-Dev-Telegram-Id"),
) -> User:
    """FastAPI dependency: Authenticates user and verifies admin privileges."""
    settings = get_settings()
    dev_id: int | None = None
    if x_dev_telegram_id and x_dev_telegram_id.isdigit():
        dev_id = int(x_dev_telegram_id)

    async with get_session() as session:
        user = await resolve_user(
            session,
            authorization=authorization,
            init_data=x_telegram_init_data,
            telegram_id=dev_id,
        )
        if not settings.is_admin(user.telegram_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrative privileges required to access the Merchant Suite.",
            )
        return user


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------

class RestockProductRequest(BaseModel):
    product_id: int
    content: str = Field(..., description="Raw text of credentials or keys (one per line)")


class CreateProductRequest(BaseModel):
    category_id: int
    name: str = Field(..., min_length=2, max_length=255)
    description: str = ""
    price: float = Field(..., gt=0)
    image_url: str = ""
    active: bool = True
    initial_stock: str = Field("", description="Optional multiline raw credentials")


class CreateCouponRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    discount_type: str = Field("percent", description="'percent' or 'fixed'")
    discount_value: float = Field(..., gt=0)
    max_uses: int | None = Field(None, ge=1)
    expires_in_days: int | None = Field(30, ge=1)


class BroadcastMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# 1. Executive Analytics & KPI Pulse
# ---------------------------------------------------------------------------

@router.get("/analytics")
async def get_admin_analytics(
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Retrieve comprehensive store analytics: today, 7d, lifetime and inventory health."""
    async with get_session() as session:
        summary_24h = await analytics_service.get_analytics_summary(session, hours=24)
        summary_7d = await analytics_service.get_analytics_summary(session, hours=168)

        # Count total inventory items available across all products
        total_avail_stmt = select(func.count(Inventory.id)).where(
            Inventory.status == InventoryStatus.AVAILABLE
        )
        total_available = (await session.execute(total_avail_stmt)).scalar() or 0

        # Count active products
        total_prods_stmt = select(func.count(Product.id)).where(Product.active == True)
        total_active_prods = (await session.execute(total_prods_stmt)).scalar() or 0

        # Calculate fulfillment rate
        lifetime_orders = summary_24h["lifetime_orders"]
        lifetime_rev = summary_24h["lifetime_revenue"]
        fulfilled_stmt = select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PAID, OrderStatus.FULFILLED])
        )
        fulfilled_count = (await session.execute(fulfilled_stmt)).scalar() or 0
        fulfillment_rate = (
            round((fulfilled_count / max(1, lifetime_orders)) * 100, 1)
            if lifetime_orders > 0
            else 100.0
        )

        return {
            "overview": {
                "revenue_today": float(summary_24h["revenue"]),
                "orders_today": summary_24h["completed_orders"],
                "revenue_7d": float(summary_7d["revenue"]),
                "orders_7d": summary_7d["completed_orders"],
                "lifetime_revenue": float(lifetime_rev),
                "lifetime_orders": lifetime_orders,
                "lifetime_customers": summary_24h["lifetime_users"],
                "fulfillment_rate": fulfillment_rate,
                "total_available_stock": total_available,
                "active_products": total_active_prods,
            },
            "top_products": [
                {
                    "name": p["name"],
                    "units": p["units"],
                    "revenue": float(p["revenue"]),
                }
                for p in summary_7d["top_products"]
            ],
            "low_stock_alerts": summary_24h["low_stock_products"],
            "wallet_topups": {
                "today_revenue": float(summary_24h["topup_revenue"]),
                "today_count": summary_24h["topup_count"],
            },
        }


# ---------------------------------------------------------------------------
# 2. Products & Inventory Management
# ---------------------------------------------------------------------------

@router.get("/products")
async def list_admin_products(
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """List all products with active status, category info, and real-time stock levels."""
    async with get_session() as session:
        stmt = (
            select(Product)
            .options(selectinload(Product.category))
            .order_by(Product.category_id, Product.id)
        )
        res = await session.execute(stmt)
        products = res.scalars().all()

        prod_ids = [p.id for p in products]
        stock_map = await inventory_repo.get_stock_counts_for_products(session, prod_ids)

        # Also get all categories for dropdowns
        cats_stmt = select(Category).order_by(Category.sort_order)
        categories = (await session.execute(cats_stmt)).scalars().all()

        return {
            "products": [
                {
                    "id": p.id,
                    "category_id": p.category_id,
                    "category_name": p.category.name if p.category else "General",
                    "category_icon": p.category.icon if p.category else "📦",
                    "name": p.name,
                    "description": p.description or "",
                    "price": float(p.price),
                    "currency": p.currency,
                    "active": p.active,
                    "image_url": p.image_url or "",
                    "stock": stock_map.get(p.id, 0),
                }
                for p in products
            ],
            "categories": [
                {
                    "id": c.id,
                    "name": c.name,
                    "icon": c.icon or "📦",
                }
                for c in categories
            ],
        }


@router.post("/products")
async def create_admin_product(
    req: CreateProductRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new product with optional initial credentials to seed."""
    async with get_session() as session:
        # Verify category exists
        cat_stmt = select(Category).where(Category.id == req.category_id)
        cat = (await session.execute(cat_stmt)).scalars().first()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected category does not exist.",
            )

        new_product = Product(
            category_id=req.category_id,
            name=req.name.strip(),
            description=req.description.strip(),
            price=Decimal(str(req.price)),
            currency="USD",
            image_url=req.image_url.strip() or None,
            delivery_type=DeliveryType.DIGITAL,
            active=req.active,
        )
        session.add(new_product)
        await session.flush()

        initial_count = 0
        if req.initial_stock.strip():
            raw_lines = [
                line.strip()
                for line in req.initial_stock.strip().splitlines()
                if line.strip()
            ]
            if raw_lines:
                items = await add_items(session, new_product.id, raw_lines)
                initial_count = len(items)

        await session.commit()
        return {
            "success": True,
            "message": f"Product '{new_product.name}' created successfully with {initial_count} items in stock.",
            "product_id": new_product.id,
            "initial_stock": initial_count,
        }


@router.post("/products/stock")
async def restock_admin_product(
    req: RestockProductRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Upload / paste raw credentials to restock an existing product."""
    raw_lines = [
        line.strip()
        for line in req.content.strip().splitlines()
        if line.strip()
    ]
    if not raw_lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid credentials provided. Each credential must be on a separate line.",
        )

    async with get_session() as session:
        prod_stmt = select(Product).where(Product.id == req.product_id)
        prod = (await session.execute(prod_stmt)).scalars().first()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )

        created_items = await add_items(session, prod.id, raw_lines)
        added_count = len(created_items)

        # Notify waiting customers who subscribed to stock alerts
        alerts_stmt = select(StockAlert).where(StockAlert.product_id == prod.id)
        alerts = (await session.execute(alerts_stmt)).scalars().all()
        user_ids = [a.user_id for a in alerts]

        # Delete fulfilled alerts
        if alerts:
            await session.execute(
                delete(StockAlert).where(StockAlert.product_id == prod.id)
            )

        # Fetch current total available stock
        stock_stmt = select(func.count(Inventory.id)).where(
            Inventory.product_id == prod.id,
            Inventory.status == InventoryStatus.AVAILABLE,
        )
        total_stock = (await session.execute(stock_stmt)).scalar() or 0
        await session.commit()

        # Send Telegram background notifications to subscribers if bot is available
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
        if bot and user_ids:
            from app.database.models import User as DBUser
            async with get_session() as n_session:
                users_stmt = select(DBUser).where(DBUser.id.in_(user_ids))
                notify_users = (await n_session.execute(users_stmt)).scalars().all()
                for nu in notify_users:
                    try:
                        await bot.send_message(
                            chat_id=nu.telegram_id,
                            text=(
                                f"🔔 *RESTOCK ALERT!* \n\n"
                                f"Good news! *{prod.name}* is now back in stock with {total_stock} units available.\n\n"
                                f"Open the store to claim yours before it sells out!"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as err:
                        logger.warning("Could not send restock alert to user %s: %s", nu.telegram_id, err)

        return {
            "success": True,
            "message": f"Successfully added {added_count} encrypted credentials to '{prod.name}'.",
            "added_count": added_count,
            "total_stock": total_stock,
            "subscribers_notified": len(user_ids),
        }


@router.patch("/products/{product_id}/toggle")
async def toggle_product_visibility(
    product_id: int,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Toggle a product between active (visible) and inactive (hidden)."""
    async with get_session() as session:
        stmt = select(Product).where(Product.id == product_id)
        prod = (await session.execute(stmt)).scalars().first()
        if not prod:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )

        prod.active = not prod.active
        await session.commit()
        return {
            "success": True,
            "product_id": prod.id,
            "active": prod.active,
            "message": f"Product '{prod.name}' is now {'active (visible)' if prod.active else 'hidden'}.",
        }


# ---------------------------------------------------------------------------
# 3. Promo Codes & Coupon Management
# ---------------------------------------------------------------------------

@router.get("/coupons")
async def list_admin_coupons(
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """List all coupons and promo codes with usage statistics."""
    async with get_session() as session:
        stmt = select(Coupon).order_by(desc(Coupon.id))
        res = await session.execute(stmt)
        coupons = res.scalars().all()

        return {
            "coupons": [
                {
                    "id": c.id,
                    "code": c.code,
                    "discount_type": c.discount_type.value,
                    "discount_value": float(c.discount_value),
                    "min_order_amount": float(c.min_order_amount),
                    "max_uses": c.max_uses,
                    "current_uses": c.current_uses,
                    "active": c.active,
                    "expires_at": c.expiry_at.isoformat() if c.expiry_at else None,
                }
                for c in coupons
            ]
        }


@router.post("/coupons")
async def create_admin_coupon(
    req: CreateCouponRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new promotional discount coupon code."""
    async with get_session() as session:
        clean_code = req.code.strip().upper()
        existing_stmt = select(Coupon).where(Coupon.code == clean_code)
        existing = (await session.execute(existing_stmt)).scalars().first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Coupon code '{clean_code}' already exists.",
            )

        c_type = CouponType.PERCENTAGE if req.discount_type.lower() == "percent" else CouponType.FIXED
        expiry = datetime.now(UTC) + timedelta(days=req.expires_in_days) if req.expires_in_days else None

        new_coupon = Coupon(
            code=clean_code,
            discount_type=c_type,
            discount_value=Decimal(str(req.discount_value)),
            max_uses=req.max_uses,
            expiry_at=expiry,
            active=True,
        )
        session.add(new_coupon)
        await session.commit()

        return {
            "success": True,
            "message": f"Coupon code '{clean_code}' created successfully.",
            "coupon": {
                "id": new_coupon.id,
                "code": new_coupon.code,
                "discount_type": new_coupon.discount_type.value,
                "discount_value": float(new_coupon.discount_value),
            },
        }


@router.delete("/coupons/{coupon_id}")
async def delete_admin_coupon(
    coupon_id: int,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Deactivate or remove a promotional coupon code."""
    async with get_session() as session:
        stmt = select(Coupon).where(Coupon.id == coupon_id)
        coupon = (await session.execute(stmt)).scalars().first()
        if not coupon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Coupon not found.",
            )

        await session.delete(coupon)
        await session.commit()
        return {
            "success": True,
            "message": f"Coupon '{coupon.code}' deleted successfully.",
        }


# ---------------------------------------------------------------------------
# 4. Order Vault & Customer Support Refunds
# ---------------------------------------------------------------------------

@router.get("/orders")
async def list_admin_orders(
    search: str = Query("", description="Search by Order ID or Username"),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Retrieve recent orders with customer profile, payment details, and search filter."""
    async with get_session() as session:
        stmt = (
            select(Order)
            .options(
                selectinload(Order.user),
                selectinload(Order.product),
                selectinload(Order.inventory_items),
            )
            .order_by(desc(Order.created_at))
            .limit(limit)
        )

        res = await session.execute(stmt)
        orders = list(res.scalars().all())

        # In-memory search filter if query is provided
        if search.strip():
            q = search.strip().lower()
            orders = [
                o for o in orders
                if q in o.public_order_id.lower()
                or (o.user and (q in (o.user.username or "").lower() or q in str(o.user.telegram_id)))
                or (o.product and q in o.product.name.lower())
            ]

        order_list = []
        for o in orders:
            delivered = []
            if o.inventory_items:
                delivered = [decrypt_content(inv.content) for inv in o.inventory_items]

            order_list.append({
                "id": o.id,
                "public_order_id": o.public_order_id,
                "amount": float(o.amount),
                "status": o.status.value,
                "created_at": o.created_at.isoformat(),
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                "customer": {
                    "id": o.user.id if o.user else None,
                    "telegram_id": o.user.telegram_id if o.user else None,
                    "name": o.user.first_name if o.user else "Customer",
                    "username": o.user.username if o.user else None,
                },
                "product": {
                    "id": o.product.id if o.product else None,
                    "name": o.product.name if o.product else "Custom Digital Item",
                },
                "delivered_credentials": delivered,
            })

        return {"orders": order_list}


@router.post("/orders/{order_id}/refund")
async def refund_order_to_balance(
    order_id: int,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """One-click customer support refund: Credits user balance and marks order as REFUNDED."""
    async with get_session() as session:
        stmt = (
            select(Order)
            .options(selectinload(Order.user), selectinload(Order.product))
            .where(Order.id == order_id)
        )
        order = (await session.execute(stmt)).scalars().first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found.",
            )

        if order.status == OrderStatus.REFUNDED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has already been refunded.",
            )

        if not order.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer user record not found for this order.",
            )

        refund_amt = order.amount
        order.user.balance = (order.user.balance or Decimal("0.00")) + refund_amt
        order.status = OrderStatus.REFUNDED
        await session.commit()

        # Send Telegram notification to user if bot is available
        from app.bot.bot import get_bot_instance
        bot = get_bot_instance()
        if bot and order.user.telegram_id:
            try:
                prod_name = order.product.name if order.product else "Order"
                await bot.send_message(
                    chat_id=order.user.telegram_id,
                    text=(
                        f"💰 *Customer Support Refund Processed!*\n\n"
                        f"Order `#{order.public_order_id}` ({prod_name}) has been refunded by store support.\n\n"
                        f"💵 *Refunded Amount:* ${refund_amt:.2f}\n"
                        f"💳 *New Wallet Balance:* ${order.user.balance:.2f}\n\n"
                        f"Your credit is ready to use immediately on any product!"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as err:
                logger.warning("Could not notify customer about refund: %s", err)

        return {
            "success": True,
            "message": f"Successfully refunded ${refund_amt:.2f} to customer balance.",
            "order_id": order.id,
            "public_order_id": order.public_order_id,
            "new_balance": float(order.user.balance),
        }


# ---------------------------------------------------------------------------
# 5. Broadcast Message Announcement
# ---------------------------------------------------------------------------

@router.post("/broadcast")
async def broadcast_store_announcement(
    req: BroadcastMessageRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """Send an immediate broadcast message to all store customers via Telegram."""
    from app.bot.bot import get_bot_instance
    bot = get_bot_instance()
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not currently active to deliver broadcasts.",
        )

    msg_text = req.message.strip()
    sent_count = 0
    fail_count = 0

    async with get_session() as session:
        users_stmt = select(User).where(User.telegram_id.is_not(None))
        users = (await session.execute(users_stmt)).scalars().all()

        for u in users:
            try:
                await bot.send_message(
                    chat_id=u.telegram_id,
                    text=msg_text,
                    parse_mode="Markdown",
                )
                sent_count += 1
            except Exception:
                fail_count += 1

    return {
        "success": True,
        "message": f"Broadcast delivered to {sent_count} customers ({fail_count} failed or blocked).",
        "sent_count": sent_count,
        "failed_count": fail_count,
    }
