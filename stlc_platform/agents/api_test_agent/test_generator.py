"""
API Test Generator
==================
Generates API test code from an APIModelArtifact using Jinja2 templates.

Supported frameworks:
  - pytest_requests (Pytest + Requests library, Python)
  - rest_assured (JUnit 5 + REST Assured, Java)
  - karate (Karate DSL, .feature files)
  - supertest (Supertest + Mocha, JavaScript/Node.js)

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
    "supertest": "supertest.js.j2",
}

# Framework name -> language
_LANGUAGE_MAP: Dict[str, str] = {
    "pytest_requests": "python",
    "rest_assured": "java",
    "karate": "karate",
    "supertest": "javascript",
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

        # Generate CRUD sequence tests (cross-endpoint integration tests)
        crud_groups = self._detect_crud_groups(api_model)
        for group in crud_groups:
            crud_tests = self._crud_sequence_tests_for_group(group, api_model)
            if crud_tests:
                artifact = self._generate_crud_artifact(
                    group, crud_tests, api_model.base_url, api_model.auth_type
                )
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
            has_schema_validation=any(t["test_type"] == "schema_validation" for t in test_cases),
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
        if endpoint.request_body_schema and self._should_include("validation", test_types_filter):
            required = endpoint.request_body_schema.get("required", [])
            if required:
                cases.append(self._validation_missing_fields_test(endpoint))

        # Boundary tests — only if request body with typed fields
        if endpoint.request_body_schema and self._should_include("boundary", test_types_filter):
            boundary = self._boundary_test(endpoint)
            if boundary:
                cases.append(boundary)

        # Schema validation — only if response schema present
        if endpoint.response_schema and self._should_include(
            "schema_validation", test_types_filter
        ):
            cases.append(self._schema_validation_test(endpoint))

        return cases

    def _should_include(self, test_type: str, filter_list: Optional[List[str]]) -> bool:
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
                "description": (
                    f"Auth: {endpoint.method} {endpoint.path} without token returns 401"
                ),
                "test_type": "auth_missing",
                "test_level": self._classifier.classify_test_level("auth"),
                "failure_type": self._classifier.classify_failure_type("auth"),
            },
            {
                "func_name": f"auth_invalid_{endpoint.method.lower()}",
                "description": (
                    f"Auth: {endpoint.method} {endpoint.path} with invalid token returns 401/403"
                ),
                "test_type": "auth_invalid",
                "test_level": self._classifier.classify_test_level("auth"),
                "failure_type": self._classifier.classify_failure_type("auth"),
            },
        ]

    def _validation_missing_fields_test(self, endpoint: APIEndpointArtifact) -> Dict[str, Any]:
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

    def _boundary_test(self, endpoint: APIEndpointArtifact) -> Optional[Dict[str, Any]]:
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

    def _schema_validation_test(self, endpoint: APIEndpointArtifact) -> Dict[str, Any]:
        """Generate response schema validation test."""
        return {
            "func_name": f"schema_validation_{endpoint.method.lower()}",
            "description": (f"Schema: {endpoint.method} {endpoint.path} response matches schema"),
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
        method_lower = endpoint.method.lower()
        if lang == "java":
            class_name = self._make_class_name(endpoint)
            return f"{class_name}.java"
        elif lang == "karate":
            return f"{method_lower}_{slug}.feature"
        elif lang == "javascript":
            return f"test_api_{method_lower}_{slug}.test.js"
        else:
            return f"test_api_{method_lower}_{slug}.py"

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

    # ------------------------------------------------------------------
    # Smart payload generation (heuristic field-name matching)
    # ------------------------------------------------------------------

    def _make_example_payload(self, endpoint: APIEndpointArtifact) -> str:
        """Generate an example payload from the request body schema.

        Uses heuristic field-name matching to produce realistic test data
        without any external dependencies (no Faker library needed).
        """
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
            payload[field_name] = self._smart_field_value(field_name, field_type, field_schema)

        return repr(payload)

    _STRING_FIELD_MAP = {
        frozenset(("email", "email_address", "emailaddress")): "test_user@example.com",
        frozenset(("name", "full_name", "fullname", "display_name", "displayname")): "John Doe",
        frozenset(("first_name", "firstname", "given_name", "givenname")): "Jane",
        frozenset(("last_name", "lastname", "family_name", "familyname", "surname")): "Smith",
        frozenset(("address", "street", "street_address", "streetaddress")): "123 Test Street",
        frozenset(("city", "town")): "Test City",
        frozenset(("state", "province", "region")): "CA",
        frozenset(("country",)): "US",
        frozenset(("zip", "zip_code", "zipcode", "postal", "postal_code", "postalcode")): "12345",
        frozenset(("url", "website", "homepage", "link", "uri")): "https://example.com",
        frozenset(("description", "desc", "bio", "about", "summary")): None,  # uses field_name
        frozenset(("age",)): None,  # wrong type, handled by integer
        frozenset(("status",)): "active",
    }
    _STRING_CONTAINS_MAP = [
        ({"phone", "mobile", "tel"}, "+1-555-0100"),
        ({"password", "secret"}, "TestPass123!"),
    ]
    _DATE_KEYWORDS = frozenset(
        (
            "date",
            "created_at",
            "updated_at",
            "timestamp",
            "datetime",
            "createdat",
            "updatedat",
        )
    )
    _INTEGER_EXACT_MAP = {
        "age": 25,
        "quantity": 5,
        "qty": 5,
        "count": 5,
        "price": 1999,
        "amount": 1999,
        "cost": 1999,
        "total": 1999,
        "year": 2024,
        "id": 1,
    }
    _NUMBER_EXACT_MAP = {
        "price": 19.99,
        "amount": 19.99,
        "cost": 19.99,
        "total": 19.99,
        "latitude": 37.7749,
        "lat": 37.7749,
        "longitude": -122.4194,
        "lng": -122.4194,
        "lon": -122.4194,
    }

    @classmethod
    def _smart_field_value(
        cls, field_name: str, field_type: str, field_schema: Dict[str, Any]
    ) -> Any:
        name_lower = field_name.lower()

        if field_type == "string":
            return cls._smart_string_value(name_lower, field_name)
        if field_type == "integer":
            return cls._INTEGER_EXACT_MAP.get(
                name_lower, 1 if name_lower.endswith("_id") or name_lower == "id" else 42
            )
        if field_type == "number":
            return cls._NUMBER_EXACT_MAP.get(name_lower, 1.0)
        if field_type == "boolean":
            return True
        if field_type == "array":
            return []
        return f"test_{field_name}"

    @classmethod
    def _smart_string_value(cls, name_lower: str, field_name: str) -> str:
        for names, value in cls._STRING_FIELD_MAP.items():
            if name_lower in names:
                return value if value is not None else f"Test description for {field_name}"
        for keywords, value in cls._STRING_CONTAINS_MAP:
            if any(kw in name_lower for kw in keywords):
                return value
        if name_lower in cls._DATE_KEYWORDS or any(kw in name_lower for kw in cls._DATE_KEYWORDS):
            return "2024-01-15T10:30:00Z"
        return f"test_{field_name}"

    # ------------------------------------------------------------------
    # CRUD sequence detection and generation
    # ------------------------------------------------------------------

    def _detect_crud_groups(self, api_model: APIModelArtifact) -> List[Dict[str, Any]]:
        """Identify resource groups that have POST + GET + PUT/PATCH + DELETE.

        Groups endpoints by base path (stripping path parameters) and checks
        that at least POST, GET, PUT (or PATCH), and DELETE are present.

        Returns:
            List of dicts, each with:
              - base_path: str (e.g. "/pets")
              - endpoints: dict mapping method -> APIEndpointArtifact
              - resource_name: str (e.g. "pets")
        """
        # Group endpoints by their base path (path without trailing {param})
        path_groups: Dict[str, Dict[str, APIEndpointArtifact]] = {}
        for endpoint in api_model.endpoints:
            # Normalize: strip trailing path params to find the base resource
            base = re.sub(r"/\{[^}]+\}$", "", endpoint.path)
            if base not in path_groups:
                path_groups[base] = {}
            method_upper = endpoint.method.upper()
            # Keep first occurrence per method
            if method_upper not in path_groups[base]:
                path_groups[base][method_upper] = endpoint

        crud_groups: List[Dict[str, Any]] = []
        for base_path, methods in path_groups.items():
            has_create = "POST" in methods
            has_read = "GET" in methods
            has_update = "PUT" in methods or "PATCH" in methods
            has_delete = "DELETE" in methods

            if has_create and has_read and has_update and has_delete:
                # Derive a resource name from the base path
                resource_name = base_path.strip("/").split("/")[-1]
                crud_groups.append(
                    {
                        "base_path": base_path,
                        "endpoints": methods,
                        "resource_name": resource_name,
                    }
                )

        return crud_groups

    def _crud_sequence_tests_for_group(
        self, group: Dict[str, Any], api_model: APIModelArtifact
    ) -> List[Dict[str, Any]]:
        """Generate CRUD sequence test cases for a single resource group.

        Returns a list with one test case dict representing the full
        POST -> GET -> PUT -> DELETE -> GET(404) chain.
        """
        endpoints = group["endpoints"]
        resource = group["resource_name"]
        base_path = group["base_path"]

        post_ep = endpoints.get("POST")
        get_ep = endpoints.get("GET")
        put_ep = endpoints.get("PUT") or endpoints.get("PATCH")
        delete_ep = endpoints.get("DELETE")

        # Build a create payload from the POST endpoint schema
        create_payload = "{}"
        if post_ep and post_ep.request_body_schema:
            create_payload = self._make_example_payload(post_ep)

        update_payload = "{}"
        if put_ep and put_ep.request_body_schema:
            update_payload = self._make_example_payload(put_ep)

        update_method = "PUT" if "PUT" in endpoints else "PATCH"

        return [
            {
                "func_name": f"crud_sequence_{resource}",
                "description": (
                    f"CRUD sequence: Create, Read, Update, Delete {resource} via {base_path}"
                ),
                "test_type": "crud_sequence",
                "test_level": self._classifier.classify_test_level("crud_sequence"),
                "failure_type": self._classifier.classify_failure_type("crud_sequence"),
                "create_payload": create_payload,
                "update_payload": update_payload,
                "base_path": base_path,
                "resource_name": resource,
                "post_path": post_ep.path if post_ep else base_path,
                "get_path": get_ep.path if get_ep else base_path,
                "put_path": put_ep.path if put_ep else base_path,
                "delete_path": delete_ep.path if delete_ep else base_path,
                "update_method": update_method.lower(),
                "auth_required": any(
                    ep.auth_required for ep in [post_ep, get_ep, put_ep, delete_ep] if ep
                ),
            }
        ]

    def _generate_crud_artifact(
        self,
        group: Dict[str, Any],
        crud_tests: List[Dict[str, Any]],
        base_url: str,
        auth_type: str,
    ) -> APITestArtifact:
        """Render CRUD sequence tests into an APITestArtifact."""
        resource = group["resource_name"]

        template = self._env.get_template(SUPPORTED_FRAMEWORKS[self.framework])
        content = template.render(
            method="CRUD",
            method_lower="crud",
            path=group["base_path"],
            path_template=group["base_path"],
            summary=f"CRUD sequence for {resource}",
            operation_id=f"crud_{resource}",
            base_url=base_url,
            auth_required=crud_tests[0].get("auth_required", False),
            auth_type=auth_type,
            class_name=f"TestCrudSequence{resource.capitalize()}",
            path_params=[],
            query_params=[],
            query_params_dict="{}",
            has_schema_validation=False,
            tests=crud_tests,
        )

        return APITestArtifact(
            framework=self.framework,
            language=_LANGUAGE_MAP.get(self.framework, "python"),
            filename=f"test_crud_sequence_{resource}.py",
            content=content,
            endpoint_path=group["base_path"],
            test_count=len(crud_tests),
            test_level="integration",
            test_type="crud_sequence",
            tags=[resource, "crud", "integration"],
        )
