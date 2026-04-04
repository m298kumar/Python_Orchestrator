"""Tests for the TestGenerationAgent class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest
from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent
from stlc_platform.core.base_agent import AgentCapabilities
from stlc_platform.core.contracts import TestCaseArtifact


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
    """Mock LLM that returns completely distinct TCs to survive dedup."""

    _SCENARIOS = [
        {
            "title": "Verify successful login with valid credentials",
            "description": "Authenticate user with correct username and password",
            "preconditions": "Active user account exists in the database",
            "steps": [
                {"action": "Navigate to login page", "expected_result": "Login form displayed"},
                {"action": "Enter valid username", "expected_result": "Username accepted"},
                {"action": "Submit credentials", "expected_result": "Redirected to dashboard"},
            ],
            "expected_outcome": "User session created and dashboard visible",
            "component": "Login Screen",
            "given": "An active user with valid credentials",
            "when": "User submits the login form",
            "then": "Dashboard is displayed with welcome message",
            "priority": "High",
            "tags": ["auth", "positive"],
        },
        {
            "title": "Verify error message for invalid password",
            "description": "System rejects incorrect password and shows alert",
            "preconditions": "User account exists but wrong password used",
            "steps": [
                {"action": "Open authentication page", "expected_result": "Form renders"},
                {"action": "Type wrong password", "expected_result": "Password field filled"},
                {"action": "Click sign-in button", "expected_result": "Error banner appears"},
            ],
            "expected_outcome": "Red error banner shows invalid password message",
            "component": "Error Handler",
            "given": "A registered user with incorrect password",
            "when": "User attempts authentication with bad credentials",
            "then": "Error notification displayed and login blocked",
            "priority": "High",
            "tags": ["auth", "negative"],
        },
        {
            "title": "Verify password reset email delivery",
            "description": "Forgotten password triggers recovery email to user",
            "preconditions": "Email server configured and user registered",
            "steps": [
                {"action": "Click forgot password link", "expected_result": "Recovery form shown"},
                {"action": "Enter registered email", "expected_result": "Email field validated"},
                {"action": "Submit recovery request", "expected_result": "Confirmation displayed"},
            ],
            "expected_outcome": "Recovery email sent within 30 seconds",
            "component": "Password Recovery",
            "given": "A registered user who forgot their password",
            "when": "User requests password recovery via email",
            "then": "Reset link delivered to registered email address",
            "priority": "Medium",
            "tags": ["recovery", "positive"],
        },
        {
            "title": "Verify account lockout after failed attempts",
            "description": "Multiple failed logins trigger temporary account freeze",
            "preconditions": "Security policy requires lockout after 5 failures",
            "steps": [
                {"action": "Attempt login with wrong password 5 times", "expected_result": "Counter increments"},
                {"action": "Try sixth login attempt", "expected_result": "Account locked message"},
                {"action": "Wait 15 minutes and retry", "expected_result": "Login succeeds"},
            ],
            "expected_outcome": "Account temporarily frozen then auto-unlocked",
            "component": "Security Module",
            "given": "A user who has exhausted login attempts",
            "when": "Sixth consecutive failed authentication occurs",
            "then": "Account locked for 15 minutes with notification",
            "priority": "High",
            "tags": ["security", "edge_case"],
        },
        {
            "title": "Verify session timeout and forced logout",
            "description": "Idle session expires after configured inactivity period",
            "preconditions": "Session timeout configured to 30 minutes",
            "steps": [
                {"action": "Login and remain idle for 31 minutes", "expected_result": "Timer expires"},
                {"action": "Attempt navigation to protected page", "expected_result": "Redirected"},
                {"action": "Check session cookie", "expected_result": "Cookie invalidated"},
            ],
            "expected_outcome": "Session destroyed and user redirected to login",
            "component": "Session Manager",
            "given": "An authenticated user with expired idle session",
            "when": "User attempts action after 30 minute inactivity",
            "then": "Session terminated and login page presented",
            "priority": "Medium",
            "tags": ["session", "timeout"],
        },
        {
            "title": "Verify multi-factor authentication prompt",
            "description": "Second factor requested after primary credential validation",
            "preconditions": "MFA enabled for user account with TOTP configured",
            "steps": [
                {"action": "Complete primary login", "expected_result": "MFA challenge shown"},
                {"action": "Enter TOTP code from authenticator", "expected_result": "Code verified"},
                {"action": "Confirm MFA approval", "expected_result": "Full access granted"},
            ],
            "expected_outcome": "Two-factor verification completed successfully",
            "component": "MFA Gateway",
            "given": "A user with TOTP multi-factor authentication enabled",
            "when": "User completes primary login and enters TOTP code",
            "then": "Full application access granted after MFA verification",
            "priority": "High",
            "tags": ["mfa", "security"],
        },
    ]

    def __init__(self):
        self._call_count = 0

    def generate_test_case(self, prompt, system_prompt=None, **kwargs):
        scenario = self._SCENARIOS[self._call_count % len(self._SCENARIOS)].copy()
        self._call_count += 1
        scenario.setdefault("estimated_duration", "5")
        return scenario


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
