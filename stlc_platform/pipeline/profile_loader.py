"""
Execution Profile Loader
========================
Named profiles (smoke, targeted, regression) that filter which tests/requirements
get processed. Profiles are loaded from config/profiles/ YAML files and applied
by the orchestrator as filter criteria passed into agent configs.

Execution profiles control SCOPE (what gets processed).
Config profiles control BEHAVIOR (how things are processed).
These are orthogonal and combinable.

Usage:
    loader = ProfileLoader(profiles_dir=Path("config/profiles"))
    profile = loader.load("smoke")
    filtered = loader.apply_filter(profile, artifacts)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file. Returns empty dict if not found or PyYAML missing."""
    if not path.exists():
        return {}
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


@dataclass
class ExecutionProfile:
    """
    A named execution profile that controls what gets processed.

    Attributes:
        name: Profile identifier (e.g., "smoke", "targeted", "regression").
        description: Human-readable description.
        filters: Dict of filter criteria applied to artifacts.
            Supported keys:
            - priority: List[str] — keep only items with these priorities
            - test_level: List[str] — keep only these test levels
            - requirement_ids: List[str] — keep only these requirement IDs
            - tags: List[str] — keep only items with at least one of these tags
            - categories: List[str] — keep only these categories
        max_tests: Optional cap on total test output count.
    """

    name: str
    description: str = ""
    filters: Dict[str, Any] = field(default_factory=dict)
    max_tests: Optional[int] = None


class ProfileLoader:
    """Loads execution profiles from YAML files in config/profiles/."""

    def __init__(self, profiles_dir: Optional[Path] = None) -> None:
        self._profiles_dir = profiles_dir or Path("config/profiles")

    @property
    def profiles_dir(self) -> Path:
        return self._profiles_dir

    def load(self, profile_name: str) -> ExecutionProfile:
        """
        Load a profile by name from the profiles directory.

        Args:
            profile_name: Name of the profile (without .yaml extension).

        Returns:
            ExecutionProfile instance.

        Raises:
            FileNotFoundError: If the profile YAML file doesn't exist.
        """
        path = self._profiles_dir / f"{profile_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Profile '{profile_name}' not found at {path}")

        data = _load_yaml(path)
        return ExecutionProfile(
            name=data.get("name", profile_name),
            description=data.get("description", ""),
            filters=data.get("filters", {}),
            max_tests=data.get("max_tests"),
        )

    def list_profiles(self) -> List[str]:
        """Return names of all available profiles."""
        if not self._profiles_dir.is_dir():
            return []
        return sorted(f.stem for f in self._profiles_dir.glob("*.yaml"))

    def apply_filter(
        self,
        profile: ExecutionProfile,
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply profile filters to artifacts dict.

        Filters are applied to list-type values in the artifacts dict.
        Each item in the list is checked against the filter criteria.
        Items that don't match are removed.

        Supported artifact keys filtered:
        - requirements: filtered by priority, tags, category, requirement_ids
        - test_cases: filtered by priority, tags, test_level

        Non-list values and unrecognized keys pass through unchanged.
        If profile has no filters, returns artifacts unchanged.

        Args:
            profile: The execution profile to apply.
            artifacts: Dict of artifacts to filter.

        Returns:
            New dict with filtered artifacts.
        """
        if not profile.filters:
            return dict(artifacts)

        result = dict(artifacts)

        # Filter requirements
        if "requirements" in result and isinstance(result["requirements"], list):
            result["requirements"] = self._filter_items(
                result["requirements"], profile.filters, item_type="requirement"
            )

        # Filter test_cases
        if "test_cases" in result and isinstance(result["test_cases"], list):
            result["test_cases"] = self._filter_items(
                result["test_cases"], profile.filters, item_type="test_case"
            )
            # Apply max_tests cap
            if profile.max_tests is not None:
                result["test_cases"] = result["test_cases"][: profile.max_tests]

        return result

    def _filter_items(
        self,
        items: List[Any],
        filters: Dict[str, Any],
        item_type: str = "",
    ) -> List[Any]:
        """Filter a list of items based on profile criteria."""
        if not items or not filters:
            return list(items)

        filtered = []
        for item in items:
            if self._item_matches(item, filters, item_type):
                filtered.append(item)

        return filtered

    _FILTER_ATTR_MAP = {
        "priority": ("priority",),
        "test_level": ("test_level", "test_type"),
        "requirement_ids": ("req_id",),
        "categories": ("category",),
    }

    def _item_matches(
        self,
        item: Any,
        filters: Dict[str, Any],
        item_type: str = "",
    ) -> bool:
        for filter_key, attr_names in self._FILTER_ATTR_MAP.items():
            filter_values = filters.get(filter_key)
            if not filter_values:
                continue
            item_value = self._get_attr(item, attr_names[0], "")
            for attr_name in attr_names[1:]:
                if not item_value:
                    item_value = self._get_attr(item, attr_name, "")
            if item_value and item_value.lower() not in [v.lower() for v in filter_values]:
                return False

        tags_filter = filters.get("tags")
        if tags_filter:
            item_tags = self._get_attr(item, "tags", [])
            if item_tags and not any(t in item_tags for t in tags_filter):
                return False

        return True

    @staticmethod
    def _get_attr(item: Any, attr: str, default: Any = None) -> Any:
        """Get attribute from object or dict."""
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)
