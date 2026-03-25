"""
Test Generation Agent
=====================
BaseAgent implementation that wires up the TestCaseGenerator with all its
dependencies and exposes it through the standard agent lifecycle.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.contracts import TestCaseArtifact  # noqa: F401 — re-exported

from stlc_platform.agents.requirements_agent.classifier import ACClassifier
from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver
from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector
from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator
from stlc_platform.agents.requirements_agent.prompts import PromptRenderer
from stlc_platform.agents.requirements_agent.sanitiser import TestCaseSanitiser
from stlc_platform.agents.requirements_agent.tech_stack import TechStackContext


class TestGenerationAgent(BaseAgent):
    """
    Agent that generates test cases from requirement artifacts.

    Lifecycle:
      1. validate_input() — check that requirements list is present
      2. execute() — wire up dependencies, run generator, return results
      3. get_capabilities() — describe input/output types

    Config keys used:
      - requirements: List of requirement objects (required)
      - llm_client: BaseLLMClient instance (required)
      - vector_store: optional ChromaDB store
      - domain: optional explicit domain label
      - tech_stack: optional dict with platform/frontend/backend/etc.
      - max_tests: int (default 6)
      - include_negative: bool (default True)
      - include_edge: bool (default True)
      - tc_format: "gherkin" or "standard" (default "gherkin")
      - classifier: optional ACClassifier instance
      - sanitiser: optional TestCaseSanitiser instance
      - prompt_renderer: optional PromptRenderer instance
      - component_resolver: optional ComponentResolver instance
      - domain_detector: optional DomainDetector instance
    """

    agent_id: str = "test_generation"
    agent_version: str = "1.0.0"

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """
        Validate that the input contains the required artifacts.

        Required:
          - artifacts["requirements"]: non-empty list of requirement objects
          - artifacts["llm_client"]: a BaseLLMClient instance
        """
        errors: List[str] = []
        warnings: List[str] = []

        requirements = artifacts.get("requirements")
        if not requirements:
            errors.append("'requirements' is required and must be a non-empty list.")
        elif not isinstance(requirements, list):
            errors.append("'requirements' must be a list.")
        elif len(requirements) == 0:
            errors.append("'requirements' list must not be empty.")

        llm_client = artifacts.get("llm_client")
        if llm_client is None:
            errors.append("'llm_client' is required.")

        # Warnings for optional but recommended fields
        if not artifacts.get("vector_store"):
            warnings.append(
                "No vector_store provided. Few-shot examples and context retrieval "
                "will be disabled."
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
        """
        Execute test case generation.

        Args:
            artifacts: Must contain "requirements" and "llm_client".
            config: Optional overrides for generation parameters.

        Returns:
            AgentResult with test_cases list in artifacts.
        """
        # Validate first
        validation = self.validate_input(artifacts)
        if not validation.valid:
            return AgentResult(
                success=False,
                errors=validation.errors,
            )

        requirements = artifacts["requirements"]
        llm_client = artifacts["llm_client"]
        vector_store = artifacts.get("vector_store")
        feedback_store = artifacts.get("feedback_store")

        # Build tech stack context
        tech_stack_config = config.get("tech_stack") or artifacts.get("tech_stack")
        tech_stack = (
            artifacts.get("tech_stack_context")
            or TechStackContext.from_config(tech_stack_config)
        )

        # Wire up generator with all dependencies
        generator = TestCaseGenerator(
            llm_client=llm_client,
            prompt_renderer=artifacts.get("prompt_renderer") or PromptRenderer(),
            classifier=artifacts.get("classifier") or ACClassifier(),
            sanitiser=artifacts.get("sanitiser") or TestCaseSanitiser(),
            component_resolver=artifacts.get("component_resolver") or ComponentResolver(
                vector_store=vector_store,
            ),
            domain_detector=artifacts.get("domain_detector") or DomainDetector(),
            tech_stack=tech_stack,
            vector_store=vector_store,
            domain=config.get("domain", "") or artifacts.get("domain", ""),
            feedback_store=feedback_store,
        )

        # Extract config
        max_tests = config.get("max_tests", 6)
        include_negative = config.get("include_negative", True)
        include_edge = config.get("include_edge", True)
        tc_format = config.get("tc_format", "gherkin")

        try:
            test_cases = generator.generate_for_all(
                requirements=requirements,
                max_tests=max_tests,
                include_negative=include_negative,
                include_edge=include_edge,
                tc_format=tc_format,
            )

            return AgentResult(
                success=True,
                artifacts={"test_cases": test_cases},
                metadata={
                    "total_test_cases": len(test_cases),
                    "total_requirements": len(requirements),
                    "domain": generator._domain,
                    "tc_format": tc_format,
                },
            )

        except Exception as e:
            return AgentResult(
                success=False,
                errors=[f"Test generation failed: {e}"],
            )

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["RequirementArtifact"],
            output_types=["TestCaseArtifact"],
            description=(
                "Generates test cases from requirements using LLM-powered "
                "prompt templates with AC classification, sanitisation, "
                "and domain-agnostic output."
            ),
            required_skills=["data_catalog", "coding_standards", "test_design_principles"],
            default_model_tier="advanced",
        )
