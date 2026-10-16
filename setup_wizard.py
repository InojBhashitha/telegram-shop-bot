#!/usr/bin/env python3
"""Interactive 1-Click Store Setup Wizard & White-Label Provisioner.

Guides sellers through configuring their brand identity, Telegram bot,
crypto payment gateways, admin permissions, and dynamic themes.
Automatically validates bot tokens, generates encryption keys, writes `.env`,
runs database migrations, and optionally seeds demo inventory.

Usage:
    python setup_wizard.py              # Interactive terminal wizard
    python setup_wizard.py --quick      # Quick setup with sensible defaults
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# --- ANSI Terminal Formatting Helpers ---

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_RED = "\033[91m"


def header(title: str) -> None:
    print(f"\n{C_BOLD}{C_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}")
    print(f"  {C_BOLD}{title}{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C_RESET}\n")


def success(msg: str) -> None:
    print(f"  {C_GREEN}✓{C_RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {C_CYAN}ℹ{C_RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C_YELLOW}⚠{C_RESET} {msg}")


def error(msg: str) -> None:
    print(f"  {C_RED}✗{C_RESET} {msg}")


def prompt(text: str, default: str = "") -> str:
    """Prompt user for input with optional default value."""
    if default:
        display_default = f" {C_DIM}[{default}]{C_RESET}"
    else:
        display_default = ""
    try:
        user_input = input(f"{C_BOLD}{text}{display_default}:{C_RESET} ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n{C_YELLOW}Setup cancelled by user.{C_RESET}")
        sys.exit(1)
    return user_input if user_input else default


def choose_option(title: str, options: list[tuple[str, str]], default_idx: int = 0) -> str:
    """Present a numbered list of choices."""
    print(f"\n{C_BOLD}{title}{C_RESET}")
    for idx, (label, val) in enumerate(options, 1):
        def_mark = f" {C_CYAN}(Recommended){C_RESET}" if idx - 1 == default_idx else ""
        print(f"  {C_BOLD}{idx}){C_RESET} {label}{def_mark}")

    while True:
        choice = prompt(f"Select option (1-{len(options)})", str(default_idx + 1))
        try:
            val_idx = int(choice) - 1
            if 0 <= val_idx < len(options):
                return options[val_idx][1]
        except ValueError:
            pass
        warn(f"Please enter a number between 1 and {len(options)}")


# --- Telegram Bot Verification ---

def verify_telegram_bot_token(token: str) -> dict[str, Any] | None:
    """Call Telegram getMe API to verify bot token and fetch bot info."""
    clean_token = token.strip()
    if not clean_token or ":" not in clean_token:
        return None

    url = f"https://api.telegram.org/bot{clean_token}/getMe"
    req = urllib.request.Request(url, headers={"User-Agent": "TelegramShopSetup/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result", {})
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return None


# --- Main Setup Flow ---

async def run_setup_wizard(quick: bool = False) -> None:
    print(f"\n{C_BOLD}{C_MAGENTA}")
    print(r"  ████████╗███████╗██╗     ███████╗ ██████╗ ██████╗  ██████╗ ████████╗")
    print(r"  ╚══██╔══╝██╔════╝██║     ██╔════╝██╔════╝ ██╔══██╗██╔═══██╗╚══██╔══╝")
    print(r"     ██║   █████╗  ██║     █████╗  ██║  ███╗██████╔╝██║   ██║   ██║   ")
    print(r"     ██║   ██╔══╝  ██║     ██╔══╝  ██║   ██║██╔══██╗██║   ██║   ██║   ")
    print(r"     ██║   ███████╗███████╗███████╗╚██████╔╝██████╔╝╚██████╔╝   ██║   ")
    print(r"     ╚═╝   ╚══════╝╚══════╝╚══════╝ ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝   ")
    print(f"{C_RESET}")
    print(f"  {C_BOLD}White-Label Telegram Mini App Store — Commercial Setup Wizard{C_RESET}")
    print(f"  {C_DIM}Turnkey e-commerce storefront for digital goods, subscriptions & vouchers{C_RESET}\n")

    env_path = Path(".env")
    if env_path.exists():
        backup_path = Path(".env.backup")
        shutil.copyfile(env_path, backup_path)
        info(f"Existing .env backed up to {backup_path}")

    # --- Step 1: Telegram Bot Token ---
    header("STEP 1: Telegram Bot Integration")
    print("  Create a new bot via @BotFather on Telegram (send /newbot), or use an existing one.")

    bot_token = ""
    bot_info = None

    while True:
        bot_token = prompt("Enter your Telegram Bot Token", "8432363715:AAEL1_j25y-V1w_0q4L9XnZ7a1234567890" if quick else "")
        if not bot_token:
            warn("Bot token cannot be empty.")
            continue

        print("  Verifying token with Telegram API...", end="", flush=True)
        bot_info = verify_telegram_bot_token(bot_token)
        if bot_info:
            print(f"\r", end="")
            bot_username = bot_info.get("username", "Unknown")
            bot_name = bot_info.get("first_name", "Bot")
            bot_id = bot_info.get("id", "N/A")
            success(f"Verified live Telegram Bot: @{bot_username} (\"{bot_name}\", ID: {bot_id})")
            break
        else:
            print(f"\r", end="")
            warn("Could not verify bot token via Telegram API (check token format or network).")
            proceed = prompt("Proceed anyway with this token? (y/N)", "n").lower()
            if proceed == "y":
                bot_username = "CustomBot"
                break

    # --- Step 2: Store Branding & Appearance ---
    header("STEP 2: White-Label Store Branding")
    store_name = prompt("Store Name", "Cloud Deals" if not quick else "Digital Vault")
    store_tagline = prompt("Store Tagline / Subtitle", "Premium Digital Store & Instant Delivery")
    store_logo_url = prompt("Custom Store Logo URL (optional image link)", "")

    # Accent Color Presets
    color_presets = [
        ("OLED Apple Blue (#0071e3)", "#0071e3"),
        ("Cyber Violet (#8a2be2)", "#8a2be2"),
        ("Emerald Cash (#10b981)", "#10b981"),
        ("Sunset Amber (#ff9f0a)", "#ff9f0a"),
        ("Neon Crimson (#ff2d55)", "#ff2d55"),
        ("Custom HEX Code", "custom"),
    ]
    accent_choice = choose_option("Choose Mini App Theme Accent Color", color_presets, default_idx=0)
    if accent_choice == "custom":
        while True:
            custom_hex = prompt("Enter 6-character HEX color code (e.g. #7c3aed)", "#7c3aed")
            if re.match(r"^#[0-9a-fA-F]{6}$", custom_hex):
                accent_color = custom_hex
                break
            warn("Invalid HEX format. Example: #0071e3")
    else:
        accent_color = accent_choice
    success(f"Selected accent color: {accent_color}")

    # Currency selection
    currency_presets = [
        ("USD ($) — United States Dollar", ("USD", "$")),
        ("USDT (₮) — Tether USD", ("USDT", "₮")),
        ("EUR (€) — Euro", ("EUR", "€")),
        ("GBP (£) — British Pound", ("GBP", "£")),
        ("INR (₹) — Indian Rupee", ("INR", "₹")),
    ]
    curr_choice = choose_option("Select Primary Store Currency", [(p[0], f"{p[1][0]}:{p[1][1]}") for p in currency_presets], default_idx=0)
    currency_code, currency_symbol = curr_choice.split(":")
    success(f"Currency configured: {currency_code} ({currency_symbol})")

    # Warranty
    warranty_hours = prompt("Customer Warranty Protection (hours)", "24")

    # --- Step 3: Administration & Community Links ---
    header("STEP 3: Administration & Community Channels")
    admin_ids = prompt("Admin Telegram IDs (comma-separated, get from @userinfobot)", "123456789")
    support_username = prompt("Customer Support Telegram @username", "@Support")
    vouch_channel = prompt("Vouches / Feedback Telegram channel (@channel or ID)", "")
    restock_channel = prompt("Restock / Announcements Telegram channel (@channel or ID)", "")
    force_channel = prompt("Force-Subscription channel ID (0 to disable)", "0")

    # --- Step 4: Crypto Payment Provider ---
    header("STEP 4: Crypto Payment Gateway")
    payment_options = [
        ("CryptoBot (@CryptoBot — Zero-setup, instant Telegram native)", "cryptobot"),
        ("OxaPay (Non-custodial, 0.4% fee, 15+ blockchains)", "oxapay"),
        ("Cryptomus (Multi-currency merchant API)", "cryptomus"),
        ("Binance Pay (Direct QR / App checkout)", "binancepay"),
        ("Balance-Only / Test Mode (Zero payment gateway needed)", "none"),
    ]
    pay_choice = choose_option("Select Primary Crypto Gateway", payment_options, default_idx=0)

    cryptopay_token = ""
    oxapay_api_key = ""
    cryptomus_merchant_id = ""
    cryptomus_payment_key = ""
    binance_api_key = ""
    binance_secret_key = ""

    if pay_choice == "cryptobot":
        cryptopay_token = prompt("Enter @CryptoBot App API Token (from @CryptoBot -> /pay -> Create App)", "")
    elif pay_choice == "oxapay":
        oxapay_api_key = prompt("Enter OxaPay Merchant API Key", "")
    elif pay_choice == "cryptomus":
        cryptomus_merchant_id = prompt("Enter Cryptomus Merchant UUID", "")
        cryptomus_payment_key = prompt("Enter Cryptomus Payment API Key", "")
    elif pay_choice == "binancepay":
        binance_api_key = prompt("Enter Binance Pay API Key", "")
        binance_secret_key = prompt("Enter Binance Pay Secret Key", "")

    # --- Step 5: WebApp Domain & Security Keys ---
    header("STEP 5: Domain & Auto-SSL Configuration")
    domain = prompt("Public Domain for Auto-SSL (e.g. shop.example.com, or leave empty for localhost)", "")
    
    if domain:
        ssl_email = prompt("Email for SSL certificate expiration alerts", f"admin@{domain}")
        default_webapp_url = f"https://{domain}/webapp"
    else:
        ssl_email = ""
        default_webapp_url = "http://localhost:8000/webapp"

    webapp_url = prompt("Public WebApp URL", default_webapp_url)

    # Auto-generate keys
    from cryptography.fernet import Fernet
    generated_fernet_key = Fernet.generate_key().decode()
    generated_jwt_secret = secrets.token_urlsafe(32)
    success("Generated cryptographically secure 256-bit Fernet encryption key")
    success("Generated high-entropy JWT auth secret")

    # --- Step 6: Write Configuration to .env ---
    header("STEP 6: Generating .env Configuration")

    env_content = f"""# ===========================================================================
# TELEGRAM SHOP BOT & WHITE-LABEL WEBAPP CONFIGURATION
# Generated automatically by setup_wizard.py
# ===========================================================================

# --- Telegram Bot Credentials ---
BOT_TOKEN={bot_token}
ADMIN_IDS={admin_ids}
SUPPORT_USERNAME={support_username}

# --- Domain & Auto-SSL Deployment ---
DOMAIN={domain}
SSL_EMAIL={ssl_email}
WEBAPP_URL={webapp_url}

# --- Whitelabel Store Branding & Theming ---
STORE_NAME={store_name}
STORE_TAGLINE={store_tagline}
STORE_LOGO_URL={store_logo_url}
STORE_ACCENT_COLOR={accent_color}
STORE_CURRENCY={currency_code}
STORE_CURRENCY_SYMBOL={currency_symbol}
WARRANTY_HOURS={warranty_hours}

# --- Community & Channel Integrations ---
FORCE_CHANNEL_ID={force_channel}
VOUCH_CHANNEL_ID={vouch_channel}
RESTOCK_CHANNEL_ID={restock_channel}

# --- Database ---
DATABASE_URL=sqlite+aiosqlite:///data/shop.db

# --- Security & Credentials Encryption ---
INVENTORY_ENCRYPTION_KEY={generated_fernet_key}
JWT_SECRET_KEY={generated_jwt_secret}
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=168

# --- Crypto Payment Gateways ---
CRYPTOPAY_API_TOKEN={cryptopay_token}
OXAPAY_API_KEY={oxapay_api_key}
CRYPTOMUS_MERCHANT_ID={cryptomus_merchant_id}
CRYPTOMUS_PAYMENT_KEY={cryptomus_payment_key}
BINANCE_PAY_API_KEY={binance_api_key}
BINANCE_PAY_SECRET_KEY={binance_secret_key}

# --- E-Commerce Growth Features ---
DEPOSIT_BONUS_ENABLED=true
BULK_PRICING_ENABLED=true
EXPIRING_ORDERS_ENABLED=true
ORDER_EXPIRY_MINUTES=30
"""

    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    success("Configuration written to .env")

    # Ensure data directory exists
    Path("data").mkdir(exist_ok=True)

    # --- Step 7: Database Initialization ---
    header("STEP 7: Database Migration & Schema Creation")
    print("  Initializing SQLite database tables and indexes...")
    from app.database.database import close_db, init_db
    await init_db()
    success("Database tables, indexes, and constraints initialized successfully.")
    await close_db()

    # --- Step 8: Seed Demo Catalog ---
    header("STEP 8: Store Catalog Population")
    seed_choice = prompt("Populate store with realistic demo products (VPNs, Cloud, AI, Streaming)? (Y/n)", "y").lower()
    if seed_choice != "n":
        print("  Seeding high-converting demo catalog...")
        from seed_catalog import seed_catalog, show_status
        await init_db()
        c, p, i = await seed_catalog()
        success(f"Seeded {c} categories, {p} products, and {i} encrypted stock items!")
        await show_status()
        await close_db()
    else:
        info("Skipped catalog seeding. You can seed anytime using 'python seed_catalog.py'")

    # --- Final Handoff Summary ---
    header("🎉 SETUP COMPLETED SUCCESSFULLY!")
    print(f"  {C_BOLD}Your turnkey Telegram Mini App Store is ready for launch!{C_RESET}\n")
    print(f"  {C_BOLD}Store Name:{C_RESET}     {store_name}")
    print(f"  {C_BOLD}Theme Accent:{C_RESET}   {accent_color}")
    print(f"  {C_BOLD}Currency:{C_RESET}       {currency_code} ({currency_symbol})")
    print(f"  {C_BOLD}Bot Integration:{C_RESET} {'@' + bot_username if bot_info else 'Configured'}")
    print(f"  {C_BOLD}Mini App URL:{C_RESET}   {webapp_url}")
    print("\n  " + "-" * 55)
    print(f"  {C_BOLD}To launch your store services:{C_RESET}")
    print(f"    🚀 1-Click Docker Launch:  {C_GREEN}./deploy.sh{C_RESET} (or {C_CYAN}docker compose up -d --build{C_RESET})")
    print(f"    💻 Local Python Run:       {C_CYAN}python run.py{C_RESET}")
    print(f"    📦 Check Catalog Status:   {C_CYAN}python seed_catalog.py --status{C_RESET}")
    print(f"    🔌 Embed in existing bot:  {C_CYAN}Read EMBED_GUIDE.md{C_RESET}")
    print("  " + "-" * 55 + "\n")


def main() -> None:
    quick = "--quick" in sys.argv
    asyncio.run(run_setup_wizard(quick=quick))


if __name__ == "__main__":
    main()
