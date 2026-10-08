"""Application configuration using Pydantic Settings."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url


class Settings(BaseSettings):
    """Cloud Deals application settings.

    All values are loaded from environment variables or a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram Bot ---
    bot_token: str = ""

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./cloud_deals.db"

    # --- Admin ---
    admin_telegram_ids: str = ""

    # --- Crypto Payment Provider ---
    crypto_provider: str = "cryptopay"  # "cryptopay" (@CryptoBot), "oxapay", "binancepay", "nowpayments", "cryptomus"

    # Crypto Pay (@CryptoBot)
    cryptopay_api_token: str = ""

    # OxaPay
    oxapay_merchant_key: str = ""

    # Binance Pay
    binance_pay_api_key: str = ""
    binance_pay_secret_key: str = ""

    # NOWPayments
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""
    nowpayments_sandbox: bool = True

    # Cryptomus
    cryptomus_merchant_id: str = ""
    cryptomus_payment_key: str = ""

    # --- Webhook & Mini App ---
    webhook_base_url: str = "http://localhost:8000"
    webapp_url: str = ""  # Custom Mini App URL; if empty, defaults to webhook_base_url + "/webapp"

    # --- API Server ---
    api_host: str = "0.0.0.0"
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("API_PORT", "PORT"),
    )

    # --- JWT Authentication ---
    jwt_secret: str = ""  # Secret for signing WebApp JWT tokens; auto-derived from bot_token if empty
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 168  # 7 days

    # --- Store Settings ---
    store_name: str = "Cloud Deals"
    support_username: str = ""
    order_expiry_minutes: int = 30
    warranty_hours: int = 24
    force_channel_id: str = ""  # e.g. "@YourChannel" or "" to disable
    vouch_channel_id: str = ""  # e.g. "@CloudDealsVouches" or "" to disable
    restock_channel_id: str = ""  # e.g. "@CloudDealsRestock" or "" to disable
    stars_usd_rate: float = 0.0  # 0.0 = disabled (no Telegram Stars); set > 0 to enable
    inventory_encryption_key: str = ""  # Fernet key or auto-derived from bot_token if empty

    # --- Referral & Affiliate Program ---
    referral_commission_percent: float = 5.0  # Percentage of order amount credited to referrer (e.g. 5.0 = 5%)
    referral_bonus_amount: float = 0.00  # Optional fixed signup bonus for new referred users

    # --- Analytics & Daily Digest ---
    daily_digest_enabled: bool = True  # Automatically send 24h sales summary to admins
    daily_digest_utc_hour: int = 0  # Hour of day (0-23 UTC) to send the daily digest (0 = midnight UTC)

    # --- Logging ---
    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Normalize database URL for async drivers (SQLite & PostgreSQL)."""
        if not v:
            return "sqlite+aiosqlite:///./cloud_deals.db"

        url_str = v.strip()

        # Handle Postgres URLs (Neon, Render, Supabase, etc.)
        if url_str.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
            try:
                parsed = make_url(url_str)
                # Ensure asyncpg driver
                if parsed.drivername in ("postgres", "postgresql"):
                    parsed = parsed.set(drivername="postgresql+asyncpg")

                # asyncpg uses ssl=require instead of sslmode=require
                query = dict(parsed.query)
                if "sslmode" in query:
                    val = query.pop("sslmode")
                    if val in ("require", "verify-ca", "verify-full"):
                        query["ssl"] = "require"

                # Remove query params not supported by asyncpg
                for unsupported in ("channel_binding", "target_session_attrs", "gssencmode"):
                    query.pop(unsupported, None)

                parsed = parsed.set(query=query)
                return parsed.render_as_string(hide_password=False)
            except Exception:
                # Fallback replacement if parsing fails
                if url_str.startswith("postgres://"):
                    url_str = "postgresql+asyncpg://" + url_str[len("postgres://"):]
                elif url_str.startswith("postgresql://"):
                    url_str = "postgresql+asyncpg://" + url_str[len("postgresql://"):]
                clean_url = url_str.replace("sslmode=require", "ssl=require")
                clean_url = clean_url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("channel_binding=require", "")
                return clean_url

        return url_str

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: str) -> str:
        """Keep raw string; parsed via property."""
        return v if v is not None else ""

    @property
    def effective_jwt_secret(self) -> str:
        """Return effective secret key used for signing JWT access tokens."""
        if self.jwt_secret and self.jwt_secret.strip():
            return self.jwt_secret.strip()
        if self.bot_token:
            import hashlib
            return hashlib.sha256(f"jwt_{self.bot_token}".encode()).hexdigest()
        return "cloud-deals-default-jwt-secret-key-change-in-production"

    @property
    def admin_ids_list(self) -> list[int]:
        """Parse comma-separated admin IDs into a list of integers."""
        if not self.admin_telegram_ids:
            return []
        ids: list[int] = []
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if part and part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def nowpayments_base_url(self) -> str:
        """Return the appropriate NOWPayments API base URL."""
        if self.nowpayments_sandbox:
            return "https://api-sandbox.nowpayments.io/v1"
        return "https://api.nowpayments.io/v1"

    @property
    def effective_webapp_url(self) -> str:
        """Return the effective Mini App URL.

        Prioritizes:
        1. Explicit webapp_url if set.
        2. RENDER_EXTERNAL_URL (automatically provided by Render).
        3. RAILWAY_PUBLIC_DOMAIN (automatically provided by Railway).
        4. FLY_APP_NAME (automatically provided by Fly.io).
        5. webhook_base_url if configured with https.
        """
        if self.webapp_url and self.webapp_url.strip():
            return self.webapp_url.strip().rstrip("/")

        # Auto-detect Render deployment environment variable
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
        if render_url:
            return f"{render_url}/webapp"

        # Auto-detect Railway deployment environment variable
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip().rstrip("/")
        if railway_domain:
            return f"https://{railway_domain}/webapp"

        # Auto-detect Fly.io deployment environment variable
        fly_app = os.environ.get("FLY_APP_NAME", "").strip().rstrip("/")
        if fly_app:
            return f"https://{fly_app}.fly.dev/webapp"

        # Auto-detect Koyeb deployment environment variable
        koyeb_domain = os.environ.get("KOYEB_PUBLIC_DOMAIN", "").strip().rstrip("/")
        if koyeb_domain:
            return f"https://{koyeb_domain}/webapp"

        # Check webhook_base_url if configured with https
        if self.webhook_base_url and self.webhook_base_url.startswith("https://"):
            return f"{self.webhook_base_url.rstrip('/')}/webapp"

        # Fallback for local testing
        if self.webhook_base_url:
            return f"{self.webhook_base_url.rstrip('/')}/webapp"

        return ""

    def is_admin(self, telegram_id: int) -> bool:
        """Check if a Telegram user ID is an admin."""
        return telegram_id in self.admin_ids_list

    def validate_production(self) -> list[str]:
        """Return a list of warnings for missing production configuration."""
        warnings: list[str] = []
        if not self.bot_token:
            warnings.append("BOT_TOKEN is required")
        if not self.admin_telegram_ids:
            warnings.append("ADMIN_TELEGRAM_IDS is empty — no admin access")

        if self.crypto_provider.lower() == "cryptopay":
            if not self.cryptopay_api_token:
                warnings.append("CRYPTOPAY_API_TOKEN is empty — Crypto Pay payments disabled")
        elif self.crypto_provider.lower() == "oxapay":
            if not self.oxapay_merchant_key:
                warnings.append("OXAPAY_MERCHANT_KEY is empty — OxaPay payments disabled")
        elif self.crypto_provider.lower() == "binancepay":
            if not self.binance_pay_api_key:
                warnings.append("BINANCE_PAY_API_KEY is empty — Binance Pay payments disabled")
            if not self.binance_pay_secret_key:
                warnings.append("BINANCE_PAY_SECRET_KEY is empty — Binance Pay verification disabled")
        elif self.crypto_provider.lower() == "cryptomus":
            if not self.cryptomus_merchant_id:
                warnings.append("CRYPTOMUS_MERCHANT_ID is empty — Cryptomus payments disabled")
            if not self.cryptomus_payment_key:
                warnings.append("CRYPTOMUS_PAYMENT_KEY is empty — Cryptomus verification disabled")
        else:
            if not self.nowpayments_api_key:
                warnings.append("NOWPAYMENTS_API_KEY is empty — payments disabled")
            if not self.nowpayments_ipn_secret:
                warnings.append("NOWPAYMENTS_IPN_SECRET is empty — webhook verification disabled")

        if self.webhook_base_url.startswith("http://") and "localhost" not in self.webhook_base_url:
            warnings.append("WEBHOOK_BASE_URL uses HTTP — use HTTPS in production")
        return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
