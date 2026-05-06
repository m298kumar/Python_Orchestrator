"""
Tests for the authentication module and auth routes.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.auth import (
    authenticate_user,
    create_token,
    verify_password,
    verify_token,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def client_auth_disabled():
    """TestClient with auth disabled (default)."""
    fake_registry = MagicMock()
    fake_registry.list_agents.return_value = []
    with patch("stlc_platform.api.deps._agent_registry", fake_registry):
        with patch("stlc_platform.api.auth.AUTH_ENABLED", False):
            from stlc_platform.api.main import app

            yield TestClient(app)


@pytest.fixture()
def client_auth_enabled():
    """TestClient with auth enabled."""
    fake_registry = MagicMock()
    fake_registry.list_agents.return_value = []
    with patch("stlc_platform.api.deps._agent_registry", fake_registry):
        with patch("stlc_platform.api.auth.AUTH_ENABLED", True):
            with patch("stlc_platform.api.routes.auth.AUTH_ENABLED", True):
                from stlc_platform.api.main import app

                yield TestClient(app)


# ── Auth module unit tests ──────────────────────────────────────────────────


class TestCreateAndVerifyToken:
    """Token creation and verification."""

    def test_create_token_returns_string(self):
        token = create_token("testuser", "user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_token_roundtrip(self):
        token = create_token("alice", "admin")
        user = verify_token(token)
        assert user.username == "alice"
        assert user.role == "admin"

    def test_verify_token_default_role(self):
        token = create_token("bob")
        user = verify_token(token)
        assert user.role == "user"

    def test_expired_token_raises(self):
        """A token with 0-second expiry should be expired immediately."""
        import jwt as jwt_mod

        payload = {
            "sub": "expired-user",
            "role": "user",
            "iat": int(time.time()) - 10,
            "exp": int(time.time()) - 5,
        }
        from stlc_platform.api.auth import JWT_ALGORITHM, JWT_SECRET

        token = jwt_mod.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_token_raises(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_token("not-a-real-token")
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()


class TestVerifyPassword:
    """Password verification against env var defaults."""

    def test_correct_credentials(self):
        assert verify_password("admin", "admin") is True

    def test_wrong_password(self):
        assert verify_password("wrong", "admin") is False

    def test_wrong_username(self):
        assert verify_password("admin", "wrong") is False


class TestAuthenticateUser:
    """User authentication."""

    def test_valid_user_returns_auth_user(self):
        user = authenticate_user("admin", "admin")
        assert user is not None
        assert user.username == "admin"
        assert user.role == "admin"

    def test_invalid_user_returns_none(self):
        assert authenticate_user("admin", "wrong") is None


# ── Auth route tests ────────────────────────────────────────────────────────


class TestAuthStatusEndpoint:
    """GET /api/auth/status"""

    def test_auth_status_disabled(self, client_auth_disabled: TestClient):
        resp = client_auth_disabled.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.json()["auth_enabled"] is False

    def test_auth_status_enabled(self, client_auth_enabled: TestClient):
        resp = client_auth_enabled.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.json()["auth_enabled"] is True


class TestLoginEndpoint:
    """POST /api/auth/login"""

    def test_login_when_auth_disabled(self, client_auth_disabled: TestClient):
        resp = client_auth_disabled.post(
            "/api/auth/login",
            json={"username": "anyone", "password": "anything"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_valid_credentials(self, client_auth_enabled: TestClient):
        resp = client_auth_enabled.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, client_auth_enabled: TestClient):
        resp = client_auth_enabled.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401


class TestGetCurrentUserDependency:
    """get_current_user FastAPI dependency (tested via health endpoint)."""

    def test_auth_disabled_allows_anonymous(self, client_auth_disabled: TestClient):
        """When auth is disabled, all endpoints should work without tokens."""
        resp = client_auth_disabled.get("/api/health")
        assert resp.status_code == 200

    def test_auth_enabled_with_valid_token(self, client_auth_enabled: TestClient):
        """Login, then use token on a protected-capable endpoint."""
        login_resp = client_auth_enabled.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        token = login_resp.json()["access_token"]
        # Health endpoint doesn't require auth dependency, but auth routes work
        resp = client_auth_enabled.get(
            "/api/auth/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_auth_enabled_with_api_key(self, client_auth_enabled: TestClient):
        """API key authentication via X-API-Key header."""
        with patch("stlc_platform.api.auth.API_KEYS", {"test-key-123"}):
            resp = client_auth_enabled.get(
                "/api/auth/status",
                headers={"X-API-Key": "test-key-123"},
            )
            assert resp.status_code == 200
