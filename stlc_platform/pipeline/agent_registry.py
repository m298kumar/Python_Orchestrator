"""
Agent Registry
==============
Central registry for discovering and instantiating STLC agents.
"""

from __future__ import annotations

from typing import Dict, List, Type

from stlc_platform.core.base_agent import AgentCapabilities, BaseAgent


class AgentRegistry:
    """Registry of available agents by agent_id."""

    def __init__(self) -> None:
        self._agents: Dict[str, Type[BaseAgent]] = {}

    def register(self, agent_id: str, agent_class: Type[BaseAgent]) -> None:
        """Register an agent class by ID."""
        self._agents[agent_id] = agent_class

    def get(self, agent_id: str) -> BaseAgent:
        """Instantiate and return an agent by ID."""
        if agent_id not in self._agents:
            raise KeyError(
                f"Agent '{agent_id}' not registered. "
                f"Available: {list(self._agents.keys())}"
            )
        return self._agents[agent_id]()

    def has(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._agents

    def list_agents(self) -> List[AgentCapabilities]:
        """Return capabilities of all registered agents."""
        seen: set = set()
        caps: List[AgentCapabilities] = []
        for agent_class in self._agents.values():
            if agent_class not in seen:
                seen.add(agent_class)
                caps.append(agent_class().get_capabilities())
        return caps

    @classmethod
    def default(cls) -> "AgentRegistry":
        """Create a registry pre-loaded with all built-in agents."""
        registry = cls()

        from stlc_platform.agents.requirements_agent.agent import (
            TestGenerationAgent,
        )
        from stlc_platform.agents.bdd_agent.agent import BDDAgent
        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent
        from stlc_platform.agents.api_test_agent.agent import APITestAgent

        registry.register("requirements_agent", TestGenerationAgent)
        registry.register("test_generation", TestGenerationAgent)
        registry.register("bdd_agent", BDDAgent)
        registry.register("bdd_generation", BDDAgent)
        registry.register("crawler_agent", CrawlerAgent)
        registry.register("web_crawler", CrawlerAgent)
        registry.register("api_test_agent", APITestAgent)
        registry.register("api_test_generation", APITestAgent)

        return registry
