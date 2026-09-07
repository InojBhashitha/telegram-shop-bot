"""Telegram bot application setup — registers handlers, shares bot instance."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Bot
from telegram.ext import Application

from app.config import get_settings

logger = logging.getLogger(__name__)

# Global bot instance for webhook-triggered notifications
_bot_instance: Optional[Bot] = None


def get_bot_instance() -> Optional[Bot]:
    """Get the shared Bot instance (available after build_bot() is called)."""
    return _bot_instance


async def _post_init(app: Application) -> None:
    """Configure Telegram Chat Menu Button on startup to launch the Mini App."""
    settings = get_settings()
    webapp_url = settings.effective_webapp_url
    if webapp_url and webapp_url.startswith("https://"):
        try:
            from telegram import MenuButtonWebApp, WebAppInfo
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🛍 Store",
                    web_app=WebAppInfo(url=webapp_url),
                )
            )
            logger.info("Telegram Chat Menu Button set to Mini App: %s", webapp_url)
        except Exception as e:
            logger.warning("Could not set Telegram menu button: %s", e)


def build_bot() -> Application:
    """Build and configure the Telegram bot application.

    Registers all handlers from the handler modules.
    """
    global _bot_instance

    settings = get_settings()
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .build()
    )
    _bot_instance = app.bot

    # Register handlers — order matters (ConversationHandlers first)
    from app.bot.handlers import admin, cart, orders, products, profile, start, support

    for module in [admin, cart, support, start, products, orders, profile]:
        for handler in module.get_handlers():
            app.add_handler(handler)

    logger.info("Bot handlers registered")
    return app
