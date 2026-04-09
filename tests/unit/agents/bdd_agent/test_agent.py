"""Tests for BDDAgent."""

import pytest
from stlc_platform.agents.bdd_agent.agent import BDDAgent
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact


@pytest.fixture
def agent():
    return BDDAgent()


def _make_tc(**overrides) -> TestCaseArtifact:
    defaults = {
        "tc_id": "TC-0001",
        "req_id": "REQ-001",
        "title": "Test case",
        "description": "Description",
        "preconditions": "Preconditions",
        "test_type": "positive",
        "priority": "High",
        "steps": [
            TestStepArtifact(action="Do something", expected_result="Expected"),
        ],
        "expected_outcome": "Expected outcome",
        "given": "A user on the page",
        "when": "The user acts",
        "then": "The system responds",
        "category": "Functional",
        "component": "Component",
    }
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


class TestValidateInput:
    def test_valid_input(self, agent):
        result = agent.validate_input({"test_cases": [_make_tc()]})
        assert result.valid is True

    def test_missing_test_cases(self, agent):
        result = agent.validate_input({})
        assert result.valid is False
        assert any("required" in e for e in result.errors)

    def test_empty_test_cases(self, agent):
        result = agent.validate_input({"test_cases": []})
        assert result.valid is False

    def test_test_cases_not_list(self, agent):
        result = agent.validate_input({"test_cases": "not a list"})
        assert result.valid is False

    def test_warning_for_empty_gwt(self, agent):
        tc = _make_tc(given="", when="")
        result = agent.validate_input({"test_cases": [tc]})
        assert result.valid is True
        assert len(result.warnings) > 0


class TestExecute:
    def test_successful_execution(self, agent):
        tcs = [
            _make_tc(tc_id="TC-1"),
            _make_tc(tc_id="TC-2", title="Second test", test_type="negative"),
        ]
        result = agent.execute(
            artifacts={"test_cases": tcs},
            config={"framework": "behave"},
        )
        assert result.success is True
        assert "feature_files" in result.artifacts
        assert "step_definitions" in result.artifacts
        assert len(result.artifacts["feature_files"]) == 1  # 1 req_id
        assert len(result.artifacts["step_definitions"]) >= 1

    def test_metadata_populated(self, agent):
        result = agent.execute(
            artifacts={"test_cases": [_make_tc()]},
            config={"framework": "behave"},
        )
        assert result.metadata["total_features"] == 1
        assert result.metadata["total_scenarios"] == 1
        assert result.metadata["framework"] == "behave"

    def test_invalid_input_returns_failure(self, agent):
        result = agent.execute(artifacts={}, config={})
        assert result.success is False
        assert len(result.errors) > 0

    def test_pytest_bdd_framework(self, agent):
        result = agent.execute(
            artifacts={"test_cases": [_make_tc()]},
            config={"framework": "pytest_bdd"},
        )
        assert result.success is True
        assert result.metadata["framework"] == "pytest_bdd"

    def test_multi_requirement_features(self, agent):
        tcs = [
            _make_tc(tc_id="TC-1", req_id="REQ-001"),
            _make_tc(tc_id="TC-2", req_id="REQ-002", title="Other test", component="Other"),
        ]
        result = agent.execute(
            artifacts={"test_cases": tcs},
            config={"framework": "behave"},
        )
        assert result.success is True
        assert result.metadata["total_features"] == 2


class TestGetCapabilities:
    def test_capabilities(self, agent):
        caps = agent.get_capabilities()
        assert caps.agent_id == "bdd_generation"
        assert "TestCaseArtifact" in caps.input_types
        assert "FeatureFileArtifact" in caps.output_types
        assert "StepDefinitionArtifact" in caps.output_types
