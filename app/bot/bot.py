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


def build_bot() -> Application:
    """Build and configure the Telegram bot application.

    Registers all handlers from the handler modules.
    """
    global _bot_instance

    settings = get_settings()
    app = Application.builder().token(settings.bot_token).build()
    _bot_instance = app.bot

    # Register handlers — order matters (ConversationHandlers first)
    from app.bot.handlers import admin, orders, products, profile, start, support

    for module in [admin, support, start, products, orders, profile]:
        for handler in module.get_handlers():
            app.add_handler(handler)

    logger.info("Bot handlers registered")
    return app
