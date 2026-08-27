"""Seed initial database categories, products, stock, and FAQs."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
import sys

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.database import close_db, get_session, init_db
from app.database.models import DeliveryType
from app.database.repositories import (
    category_repo,
    inventory_repo,
    product_repo,
    settings_repo,
)


async def seed() -> None:
    """Populate database with initial store data."""
    await init_db()
    print("🌱 Seeding Cloud Deals store data...")

    async with get_session() as session:
        # 1. Categories
        existing_cats = await category_repo.list_all(session)
        if not existing_cats:
            do_cat = await category_repo.create(
                session,
                name="Digital Ocean",
                description="DigitalOcean credits and droplets",
                icon="🌊",
                sort_order=1,
            )
            oracle_cat = await category_repo.create(
                session,
                name="Oracle Cloud",
                description="Oracle Cloud accounts & credits",
                icon="☁️",
                sort_order=2,
            )
            vps_cat = await category_repo.create(
                session,
                name="VPS",
                description="High performance virtual private servers",
                icon="🖥",
                sort_order=3,
            )
            other_cat = await category_repo.create(
                session,
                name="Other Services",
                description="VPNs, proxies, and digital vouchers",
                icon="🔐",
                sort_order=4,
            )

            # 2. Products
            p1 = await product_repo.create(
                session,
                category_id=do_cat.id,
                name="DO $5 Credit",
                description="Digital service credit code for DigitalOcean accounts.",
                price=Decimal("4.50"),
                currency="USD",
                delivery_type=DeliveryType.DIGITAL,
            )
            p2 = await product_repo.create(
                session,
                category_id=do_cat.id,
                name="DO $100 Promo Code",
                description="DigitalOcean $100 60-day promotional credit.",
                price=Decimal("15.00"),
                currency="USD",
                delivery_type=DeliveryType.DIGITAL,
            )
            p3 = await product_repo.create(
                session,
                category_id=oracle_cat.id,
                name="Oracle Free Tier Account",
                description="Verified Oracle Cloud Pay-As-You-Go upgraded account.",
                price=Decimal("25.00"),
                currency="USD",
                delivery_type=DeliveryType.DIGITAL,
            )

            # 3. Inventory Stock
            await inventory_repo.add_items(
                session,
                product_id=p1.id,
                contents=[
                    "DO-CREDIT-5-ABC-12345-KLM",
                    "DO-CREDIT-5-DEF-67890-NOP",
                    "DO-CREDIT-5-GHI-13579-QRS",
                    "DO-CREDIT-5-JKL-24680-TUV",
                ],
            )
            await inventory_repo.add_items(
                session,
                product_id=p2.id,
                contents=[
                    "DO-PROMO-100-PROMO-998811",
                    "DO-PROMO-100-PROMO-223344",
                ],
            )
            await inventory_repo.add_items(
                session,
                product_id=p3.id,
                contents=[
                    "ORACLE-ACC: user=oracle_demo1@cloud.com | pass=DemoSecret123#",
                ],
            )

            # 4. Default FAQs
            await settings_repo.create_faq(
                session,
                question="What payment methods are supported?",
                answer="We accept crypto payments (USDT, BTC, ETH, LTC, TON, and more) powered by NOWPayments checkout.",
                sort_order=1,
            )
            await settings_repo.create_faq(
                session,
                question="How long does delivery take?",
                answer="Delivery is 100% automated. Your digital item is delivered directly inside this Telegram bot as soon as network confirmations complete.",
                sort_order=2,
            )
            await settings_repo.create_faq(
                session,
                question="What if a code or credential is defective?",
                answer="Open a ticket using ☎️ Support within 24 hours of purchase and our staff will assist or issue a replacement.",
                sort_order=3,
            )

            print("✅ Default categories, products, inventory, and FAQs seeded successfully!")
        else:
            print("ℹ️ Database already contains categories, skipping seeding.")

    await close_db()


if __name__ == "__main__":
    asyncio.run(seed())
