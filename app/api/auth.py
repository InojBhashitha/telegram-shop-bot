"""JWT authentication utilities for Telegram Mini App and API."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import User
from app.database.repositories import user_repo

logger = logging.getLogger(__name__)


def create_access_token(
    user_id: int,
    telegram_id: int,
    is_admin: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token containing standard claims."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=settings.jwt_expiration_hours)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": user_id,
        "telegram_id": telegram_id,
        "is_admin": is_admin,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    return jwt.encode(
        payload,
        settings.effective_jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Raises:
        HTTPException (401): If token is expired or signature is invalid.
    """
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.effective_jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token signature expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please authenticate again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as err:
        logger.debug("Invalid JWT token: %s", err)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_bearer_token(authorization: Optional[str] = None) -> Optional[str]:
    """Extract raw JWT token string from Authorization header."""
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    # In case token was sent directly without Bearer prefix
    if len(parts) == 1 and "." in parts[0]:
        return parts[0]
    return None


async def get_user_from_token(
    session: AsyncSession,
    token: str,
) -> Optional[User]:
    """Resolve database User instance from a validated JWT token."""
    payload = decode_access_token(token)
    user_id = payload.get("user_id")
    telegram_id = payload.get("telegram_id")

    if user_id:
        user = await user_repo.get_by_id(session, int(user_id))
        if user:
            return user

    if telegram_id:
        user = await user_repo.get_by_telegram_id(session, int(telegram_id))
        if user:
            return user

    return None
