"""Symmetric encryption vault for sensitive inventory credentials.

Uses AES-256 in CBC/HMAC-SHA256 mode via Fernet.
Supports transparent backward-compatibility for unencrypted legacy content.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Get or initialize the Fernet cipher instance."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    settings = get_settings()
    custom_key = settings.inventory_encryption_key.strip()

    if custom_key:
        try:
            # Validate if it's already a valid 32-byte urlsafe base64 key
            key_bytes = custom_key.encode("utf-8")
            _fernet_instance = Fernet(key_bytes)
            return _fernet_instance
        except Exception as e:
            logger.warning("Custom INVENTORY_ENCRYPTION_KEY is invalid, falling back to derived key: %s", e)

    # Derive deterministic 32-byte Fernet key from bot_token using SHA-256
    seed = (settings.bot_token or "cloud-deals-default-encryption-seed").encode("utf-8")
    derived_bytes = hashlib.sha256(seed).digest()
    fernet_key = base64.urlsafe_b64encode(derived_bytes)
    _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_content(plaintext: str) -> str:
    """Encrypt deliverable content at rest.

    If input is empty, returns empty string.
    If already encrypted (starts with Fernet header gAAAAA), returns as-is.
    """
    if not plaintext:
        return ""

    stripped = plaintext.strip()
    # Check if already encrypted
    if stripped.startswith("gAAAAA") and len(stripped) > 50:
        return stripped

    cipher = _get_fernet()
    encrypted = cipher.encrypt(plaintext.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_content(stored_content: str) -> str:
    """Decrypt stored inventory content.

    If the content is not an encrypted Fernet token or cannot be decrypted,
    it gracefully returns the stored string as-is (backward compatible).
    """
    if not stored_content:
        return ""

    stripped = stored_content.strip()
    if not (stripped.startswith("gAAAAA") and len(stripped) > 50):
        # Plaintext legacy record
        return stored_content

    cipher = _get_fernet()
    try:
        decrypted = cipher.decrypt(stripped.encode("utf-8"))
        return decrypted.decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning("Could not decrypt inventory content, returning as plaintext fallback: %s", e)
        return stored_content
