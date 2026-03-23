"""Tests for the TestGenerationAgent class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock

import pytest

from stlc_platform.core.base_agent import AgentCapabilities, AgentResult, ValidationResult
from stlc_platform.core.contracts import TestCaseArtifact
from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    title: str = "User Login Feature"
    description: str = "User should be able to log in with valid credentials"
    category: str = "Authentication"
    priority: str = "High"
    acceptance_criteria: List[str] = field(default_factory=lambda: [
        "User can login with valid credentials",
        "System displays error for invalid password",
    ])


class MockLLMClient:
    def generate_test_case(self, prompt, system_prompt=None):
        return {
            "title": "Test Title",
            "description": "Test login functionality",
            "preconditions": "Valid user account exists",
            "steps": [
                {"action": "Navigate to login", "expected_result": "Login page loads"},
                {"action": "Enter credentials", "expected_result": "Fields populated"},
                {"action": "Click login", "expected_result": "Dashboard loads"},
            ],
            "expected_outcome": "User logged in",
            "component": "Login Screen",
            "given": "A valid user",
            "when": "User logs in",
            "then": "Dashboard shown",
            "priority": "High",
            "tags": ["auth", "positive"],
            "estimated_duration": "5",
        }


class TestValidateInput:
    """Test input validation."""

    @pytest.fixture
    def agent(self):
        return TestGenerationAgent()

    def test_valid_input(self, agent):
        result = agent.validate_input({
            "requirements": [MockRequirement()],
            "llm_client": MockLLMClient(),
        })
        assert result.valid is True
        assert result.errors == []

    def test_missing_requirements(self, agent):
        result = agent.validate_input({"llm_client": MockLLMClient()})
        assert result.valid is False
        assert any("requirements" in e for e in result.errors)

    def test_empty_requirements(self, agent):
        result = agent.validate_input({
            "requirements": [],
            "llm_client": MockLLMClient(),
        })
        assert result.valid is False

    def test_requirements_not_list(self, agent):
        result = agent.validate_input({
            "requirements": "not a list",
            "llm_client": MockLLMClient(),
        })
        assert result.valid is False

    def test_missing_llm_client(self, agent):
        result = agent.validate_input({
            "requirements": [MockRequirement()],
        })
        assert result.valid is False
        assert any("llm_client" in e for e in result.errors)

    def test_no_vector_store_warning(self, agent):
        result = agent.validate_input({
            "requirements": [MockRequirement()],
            "llm_client": MockLLMClient(),
        })
        assert len(result.warnings) > 0
        assert any("vector_store" in w for w in result.warnings)


class TestExecute:
    """Test agent execution."""

    @pytest.fixture
    def agent(self):
        return TestGenerationAgent()

    def test_successful_execution(self, agent):
        artifacts = {
            "requirements": [MockRequirement()],
            "llm_client": MockLLMClient(),
        }
        config = {"max_tests": 1, "include_negative": False, "include_edge": False}
        result = agent.execute(artifacts, config)
        assert result.success is True
        assert "test_cases" in result.artifacts
        # AC-aware: MockRequirement has 2 ACs, effective_max = max(1, 2) = 2
        assert len(result.artifacts["test_cases"]) == 2
        assert isinstance(result.artifacts["test_cases"][0], TestCaseArtifact)

    def test_metadata_populated(self, agent):
        artifacts = {
            "requirements": [MockRequirement()],
            "llm_client": MockLLMClient(),
        }
        config = {"max_tests": 1, "include_negative": False, "include_edge": False}
        result = agent.execute(artifacts, config)
        assert "total_test_cases" in result.metadata
        assert "total_requirements" in result.metadata
        assert result.metadata["total_requirements"] == 1

    def test_invalid_input_returns_failure(self, agent):
        result = agent.execute({}, {})
        assert result.success is False
        assert len(result.errors) > 0

    def test_multiple_requirements(self, agent):
        artifacts = {
            "requirements": [
                MockRequirement(req_id="REQ-001"),
                MockRequirement(req_id="REQ-002", title="Password Reset"),
            ],
            "llm_client": MockLLMClient(),
        }
        config = {"max_tests": 1, "include_negative": False, "include_edge": False}
        result = agent.execute(artifacts, config)
        assert result.success is True
        # AC-aware: each MockRequirement has 2 ACs, effective_max = max(1, 2) = 2 per req
        assert result.metadata["total_test_cases"] == 4

    def test_custom_config(self, agent):
        artifacts = {
            "requirements": [MockRequirement()],
            "llm_client": MockLLMClient(),
        }
        config = {
            "max_tests": 3,
            "include_negative": True,
            "include_edge": True,
            "tc_format": "standard",
        }
        result = agent.execute(artifacts, config)
        assert result.success is True
        assert result.metadata["tc_format"] == "standard"
        assert result.metadata["total_test_cases"] == 3


class TestGetCapabilities:
    """Test capability discovery."""

    def test_capabilities(self):
        agent = TestGenerationAgent()
        caps = agent.get_capabilities()
        assert isinstance(caps, AgentCapabilities)
        assert caps.agent_id == "test_generation"
        assert caps.agent_version == "1.0.0"
        assert "RequirementArtifact" in caps.input_types
        assert "TestCaseArtifact" in caps.output_types
        assert len(caps.description) > 20

    def test_agent_id_and_version(self):
        agent = TestGenerationAgent()
        assert agent.agent_id == "test_generation"
        assert agent.agent_version == "1.0.0"
