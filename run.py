"""Cloud Deals — Main entry point.

Starts both the Telegram bot (polling) and FastAPI webhook server.
"""

from __future__ import annotations

import asyncio
import logging
import threading

import uvicorn

from app.config import get_settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def run_api_server(host: str, port: int) -> None:
    """Run the FastAPI server in a background thread."""
    from app.api.main import create_api
    api = create_api()
    config = uvicorn.Config(api, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


async def expire_orders_task(interval_seconds: int = 300) -> None:
    """Periodic task to expire old orders and release inventory."""
    from app.database.database import get_session
    from app.services import order_service
    settings = get_settings()

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with get_session() as session:
                expired = await order_service.expire_old_orders(
                    session, settings.order_expiry_minutes
                )
                if expired > 0:
                    logger.info("Periodic cleanup: expired %s orders", expired)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Order expiry task error: %s", e)
            await asyncio.sleep(60)


async def main() -> None:
    """Main async entry point."""
    settings = get_settings()
    setup_logging(settings.log_level)

    # Log startup warnings
    warnings = settings.validate_production()
    for w in warnings:
        logger.warning("Config: %s", w)

    # Initialize database
    from app.database.database import init_db
    await init_db()
    logger.info("Database initialized")

    # Start FastAPI server in background thread
    api_thread = threading.Thread(
        target=run_api_server,
        args=(settings.api_host, settings.api_port),
        daemon=True,
    )
    api_thread.start()
    logger.info("API server starting on %s:%s", settings.api_host, settings.api_port)

    # Start order expiry background task
    expiry_task = asyncio.create_task(expire_orders_task())

    # Build and run the Telegram bot
    from app.bot.bot import build_bot
    bot_app = build_bot()

    logger.info("☁️ Cloud Deals bot is running...")

    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)

        # Keep running until interrupted
        stop_event = asyncio.Event()
        await stop_event.wait()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    finally:
        expiry_task.cancel()
        try:
            await expiry_task
        except asyncio.CancelledError:
            pass

        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()

        from app.database.database import close_db
        await close_db()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
