"""
Tests for ProfileLoader — execution profile loading and artifact filtering.
"""

import pytest
from pathlib import Path
from dataclasses import dataclass

from stlc_platform.pipeline.profile_loader import (
    ProfileLoader,
    ExecutionProfile,
)


# ── Profile Loading Tests ─────────────────────────────────────────────────────


class TestProfileLoading:
    def test_load_smoke_profile(self, tmp_path):
        (tmp_path / "smoke.yaml").write_text(
            "name: smoke\n"
            "description: Critical path\n"
            "filters:\n"
            "  priority:\n"
            "    - critical\n"
            "    - high\n"
            "max_tests: 20\n"
        )
        loader = ProfileLoader(profiles_dir=tmp_path)
        profile = loader.load("smoke")
        assert profile.name == "smoke"
        assert profile.filters["priority"] == ["critical", "high"]
        assert profile.max_tests == 20

    def test_load_regression_no_filters(self, tmp_path):
        (tmp_path / "regression.yaml").write_text(
            "name: regression\ndescription: Full\nfilters: {}\n"
        )
        loader = ProfileLoader(profiles_dir=tmp_path)
        profile = loader.load("regression")
        assert profile.filters == {}
        assert profile.max_tests is None

    def test_load_missing_profile_raises(self, tmp_path):
        loader = ProfileLoader(profiles_dir=tmp_path)
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            loader.load("nonexistent")

    def test_list_profiles(self, tmp_path):
        (tmp_path / "alpha.yaml").write_text("name: alpha\n")
        (tmp_path / "beta.yaml").write_text("name: beta\n")
        loader = ProfileLoader(profiles_dir=tmp_path)
        assert loader.list_profiles() == ["alpha", "beta"]

    def test_list_profiles_empty_dir(self, tmp_path):
        loader = ProfileLoader(profiles_dir=tmp_path)
        assert loader.list_profiles() == []


# ── Profile Filtering Tests ──────────────────────────────────────────────────


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    priority: str = "High"
    category: str = "Functional"
    tags: list = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class MockTestCase:
    tc_id: str = "TC-001"
    req_id: str = "REQ-001"
    priority: str = "High"
    test_type: str = "functional"
    tags: list = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class TestProfileFiltering:
    def test_priority_filter(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["critical", "high"]},
        )
        artifacts = {
            "requirements": [
                MockRequirement(req_id="R1", priority="High"),
                MockRequirement(req_id="R2", priority="Low"),
                MockRequirement(req_id="R3", priority="Critical"),
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["requirements"]) == 2
        assert all(
            r.priority.lower() in ("high", "critical")
            for r in filtered["requirements"]
        )

    def test_requirement_id_filter(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="targeted",
            filters={"requirement_ids": ["REQ-001", "REQ-003"]},
        )
        artifacts = {
            "requirements": [
                MockRequirement(req_id="REQ-001"),
                MockRequirement(req_id="REQ-002"),
                MockRequirement(req_id="REQ-003"),
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        ids = [r.req_id for r in filtered["requirements"]]
        assert ids == ["REQ-001", "REQ-003"]

    def test_tags_filter(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="tagged",
            filters={"tags": ["auth"]},
        )
        artifacts = {
            "test_cases": [
                MockTestCase(tc_id="T1", tags=["auth", "login"]),
                MockTestCase(tc_id="T2", tags=["checkout"]),
                MockTestCase(tc_id="T3", tags=["auth"]),
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["test_cases"]) == 2

    def test_max_tests_cap(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["high"]},
            max_tests=2,
        )
        artifacts = {
            "test_cases": [
                MockTestCase(tc_id=f"T{i}", priority="High")
                for i in range(10)
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["test_cases"]) == 2

    def test_empty_filter_passes_everything(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(name="regression", filters={})
        artifacts = {
            "requirements": [MockRequirement() for _ in range(5)],
            "test_cases": [MockTestCase() for _ in range(3)],
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["requirements"]) == 5
        assert len(filtered["test_cases"]) == 3

    def test_non_list_values_pass_through(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["high"]},
        )
        artifacts = {
            "config": {"key": "value"},
            "count": 42,
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert filtered["config"] == {"key": "value"}
        assert filtered["count"] == 42

    def test_dict_items_filtered(self):
        """Test filtering with dict-based items instead of objects."""
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["high"]},
        )
        artifacts = {
            "requirements": [
                {"req_id": "R1", "priority": "High"},
                {"req_id": "R2", "priority": "Low"},
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["requirements"]) == 1
        assert filtered["requirements"][0]["req_id"] == "R1"

    def test_category_filter(self):
        loader = ProfileLoader()
        profile = ExecutionProfile(
            name="functional_only",
            filters={"categories": ["Functional"]},
        )
        artifacts = {
            "requirements": [
                MockRequirement(req_id="R1", category="Functional"),
                MockRequirement(req_id="R2", category="Non-Functional"),
            ]
        }
        filtered = loader.apply_filter(profile, artifacts)
        assert len(filtered["requirements"]) == 1


class TestProfileLoaderWithRealFiles:
    """Tests against the actual config/profiles/ directory."""

    def test_real_smoke_profile_exists(self):
        loader = ProfileLoader(profiles_dir=Path("config/profiles"))
        profiles = loader.list_profiles()
        assert "smoke" in profiles
        assert "regression" in profiles
        assert "targeted" in profiles

    def test_real_smoke_profile_loads(self):
        loader = ProfileLoader(profiles_dir=Path("config/profiles"))
        profile = loader.load("smoke")
        assert profile.name == "smoke"
        assert "priority" in profile.filters
