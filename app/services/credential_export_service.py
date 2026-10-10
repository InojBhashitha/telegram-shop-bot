"""Credential export service — Generate clean, structured .txt and .csv account files."""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import Order
from app.database.repositories import inventory_repo, product_repo
from app.utils.crypto_vault import decrypt_content

logger = logging.getLogger(__name__)


def parse_credential_fields(raw_content: str) -> dict[str, str]:
    """Parse raw account credential content into structured fields:
    - login / email
    - password
    - extra / recovery / 2fa
    - raw
    - combo (email:pass:extra)
    """
    content = raw_content.strip()
    lines = [l.strip() for l in content.split("\n") if l.strip()]

    # 1. Multi-line Key: Value format
    kv_pattern = re.compile(r"^(.+?):\s+(.+)$")
    kv_matches = [kv_pattern.match(l) for l in lines]
    if all(m is not None for m in kv_matches) and len(lines) >= 2:
        fields = {}
        for m in kv_matches:
            if m:
                fields[m.group(1).strip().lower()] = m.group(2).strip()

        login = (
            fields.get("email")
            or fields.get("mail")
            or fields.get("e-mail")
            or fields.get("username")
            or fields.get("user")
            or fields.get("login")
            or ""
        )
        password = (
            fields.get("password")
            or fields.get("pass")
            or fields.get("pwd")
            or fields.get("account pass")
            or fields.get("account password")
            or ""
        )

        extras = []
        for k, v in fields.items():
            if k not in (
                "email", "mail", "e-mail", "username", "user", "login",
                "password", "pass", "pwd", "account pass", "account password",
            ):
                extras.append(f"{k.title()}: {v}")
        extra_str = " | ".join(extras) if extras else "N/A"

        raw_combo = f"{login}:{password}" if login and password else content
        if extra_str != "N/A" and raw_combo != content:
            raw_combo += f":{extra_str}"

        return {
            "login": login or content,
            "password": password or "N/A",
            "extra": extra_str,
            "raw": content,
            "combo": raw_combo,
        }

    # 2. Delimited single-line format (email:pass:extra or email|pass|extra)
    if len(lines) == 1:
        line = lines[0]
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif line.count(":") >= 1:
            parts = [p.strip() for p in line.split(":")]
        else:
            parts = [line]

        login = parts[0] if len(parts) >= 1 else line
        password = parts[1] if len(parts) >= 2 else "N/A"
        extra = " | ".join(parts[2:]) if len(parts) >= 3 else "N/A"

        return {
            "login": login,
            "password": password,
            "extra": extra,
            "raw": line,
            "combo": line,
        }

    # 3. Generic multiline fallback
    return {
        "login": lines[0] if lines else "N/A",
        "password": lines[1] if len(lines) > 1 else "N/A",
        "extra": " | ".join(lines[2:]) if len(lines) > 2 else "N/A",
        "raw": content,
        "combo": ":".join(lines),
    }


def generate_credentials_txt(
    order: Order,
    items_data: list[dict[str, str]],
    store_name: str = "Cloud Deals",
    warranty_hours: int = 24,
) -> bytes:
    """Generate a beautifully formatted .txt credentials document."""
    dt_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if order.created_at else "Recently"
    product_name = order.product.name if order.product else "Digital Accounts"
    count = len(items_data)

    out = io.StringIO()
    out.write("=" * 70 + "\n")
    out.write(f"  {store_name.upper()} — DIGITAL CREDENTIALS\n")
    out.write("=" * 70 + "\n")
    out.write(f"Order ID:        #{order.public_order_id}\n")
    out.write(f"Product:         {product_name}\n")
    out.write(f"Total Accounts:  {count}\n")
    out.write(f"Purchase Date:   {dt_str}\n")
    out.write(f"Warranty Period: {warranty_hours} Hours Replacement Coverage\n")
    out.write("=" * 70 + "\n\n")

    out.write("DETAILED ACCOUNT CREDENTIALS:\n")
    out.write("-" * 70 + "\n")

    for i, item in enumerate(items_data, 1):
        parsed = parse_credential_fields(item["content"])
        p_name = item.get("product_name", product_name)
        out.write(f"\n[ACCOUNT #{i}] — {p_name}\n")
        out.write(f"  Login / Email : {parsed['login']}\n")
        out.write(f"  Password      : {parsed['password']}\n")
        if parsed["extra"] != "N/A":
            out.write(f"  Additional    : {parsed['extra']}\n")
        out.write(f"  Raw Content   :\n    {parsed['raw'].replace(chr(10), chr(10) + '    ')}\n")

    out.write("\n" + "=" * 70 + "\n")
    out.write("RAW COMBO LIST (Ready for tools & checkers — user:pass:extra):\n")
    out.write("=" * 70 + "\n")
    for item in items_data:
        parsed = parse_credential_fields(item["content"])
        out.write(f"{parsed['combo']}\n")

    out.write("\n" + "=" * 70 + "\n")
    out.write(f"Thank you for your purchase from {store_name}!\n")
    out.write("For support or warranty claims, contact us directly in the Telegram Bot.\n")
    out.write("=" * 70 + "\n")

    return out.getvalue().encode("utf-8")


def generate_credentials_csv(
    order: Order,
    items_data: list[dict[str, str]],
    store_name: str = "Cloud Deals",
) -> bytes:
    """Generate RFC 4180 compliant CSV document with account details."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_MINIMAL)

    # Header row
    writer.writerow([
        "Account #",
        "Order ID",
        "Product Name",
        "Username / Email",
        "Password",
        "Additional Details",
        "Raw Credential String",
    ])

    default_prod = order.product.name if order.product else "Digital Account"
    for i, item in enumerate(items_data, 1):
        parsed = parse_credential_fields(item["content"])
        p_name = item.get("product_name", default_prod)
        writer.writerow([
            i,
            order.public_order_id,
            p_name,
            parsed["login"],
            parsed["password"],
            parsed["extra"],
            parsed["combo"],
        ])

    return out.getvalue().encode("utf-8")


async def get_order_items_payload(
    session: AsyncSession,
    order: Order,
) -> list[dict[str, str]]:
    """Retrieve and decrypt all credentials associated with an order."""
    items = await inventory_repo.get_items_by_order_id(session, order.id)
    contents = [item.content for item in items if item.content]

    # Fallback to single inventory_id if items list empty
    if not contents and order.inventory_id:
        single_item = await inventory_repo.get_item_by_id(session, order.inventory_id)
        if single_item and single_item.content:
            items = [single_item]
            contents = [single_item.content]

    if not contents:
        return []

    decrypted = [decrypt_content(c) for c in contents]
    default_prod = order.product.name if order.product else "Digital Account"

    # Resolve product names for each item
    payload: list[dict[str, str]] = []
    for i, item in enumerate(items):
        content_val = decrypted[i] if i < len(decrypted) else decrypt_content(item.content)
        prod_name = default_prod
        if hasattr(item, "product") and item.product:
            prod_name = item.product.name
        elif item.product_id:
            p = await product_repo.get_by_id(session, item.product_id)
            if p:
                prod_name = p.name

        payload.append({
            "content": content_val,
            "product_name": prod_name,
        })

    return payload


async def export_and_send_order_credentials(
    bot: Bot,
    session: AsyncSession,
    chat_id: int,
    order: Order,
    file_format: str = "txt",
) -> tuple[bool, str]:
    """Compile and send the order's credentials document directly to the chat.

    Returns:
        (success: bool, filename_or_error: str)
    """
    settings = get_settings()
    items_payload = await get_order_items_payload(session, order)
    if not items_payload:
        return False, "No credentials found for this order"

    order_hash = order.public_order_id[:8].upper()
    fmt = file_format.lower()

    if fmt == "csv":
        data = generate_credentials_csv(order, items_payload, settings.store_name)
        filename = f"credentials_{order_hash}.csv"
        caption = (
            f"📊 *Order #{order_hash} — Accounts Export (.csv)*\n\n"
            f"🔢 Total Accounts: {len(items_payload)}\n"
            f"🛡️ Warranty: {settings.warranty_hours}h active\n\n"
            f"Compatible with Excel, Google Sheets, and bulk importers."
        )
    else:
        data = generate_credentials_txt(
            order, items_payload, settings.store_name, settings.warranty_hours
        )
        filename = f"credentials_{order_hash}.txt"
        caption = (
            f"📄 *Order #{order_hash} — Credentials File (.txt)*\n\n"
            f"🔢 Total Accounts: {len(items_payload)}\n"
            f"🛡️ Warranty: {settings.warranty_hours}h active\n\n"
            f"Includes individual account details & clean raw combo list."
        )

    try:
        doc_stream = io.BytesIO(data)
        doc_stream.name = filename
        await bot.send_document(
            chat_id=chat_id,
            document=doc_stream,
            filename=filename,
            caption=caption,
            parse_mode="Markdown",
        )
        logger.info("Sent %s credentials document for order %s to chat %s", fmt, order.public_order_id, chat_id)
        return True, filename

    except TelegramError as e:
        logger.error("Failed to send credentials document for order %s: %s", order.public_order_id, e)
        return False, str(e)
