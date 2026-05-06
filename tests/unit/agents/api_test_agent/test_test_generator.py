"""Unit tests for the API Test Generator."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from stlc_platform.agents.api_test_agent.test_generator import (
    SUPPORTED_FRAMEWORKS,
    APITestGenerator,
)
from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact

_FIXTURES = Path(__file__).resolve().parent.parent.parent.parent / "fixtures"


def _make_endpoint(**overrides) -> APIEndpointArtifact:
    """Factory with sensible defaults."""
    defaults = {
        "path": "/items",
        "method": "GET",
        "operation_id": "listItems",
        "summary": "List items",
        "tags": ["items"],
        "status_codes": [200],
    }
    defaults.update(overrides)
    return APIEndpointArtifact(**defaults)


def _make_model(endpoints=None, **overrides) -> APIModelArtifact:
    defaults = {
        "base_url": "http://localhost:8080",
        "auth_type": "bearer",
        "spec_format": "openapi_3.0",
        "spec_title": "Test API",
    }
    defaults.update(overrides)
    if endpoints:
        defaults["endpoints"] = endpoints
    return APIModelArtifact(**defaults)


@pytest.fixture
def generator():
    return APITestGenerator()


@pytest.fixture
def petstore_model():
    from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser

    spec = json.loads((_FIXTURES / "openapi_petstore.json").read_text())
    return OpenAPIParser().parse(spec)


# ── Happy Path Generation ────────────────────────────────────────────────────


class TestHappyPathGeneration:
    def test_get_endpoint_generates_happy_path(self, generator):
        endpoint = _make_endpoint(method="GET")
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        # 1 conftest + 1 test file
        assert len(artifacts) == 2
        test_file = artifacts[1]
        assert test_file.test_count >= 1
        assert "happy_path" in test_file.content

    def test_post_endpoint_with_body(self, generator):
        endpoint = _make_endpoint(
            method="POST",
            request_body_schema={
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "requests.post" in test_file.content

    def test_put_endpoint_generates_test(self, generator):
        endpoint = _make_endpoint(
            method="PUT",
            path="/items/{itemId}",
            path_params=[{"name": "itemId", "type": "integer"}],
            request_body_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "requests.put" in test_file.content


# ── Auth Test Generation ─────────────────────────────────────────────────────


class TestAuthTestGeneration:
    def test_auth_required_generates_auth_tests(self, generator):
        endpoint = _make_endpoint(auth_required=True, auth_type="bearer")
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "auth_missing" in test_file.content
        assert "auth_invalid" in test_file.content
        # Happy path + 2 auth tests
        assert test_file.test_count >= 3

    def test_no_auth_skips_auth_tests(self, generator):
        endpoint = _make_endpoint(auth_required=False)
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "auth_missing" not in test_file.content

    def test_auth_test_expects_401(self, generator):
        endpoint = _make_endpoint(auth_required=True)
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "401" in test_file.content


# ── Validation Test Generation ───────────────────────────────────────────────


class TestValidationTestGeneration:
    def test_validation_with_required_fields(self, generator):
        endpoint = _make_endpoint(
            method="POST",
            request_body_schema={
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "validation_missing_fields" in test_file.content

    def test_no_body_skips_validation(self, generator):
        endpoint = _make_endpoint(method="GET")
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "validation_missing_fields" not in test_file.content

    def test_no_required_fields_skips_validation(self, generator):
        endpoint = _make_endpoint(
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "validation_missing_fields" not in test_file.content


# ── Boundary Test Generation ─────────────────────────────────────────────────


class TestBoundaryTestGeneration:
    def test_boundary_for_string_maxlength(self, generator):
        endpoint = _make_endpoint(
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "maxLength": 100}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "boundary" in test_file.content

    def test_boundary_for_integer_minimum(self, generator):
        endpoint = _make_endpoint(
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {"age": {"type": "integer", "minimum": 0}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "boundary" in test_file.content


# ── Schema Validation Generation ─────────────────────────────────────────────


class TestSchemaValidationGeneration:
    def test_response_schema_generates_validation(self, generator):
        endpoint = _make_endpoint(
            response_schema={
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "schema_validation" in test_file.content
        assert "jsonschema" in test_file.content

    def test_no_response_schema_skips_validation(self, generator):
        endpoint = _make_endpoint(response_schema=None)
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "schema_validation" not in test_file.content


# ── Conftest Generation ──────────────────────────────────────────────────────


class TestConftestGeneration:
    def test_conftest_generated(self, generator):
        model = _make_model([_make_endpoint()])
        artifacts = generator.generate(model)
        conftest = artifacts[0]
        assert conftest.filename == "conftest.py"
        assert conftest.test_count == 0
        assert "base_url" in conftest.content

    def test_conftest_has_base_url(self, generator):
        model = _make_model([_make_endpoint()], base_url="http://example.com/api")
        artifacts = generator.generate(model)
        conftest = artifacts[0]
        assert "http://example.com/api" in conftest.content


# ── Filename and Naming ──────────────────────────────────────────────────────


class TestNaming:
    def test_filename_format(self, generator):
        endpoint = _make_endpoint(path="/pets/{petId}", method="GET")
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert test_file.filename == "test_api_get_pets_petid.py"

    def test_class_name_in_content(self, generator):
        endpoint = _make_endpoint(path="/pets", method="POST")
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "TestPostPets" in test_file.content


# ── Generated Code Quality ───────────────────────────────────────────────────


class TestGeneratedCodeQuality:
    def test_all_generated_code_is_valid_python(self, generator, petstore_model):
        artifacts = generator.generate(petstore_model)
        for artifact in artifacts:
            try:
                ast.parse(artifact.content)
            except SyntaxError as e:
                pytest.fail(
                    f"SyntaxError in {artifact.filename}: {e}\nContent:\n{artifact.content[:500]}"
                )

    def test_failure_type_comments_present(self, generator):
        endpoint = _make_endpoint(auth_required=True)
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "# failure_type:" in test_file.content

    def test_test_level_marks_present(self, generator):
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = generator.generate(model)
        test_file = artifacts[1]
        assert "@pytest.mark.api" in test_file.content


# ── Filter test types ────────────────────────────────────────────────────────


class TestFilterTestTypes:
    def test_filter_to_happy_path_only(self, generator):
        endpoint = _make_endpoint(
            auth_required=True,
            request_body_schema={
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        )
        model = _make_model([endpoint])
        artifacts = generator.generate(model, config={"test_types": ["happy_path"]})
        test_file = artifacts[1]
        assert test_file.test_count == 1
        assert "auth_missing" not in test_file.content


# ── REST Assured Generation ─────────────────────────────────────────────────


class TestRestAssuredGeneration:
    def test_happy_path_generates_rest_assured_syntax(self):
        gen = APITestGenerator(framework="rest_assured")
        endpoint = _make_endpoint(method="GET")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        # No conftest for Java
        assert all(a.filename != "conftest.py" for a in artifacts)
        test_file = artifacts[0]
        assert "import io.restassured" in test_file.content
        assert "@Test" in test_file.content
        assert "given()" in test_file.content

    def test_filename_is_java(self):
        gen = APITestGenerator(framework="rest_assured")
        endpoint = _make_endpoint(path="/pets", method="GET")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert test_file.filename.endswith(".java")
        assert test_file.filename == "TestGetPets.java"

    def test_language_is_java(self):
        gen = APITestGenerator(framework="rest_assured")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        assert artifacts[0].language == "java"

    def test_auth_tests_present(self):
        gen = APITestGenerator(framework="rest_assured")
        endpoint = _make_endpoint(auth_required=True, auth_type="bearer")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert "401" in test_file.content
        assert "invalid_token" in test_file.content

    def test_no_conftest_generated(self):
        gen = APITestGenerator(framework="rest_assured")
        model = _make_model([_make_endpoint()])
        artifacts = gen.generate(model)
        filenames = [a.filename for a in artifacts]
        assert "conftest.py" not in filenames

    def test_petstore_produces_8_test_files(self, petstore_model):
        gen = APITestGenerator(framework="rest_assured")
        artifacts = gen.generate(petstore_model)
        # 8 per-endpoint files + 1 CRUD sequence artifact = 9
        assert len(artifacts) == 9


# ── Karate Generation ───────────────────────────────────────────────────────


class TestKarateGeneration:
    def test_happy_path_generates_karate_syntax(self):
        gen = APITestGenerator(framework="karate")
        endpoint = _make_endpoint(method="GET")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert "Feature:" in test_file.content
        assert "Scenario:" in test_file.content
        assert "Given path" in test_file.content
        assert "When method" in test_file.content

    def test_filename_is_feature(self):
        gen = APITestGenerator(framework="karate")
        endpoint = _make_endpoint(path="/pets", method="GET")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert test_file.filename.endswith(".feature")
        assert test_file.filename == "get_pets.feature"

    def test_language_is_karate(self):
        gen = APITestGenerator(framework="karate")
        endpoint = _make_endpoint()
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        assert artifacts[0].language == "karate"

    def test_auth_scenarios_present(self):
        gen = APITestGenerator(framework="karate")
        endpoint = _make_endpoint(auth_required=True, auth_type="bearer")
        model = _make_model([endpoint])
        artifacts = gen.generate(model)
        test_file = artifacts[0]
        assert "status 401" in test_file.content
        assert "invalid_token" in test_file.content

    def test_no_conftest_generated(self):
        gen = APITestGenerator(framework="karate")
        model = _make_model([_make_endpoint()])
        artifacts = gen.generate(model)
        filenames = [a.filename for a in artifacts]
        assert "conftest.py" not in filenames

    def test_petstore_produces_8_test_files(self, petstore_model):
        gen = APITestGenerator(framework="karate")
        artifacts = gen.generate(petstore_model)
        # 8 per-endpoint files + 1 CRUD sequence artifact = 9
        assert len(artifacts) == 9


# ── Multi-Framework Support ─────────────────────────────────────────────────


class TestMultiFrameworkSupport:
    def test_four_frameworks_supported(self):
        assert len(SUPPORTED_FRAMEWORKS) == 4
        assert "pytest_requests" in SUPPORTED_FRAMEWORKS
        assert "rest_assured" in SUPPORTED_FRAMEWORKS
        assert "karate" in SUPPORTED_FRAMEWORKS
        assert "supertest" in SUPPORTED_FRAMEWORKS

    def test_all_frameworks_produce_output(self, petstore_model):
        for fw in SUPPORTED_FRAMEWORKS:
            gen = APITestGenerator(framework=fw)
            artifacts = gen.generate(petstore_model)
            assert len(artifacts) >= 8, f"{fw} produced too few artifacts"
