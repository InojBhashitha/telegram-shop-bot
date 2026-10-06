"""Tests for JWT token authentication in Telegram Mini App API."""

from __future__ import annotations

from datetime import timedelta
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.auth import (
    create_access_token,
    decode_access_token,
    extract_bearer_token,
)
from app.api.main import create_api
from app.database.database import close_db, get_session, init_db
from app.database.models import User
from app.services import user_service
from fastapi import HTTPException


class TestJWTTokenCore:
    """Test core JWT token generation, signature validation and decoding."""

    def test_create_and_decode_valid_token(self):
        token = create_access_token(user_id=42, telegram_id=987654321, is_admin=True)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

        payload = decode_access_token(token)
        assert payload["user_id"] == 42
        assert payload["telegram_id"] == 987654321
        assert payload["is_admin"] is True
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_raises_401(self):
        # Create token that expired 1 hour ago
        token = create_access_token(
            user_id=42,
            telegram_id=987654321,
            expires_delta=timedelta(seconds=-3600),
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_tampered_token_raises_401(self):
        token = create_access_token(user_id=42, telegram_id=987654321)
        # Modify the payload part
        parts = token.split(".")
        tampered_token = f"{parts[0]}.eyJzdWIiOiIxIn0.{parts[2]}"
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered_token)
        assert exc_info.value.status_code == 401

    def test_extract_bearer_token(self):
        token = "header.payload.signature"
        assert extract_bearer_token(f"Bearer {token}") == token
        assert extract_bearer_token(f"bearer {token}") == token
        assert extract_bearer_token(token) == token
        assert extract_bearer_token(None) is None
        assert extract_bearer_token("") is None


class TestJWTAPIEndpoints:
    """Test API integration with JWT bearer tokens."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_db(self):
        await init_db()
        yield
        await close_db()

    @pytest_asyncio.fixture
    async def client(self):
        api = create_api()
        transport = ASGITransport(app=api)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_auth_issues_jwt_token(self, client: AsyncClient):
        response = await client.post(
            "/api/webapp/auth",
            json={
                "dev_telegram_id": 777001,
                "dev_username": "jwt_user",
                "dev_first_name": "Johnny",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert "token" in data
        assert data["token_type"] == "bearer"
        assert len(data["token"].split(".")) == 3

    @pytest.mark.asyncio
    async def test_access_user_profile_with_jwt_bearer(self, client: AsyncClient):
        # 1. Authenticate to get JWT token
        auth_resp = await client.post(
            "/api/webapp/auth",
            json={"dev_telegram_id": 777002, "dev_username": "bearer_tester"},
        )
        token = auth_resp.json()["token"]

        # 2. Call /api/webapp/user using Bearer token
        user_resp = await client.get(
            "/api/webapp/user",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert user_resp.status_code == 200
        user_data = user_resp.json()["user"]
        assert user_data["telegram_id"] == 777002
        assert user_data["username"] == "bearer_tester"

    @pytest.mark.asyncio
    async def test_access_cart_with_jwt_bearer(self, client: AsyncClient):
        auth_resp = await client.post(
            "/api/webapp/auth",
            json={"dev_telegram_id": 777003},
        )
        token = auth_resp.json()["token"]

        cart_resp = await client.get(
            "/api/webapp/cart",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cart_resp.status_code == 200
        assert "items" in cart_resp.json()

    @pytest.mark.asyncio
    async def test_tampered_bearer_token_returns_401(self, client: AsyncClient):
        user_resp = await client.get(
            "/api/webapp/user",
            headers={"Authorization": "Bearer totally.invalid.signature"},
        )
        assert user_resp.status_code == 401
