"""Analytics service — sales metrics, daily digests, and CSV data exports."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database.models import (
    Category,
    Inventory,
    InventoryStatus,
    Order,
    OrderStatus,
    Product,
    TopUp,
    TopUpStatus,
    User,
)
from app.database.repositories import inventory_repo, user_repo

logger = logging.getLogger(__name__)


async def get_analytics_summary(session: AsyncSession, hours: int = 24) -> dict:
    """Aggregate shop performance metrics for the specified trailing window in hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # 1. Orders in period
    stmt_orders = (
        select(Order)
        .options(selectinload(Order.product))
        .where(Order.created_at >= cutoff)
    )
    res_orders = await session.execute(stmt_orders)
    period_orders = list(res_orders.scalars().all())

    completed_orders = [
        o for o in period_orders if o.status in (OrderStatus.PAID, OrderStatus.FULFILLED)
    ]
    revenue = sum((o.amount for o in completed_orders), Decimal("0.00"))
    cancelled_count = sum(1 for o in period_orders if o.status == OrderStatus.CANCELLED)

    # 2. Top-selling products in period
    prod_sales: dict[str, dict] = {}
    for o in completed_orders:
        p_name = o.product.name if o.product else "Unknown Product"
        if p_name not in prod_sales:
            prod_sales[p_name] = {"units": 0, "revenue": Decimal("0.00")}
        prod_sales[p_name]["units"] += o.quantity
        prod_sales[p_name]["revenue"] += o.amount

    top_products = sorted(
        [{"name": k, **v} for k, v in prod_sales.items()],
        key=lambda x: (x["units"], x["revenue"]),
        reverse=True,
    )[:5]

    # 3. New registered users in period
    stmt_users = select(func.count(User.id)).where(User.created_at >= cutoff)
    res_users = await session.execute(stmt_users)
    new_users = res_users.scalar_one()

    # 4. Wallet top-ups in period
    stmt_topups = (
        select(func.coalesce(func.sum(TopUp.amount), Decimal("0.00")), func.count(TopUp.id))
        .where(TopUp.created_at >= cutoff)
        .where(TopUp.status == TopUpStatus.PAID)
    )
    res_topups = await session.execute(stmt_topups)
    topup_row = res_topups.first()
    topup_revenue = Decimal(str(topup_row[0])) if topup_row else Decimal("0.00")
    topup_count = topup_row[1] if topup_row else 0

    # 5. Low / Zero stock products
    stmt_all_prods = select(Product).where(Product.active == True)
    res_prods = await session.execute(stmt_all_prods)
    all_prods = list(res_prods.scalars().all())

    low_stock = []
    prod_ids = [p.id for p in all_prods]
    stock_counts = await inventory_repo.get_stock_counts_for_products(session, prod_ids)
    for p in all_prods:
        avail = stock_counts.get(p.id, 0)
        if avail <= 3:
            low_stock.append({"id": p.id, "name": p.name, "available": avail})

    # Lifetime overall stats for comparison
    lifetime_revenue_stmt = select(
        func.coalesce(func.sum(Order.amount), Decimal("0.00"))
    ).where(Order.status.in_([OrderStatus.PAID, OrderStatus.FULFILLED]))
    lifetime_rev = Decimal(str((await session.execute(lifetime_revenue_stmt)).scalar_one()))
    lifetime_orders_stmt = select(func.count(Order.id))
    lifetime_orders = (await session.execute(lifetime_orders_stmt)).scalar_one()
    lifetime_users_stmt = select(func.count(User.id))
    lifetime_users = (await session.execute(lifetime_users_stmt)).scalar_one()

    return {
        "hours": hours,
        "revenue": revenue,
        "completed_orders": len(completed_orders),
        "total_orders_created": len(period_orders),
        "cancelled_orders": cancelled_count,
        "new_users": new_users,
        "topup_revenue": topup_revenue,
        "topup_count": topup_count,
        "top_products": top_products,
        "low_stock_products": low_stock,
        "lifetime_revenue": lifetime_rev,
        "lifetime_orders": lifetime_orders,
        "lifetime_users": lifetime_users,
    }


def format_digest_message(summary: dict, hours: int = 24) -> str:
    """Format daily analytics digest into an elegant Telegram Markdown message."""
    settings = get_settings()
    rev = summary["revenue"]
    completed = summary["completed_orders"]
    new_users = summary["new_users"]
    topups = summary["topup_revenue"]

    lines = [
        f"📊 *{settings.store_name} — Daily Sales Digest*",
        f"📅 _Period: Last {hours} Hours_\n",
        f"💰 *Revenue:* `${rev:.2f}`",
        f"📦 *Completed Orders:* `{completed}`",
        f"👥 *New Customers:* `{new_users}`",
        f"💳 *Wallet Top-ups:* `${topups:.2f}` ({summary['topup_count']} payments)\n",
    ]

    # Top selling items
    top_prods = summary.get("top_products", [])
    if top_prods:
        lines.append("🏆 *Top Selling Products:*")
        for item in top_prods:
            lines.append(f"• *{item['name']}:* {item['units']} sold (`${item['revenue']:.2f}`)")
        lines.append("")
    else:
        lines.append("🏆 *Top Selling Products:* None in this period\n")

    # Restock warnings
    low_stocks = summary.get("low_stock_products", [])
    if low_stocks:
        lines.append("⚠️ *Restock Needed (Low/Zero Stock):*")
        for item in low_stocks:
            badge = "🚨 OUT OF STOCK" if item["available"] == 0 else f"⚠️ only {item['available']} left"
            lines.append(f"• *{item['name']}:* {badge}")
        lines.append("")
    else:
        lines.append("✅ *Stock Status:* All products healthy\n")

    lines.append(
        f"📈 *All-Time Store Totals:*\n"
        f"💰 `${summary['lifetime_revenue']:.2f}` revenue • "
        f"📦 `{summary['lifetime_orders']}` orders • "
        f"👥 `{summary['lifetime_users']}` customers"
    )

    return "\n".join(lines)


async def send_digest_to_admins(
    session: AsyncSession,
    bot: Optional[Bot] = None,
    hours: int = 24,
) -> int:
    """Dispatch the daily digest message to all configured admin Telegram IDs."""
    if bot is None:
        try:
            from app.bot.bot import get_bot_instance
            bot = get_bot_instance()
        except Exception:
            pass

    if bot is None:
        logger.warning("Cannot send daily digest: No bot instance available")
        return 0

    settings = get_settings()
    summary = await get_analytics_summary(session, hours=hours)
    text = format_digest_message(summary, hours=hours)

    sent_count = 0
    for admin_id_str in settings.admin_telegram_ids.split(","):
        admin_id_str = admin_id_str.strip()
        if not admin_id_str.isdigit():
            continue
        admin_id = int(admin_id_str)
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="Markdown",
            )
            sent_count += 1
        except TelegramError as e:
            logger.warning("Could not send daily digest to admin %s: %s", admin_id, e)

    logger.info("Daily sales digest dispatched to %s admin(s)", sent_count)
    return sent_count


# ---------------------------------------------------------------------------
# CSV Exporters
# ---------------------------------------------------------------------------

async def export_orders_csv(session: AsyncSession) -> bytes:
    """Generate in-memory CSV bytes of all orders."""
    stmt = (
        select(Order)
        .options(selectinload(Order.user), selectinload(Order.product), selectinload(Order.payment))
        .order_by(Order.created_at.desc())
    )
    result = await session.execute(stmt)
    orders = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)

    # Headers
    writer.writerow([
        "Order ID",
        "Date (UTC)",
        "Telegram ID",
        "Username",
        "Product Name",
        "Quantity",
        "Amount ($)",
        "Discount ($)",
        "Currency",
        "Status",
        "Payment Provider",
        "Payment Status",
        "Warranty Expires (UTC)",
    ])

    for o in orders:
        tg_id = o.user.telegram_id if o.user else ""
        username = o.user.username if o.user and o.user.username else ""
        prod_name = o.product.name if o.product else "Unknown Product"
        date_str = o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else ""
        provider = o.payment.provider if o.payment else "balance/manual"
        pay_status = o.payment.status.value if o.payment else "n/a"
        warr_str = o.warranty_expires_at.strftime("%Y-%m-%d %H:%M:%S") if o.warranty_expires_at else ""

        writer.writerow([
            o.public_order_id,
            date_str,
            tg_id,
            username,
            prod_name,
            o.quantity,
            f"{o.amount:.2f}",
            f"{o.discount_amount:.2f}",
            o.currency,
            o.status.value,
            provider,
            pay_status,
            warr_str,
        ])

    return output.getvalue().encode("utf-8-sig")


async def export_inventory_csv(session: AsyncSession) -> bytes:
    """Generate in-memory CSV bytes of active and inactive products with stock counts."""
    stmt = (
        select(Product)
        .options(selectinload(Product.category))
        .order_by(Product.category_id, Product.id)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Product ID",
        "Category",
        "Product Name",
        "Price ($)",
        "Currency",
        "Delivery Type",
        "Status",
        "Available Stock",
        "Reserved Stock",
        "Sold Count",
        "Total Stock",
    ])

    for p in products:
        cat_name = p.category.name if p.category else "Uncategorized"
        summary = await inventory_repo.get_stock_summary(session, p.id)
        avail = summary.get("available", 0)
        reserved = summary.get("reserved", 0)
        sold = summary.get("sold", 0)
        total = avail + reserved + sold

        writer.writerow([
            p.id,
            cat_name,
            p.name,
            f"{p.price:.2f}",
            p.currency,
            p.delivery_type.value,
            "Active" if p.active else "Inactive",
            avail,
            reserved,
            sold,
            total,
        ])

    return output.getvalue().encode("utf-8-sig")


async def export_customers_csv(session: AsyncSession) -> bytes:
    """Generate in-memory CSV bytes of registered customers and lifetime statistics."""
    stmt = select(User).order_by(User.created_at.desc())
    result = await session.execute(stmt)
    users = list(result.scalars().all())

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "User ID",
        "Telegram ID",
        "Username",
        "First Name",
        "Balance ($)",
        "Completed Orders",
        "Total Spent ($)",
        "Referrals Count",
        "Referral Code",
        "Referred By ID",
        "Blocked",
        "Joined Date (UTC)",
    ])

    for u in users:
        stats = await user_repo.get_user_stats(session, u.id)
        ref_count = await user_repo.count_referrals(session, u.id)
        date_str = u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""

        writer.writerow([
            u.id,
            u.telegram_id,
            u.username or "",
            u.first_name or "",
            f"{u.balance:.2f}",
            stats["order_count"],
            f"{stats['total_spent']:.2f}",
            ref_count,
            u.referral_code or "",
            u.referred_by or "",
            "Yes" if u.is_blocked else "No",
            date_str,
        ])

    return output.getvalue().encode("utf-8-sig")
