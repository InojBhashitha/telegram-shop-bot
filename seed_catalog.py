#!/usr/bin/env python3
"""Catalog Seeder & Demo Population Utility.

Quickly populates the Telegram WebApp store with high-converting demo categories,
products, and encrypted stock inventory for instant client presentations.
Also supports wiping or checking inventory status.

Usage:
    python seed_catalog.py              # Seeds demo data if not already present
    python seed_catalog.py --force      # Wipes and reseeds fresh demo data
    python seed_catalog.py --wipe       # Clears all demo categories, products, inventory
    python seed_catalog.py --status     # Displays summary of current catalog & stock
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import delete, func, select

from app.database.database import close_db, get_session, init_db
from app.database.models import Category, DeliveryType, Inventory, InventoryStatus, Product
from app.database.repositories.inventory_repo import add_items


# --- High-Converting Demo Catalog Definition & Typed Models ---

class CategoryInfo(TypedDict):
    name: str
    icon: str
    description: str
    sort_order: int


class ProductInfo(TypedDict):
    name: str
    description: str
    price: Decimal
    stock_count: int
    prefix: str


class CatalogCategory(TypedDict):
    category: CategoryInfo
    products: list[ProductInfo]


DEMO_CATALOG: list[CatalogCategory] = [
    {
        "category": {
            "name": "VPN & Privacy",
            "icon": "🛡️",
            "description": "High-speed encrypted VPN accounts and private WireGuard keys.",
            "sort_order": 1,
        },
        "products": [
            {
                "name": "Mullvad VPN — 1 Month Key",
                "description": "Anonymous wireguard/OpenVPN key with zero logs. Supports up to 5 devices simultaneously.",
                "price": Decimal("5.50"),
                "stock_count": 8,
                "prefix": "mullvad-wireguard-privkey-",
            },
            {
                "name": "NordVPN — 1 Year Ultimate",
                "description": "NordVPN Ultimate account with Threat Protection Pro and 1TB cloud storage.",
                "price": Decimal("14.99"),
                "stock_count": 6,
                "prefix": "nord-account-user-",
            },
            {
                "name": "Proton VPN — Plus 6 Months",
                "description": "Swiss-based high-speed privacy VPN with P2P support and NetShield ad-blocker.",
                "price": Decimal("18.00"),
                "stock_count": 5,
                "prefix": "proton-vpn-credentials-",
            },
        ],
    },
    {
        "category": {
            "name": "Cloud & Compute",
            "icon": "☁️",
            "description": "Verified cloud infrastructure accounts with upfront billing credits.",
            "sort_order": 2,
        },
        "products": [
            {
                "name": "Oracle Cloud — Free Tier Activated",
                "description": "Pre-warmed Oracle Cloud Infrastructure account with 4 OCPU ARM and 24GB RAM available forever.",
                "price": Decimal("24.99"),
                "stock_count": 5,
                "prefix": "oci-cloud-login-",
            },
            {
                "name": "AWS — $300 Credits Fresh Account",
                "description": "Ready-to-use Amazon Web Services account with valid $300 promotional credit balance.",
                "price": Decimal("19.99"),
                "stock_count": 7,
                "prefix": "aws-console-auth-",
            },
            {
                "name": "DigitalOcean — $200 Credit 60-Day Trial",
                "description": "Port 25 enabled, 3 droplets limit, clean IP registration ready for deployment.",
                "price": Decimal("12.50"),
                "stock_count": 8,
                "prefix": "digitalocean-token-",
            },
            {
                "name": "Hetzner Cloud — Verified Console",
                "description": "European high-performance VPS account with clean verification and immediate server launch permissions.",
                "price": Decimal("29.00"),
                "stock_count": 4,
                "prefix": "hetzner-console-creds-",
            },
        ],
    },
    {
        "category": {
            "name": "Developer & AI Tools",
            "icon": "💻",
            "description": "Access tokens and premium subscriptions for cutting-edge AI and coding suites.",
            "sort_order": 3,
        },
        "products": [
            {
                "name": "ChatGPT Plus — 1 Month Fast Access",
                "description": "Full access to GPT-4o, DALL-E, Canvas, Code Interpreter, and Advanced Voice Mode.",
                "price": Decimal("11.99"),
                "stock_count": 10,
                "prefix": "chatgpt-plus-token-",
            },
            {
                "name": "GitHub Copilot Pro — 1 Year Key",
                "description": "AI pair programmer license compatible with VS Code, JetBrains, and Neovim.",
                "price": Decimal("22.00"),
                "stock_count": 6,
                "prefix": "gh-copilot-license-",
            },
            {
                "name": "Claude Pro — 1 Month Account",
                "description": "Anthropic Claude Pro with Opus, Sonnet 3.5, artifacts workspace, and 5x usage limits.",
                "price": Decimal("14.50"),
                "stock_count": 5,
                "prefix": "claude-pro-auth-",
            },
        ],
    },
    {
        "category": {
            "name": "Streaming & Audio",
            "icon": "🎬",
            "description": "Ad-free ultra-high-definition music and movie streaming subscriptions.",
            "sort_order": 4,
        },
        "products": [
            {
                "name": "Spotify Premium — 12 Month Upgrade",
                "description": "Individual premium plan upgrade for your existing account. Offline music & zero ads.",
                "price": Decimal("9.99"),
                "stock_count": 12,
                "prefix": "spotify-prem-upgrade-",
            },
            {
                "name": "YouTube Premium — 6 Month Member",
                "description": "Ad-free YouTube and YouTube Music with background playback on mobile and TV.",
                "price": Decimal("7.50"),
                "stock_count": 9,
                "prefix": "yt-premium-invite-",
            },
            {
                "name": "Netflix UHD 4K — 1 Month Private Profile",
                "description": "Private PIN-protected profile on an Ultra HD 4K screen with full warranty.",
                "price": Decimal("4.99"),
                "stock_count": 15,
                "prefix": "netflix-profile-pin-",
            },
        ],
    },
    {
        "category": {
            "name": "Gaming & Gift Codes",
            "icon": "🎮",
            "description": "Global wallet top-ups, community badges, and console passes.",
            "sort_order": 5,
        },
        "products": [
            {
                "name": "Discord Nitro — 3 Months Boost Link",
                "description": "Official Discord Nitro gift link with 2 server boosts, HD streaming, and custom emoji everywhere.",
                "price": Decimal("8.99"),
                "stock_count": 10,
                "prefix": "https://discord.gift/nitro-promo-",
            },
            {
                "name": "Steam Global — $20 Wallet Code",
                "description": "Redeemable in any region, automatically converts to local currency balance.",
                "price": Decimal("18.50"),
                "stock_count": 8,
                "prefix": "STEAM-WALLET-CODE-",
            },
            {
                "name": "Xbox Game Pass Ultimate — 2 Months",
                "description": "Cloud gaming + hundreds of PC and Xbox console titles with EA Play included.",
                "price": Decimal("6.50"),
                "stock_count": 7,
                "prefix": "XBOX-GPU-TOKEN-",
            },
        ],
    },
]


async def seed_catalog(force: bool = False) -> tuple[int, int, int]:
    """Seed demo categories, products, and encrypted inventory.

    Returns:
        tuple of (categories_added, products_added, inventory_items_added)
    """
    total_categories = 0
    total_products = 0
    total_items = 0

    async with get_session() as session:
        for cat_data in DEMO_CATALOG:
            cat_info: CategoryInfo = cat_data["category"]
            c_name: str = cat_info["name"]
            c_icon: str = cat_info["icon"]
            c_desc: str = cat_info["description"]
            c_sort: int = cat_info["sort_order"]

            stmt = select(Category).where(Category.name == c_name)
            existing_cat = (await session.execute(stmt)).scalars().first()

            if existing_cat is None:
                category = Category(
                    name=c_name,
                    icon=c_icon,
                    description=c_desc,
                    sort_order=c_sort,
                    active=True,
                )
                session.add(category)
                await session.flush()
                total_categories += 1
            else:
                category = existing_cat

            products_list: list[ProductInfo] = cat_data["products"]
            for prod_data in products_list:
                p_name: str = prod_data["name"]
                p_desc: str = prod_data["description"]
                p_price: Decimal = prod_data["price"]
                p_stock: int = prod_data["stock_count"]
                p_prefix: str = prod_data["prefix"]

                stmt = select(Product).where(
                    Product.name == p_name,
                    Product.category_id == category.id,
                )
                existing_prod = (await session.execute(stmt)).scalars().first()

                if existing_prod is None:
                    product = Product(
                        category_id=category.id,
                        name=p_name,
                        description=p_desc,
                        price=p_price,
                        currency="USD",
                        delivery_type=DeliveryType.DIGITAL,
                        active=True,
                    )
                    session.add(product)
                    await session.flush()
                    total_products += 1
                else:
                    product = existing_prod

                # Check current stock
                stock_stmt = select(func.count(Inventory.id)).where(
                    Inventory.product_id == product.id,
                    Inventory.status == InventoryStatus.AVAILABLE,
                )
                current_stock = (await session.execute(stock_stmt)).scalar() or 0
                needed_stock = p_stock - current_stock

                if needed_stock > 0 or force:
                    add_qty = p_stock if force else needed_stock
                    contents = [
                        f"{p_prefix}{i+100:04d} | PASS: SafePass_{i+10}! | EXP: 2027-12-31"
                        for i in range(1, add_qty + 1)
                    ]
                    created_items = await add_items(session, product.id, contents)
                    total_items += len(created_items)

    return total_categories, total_products, total_items


async def wipe_catalog() -> tuple[int, int, int]:
    """Wipe demo inventory, products, and categories."""
    async with get_session() as session:
        # Count items before deleting
        inv_count = (await session.execute(select(func.count(Inventory.id)))).scalar() or 0
        prod_count = (await session.execute(select(func.count(Product.id)))).scalar() or 0
        cat_count = (await session.execute(select(func.count(Category.id)))).scalar() or 0

        # Delete inventory first due to foreign keys
        await session.execute(delete(Inventory))
        await session.execute(delete(Product))
        await session.execute(delete(Category))

    return cat_count, prod_count, inv_count


async def show_status() -> None:
    """Print current catalog status."""
    async with get_session() as session:
        cat_stmt = select(Category).order_by(Category.sort_order)
        categories = (await session.execute(cat_stmt)).scalars().all()

        print("\n==================================================")
        print("   📦 CURRENT TELEGRAM SHOP BOT CATALOG STATUS    ")
        print("==================================================")

        if not categories:
            print("⚠️  No categories or products found in database.")
            print("Run 'python seed_catalog.py' to populate demo data.\n")
            return

        total_prods = 0
        total_available = 0

        for cat in categories:
            prod_stmt = select(Product).where(Product.category_id == cat.id)
            products = (await session.execute(prod_stmt)).scalars().all()
            print(f"\n{cat.icon or '📁'} {cat.name} ({len(products)} products)")

            for prod in products:
                stock_stmt = select(func.count(Inventory.id)).where(
                    Inventory.product_id == prod.id,
                    Inventory.status == InventoryStatus.AVAILABLE,
                )
                stock = (await session.execute(stock_stmt)).scalar() or 0
                total_available += stock
                total_prods += 1
                status_icon = "🟢" if stock > 2 else ("🟡" if stock > 0 else "🔴")
                print(f"   {status_icon} [{stock:2d} in stock] {prod.name:<38} ${prod.price:.2f}")

        print("--------------------------------------------------")
        print(f"Total: {len(categories)} categories | {total_prods} products | {total_available} available stock items")
        print("==================================================\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram Shop Bot Demo Catalog Seeder")
    parser.add_argument("--wipe", action="store_true", help="Wipe all categories, products, and inventory")
    parser.add_argument("--status", action="store_true", help="Display current catalog and inventory count")
    parser.add_argument("--force", action="store_true", help="Wipe and reseed fresh demo catalog")
    args = parser.parse_args()

    await init_db()

    try:
        if args.wipe:
            c, p, i = await wipe_catalog()
            print(f"🗑️ Wiped {c} categories, {p} products, and {i} inventory credentials.")
        elif args.status:
            await show_status()
        elif args.force:
            print("🔄 Force reseeding demo catalog...")
            await wipe_catalog()
            c, p, i = await seed_catalog(force=True)
            print(f"✨ Successfully seeded {c} categories, {p} products, and {i} encrypted inventory items!")
            await show_status()
        else:
            c, p, i = await seed_catalog()
            print(f"✨ Demo catalog ready! Added {c} new categories, {p} new products, and {i} encrypted stock items.")
            await show_status()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
