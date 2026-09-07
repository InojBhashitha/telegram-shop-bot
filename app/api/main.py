"""FastAPI application — webhook server and health check."""

from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.webhooks.crypto import router as crypto_router
from app.api.webapp import router as webapp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan — ensure DB is initialized on startup."""
    from app.database.database import init_db
    try:
        await init_db()
        logger.info("FastAPI lifespan: Database initialized")
    except Exception as e:
        logger.warning("FastAPI lifespan init_db note: %s", e)
    yield


def create_api() -> FastAPI:
    """Create and configure the FastAPI application."""
    api = FastAPI(
        title="Cloud Deals API",
        description="Webhook and API server for Cloud Deals Telegram bot and Mini App",
        version="1.0.0",
        docs_url=None,  # Disable Swagger in production
        redoc_url=None,
        lifespan=lifespan,
    )

    # Enable CORS for Telegram WebApp
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    api.include_router(crypto_router, prefix="/webhooks/crypto", tags=["webhooks"])
    api.include_router(webapp_router, prefix="/api/webapp", tags=["webapp"])

    # Mount static assets for Telegram Mini App storefront
    webapp_dir = Path(__file__).resolve().parent.parent / "webapp"
    webapp_dir.mkdir(parents=True, exist_ok=True)
    index_file = webapp_dir / "index.html"

    @api.get("/")
    @api.get("/webapp")
    @api.get("/webapp/")
    @api.get("/app")
    @api.get("/store")
    @api.get("/shop")
    async def serve_webapp(request: Request):
        """Serve the Telegram Mini App storefront directly across all common paths."""
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/html" not in accept:
            return {
                "name": "Cloud Deals API",
                "status": "online",
                "message": "Telegram Bot and Webhook Service are running.",
            }
        return FileResponse(str(index_file))

    @api.get("/style.css")
    async def serve_root_style():
        return FileResponse(str(webapp_dir / "style.css"))

    @api.get("/app.js")
    async def serve_root_js():
        return FileResponse(str(webapp_dir / "app.js"))

    # Mount static directory for relative paths like /webapp/style.css
    api.mount("/webapp", StaticFiles(directory=str(webapp_dir), html=True), name="webapp")

    @api.get("/api")
    async def api_info():
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
