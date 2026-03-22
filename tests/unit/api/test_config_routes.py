"""
Tests for /api/config/* endpoints.

The config route uses a module-level dict ``_config`` for storage.
We reset it between tests to ensure isolation.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import config as config_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_config():
    """Reset the in-memory config state between tests."""
    config_module._config.clear()
    config_module._config.update({"project": {}, "ollama": {}, "output": {}})
    yield
    config_module._config.clear()
    config_module._config.update({"project": {}, "ollama": {}, "output": {}})


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/config/
# ---------------------------------------------------------------------------

class TestGetConfig:
    """GET /api/config/ returns the current configuration."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/config/")
        assert resp.status_code == 200

    def test_response_has_required_keys(self, client: TestClient):
        data = client.get("/api/config/").json()
        assert "project" in data
        assert "ollama" in data
        assert "output" in data

    def test_values_are_dicts(self, client: TestClient):
        data = client.get("/api/config/").json()
        assert isinstance(data["project"], dict)
        assert isinstance(data["ollama"], dict)
        assert isinstance(data["output"], dict)

    def test_sensitive_values_masked(self, client: TestClient):
        config_module._config["ollama"]["api_key"] = "secret-123"
        config_module._config["_loaded"] = True
        data = client.get("/api/config/").json()
        assert data["ollama"]["api_key"] == "***"


# ---------------------------------------------------------------------------
# PUT /api/config/
# ---------------------------------------------------------------------------

class TestUpdateConfig:
    """PUT /api/config/ updates configuration values."""

    def test_returns_200(self, client: TestClient):
        resp = client.put("/api/config/", json={"updates": {"ollama.model": "llama3"}})
        assert resp.status_code == 200

    def test_update_applies_value(self, client: TestClient):
        client.put("/api/config/", json={"updates": {"ollama.model": "llama3"}})
        data = client.get("/api/config/").json()
        assert data["ollama"]["model"] == "llama3"

    def test_update_dot_notation_creates_nested(self, client: TestClient):
        client.put("/api/config/", json={"updates": {"project.name": "my-project"}})
        data = client.get("/api/config/").json()
        assert data["project"]["name"] == "my-project"
