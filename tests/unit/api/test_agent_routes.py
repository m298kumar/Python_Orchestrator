"""
Tests for /api/agents/* endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.core.base_agent import AgentCapabilities


def _make_fake_registry():
    """
    Build a lightweight fake AgentRegistry that avoids importing real agents
    (which pull in heavy dependencies). Returns a mock with list_agents(),
    has(), and get() that behave like the real registry.
    """
    caps = [
        AgentCapabilities(
            agent_id="requirements_agent",
            agent_version="1.0.0",
            description="Generates test cases from requirements.",
            input_types=["RequirementArtifact"],
            output_types=["TestCaseArtifact"],
        ),
        AgentCapabilities(
            agent_id="bdd_agent",
            agent_version="1.0.0",
            description="Generates BDD feature files.",
            input_types=["TestCaseArtifact"],
            output_types=["FeatureFileArtifact"],
        ),
        AgentCapabilities(
            agent_id="crawler_agent",
            agent_version="1.0.0",
            description="Crawls web pages and builds site model.",
            input_types=["CrawledPageArtifact"],
            output_types=["SiteModelArtifact"],
        ),
        AgentCapabilities(
            agent_id="api_test_agent",
            agent_version="1.0.0",
            description="Generates API tests from OpenAPI specs.",
            input_types=["APIModelArtifact"],
            output_types=["APITestArtifact"],
        ),
    ]
    caps_by_id = {c.agent_id: c for c in caps}

    registry = MagicMock()
    registry.list_agents.return_value = caps
    registry.has.side_effect = lambda aid: aid in caps_by_id

    def _get(aid):
        if aid not in caps_by_id:
            raise KeyError(f"Agent '{aid}' not registered.")
        mock_agent = MagicMock()
        mock_agent.get_capabilities.return_value = caps_by_id[aid]
        return mock_agent

    registry.get.side_effect = _get
    return registry


@pytest.fixture()
def client():
    fake_registry = _make_fake_registry()
    with patch("stlc_platform.api.deps._agent_registry", fake_registry):
        yield TestClient(app)


class TestListAgents:
    """GET /api/agents/ returns all registered agents."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/agents/")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/agents/").json()
        assert isinstance(data, list)

    def test_contains_expected_agent_ids(self, client: TestClient):
        data = client.get("/api/agents/").json()
        ids = {a["agent_id"] for a in data}
        assert "requirements_agent" in ids
        assert "bdd_agent" in ids
        assert "crawler_agent" in ids
        assert "api_test_agent" in ids

    def test_agent_has_required_fields(self, client: TestClient):
        data = client.get("/api/agents/").json()
        for agent in data:
            assert "agent_id" in agent
            assert "agent_version" in agent
            assert "description" in agent
            assert "input_types" in agent
            assert "output_types" in agent


class TestGetAgent:
    """GET /api/agents/{agent_id} returns capabilities for a single agent."""

    def test_known_agent_returns_200(self, client: TestClient):
        resp = client.get("/api/agents/requirements_agent")
        assert resp.status_code == 200

    def test_known_agent_has_capabilities(self, client: TestClient):
        data = client.get("/api/agents/requirements_agent").json()
        assert data["agent_id"] == "requirements_agent"
        assert "description" in data
        assert "input_types" in data
        assert "output_types" in data

    def test_nonexistent_agent_returns_404(self, client: TestClient):
        resp = client.get("/api/agents/nonexistent")
        assert resp.status_code == 404

    def test_bdd_agent_returns_correct_id(self, client: TestClient):
        data = client.get("/api/agents/bdd_agent").json()
        assert data["agent_id"] == "bdd_agent"

    def test_404_response_has_detail(self, client: TestClient):
        data = client.get("/api/agents/nonexistent").json()
        assert "detail" in data
