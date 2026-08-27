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
    bot_token: str

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./cloud_deals.db"

    # --- Admin ---
    admin_telegram_ids: str = ""

    # --- Crypto Payment Provider ---
    crypto_provider: str = "nowpayments"

    # NOWPayments
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""
    nowpayments_sandbox: bool = True

    # --- Webhook ---
    webhook_base_url: str = "http://localhost:8000"

    # --- API Server ---
    api_host: str = "0.0.0.0"
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("API_PORT", "PORT"),
    )

    # --- Store Settings ---
    store_name: str = "Cloud Deals"
    support_username: str = ""
    order_expiry_minutes: int = 30

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

                parsed = parsed._replace(query=query)
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
