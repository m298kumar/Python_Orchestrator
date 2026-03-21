"""
API Test Agent
==============
BaseAgent implementation that wires up the OpenAPIParser, APITestGenerator,
and TestClassifier to produce API test artifacts from OpenAPI specs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser
from stlc_platform.agents.api_test_agent.test_generator import APITestGenerator
from stlc_platform.agents.api_test_agent.test_classifier import TestClassifier
from stlc_platform.core.contracts import APIModelArtifact


class APITestAgent(BaseAgent):
    """
    Agent that parses OpenAPI specs and generates API test code.

    Lifecycle:
      1. validate_input() -- check for openapi_spec or api_model
      2. execute() -- parse spec, generate tests, classify
      3. get_capabilities() -- describe input/output types

    Input modes:
      - openapi_spec: str or dict (raw spec -> full pipeline)
      - api_model: APIModelArtifact (skip parsing -> generate tests only)

    Config keys:
      - framework: str (default: "pytest_requests")
      - test_types: List[str] (default: all types)
    """

    agent_id: str = "api_test_generation"
    agent_version: str = "1.0.0"

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """Validate that input contains openapi_spec or api_model."""
        errors: List[str] = []
        warnings: List[str] = []

        openapi_spec = artifacts.get("openapi_spec")
        api_model = artifacts.get("api_model")

        if openapi_spec is None and api_model is None:
            errors.append(
                "'openapi_spec' (str or dict) or 'api_model' "
                "(APIModelArtifact) is required."
            )
        elif openapi_spec is not None:
            if not isinstance(openapi_spec, (str, dict)):
                errors.append("'openapi_spec' must be a string or dict.")
        elif api_model is not None:
            if not isinstance(api_model, APIModelArtifact):
                errors.append("'api_model' must be an APIModelArtifact instance.")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        """
        Parse an OpenAPI spec and generate API test code.

        Args:
            artifacts: Must contain "openapi_spec" or "api_model".
            config: Optional overrides (framework, test_types).

        Returns:
            AgentResult with api_model, test_files, and conftest.
        """
        # Validate
        validation = self.validate_input(artifacts)
        if not validation.valid:
            return AgentResult(
                success=False,
                errors=validation.errors,
            )

        try:
            api_model = artifacts.get("api_model")

            if api_model is None:
                # Full pipeline: parse spec -> API model
                parser = OpenAPIParser()
                api_model = parser.parse(artifacts["openapi_spec"])

            # Generate tests
            framework = config.get("framework", "pytest_requests")
            generator = APITestGenerator(framework=framework)
            test_artifacts = generator.generate(
                api_model,
                config={"test_types": config.get("test_types")},
            )

            # Classify and validate pyramid
            classifier = TestClassifier()
            # Filter out conftest for pyramid validation
            test_only = [t for t in test_artifacts if t.test_count > 0]
            pyramid = classifier.validate_pyramid(test_only)

            # Separate conftest from test files
            conftest = None
            test_files = []
            for artifact in test_artifacts:
                if artifact.filename == "conftest.py":
                    conftest = artifact
                else:
                    test_files.append(artifact)

            result_artifacts: Dict[str, Any] = {
                "api_model": api_model,
                "test_files": test_files,
            }
            if conftest:
                result_artifacts["conftest"] = conftest

            total_tests = sum(t.test_count for t in test_files)
            metadata: Dict[str, Any] = {
                "total_endpoints": len(api_model.endpoints),
                "total_test_files": len(test_files),
                "total_tests": total_tests,
                "framework": framework,
                "spec_format": api_model.spec_format,
                "test_level_distribution": pyramid.get("distribution", {}),
            }

            if pyramid.get("warnings"):
                metadata["pyramid_warnings"] = pyramid["warnings"]

            if validation.warnings:
                metadata["validation_warnings"] = validation.warnings

            return AgentResult(
                success=True,
                artifacts=result_artifacts,
                metadata=metadata,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                errors=[f"API test agent failed: {e}"],
            )

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["openapi_spec", "APIModelArtifact"],
            output_types=["APIModelArtifact", "APITestArtifact"],
            description=(
                "Parses OpenAPI/Swagger specifications into API models "
                "and generates framework-specific API test code with "
                "test level classification and failure type metadata."
            ),
        )
