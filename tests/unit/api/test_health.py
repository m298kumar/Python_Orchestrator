"""
Tests for the /api/health endpoint.
"""

import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.core.base_agent import AgentCapabilities


@pytest.fixture()
def client():
    """TestClient with a lightweight mock registry to avoid heavy imports."""
    fake_registry = MagicMock()
    fake_registry.list_agents.return_value = [
        AgentCapabilities(agent_id="a", agent_version="1.0"),
        AgentCapabilities(agent_id="b", agent_version="1.0"),
    ]
    with patch("stlc_platform.api.deps._agent_registry", fake_registry):
        yield TestClient(app)


class TestHealthEndpoint:
    """GET /api/health returns service status."""

    def test_health_returns_200(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_has_status_ok(self, client: TestClient):
        data = client.get("/api/health").json()
        assert data["status"] == "ok"

    def test_health_response_has_version(self, client: TestClient):
        data = client.get("/api/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_response_has_stage(self, client: TestClient):
        data = client.get("/api/health").json()
        assert "stage" in data
        assert isinstance(data["stage"], int)

    def test_health_response_has_agents_registered(self, client: TestClient):
        data = client.get("/api/health").json()
        assert "agents_registered" in data
        assert isinstance(data["agents_registered"], int)
        assert data["agents_registered"] >= 0

    def test_health_response_matches_schema(self, client: TestClient):
        """Verify the full shape matches HealthResponse."""
        data = client.get("/api/health").json()
        required_keys = {"status", "version", "stage", "agents_registered"}
        assert required_keys.issubset(data.keys())
