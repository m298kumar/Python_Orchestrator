"""
API Test Generator
==================
Generates API test code from an APIModelArtifact using Jinja2 templates.

Supported frameworks:
  - pytest_requests (Pytest + Requests library, Python)
  - rest_assured (JUnit 5 + REST Assured, Java)
  - karate (Karate DSL, .feature files)

Extension: Add new frameworks by placing a .j2 template in the templates/
directory and adding an entry to SUPPORTED_FRAMEWORKS.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from stlc_platform.agents.api_test_agent.test_classifier import TestClassifier
from stlc_platform.core.contracts import (
    APIEndpointArtifact,
    APIModelArtifact,
    APITestArtifact,
)


_BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"
_DEFAULT_OVERRIDES = Path(__file__).resolve().parent / "template_overrides"

# Framework name -> template filename
SUPPORTED_FRAMEWORKS: Dict[str, str] = {
    "pytest_requests": "pytest_requests.py.j2",
    "rest_assured": "rest_assured.java.j2",
    "karate": "karate.feature.j2",
}

# Framework name -> language
_LANGUAGE_MAP: Dict[str, str] = {
    "pytest_requests": "python",
    "rest_assured": "java",
    "karate": "karate",
}

# Conftest template (Python frameworks only)
_CONFTEST_TEMPLATE = "conftest.py.j2"


class APITestGenerator:
    """Generate API test artifacts from an API model."""

    def __init__(
        self,
        framework: str = "pytest_requests",
        template_dir: Optional[Path] = None,
        override_dir: Optional[Path] = None,
    ) -> None:
        if framework not in SUPPORTED_FRAMEWORKS:
            raise ValueError(
                f"Unsupported framework '{framework}'. "
                f"Supported: {list(SUPPORTED_FRAMEWORKS.keys())}"
            )

        self.framework = framework
        self._classifier = TestClassifier()

        # ChoiceLoader: overrides first, then builtins
        loaders = []
        override = override_dir or _DEFAULT_OVERRIDES
        if override.is_dir():
            loaders.append(FileSystemLoader(str(override)))
        builtin = template_dir or _BUILTIN_TEMPLATES
        loaders.append(FileSystemLoader(str(builtin)))

        self._env = Environment(
            loader=ChoiceLoader(loaders),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate(
        self,
        api_model: APIModelArtifact,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[APITestArtifact]:
        """
        Generate test artifacts for all endpoints in the API model.

        Args:
            api_model: The parsed API model.
            config: Optional overrides (test_types to include/exclude).

        Returns:
            List of APITestArtifact (one per endpoint + one conftest).
        """
        config = config or {}
        test_types_filter = config.get("test_types")  # None = generate all

        artifacts: List[APITestArtifact] = []

        # Generate conftest (Python frameworks only)
        if _LANGUAGE_MAP.get(self.framework) == "python":
            conftest = self._generate_conftest(api_model)
            artifacts.append(conftest)

        # Generate test file per endpoint
        for endpoint in api_model.endpoints:
            artifact = self._generate_endpoint_tests(
                endpoint,
                base_url=api_model.base_url,
                auth_type=api_model.auth_type,
                test_types_filter=test_types_filter,
            )
            if artifact.test_count > 0:
                artifacts.append(artifact)

        return artifacts

    # ------------------------------------------------------------------
    # Conftest generation
    # ------------------------------------------------------------------

    def _generate_conftest(self, api_model: APIModelArtifact) -> APITestArtifact:
        """Generate the conftest.py file."""
        template = self._env.get_template(_CONFTEST_TEMPLATE)
        content = template.render(
            base_url=api_model.base_url,
            spec_title=api_model.spec_title,
            auth_type=api_model.auth_type,
        )
        return APITestArtifact(
            framework=self.framework,
            language="python",
            filename="conftest.py",
            content=content,
            test_count=0,
            test_level="api",
            test_type="conftest",
        )

    # ------------------------------------------------------------------
    # Per-endpoint test generation
    # ------------------------------------------------------------------

    def _generate_endpoint_tests(
        self,
        endpoint: APIEndpointArtifact,
        base_url: str,
        auth_type: str,
        test_types_filter: Optional[List[str]] = None,
    ) -> APITestArtifact:
        """Generate a test file for a single endpoint."""
        # Build test cases
        test_cases = self._build_test_cases(endpoint, test_types_filter)

        # Compute template context
        class_name = self._make_class_name(endpoint)
        path_template = self._make_path_template(endpoint)
        query_params_dict = self._make_query_params_dict(endpoint)

        template = self._env.get_template(SUPPORTED_FRAMEWORKS[self.framework])
        content = template.render(
            method=endpoint.method,
            method_lower=endpoint.method.lower(),
            path=endpoint.path,
            path_template=path_template,
            summary=endpoint.summary,
            operation_id=endpoint.operation_id,
            base_url=base_url,
            auth_required=endpoint.auth_required,
            auth_type=auth_type,
            class_name=class_name,
            path_params=endpoint.path_params,
            query_params=endpoint.query_params,
            query_params_dict=query_params_dict,
            has_schema_validation=any(
                t["test_type"] == "schema_validation" for t in test_cases
            ),
            tests=test_cases,
        )

        # Determine the dominant test level
        levels = [t["test_level"] for t in test_cases]
        dominant_level = max(set(levels), key=levels.count) if levels else "api"

        return APITestArtifact(
            framework=self.framework,
            language=_LANGUAGE_MAP.get(self.framework, "python"),
            filename=self._make_filename(endpoint),
            content=content,
            endpoint_path=endpoint.path,
            test_count=len(test_cases),
            test_level=dominant_level,
            test_type="mixed",
            tags=endpoint.tags,
        )

    # ------------------------------------------------------------------
    # Test case builders
    # ------------------------------------------------------------------

    def _build_test_cases(
        self,
        endpoint: APIEndpointArtifact,
        test_types_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build all test cases for an endpoint."""
        cases: List[Dict[str, Any]] = []

        # Happy path — always generated
        if self._should_include("happy_path", test_types_filter):
            cases.append(self._happy_path_test(endpoint))

        # Auth tests — only if auth_required
        if endpoint.auth_required and self._should_include("auth", test_types_filter):
            cases.extend(self._auth_tests(endpoint))

        # Validation tests — only if request body with required fields
        if (
            endpoint.request_body_schema
            and self._should_include("validation", test_types_filter)
        ):
            required = endpoint.request_body_schema.get("required", [])
            if required:
                cases.append(self._validation_missing_fields_test(endpoint))

        # Boundary tests — only if request body with typed fields
        if (
            endpoint.request_body_schema
            and self._should_include("boundary", test_types_filter)
        ):
            boundary = self._boundary_test(endpoint)
            if boundary:
                cases.append(boundary)

        # Schema validation — only if response schema present
        if (
            endpoint.response_schema
            and self._should_include("schema_validation", test_types_filter)
        ):
            cases.append(self._schema_validation_test(endpoint))

        return cases

    def _should_include(
        self, test_type: str, filter_list: Optional[List[str]]
    ) -> bool:
        """Check if a test type should be included."""
        if filter_list is None:
            return True
        return test_type in filter_list

    def _happy_path_test(self, endpoint: APIEndpointArtifact) -> Dict[str, Any]:
        """Generate happy path test case."""
        payload = self._make_example_payload(endpoint) if endpoint.request_body_schema else "{}"
        return {
            "func_name": f"happy_path_{endpoint.method.lower()}",
            "description": f"Happy path: {endpoint.method} {endpoint.path} returns success",
            "test_type": "happy_path",
            "test_level": self._classifier.classify_test_level("happy_path"),
            "failure_type": self._classifier.classify_failure_type("happy_path"),
            "payload": payload,
        }

    def _auth_tests(self, endpoint: APIEndpointArtifact) -> List[Dict[str, Any]]:
        """Generate auth test cases (missing + invalid)."""
        return [
            {
                "func_name": f"auth_missing_{endpoint.method.lower()}",
                "description": f"Auth: {endpoint.method} {endpoint.path} without token returns 401",
                "test_type": "auth_missing",
                "test_level": self._classifier.classify_test_level("auth"),
                "failure_type": self._classifier.classify_failure_type("auth"),
            },
            {
                "func_name": f"auth_invalid_{endpoint.method.lower()}",
                "description": f"Auth: {endpoint.method} {endpoint.path} with invalid token returns 401/403",
                "test_type": "auth_invalid",
                "test_level": self._classifier.classify_test_level("auth"),
                "failure_type": self._classifier.classify_failure_type("auth"),
            },
        ]

    def _validation_missing_fields_test(
        self, endpoint: APIEndpointArtifact
    ) -> Dict[str, Any]:
        """Generate validation test for missing required fields."""
        return {
            "func_name": f"validation_missing_fields_{endpoint.method.lower()}",
            "description": (
                f"Validation: {endpoint.method} {endpoint.path} with empty payload returns 400/422"
            ),
            "test_type": "validation_missing_fields",
            "test_level": self._classifier.classify_test_level("validation"),
            "failure_type": self._classifier.classify_failure_type("validation"),
        }

    def _boundary_test(
        self, endpoint: APIEndpointArtifact
    ) -> Optional[Dict[str, Any]]:
        """Generate boundary test for string/integer fields."""
        schema = endpoint.request_body_schema
        if not schema:
            return None

        props = schema.get("properties", {})
        boundary_payload: Dict[str, Any] = {}

        for field_name, field_schema in props.items():
            field_type = field_schema.get("type", "")
            if field_type == "string":
                max_len = field_schema.get("maxLength", 255)
                boundary_payload[field_name] = "x" * (max_len + 1)
            elif field_type == "integer":
                min_val = field_schema.get("minimum")
                if min_val is not None and min_val >= 0:
                    boundary_payload[field_name] = -1
                else:
                    max_val = field_schema.get("maximum", 999999)
                    boundary_payload[field_name] = max_val + 1

        if not boundary_payload:
            return None

        return {
            "func_name": f"boundary_{endpoint.method.lower()}",
            "description": (
                f"Boundary: {endpoint.method} {endpoint.path} with boundary values returns 400/422"
            ),
            "test_type": "boundary",
            "test_level": self._classifier.classify_test_level("boundary"),
            "failure_type": self._classifier.classify_failure_type("boundary"),
            "payload": repr(boundary_payload),
        }

    def _schema_validation_test(
        self, endpoint: APIEndpointArtifact
    ) -> Dict[str, Any]:
        """Generate response schema validation test."""
        return {
            "func_name": f"schema_validation_{endpoint.method.lower()}",
            "description": (
                f"Schema: {endpoint.method} {endpoint.path} response matches schema"
            ),
            "test_type": "schema_validation",
            "test_level": self._classifier.classify_test_level("schema_validation"),
            "failure_type": self._classifier.classify_failure_type("schema_validation"),
            "schema": repr(endpoint.response_schema),
        }

    # ------------------------------------------------------------------
    # Naming helpers
    # ------------------------------------------------------------------

    def _make_filename(self, endpoint: APIEndpointArtifact) -> str:
        """Generate a filename appropriate for the framework.

        - pytest_requests: test_api_get_pets.py
        - rest_assured: TestGetPets.java
        - karate: get_pets.feature
        """
        slug = re.sub(r"[^a-zA-Z0-9]", "_", endpoint.path.strip("/"))
        slug = re.sub(r"_+", "_", slug).strip("_").lower()

        lang = _LANGUAGE_MAP.get(self.framework, "python")
        if lang == "java":
            class_name = self._make_class_name(endpoint)
            return f"{class_name}.java"
        elif lang == "karate":
            return f"{endpoint.method.lower()}_{slug}.feature"
        else:
            return f"test_api_{endpoint.method.lower()}_{slug}.py"

    def _make_class_name(self, endpoint: APIEndpointArtifact) -> str:
        """Generate a class name like TestGetPets."""
        slug = re.sub(r"[^a-zA-Z0-9]", "_", endpoint.path.strip("/"))
        parts = [p.capitalize() for p in slug.split("_") if p]
        return f"Test{endpoint.method.capitalize()}{''.join(parts)}"

    def _make_path_template(self, endpoint: APIEndpointArtifact) -> str:
        """Convert /pets/{petId} to /pets/1 for path param substitution."""
        result = endpoint.path
        for param in endpoint.path_params:
            name = param["name"]
            ptype = param.get("type", "string")
            if ptype == "integer":
                result = result.replace(f"{{{name}}}", "1")
            else:
                result = result.replace(f"{{{name}}}", "test_value")
        return result

    def _make_query_params_dict(self, endpoint: APIEndpointArtifact) -> str:
        """Generate a dict literal for query params."""
        if not endpoint.query_params:
            return "{}"
        pairs = []
        for qp in endpoint.query_params:
            name = qp["name"]
            ptype = qp.get("type", "string")
            if ptype == "integer":
                pairs.append(f'"{name}": 10')
            else:
                pairs.append(f'"{name}": "test"')
        return "{" + ", ".join(pairs) + "}"

    def _make_example_payload(self, endpoint: APIEndpointArtifact) -> str:
        """Generate an example payload from the request body schema."""
        # Use examples if available
        if endpoint.examples.get("request"):
            return repr(endpoint.examples["request"])

        # Generate from schema
        schema = endpoint.request_body_schema
        if not schema:
            return "{}"

        props = schema.get("properties", {})
        payload: Dict[str, Any] = {}
        for field_name, field_schema in props.items():
            field_type = field_schema.get("type", "string")
            if field_type == "string":
                payload[field_name] = f"test_{field_name}"
            elif field_type == "integer":
                payload[field_name] = 1
            elif field_type == "number":
                payload[field_name] = 1.0
            elif field_type == "boolean":
                payload[field_name] = True
            elif field_type == "array":
                payload[field_name] = []
            else:
                payload[field_name] = f"test_{field_name}"

        return repr(payload)
