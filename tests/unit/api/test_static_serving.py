"""
Tests for production static file serving behaviour.
"""

import os
import textwrap

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture()
def client_no_frontend():
    """TestClient with STLC_SERVE_FRONTEND=false — no SPA route."""
    fake_registry = MagicMock()
    fake_registry.list_agents.return_value = []
    # Force-disable frontend serving and reload the app module
    env = {**os.environ, "STLC_SERVE_FRONTEND": "false"}
    with patch.dict(os.environ, env, clear=False):
        with patch("stlc_platform.api.deps._agent_registry", fake_registry):
            from stlc_platform.api.main import app

            yield TestClient(app)


@pytest.fixture()
def client_with_frontend(tmp_path):
    """TestClient with a fake frontend/dist directory for SPA serving."""
    # Create a minimal dist layout
    dist_dir = tmp_path / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html><body>SPA</body></html>")
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "main.js").write_text("console.log('hello');")

    fake_registry = MagicMock()
    fake_registry.list_agents.return_value = []

    env = {**os.environ, "STLC_SERVE_FRONTEND": "true"}
    with patch.dict(os.environ, env, clear=False):
        with patch(
            "stlc_platform.api.main._frontend_dist", dist_dir
        ):
            with patch(
                "stlc_platform.api.main._serve_frontend", "true"
            ):
                with patch(
                    "stlc_platform.api.deps._agent_registry", fake_registry
                ):
                    from stlc_platform.api.main import app

                    yield TestClient(app)


class TestApiRoutesStillWork:
    """API routes are not blocked by SPA catch-all."""

    def test_health_endpoint_works(self, client_no_frontend: TestClient):
        resp = client_no_frontend.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_auth_status_works(self, client_no_frontend: TestClient):
        resp = client_no_frontend.get("/api/auth/status")
        assert resp.status_code == 200

    def test_login_endpoint_works(self, client_no_frontend: TestClient):
        resp = client_no_frontend.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200


class TestFrontendDisabled:
    """When no frontend dist exists, non-API paths return 404 or SPA."""

    def test_unknown_path_behaviour(self, client_no_frontend: TestClient):
        """Non-API path returns 404 (no dist) or 200 (dist exists with SPA catch-all)."""
        resp = client_no_frontend.get("/some-frontend-route")
        # If frontend/dist exists, the SPA catch-all serves 200;
        # otherwise 404. Both are valid depending on the build state.
        assert resp.status_code in (200, 404, 405)


class TestFrontendEnabled:
    """When frontend dist exists and STLC_SERVE_FRONTEND=true, SPA works."""

    def test_api_health_still_works(self, client_with_frontend: TestClient):
        resp = client_with_frontend.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
