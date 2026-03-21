"""
Skill File Loader
=================
Discovers and loads per-agent domain knowledge YAML files from config/skills/.

Skill files provide institutional knowledge that agents can use to improve
their output quality. Files are organized by category under common/ (always
loaded) and {domain}/ (loaded when the project domain matches).

Usage:
    loader = SkillLoader(skills_dir=Path("config/skills"), domain="ecommerce")
    context = loader.load_for_agent(agent.get_capabilities())
    # context is merged into the agent's config dict
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from stlc_platform.core.base_agent import AgentCapabilities


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file. Returns empty dict if file not found or PyYAML missing."""
    if not path.exists():
        return {}
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge overlay into base.

    - Dict values are merged recursively
    - List values are concatenated (overlay appended)
    - Scalar values in overlay overwrite base
    """
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    return result


class SkillLoader:
    """
    Discovers and loads skill files for agents.

    Directory structure:
        config/skills/
            common/
                coding_standards.yaml
                test_design_principles.yaml
            ecommerce/
                data_catalog.yaml
            healthcare/
                data_catalog.yaml
    """

    def __init__(
        self,
        skills_dir: Optional[Path] = None,
        domain: str = "",
    ) -> None:
        self._skills_dir = skills_dir or Path("config/skills")
        self._domain = domain.strip().lower().replace(" ", "_")

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    @property
    def domain(self) -> str:
        return self._domain

    def discover(self) -> Dict[str, List[Path]]:
        """
        Discover all skill files organized by category.

        Returns:
            Dict mapping category name -> list of YAML file paths.
            Categories are derived from filenames (without extension).
        """
        categories: Dict[str, List[Path]] = {}

        # Common skills (always loaded)
        common_dir = self._skills_dir / "common"
        if common_dir.is_dir():
            for f in sorted(common_dir.glob("*.yaml")):
                cat = f.stem
                categories.setdefault(cat, []).append(f)

        # Domain-specific skills (layered on top)
        if self._domain:
            domain_dir = self._skills_dir / self._domain
            if domain_dir.is_dir():
                for f in sorted(domain_dir.glob("*.yaml")):
                    cat = f.stem
                    categories.setdefault(cat, []).append(f)

        return categories

    def load_category(self, category: str) -> Dict[str, Any]:
        """
        Load and merge all skill files for a given category.

        Common files are loaded first, then domain files overlay on top.
        """
        result: Dict[str, Any] = {}

        # Load common
        common_path = self._skills_dir / "common" / f"{category}.yaml"
        if common_path.exists():
            result = _load_yaml(common_path)

        # Overlay domain-specific
        if self._domain:
            domain_path = self._skills_dir / self._domain / f"{category}.yaml"
            if domain_path.exists():
                domain_data = _load_yaml(domain_path)
                result = _deep_merge(result, domain_data)

        return result

    def load_for_agent(self, capabilities: AgentCapabilities) -> Dict[str, Any]:
        """
        Load all relevant skill files for an agent based on its required_skills.

        Args:
            capabilities: The agent's capabilities (must have required_skills).

        Returns:
            Dict with skill data keyed by category name.
            Returns empty dict if agent declares no required_skills.
        """
        required = getattr(capabilities, "required_skills", [])
        if not required:
            return {}

        skills_context: Dict[str, Any] = {}
        for category in required:
            data = self.load_category(category)
            if data:
                skills_context[category] = data

        return skills_context

    def list_categories(self) -> List[str]:
        """Return all available skill category names."""
        return sorted(self.discover().keys())
