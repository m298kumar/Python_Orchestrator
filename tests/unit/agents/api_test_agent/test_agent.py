"""Unit tests for the APITestAgent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stlc_platform.agents.api_test_agent import APITestAgent
from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact

_FIXTURES = Path(__file__).resolve().parent.parent.parent.parent / "fixtures"


def _make_model(**overrides) -> APIModelArtifact:
    defaults = {
        "base_url": "http://localhost:8080",
        "auth_type": "bearer",
        "spec_format": "openapi_3.0",
        "spec_title": "Test API",
        "endpoints": [
            APIEndpointArtifact(
                path="/items",
                method="GET",
                operation_id="listItems",
                summary="List items",
                response_schema={"type": "object", "properties": {"id": {"type": "integer"}}},
            )
        ],
    }
    defaults.update(overrides)
    return APIModelArtifact(**defaults)


@pytest.fixture
def agent():
    return APITestAgent()


@pytest.fixture
def petstore_spec():
    return json.loads((_FIXTURES / "openapi_petstore.json").read_text(encoding="utf-8"))


# ── Input Validation ─────────────────────────────────────────────────────────


class TestValidateInput:
    def test_valid_spec_input(self, agent, petstore_spec):
        result = agent.validate_input({"openapi_spec": petstore_spec})
        assert result.valid is True

    def test_valid_model_input(self, agent):
        result = agent.validate_input({"api_model": _make_model()})
        assert result.valid is True

    def test_missing_both_inputs(self, agent):
        result = agent.validate_input({})
        assert result.valid is False
        assert len(result.errors) == 1

    def test_spec_wrong_type(self, agent):
        result = agent.validate_input({"openapi_spec": 12345})
        assert result.valid is False

    def test_model_wrong_type(self, agent):
        result = agent.validate_input({"api_model": {"not": "a model"}})
        assert result.valid is False


# ── Execute ──────────────────────────────────────────────────────────────────


class TestExecute:
    def test_execute_from_spec(self, agent, petstore_spec):
        result = agent.execute({"openapi_spec": petstore_spec}, {})
        assert result.success is True
        assert "api_model" in result.artifacts
        assert "test_files" in result.artifacts
        assert result.metadata["total_endpoints"] == 8
        assert result.metadata["total_tests"] > 0

    def test_execute_from_model(self, agent):
        model = _make_model()
        result = agent.execute({"api_model": model}, {})
        assert result.success is True
        assert result.metadata["total_endpoints"] == 1

    def test_execute_invalid_input(self, agent):
        result = agent.execute({}, {})
        assert result.success is False
        assert len(result.errors) > 0

    def test_metadata_has_framework(self, agent, petstore_spec):
        result = agent.execute({"openapi_spec": petstore_spec}, {})
        assert result.metadata["framework"] == "pytest_requests"

    def test_metadata_has_spec_format(self, agent, petstore_spec):
        result = agent.execute({"openapi_spec": petstore_spec}, {})
        assert result.metadata["spec_format"] == "openapi_3.0"

    def test_conftest_in_artifacts(self, agent, petstore_spec):
        result = agent.execute({"openapi_spec": petstore_spec}, {})
        assert "conftest" in result.artifacts
        assert result.artifacts["conftest"].filename == "conftest.py"


# ── Capabilities ─────────────────────────────────────────────────────────────


class TestGetCapabilities:
    def test_agent_id(self, agent):
        caps = agent.get_capabilities()
        assert caps.agent_id == "api_test_generation"

    def test_output_types(self, agent):
        caps = agent.get_capabilities()
        assert "APIModelArtifact" in caps.output_types
        assert "APITestArtifact" in caps.output_types
