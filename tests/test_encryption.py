"""Tests for sensitive inventory encryption vault."""

import pytest
from app.utils.crypto_vault import encrypt_content, decrypt_content, _get_fernet


def test_encryption_roundtrip():
    """Test encrypting and decrypting secret inventory contents."""
    secret = "user@example.com:supersecretpassword123"
    encrypted = encrypt_content(secret)

    # Must be changed and not equal to original
    assert encrypted != secret
    assert encrypted.startswith("gAAAAA")

    decrypted = decrypt_content(encrypted)
    assert decrypted == secret


def test_legacy_plaintext_fallback():
    """Legacy unencrypted credentials must pass through decrypt_content unchanged."""
    plaintext = "legacy_login:plain_password_no_encryption"
    decrypted = decrypt_content(plaintext)
    assert decrypted == plaintext


def test_empty_and_whitespace_content():
    """Empty or None content should be handled gracefully."""
    assert decrypt_content("") == ""
    assert decrypt_content("   ") == "   "


def test_fernet_instance():
    """Test _get_fernet instance."""
    suite = _get_fernet()
    assert suite is not None
