"""
API Test Agent
==============
BaseAgent implementation that wires up the OpenAPIParser, APITestGenerator,
and TestClassifier to produce API test artifacts from OpenAPI specs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.agents.api_test_agent.graphql_parser import GraphQLParser
from stlc_platform.agents.api_test_agent.har_parser import HARParser
from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser
from stlc_platform.agents.api_test_agent.test_classifier import TestClassifier
from stlc_platform.agents.api_test_agent.test_generator import APITestGenerator
from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.contracts import APIModelArtifact


class APITestAgent(BaseAgent):
    """
    Agent that parses OpenAPI specs and generates API test code.

    Lifecycle:
      1. validate_input() -- check for openapi_spec or api_model
      2. execute() -- parse spec, generate tests, classify
      3. get_capabilities() -- describe input/output types

    Input modes (priority order):
      - openapi_spec: str or dict (OpenAPI/Swagger spec -> full pipeline)
      - har_data: str or dict (HAR file -> API discovery -> test gen)
      - graphql_schema: str or dict (GraphQL introspection/SDL -> test gen)
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

        # Treat empty strings the same as None — an empty string is not a valid spec
        openapi_spec = artifacts.get("openapi_spec") or None
        har_data = artifacts.get("har_data") or None
        graphql_schema = artifacts.get("graphql_schema") or None
        api_model = artifacts.get("api_model")

        if all(v is None for v in [openapi_spec, har_data, graphql_schema, api_model]):
            errors.append(
                "'openapi_spec', 'har_data', 'graphql_schema', or 'api_model' is required."
            )
        elif openapi_spec is not None:
            if not isinstance(openapi_spec, (str, dict)):
                errors.append("'openapi_spec' must be a string or dict.")
        elif har_data is not None:
            if not isinstance(har_data, (str, dict)):
                errors.append("'har_data' must be a string or dict.")
        elif graphql_schema is not None:
            if not isinstance(graphql_schema, (str, dict)):
                errors.append("'graphql_schema' must be a string or dict.")
        elif api_model is not None:
            if not isinstance(api_model, APIModelArtifact):
                errors.append("'api_model' must be an APIModelArtifact instance.")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
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
                api_model = self._parse_spec(artifacts)

            if api_model is None:
                return AgentResult(
                    success=False,
                    errors=[
                        "No API model available: provide api_model, openapi_spec, har_data, or graphql_schema"
                    ],
                )

            # Generate tests
            framework = config.get("framework", "pytest_requests")
            generator = APITestGenerator(framework=framework)
            test_artifacts = generator.generate(
                api_model,
                config={"test_types": config.get("test_types")},
            )

            test_files, conftest = self._split_test_artifacts(test_artifacts)
            pyramid = TestClassifier().validate_pyramid(
                [t for t in test_artifacts if t.test_count > 0]
            )

            result_artifacts: Dict[str, Any] = {
                "api_model": api_model,
                "test_files": test_files,
            }
            if conftest:
                result_artifacts["conftest"] = conftest

            metadata = self._build_metadata(api_model, test_files, framework, pyramid, validation)

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

    def _parse_spec(self, artifacts: Dict[str, Any]) -> Any:
        """Parse an API spec from artifacts into an APIModelArtifact."""
        if artifacts.get("openapi_spec"):  # falsy check treats empty string as absent
            return OpenAPIParser().parse(artifacts["openapi_spec"])
        if artifacts.get("har_data"):
            return HARParser().parse(artifacts["har_data"])
        if artifacts.get("graphql_schema"):
            gql_parser = GraphQLParser()
            schema = artifacts["graphql_schema"]
            if isinstance(schema, str) and "type " in schema:
                return gql_parser.parse_sdl(schema)
            return gql_parser.parse(schema)
        return None

    def _split_test_artifacts(self, test_artifacts: List[Any]) -> tuple:
        """Separate conftest from test file artifacts."""
        conftest = None
        test_files = []
        for artifact in test_artifacts:
            if artifact.filename == "conftest.py":
                conftest = artifact
            else:
                test_files.append(artifact)
        return test_files, conftest

    def _build_metadata(
        self,
        api_model: Any,
        test_files: List[Any],
        framework: str,
        pyramid: Dict[str, Any],
        validation: Any,
    ) -> Dict[str, Any]:
        """Build result metadata dict."""
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
        return metadata

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["openapi_spec", "har_data", "graphql_schema", "APIModelArtifact"],
            output_types=["APIModelArtifact", "APITestArtifact"],
            description=(
                "Parses OpenAPI/Swagger specs, HAR files, and GraphQL schemas into API models "
                "and generates framework-specific API test code with "
                "test level classification and failure type metadata."
            ),
            required_skills=["coding_standards", "data_catalog"],
            default_model_tier="standard",
        )
