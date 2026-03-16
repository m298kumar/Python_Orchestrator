"""
BaseAgent ABC
=============
All STLC agents implement this interface. This enables:
  - Uniform lifecycle management by the pipeline orchestrator
  - Input validation before execution
  - Capability discovery for dynamic pipeline construction
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentCapabilities:
    """Describes what an agent can do — used by the pipeline orchestrator."""

    agent_id: str
    agent_version: str
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ValidationResult:
    """Result of input validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Result of agent execution."""

    success: bool
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class for all STLC agents."""

    agent_id: str = "base"
    agent_version: str = "0.0.0"

    @abstractmethod
    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """Validate input artifacts before execution."""
        ...

    @abstractmethod
    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
        """Execute the agent's main logic."""
        ...

    def get_capabilities(self) -> AgentCapabilities:
        """Return this agent's capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
        )
