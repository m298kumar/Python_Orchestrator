"""
Tests for config profile merging — deep_merge and load_config_yaml.
"""

import pytest
from stlc_platform.core.config_loader import deep_merge, load_config_yaml


class TestDeepMerge:
    def test_simple_overlay(self):
        base = {"a": 1, "b": 2}
        overlay = {"b": 99, "c": 3}
        result = deep_merge(base, overlay)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_nested_dict_preserved(self):
        base = {"llm": {"provider": "ollama", "model": "phi4", "temperature": 0.6}}
        overlay = {"llm": {"model": "gpt-4o"}}
        result = deep_merge(base, overlay)
        assert result["llm"]["provider"] == "ollama"  # preserved
        assert result["llm"]["model"] == "gpt-4o"  # overridden
        assert result["llm"]["temperature"] == 0.6  # preserved

    def test_deeply_nested_merge(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        overlay = {"a": {"b": {"d": 99, "e": 3}}}
        result = deep_merge(base, overlay)
        assert result == {"a": {"b": {"c": 1, "d": 99, "e": 3}}}

    def test_overlay_replaces_non_dict_with_dict(self):
        base = {"a": "string"}
        overlay = {"a": {"nested": True}}
        result = deep_merge(base, overlay)
        assert result == {"a": {"nested": True}}

    def test_empty_base(self):
        result = deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_overlay(self):
        result = deep_merge({"a": 1}, {})
        assert result == {"a": 1}

    def test_original_not_mutated(self):
        base = {"a": {"b": 1}}
        overlay = {"a": {"c": 2}}
        deep_merge(base, overlay)
        assert "c" not in base["a"]


class TestLoadConfigYaml:
    def test_base_config_loads(self):
        """Base config should load without a profile."""
        cfg = load_config_yaml()
        assert "llm" in cfg
        assert "project" in cfg

    def test_missing_profile_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            load_config_yaml(profile="nonexistent")

    def test_web_profile_overlays(self):
        """Web profile should modify crawler settings."""
        cfg = load_config_yaml(profile="web")
        assert cfg["crawler"]["max_depth"] == 5
        assert cfg["crawler"]["max_pages"] == 200
        # Base config keys should still be present
        assert "llm" in cfg
        assert "chromadb" in cfg

    def test_api_profile_overlays(self):
        """API profile should set platform to api."""
        cfg = load_config_yaml(profile="api")
        assert cfg["project"]["tech_stack"]["platform"] == "api"
        assert cfg["crawler"]["max_depth"] == 0
        # Unchanged keys preserved
        assert "llm" in cfg

    def test_profile_preserves_unmodified_keys(self):
        """Profile overlay must not remove keys not mentioned in overlay."""
        base = load_config_yaml()
        with_profile = load_config_yaml(profile="web")
        # chromadb not mentioned in web profile, should be identical
        assert with_profile["chromadb"] == base["chromadb"]
