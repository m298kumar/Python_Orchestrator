"""Unit tests for Supertest (JavaScript/Node.js) API test generation."""

from __future__ import annotations

import pytest

from stlc_platform.agents.api_test_agent.test_generator import (
    APITestGenerator,
    SUPPORTED_FRAMEWORKS,
)
from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact


def _make_endpoint(**overrides) -> APIEndpointArtifact:
    """Factory with sensible defaults for a POST endpoint with auth + schemas."""
    defaults = {
        "path": "/users",
        "method": "POST",
        "operation_id": "createUser",
        "summary": "Create a new user",
        "tags": ["users"],
        "status_codes": [201, 400, 401],
        "auth_required": True,
        "auth_type": "bearer",
        "request_body_schema": {
            "type": "object",
            "required": ["name", "email"],
            "properties": {
                "name": {"type": "string", "maxLength": 100},
                "email": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
        },
    }
    defaults.update(overrides)
    return APIEndpointArtifact(**defaults)


def _make_model(endpoints=None, **overrides) -> APIModelArtifact:
    defaults = {
        "base_url": "http://localhost:3000",
        "auth_type": "bearer",
        "spec_format": "openapi_3.0",
        "spec_title": "User API",
    }
    defaults.update(overrides)
    if endpoints:
        defaults["endpoints"] = endpoints
    return APIModelArtifact(**defaults)


# ── Framework Registration ───────────────────────────────────────────────────


class TestSupertestFrameworkRegistration:
    def test_supertest_in_supported_frameworks(self):
        assert "supertest" in SUPPORTED_FRAMEWORKS

    def test_supertest_template_filename(self):
        assert SUPPORTED_FRAMEWORKS["supertest"] == "supertest.js.j2"

    def test_supertest_generator_instantiates(self):
        gen = APITestGenerator(framework="supertest")
        assert gen.framework == "supertest"


# ── Content Generation ───────────────────────────────────────────────────────


class TestSupertestContentGeneration:
    def test_generates_valid_js_content(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        assert len(artifacts) >= 1
        test_file = artifacts[0]
        content = test_file.content
        assert "require('supertest')" in content
        assert "describe(" in content
        assert "it(" in content

    def test_base_url_present(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint], base_url="http://api.example.com")
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert "http://api.example.com" in test_file.content

    def test_language_is_javascript(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        assert artifacts[0].language == "javascript"


# ── Filename Generation ──────────────────────────────────────────────────────


class TestSupertestFilename:
    def test_filename_ends_with_test_js(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint(path="/users", method="POST")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert test_file.filename.endswith(".test.js")

    def test_filename_format(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint(path="/users", method="POST")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert test_file.filename == "test_api_post_users.test.js"

    def test_filename_with_path_params(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint(
            path="/users/{userId}",
            method="GET",
            path_params=[{"name": "userId", "type": "integer"}],
            request_body_schema=None,
            response_schema=None,
            auth_required=False,
        )
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert test_file.filename == "test_api_get_users_userid.test.js"


# ── Test Types Rendered ──────────────────────────────────────────────────────


class TestSupertestTestTypes:
    """Verify all test types are rendered for a fully-configured endpoint."""

    @pytest.fixture
    def full_artifacts(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()  # Has auth, request body, response schema
        model = _make_model([endpoint])
        return gen.generate(model)

    def test_happy_path_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "happy_path" in content.lower() or "Happy path" in content

    def test_auth_missing_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "auth_missing" in content.lower() or "without token" in content

    def test_auth_invalid_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "invalid_token_12345" in content

    def test_validation_missing_fields_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "validation_missing_fields" in content.lower() or "empty payload" in content.lower()

    def test_boundary_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "boundary" in content.lower()

    def test_schema_validation_rendered(self, full_artifacts):
        content = full_artifacts[0].content
        assert "schema_validation" in content.lower() or "schema" in content.lower()

    def test_all_test_types_count(self, full_artifacts):
        # happy_path + auth_missing + auth_invalid + validation + boundary + schema = 6
        assert full_artifacts[0].test_count == 6


# ── Conftest Not Generated ───────────────────────────────────────────────────


class TestSupertestNoConftest:
    def test_no_conftest_generated(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        filenames = [a.filename for a in artifacts]
        assert "conftest.py" not in filenames

    def test_single_artifact_per_endpoint(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        # No conftest, so 1 endpoint = 1 artifact
        assert len(artifacts) == 1


# ── Failure Type and Test Level Comments ─────────────────────────────────────


class TestSupertestMetadataComments:
    def test_failure_type_comments_present(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        content = artifacts[0].content
        assert "// failure_type:" in content

    def test_test_level_comments_present(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        content = artifacts[0].content
        assert "// test_level:" in content


# ── GET Endpoint ─────────────────────────────────────────────────────────────


class TestSupertestGetEndpoint:
    def test_get_uses_supertest_get(self):
        gen = APITestGenerator(framework="supertest")
        endpoint = _make_endpoint(
            method="GET",
            path="/items",
            request_body_schema=None,
            auth_required=False,
        )
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        content = artifacts[0].content
        assert ".get(" in content
