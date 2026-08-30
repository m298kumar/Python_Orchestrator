"""Unit tests for the Artifact Resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        resolved = resolver.resolve(
            {
                "test_cases": "$parse_reqs.test_cases",
                "base_url": "$config.app_url",
                "threshold": "0.8",
            }
        )
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

    def test_runtime_vector_store_is_cached(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        vector_store = MagicMock()

        with patch.object(resolver, "_create_vector_store", return_value=vector_store) as create:
            first = resolver.resolve_single("$runtime.vector_store")
            second = resolver.resolve_single("$runtime.vector_store")

        assert first is vector_store
        assert second is vector_store
        create.assert_called_once_with()

    def test_feedback_reuses_cached_vector_store(self, store_with_data, config):
        resolver = ArtifactResolver(store_with_data, config)
        vector_store = MagicMock()
        feedback_store = MagicMock()

        with (
            patch.object(resolver, "_create_vector_store", return_value=vector_store),
            patch(
                "stlc_platform.pipeline.feedback_store.FeedbackStore",
                return_value=feedback_store,
            ) as feedback_cls,
        ):
            assert resolver.resolve_single("$runtime.vector_store") is vector_store
            assert resolver.resolve_single("$runtime.feedback_store") is feedback_store

        feedback_cls.assert_called_once()
        assert feedback_cls.call_args.kwargs["chroma_store"] is vector_store
