"""FastAPI application — webhook server and health check."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.webhooks.crypto import router as crypto_router

logger = logging.getLogger(__name__)


def create_api() -> FastAPI:
    """Create and configure the FastAPI application."""
    api = FastAPI(
        title="Cloud Deals API",
        description="Webhook and API server for Cloud Deals Telegram bot",
        version="1.0.0",
        docs_url=None,  # Disable Swagger in production
        redoc_url=None,
    )

    # Mount webhook routes
    api.include_router(crypto_router, prefix="/webhooks/crypto", tags=["webhooks"])

    @api.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "Cloud Deals API",
            "status": "online",
            "message": "Telegram Bot and Webhook Service are running.",
        }

    @api.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "cloud-deals"}

    return api
