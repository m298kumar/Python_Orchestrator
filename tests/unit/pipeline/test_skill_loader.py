"""
Tests for SkillLoader — domain knowledge skill file discovery and loading.
"""

import pytest
from pathlib import Path

from stlc_platform.pipeline.skill_loader import SkillLoader, _deep_merge
from stlc_platform.core.base_agent import AgentCapabilities


# ── deep_merge tests ──────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_scalar_overlay(self):
        base = {"a": 1, "b": 2}
        overlay = {"b": 99}
        result = _deep_merge(base, overlay)
        assert result == {"a": 1, "b": 99}

    def test_nested_dict_merge(self):
        base = {"x": {"a": 1, "b": 2}}
        overlay = {"x": {"b": 99, "c": 3}}
        result = _deep_merge(base, overlay)
        assert result == {"x": {"a": 1, "b": 99, "c": 3}}

    def test_list_concatenation(self):
        base = {"tags": ["a", "b"]}
        overlay = {"tags": ["c"]}
        result = _deep_merge(base, overlay)
        assert result == {"tags": ["a", "b", "c"]}

    def test_new_key_added(self):
        base = {"a": 1}
        overlay = {"b": 2}
        result = _deep_merge(base, overlay)
        assert result == {"a": 1, "b": 2}

    def test_empty_overlay(self):
        base = {"a": 1}
        result = _deep_merge(base, {})
        assert result == {"a": 1}


# ── SkillLoader tests ────────────────────────────────────────────────────────


class TestSkillLoaderDiscover:
    def test_discovers_common_files(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "coding_standards.yaml").write_text("naming: snake_case\n")
        (common / "test_design.yaml").write_text("pyramid: unit\n")

        loader = SkillLoader(skills_dir=tmp_path)
        categories = loader.discover()
        assert "coding_standards" in categories
        assert "test_design" in categories
        assert len(categories["coding_standards"]) == 1

    def test_discovers_domain_files(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "data_catalog.yaml").write_text("common: true\n")

        domain = tmp_path / "ecommerce"
        domain.mkdir()
        (domain / "data_catalog.yaml").write_text("domain: ecommerce\n")

        loader = SkillLoader(skills_dir=tmp_path, domain="ecommerce")
        categories = loader.discover()
        assert "data_catalog" in categories
        # Both common and domain files
        assert len(categories["data_catalog"]) == 2

    def test_empty_dir_returns_empty(self, tmp_path):
        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.discover() == {}

    def test_missing_dir_returns_empty(self, tmp_path):
        loader = SkillLoader(skills_dir=tmp_path / "nonexistent")
        assert loader.discover() == {}


class TestSkillLoaderLoad:
    def test_load_category_common_only(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "coding_standards.yaml").write_text(
            "naming:\n  variables: snake_case\n  classes: PascalCase\n"
        )

        loader = SkillLoader(skills_dir=tmp_path)
        data = loader.load_category("coding_standards")
        assert data["naming"]["variables"] == "snake_case"

    def test_load_category_domain_overlays_common(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "data_catalog.yaml").write_text(
            "entities:\n  user:\n    fields: [email, name]\n"
        )

        domain = tmp_path / "ecommerce"
        domain.mkdir()
        (domain / "data_catalog.yaml").write_text(
            "entities:\n  product:\n    fields: [sku, price]\n"
        )

        loader = SkillLoader(skills_dir=tmp_path, domain="ecommerce")
        data = loader.load_category("data_catalog")
        # Both user (from common) and product (from domain) should exist
        assert "user" in data["entities"]
        assert "product" in data["entities"]

    def test_load_missing_category_returns_empty(self, tmp_path):
        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.load_category("nonexistent") == {}


class TestSkillLoaderForAgent:
    def test_loads_matching_skills(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "coding_standards.yaml").write_text("naming: snake_case\n")
        (common / "test_design.yaml").write_text("pyramid: unit\n")

        caps = AgentCapabilities(
            agent_id="test_agent",
            agent_version="1.0",
            required_skills=["coding_standards"],
        )

        loader = SkillLoader(skills_dir=tmp_path)
        context = loader.load_for_agent(caps)
        assert "coding_standards" in context
        assert "test_design" not in context

    def test_empty_required_skills_returns_empty(self, tmp_path):
        caps = AgentCapabilities(
            agent_id="test_agent",
            agent_version="1.0",
            required_skills=[],
        )
        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.load_for_agent(caps) == {}

    def test_no_required_skills_attr_returns_empty(self, tmp_path):
        """Backward compat: old capabilities without required_skills."""
        caps = AgentCapabilities(
            agent_id="test_agent",
            agent_version="1.0",
        )
        loader = SkillLoader(skills_dir=tmp_path)
        assert loader.load_for_agent(caps) == {}

    def test_list_categories(self, tmp_path):
        common = tmp_path / "common"
        common.mkdir()
        (common / "a.yaml").write_text("x: 1\n")
        (common / "b.yaml").write_text("y: 2\n")

        loader = SkillLoader(skills_dir=tmp_path)
        cats = loader.list_categories()
        assert cats == ["a", "b"]


class TestSkillLoaderWithRealFiles:
    """Tests against the actual config/skills/ directory."""

    def test_real_common_skills_exist(self):
        loader = SkillLoader(skills_dir=Path("config/skills"))
        categories = loader.discover()
        assert "coding_standards" in categories
        assert "test_design_principles" in categories

    def test_real_ecommerce_domain(self):
        loader = SkillLoader(skills_dir=Path("config/skills"), domain="ecommerce")
        data = loader.load_category("data_catalog")
        assert "entities" in data
        assert "product" in data["entities"]
