"""
Tests for BaseAgent ABC.
"""

import pytest
from stlc_platform.core.base_agent import (
    BaseAgent,
    AgentCapabilities,
    AgentResult,
    ValidationResult,
)


class ConcreteAgent(BaseAgent):
    """Minimal concrete implementation for testing."""

    agent_id = "test-agent"
    agent_version = "1.0.0"

    def validate_input(self, artifacts):
        if "requirements" not in artifacts:
            return ValidationResult(valid=False, errors=["Missing requirements"])
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(success=True, artifacts={"output": "done"})


class TestBaseAgent:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseAgent()

    def test_concrete_agent_works(self):
        agent = ConcreteAgent()
        assert agent.agent_id == "test-agent"

    def test_validate_input_pass(self):
        agent = ConcreteAgent()
        result = agent.validate_input({"requirements": []})
        assert result.valid is True

    def test_validate_input_fail(self):
        agent = ConcreteAgent()
        result = agent.validate_input({})
        assert result.valid is False
        assert "Missing requirements" in result.errors

    def test_execute(self):
        agent = ConcreteAgent()
        result = agent.execute({"requirements": []}, {})
        assert result.success is True
        assert result.artifacts["output"] == "done"

    def test_get_capabilities(self):
        agent = ConcreteAgent()
        caps = agent.get_capabilities()
        assert isinstance(caps, AgentCapabilities)
        assert caps.agent_id == "test-agent"
        assert caps.agent_version == "1.0.0"
