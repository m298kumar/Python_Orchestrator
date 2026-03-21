"""Unit tests for the Agent Registry."""

from __future__ import annotations

import pytest

from stlc_platform.pipeline.agent_registry import AgentRegistry


class TestDefaultRegistry:
    def test_default_has_four_agents(self):
        registry = AgentRegistry.default()
        caps = registry.list_agents()
        assert len(caps) == 4

    def test_get_agent_by_id(self):
        registry = AgentRegistry.default()
        agent = registry.get("bdd_agent")
        assert agent.agent_id == "bdd_generation"

    def test_get_agent_by_alias(self):
        registry = AgentRegistry.default()
        agent = registry.get("web_crawler")
        assert agent.agent_id == "web_crawler"

    def test_unknown_agent_raises(self):
        registry = AgentRegistry.default()
        with pytest.raises(KeyError, match="nonexistent"):
            registry.get("nonexistent")

    def test_list_agents_returns_capabilities(self):
        registry = AgentRegistry.default()
        caps = registry.list_agents()
        agent_ids = {c.agent_id for c in caps}
        assert "bdd_generation" in agent_ids
        assert "api_test_generation" in agent_ids
