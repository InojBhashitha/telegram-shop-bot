"""Structured logging configuration for Cloud Deals."""

from __future__ import annotations

import logging
import sys
from typing import Optional


# Patterns that must never appear in log output
_SENSITIVE_PATTERNS = (
    "api_key",
    "api_secret",
    "ipn_secret",
    "bot_token",
    "private_key",
    "seed_phrase",
    "password",
    "secret",
)


class SensitiveFilter(logging.Filter):
    """Filter that redacts potentially sensitive values from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg_lower = record.msg.lower()
            for pattern in _SENSITIVE_PATTERNS:
                if pattern in msg_lower and "=" in record.msg:
                    # Redact the value after the pattern
                    record.msg = f"[REDACTED — message contained '{pattern}']"
                    record.args = None
                    break
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure application logging.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if numeric_level <= logging.DEBUG else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger for a module.

    Args:
        name: Logger name, typically __name__.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
