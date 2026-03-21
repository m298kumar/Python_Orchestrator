"""Unit tests for the Artifact Resolver."""

from __future__ import annotations

import pytest

from stlc_platform.pipeline.artifact_store import ArtifactResolver, ArtifactStore


@pytest.fixture
def store_with_data():
    store = ArtifactStore()
    store.store("parse_reqs", {"test_cases": [{"id": "TC-001"}]})
    store.store("crawl", {"site_model": {"pages": 5}})
    return store


@pytest.fixture
def config():
    return {
        "llm": {"model": "gpt-4", "provider": "openai"},
        "app_url": "http://localhost:8080",
    }


class TestResolveReferences:
    def test_resolve_stage_reference(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        result = resolver.resolve_single("$parse_reqs.test_cases")
        assert result == [{"id": "TC-001"}]

    def test_resolve_config_reference(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        result = resolver.resolve_single("$config.llm.model")
        assert result == "gpt-4"

    def test_resolve_config_top_level(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        result = resolver.resolve_single("$config.app_url")
        assert result == "http://localhost:8080"

    def test_literal_value_passes_through(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        assert resolver.resolve_single("hello") == "hello"
        assert resolver.resolve_single(42) == 42

    def test_resolve_full_input_map(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        resolved = resolver.resolve({
            "test_cases": "$parse_reqs.test_cases",
            "base_url": "$config.app_url",
            "threshold": "0.8",
        })
        assert resolved["test_cases"] == [{"id": "TC-001"}]
        assert resolved["base_url"] == "http://localhost:8080"
        assert resolved["threshold"] == "0.8"

    def test_missing_stage_raises(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        with pytest.raises(KeyError, match="nonexistent"):
            resolver.resolve_single("$nonexistent.key")

    def test_missing_config_path_raises(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        with pytest.raises(KeyError, match="bad_key"):
            resolver.resolve_single("$config.bad_key")
