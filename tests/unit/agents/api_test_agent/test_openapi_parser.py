"""Unit tests for the OpenAPI / Swagger spec parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser

_FIXTURES = Path(__file__).resolve().parent.parent.parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def parser():
    return OpenAPIParser()


@pytest.fixture
def petstore_v3():
    return _load_fixture("openapi_petstore.json")


@pytest.fixture
def petstore_v2():
    return _load_fixture("swagger_petstore.json")


@pytest.fixture
def minimal_spec():
    return _load_fixture("openapi_minimal.json")


# ── Format Detection ─────────────────────────────────────────────────────────


class TestFormatDetection:
    def test_detects_openapi_3(self, parser, petstore_v3):
        assert parser._detect_format(petstore_v3) == "openapi_3.0"

    def test_detects_swagger_2(self, parser, petstore_v2):
        assert parser._detect_format(petstore_v2) == "swagger_2.0"

    def test_detects_unknown_format(self, parser):
        assert parser._detect_format({"api": "1.0"}) == "unknown"

    def test_unknown_format_raises(self, parser):
        with pytest.raises(ValueError, match="Unknown spec format"):
            parser.parse({"api": "1.0"})


# ── OpenAPI 3.x Parsing ─────────────────────────────────────────────────────


class TestOpenAPI3Parsing:
    def test_parses_all_endpoints(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        # 8 endpoints: GET/POST /pets, GET/PUT/DELETE /pets/{petId},
        # GET /pets/{petId}/vaccinations, POST /auth/login, GET /health
        assert len(model.endpoints) == 8

    def test_extracts_base_url(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        assert model.base_url == "http://localhost:8080/api/v1"

    def test_extracts_spec_metadata(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        assert model.spec_format == "openapi_3.0"
        assert model.spec_title == "Petstore API"

    def test_extracts_path_params(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        get_pet = next(e for e in model.endpoints if e.operation_id == "getPet")
        assert len(get_pet.path_params) == 1
        assert get_pet.path_params[0]["name"] == "petId"
        assert get_pet.path_params[0]["type"] == "integer"

    def test_extracts_query_params(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        list_pets = next(e for e in model.endpoints if e.operation_id == "listPets")
        assert len(list_pets.query_params) == 2
        names = {p["name"] for p in list_pets.query_params}
        assert "limit" in names
        assert "offset" in names

    def test_extracts_request_body(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert create_pet.request_body_schema is not None
        assert "properties" in create_pet.request_body_schema
        assert "name" in create_pet.request_body_schema["properties"]

    def test_extracts_response_schema(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        get_pet = next(e for e in model.endpoints if e.operation_id == "getPet")
        assert get_pet.response_schema is not None
        assert "properties" in get_pet.response_schema
        assert "id" in get_pet.response_schema["properties"]

    def test_extracts_status_codes(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert 201 in create_pet.status_codes
        assert 400 in create_pet.status_codes
        assert 401 in create_pet.status_codes

    def test_extracts_operation_id_and_tags(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert create_pet.summary == "Create a new pet"
        assert "pets" in create_pet.tags

    def test_extracts_examples(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert "request" in create_pet.examples
        assert create_pet.examples["request"]["name"] == "Buddy"


# ── Swagger 2.0 Parsing ─────────────────────────────────────────────────────


class TestSwagger2Parsing:
    def test_parses_all_endpoints(self, parser, petstore_v2):
        model = parser.parse(petstore_v2)
        assert len(model.endpoints) == 8

    def test_extracts_base_url(self, parser, petstore_v2):
        model = parser.parse(petstore_v2)
        assert model.base_url == "http://localhost:8080/api/v1"

    def test_extracts_spec_metadata(self, parser, petstore_v2):
        model = parser.parse(petstore_v2)
        assert model.spec_format == "swagger_2.0"
        assert model.spec_title == "Petstore API"

    def test_extracts_request_body_from_body_param(self, parser, petstore_v2):
        model = parser.parse(petstore_v2)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert create_pet.request_body_schema is not None
        assert "properties" in create_pet.request_body_schema


# ── Auth Detection ───────────────────────────────────────────────────────────


class TestAuthDetection:
    def test_global_bearer_auth(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        assert model.auth_type == "bearer"

    def test_public_endpoints_have_no_auth(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        health = next(e for e in model.endpoints if e.operation_id == "healthCheck")
        assert health.auth_required is False

    def test_protected_endpoints_have_auth(self, parser, petstore_v3):
        model = parser.parse(petstore_v3)
        create_pet = next(e for e in model.endpoints if e.operation_id == "createPet")
        assert create_pet.auth_required is True
        assert create_pet.auth_type == "bearer"

    def test_api_key_auth_swagger2(self, parser, petstore_v2):
        model = parser.parse(petstore_v2)
        assert model.auth_type == "api_key"


# ── Ref Resolution ───────────────────────────────────────────────────────────


class TestRefResolution:
    def test_resolves_component_ref(self, parser, petstore_v3):
        ref = {"$ref": "#/components/schemas/Pet"}
        resolved = parser._resolve_ref(ref, petstore_v3)
        assert "properties" in resolved
        assert "name" in resolved["properties"]

    def test_resolves_definition_ref(self, parser, petstore_v2):
        ref = {"$ref": "#/definitions/Pet"}
        resolved = parser._resolve_ref(ref, petstore_v2)
        assert "properties" in resolved
        assert "name" in resolved["properties"]

    def test_unresolved_ref_returns_marker(self, parser):
        ref = {"$ref": "#/components/schemas/Missing"}
        resolved = parser._resolve_ref(ref, {"components": {"schemas": {}}})
        assert resolved.get("_unresolved") is True


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_paths(self, parser):
        spec = {"openapi": "3.0.0", "info": {"title": "Empty"}, "paths": {}}
        model = parser.parse(spec)
        assert len(model.endpoints) == 0

    def test_minimal_spec(self, parser, minimal_spec):
        model = parser.parse(minimal_spec)
        assert len(model.endpoints) == 1
        assert model.endpoints[0].path == "/health"
        assert model.endpoints[0].method == "GET"

    def test_parse_from_json_string(self, parser, minimal_spec):
        json_str = json.dumps(minimal_spec)
        model = parser.parse(json_str)
        assert len(model.endpoints) == 1
