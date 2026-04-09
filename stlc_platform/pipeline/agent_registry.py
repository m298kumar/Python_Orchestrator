"""
Agent Registry
==============
Central registry for discovering and instantiating STLC agents.
Supports both built-in agents and plugin agents discovered via
``stlc_platform.agents`` entry points.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Type

from stlc_platform.core.base_agent import AgentCapabilities, BaseAgent

logger = logging.getLogger(__name__)


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
                f"Agent '{agent_id}' not registered. Available: {list(self._agents.keys())}"
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

    def _discover_plugins(self) -> None:
        """Load agents from ``stlc_platform.agents`` entry points.

        Third-party packages can register agents by adding an entry point::

            [project.entry-points."stlc_platform.agents"]
            my_agent = "my_package.agent:MyAgent"
        """
        try:
            from importlib.metadata import entry_points

            eps = entry_points()
            # Python 3.12+ returns a SelectableGroups; 3.9+ supports .select()
            group = (
                eps.select(group="stlc_platform.agents")
                if hasattr(eps, "select")
                else eps.get("stlc_platform.agents", [])
            )
            for ep in group:
                try:
                    agent_class = ep.load()
                    if isinstance(agent_class, type) and issubclass(agent_class, BaseAgent):
                        self.register(ep.name, agent_class)
                        logger.info(
                            "Discovered plugin agent: %s -> %s", ep.name, agent_class.__name__
                        )
                    else:
                        logger.warning(
                            "Plugin entry point '%s' is not a BaseAgent subclass", ep.name
                        )
                except Exception as exc:
                    logger.warning("Failed to load plugin agent '%s': %s", ep.name, exc)
        except Exception as exc:
            logger.debug("Entry point discovery unavailable: %s", exc)

    @classmethod
    def default(cls) -> "AgentRegistry":
        """Create a registry pre-loaded with all built-in agents and discovered plugins."""
        registry = cls()

        from stlc_platform.agents.api_test_agent.agent import APITestAgent
        from stlc_platform.agents.bdd_agent.agent import BDDAgent
        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent
        from stlc_platform.agents.enrichment_agent.agent import EnrichmentAgent
        from stlc_platform.agents.requirements_agent.agent import (
            TestGenerationAgent,
        )

        registry.register("requirements_agent", TestGenerationAgent)
        registry.register("test_generation", TestGenerationAgent)
        registry.register("bdd_agent", BDDAgent)
        registry.register("bdd_generation", BDDAgent)
        registry.register("crawler_agent", CrawlerAgent)
        registry.register("web_crawler", CrawlerAgent)
        registry.register("api_test_agent", APITestAgent)
        registry.register("api_test_generation", APITestAgent)
        registry.register("enrich_test_cases", EnrichmentAgent)
        registry.register("enrichment_agent", EnrichmentAgent)

        # Discover plugin agents from entry points
        registry._discover_plugins()

        return registry
