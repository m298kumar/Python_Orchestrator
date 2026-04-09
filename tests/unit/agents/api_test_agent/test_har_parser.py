"""Tests for HAR file parser."""

import json
from pathlib import Path

import pytest
from stlc_platform.agents.api_test_agent.har_parser import HARParser
from stlc_platform.core.contracts import APIModelArtifact


@pytest.fixture
def har_parser():
    return HARParser()


@pytest.fixture
def sample_har():
    path = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "sample.har"
    return json.loads(path.read_text())


@pytest.fixture
def minimal_har():
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://api.test.com/api/items",
                        "headers": [],
                    },
                    "response": {
                        "status": 200,
                        "content": {
                            "mimeType": "application/json",
                            "text": "[]",
                        },
                    },
                },
            ],
        },
    }


class TestHARParsing:
    def test_parses_har_dict(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        assert isinstance(result, APIModelArtifact)
        assert result.spec_format == "har"

    def test_parses_har_string(self, har_parser, sample_har):
        result = har_parser.parse(json.dumps(sample_har))
        assert isinstance(result, APIModelArtifact)

    def test_discovers_api_endpoints(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        assert len(result.endpoints) >= 3  # GET/POST/DELETE users + products

    def test_filters_static_assets(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        paths = [ep.path for ep in result.endpoints]
        assert not any(".js" in p for p in paths)

    def test_parameterizes_numeric_ids(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        paths = [ep.path for ep in result.endpoints]
        assert any("{id}" in p for p in paths)

    def test_extracts_methods(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        methods = {ep.method for ep in result.endpoints}
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_detects_bearer_auth(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        assert result.auth_type == "bearer"

    def test_extracts_query_params(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        products_ep = next((ep for ep in result.endpoints if "products" in ep.path), None)
        assert products_ep is not None
        param_names = [p["name"] for p in products_ep.query_params]
        assert "category" in param_names

    def test_extracts_request_body(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        post_ep = next((ep for ep in result.endpoints if ep.method == "POST"), None)
        assert post_ep is not None
        assert post_ep.request_body_schema is not None

    def test_infers_base_url(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        assert "api.example.com" in result.base_url

    def test_deduplicates_endpoints(self, har_parser, sample_har):
        result = har_parser.parse(sample_har)
        # GET /api/users/123 and DELETE /api/users/456 both become /api/users/{id}
        # but with different methods, so both should be present
        user_eps = [ep for ep in result.endpoints if "users/{id}" in ep.path]
        methods = {ep.method for ep in user_eps}
        assert len(methods) >= 2


class TestHAREdgeCases:
    def test_invalid_json_raises(self, har_parser):
        with pytest.raises(ValueError, match="Invalid HAR JSON"):
            har_parser.parse("not json")

    def test_missing_log_key_raises(self, har_parser):
        with pytest.raises(ValueError, match="Invalid HAR format"):
            har_parser.parse({"entries": []})

    def test_empty_entries_returns_empty(self, har_parser):
        result = har_parser.parse({"log": {"entries": []}})
        assert len(result.endpoints) == 0

    def test_base_url_filter(self, har_parser, sample_har):
        result = har_parser.parse(sample_har, base_url_filter="https://api.example.com")
        assert len(result.endpoints) >= 3

    def test_minimal_har(self, har_parser, minimal_har):
        result = har_parser.parse(minimal_har)
        assert len(result.endpoints) == 1
        assert result.endpoints[0].path == "/api/items"

    def test_uuid_parameterization(self, har_parser):
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://api.test.com/api/items/550e8400-e29b-41d4-a716-446655440000",
                            "headers": [],
                        },
                        "response": {
                            "status": 200,
                            "content": {"mimeType": "application/json", "text": "{}"},
                        },
                    },
                ],
            },
        }
        result = har_parser.parse(har)
        assert "{uuid}" in result.endpoints[0].path

    def test_preserves_example_request(self, har_parser, sample_har):
        """Bug fix: example_request was silently dropped before contract v1.2."""
        result = har_parser.parse(sample_har)
        post_ep = next((ep for ep in result.endpoints if ep.method == "POST"), None)
        assert post_ep is not None
        assert post_ep.example_request is not None
        assert "name" in post_ep.example_request

    def test_preserves_example_response(self, har_parser, sample_har):
        """Bug fix: example_response was silently dropped before contract v1.2."""
        result = har_parser.parse(sample_har)
        get_ep = next(
            (ep for ep in result.endpoints if ep.method == "GET" and "users" in ep.path),
            None,
        )
        assert get_ep is not None
        assert get_ep.example_response is not None

    def test_status_codes_are_ints(self, har_parser, sample_har):
        """Status codes should be stored as integers in the contract."""
        result = har_parser.parse(sample_har)
        for ep in result.endpoints:
            for code in ep.status_codes:
                assert isinstance(code, int)
