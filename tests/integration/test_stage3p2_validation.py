"""
Stage 3 Phase 2 Integration Tests
===================================
End-to-end validation of the API Discovery + API Test Generator pipeline.
Uses the petstore fixtures to exercise the full OpenAPI -> test code flow.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from stlc_platform.agents.api_test_agent import (
    APITestAgent,
    APITestGenerator,
    OpenAPIParser,
    TestClassifier,
)
from stlc_platform.core.contracts import APIModelArtifact

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def petstore_v3():
    return _load_fixture("openapi_petstore.json")


@pytest.fixture
def petstore_v2():
    return _load_fixture("swagger_petstore.json")


@pytest.fixture
def petstore_model(petstore_v3) -> APIModelArtifact:
    return OpenAPIParser().parse(petstore_v3)


# ── OpenAPI Parsing End-to-End ───────────────────────────────────────────────


class TestOpenAPIParsingEndToEnd:
    def test_petstore_has_8_endpoints(self, petstore_model):
        assert len(petstore_model.endpoints) == 8

    def test_auth_detection_across_endpoints(self, petstore_model):
        auth_endpoints = [e for e in petstore_model.endpoints if e.auth_required]
        public_endpoints = [e for e in petstore_model.endpoints if not e.auth_required]
        # createPet, updatePet, deletePet, listVaccinations = 4 auth
        # listPets, getPet, login, healthCheck = 4 public
        assert len(auth_endpoints) == 4
        assert len(public_endpoints) == 4

    def test_schema_extraction_completeness(self, petstore_model):
        endpoints_with_response_schema = [
            e for e in petstore_model.endpoints if e.response_schema
        ]
        # Most endpoints have response schemas
        assert len(endpoints_with_response_schema) >= 6


# ── Test Generation End-to-End ───────────────────────────────────────────────


class TestTestGenerationEndToEnd:
    def test_generates_test_files_for_all_endpoints(self, petstore_model):
        generator = APITestGenerator()
        artifacts = generator.generate(petstore_model)
        # 1 conftest + 8 test files
        test_files = [a for a in artifacts if a.test_count > 0]
        assert len(test_files) == 8

    def test_total_test_count(self, petstore_model):
        generator = APITestGenerator()
        artifacts = generator.generate(petstore_model)
        total = sum(a.test_count for a in artifacts)
        # Each endpoint has at least 1 (happy path), auth endpoints have +2,
        # endpoints with body have +1-2 more, schema endpoints have +1
        assert total >= 20

    def test_all_test_types_represented(self, petstore_model):
        generator = APITestGenerator()
        artifacts = generator.generate(petstore_model)
        all_content = "\n".join(a.content for a in artifacts)
        assert "happy_path" in all_content
        assert "auth_missing" in all_content
        assert "validation_missing_fields" in all_content
        assert "schema_validation" in all_content

    def test_boundary_tests_generated(self, petstore_model):
        generator = APITestGenerator()
        artifacts = generator.generate(petstore_model)
        all_content = "\n".join(a.content for a in artifacts)
        assert "boundary" in all_content


# ── Agent Pipeline ───────────────────────────────────────────────────────────


class TestAgentPipeline:
    def test_full_pipeline_from_spec(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        assert result.success is True
        assert "api_model" in result.artifacts
        assert "test_files" in result.artifacts
        assert "conftest" in result.artifacts

    def test_metadata_complete(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        assert result.metadata["total_endpoints"] == 8
        assert result.metadata["total_test_files"] == 8
        assert result.metadata["total_tests"] >= 20
        assert result.metadata["framework"] == "pytest_requests"
        assert "test_level_distribution" in result.metadata

    def test_from_prebuilt_model(self, petstore_model):
        agent = APITestAgent()
        result = agent.execute({"api_model": petstore_model}, {})
        assert result.success is True
        assert result.metadata["total_endpoints"] == 8


# ── Generated Code Quality ───────────────────────────────────────────────────


class TestGeneratedCodeQuality:
    def test_all_files_valid_python(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        for test_file in result.artifacts["test_files"]:
            try:
                ast.parse(test_file.content)
            except SyntaxError as e:
                pytest.fail(
                    f"SyntaxError in {test_file.filename}: {e}"
                )

    def test_conftest_valid_python(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        ast.parse(result.artifacts["conftest"].content)

    def test_pytest_marks_present(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        all_content = "\n".join(
            t.content for t in result.artifacts["test_files"]
        )
        assert "@pytest.mark.api" in all_content

    def test_failure_type_comments_present(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        all_content = "\n".join(
            t.content for t in result.artifacts["test_files"]
        )
        assert "# failure_type:" in all_content


# ── Pyramid Distribution ─────────────────────────────────────────────────────


class TestPyramidDistribution:
    def test_api_level_is_majority(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        dist = result.metadata["test_level_distribution"]
        total = sum(dist.values())
        api_count = dist.get("api", 0)
        # API-level tests should be > 80%
        assert api_count / total > 0.8


# ── Swagger 2.0 Compatibility ───────────────────────────────────────────────


class TestSwagger2Compatibility:
    def test_swagger2_same_pipeline(self, petstore_v2):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v2}, {})
        assert result.success is True
        assert result.metadata["total_endpoints"] == 8
        assert result.metadata["spec_format"] == "swagger_2.0"
