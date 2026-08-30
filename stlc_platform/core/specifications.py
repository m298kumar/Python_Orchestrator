"""Versioned runtime loader and deterministic gates for approved specifications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class LoadedSpecification:
    specification_id: str
    version: str
    status: str
    content: str
    path: Path


class SpecificationLoader:
    """Load configured Markdown specifications and verify approval metadata."""

    def __init__(self, config: Dict[str, Any], project_root: Path | None = None) -> None:
        self._config = config.get("specifications", {}) or {}
        self._root = project_root or Path(__file__).resolve().parents[2]
        self._cache: Dict[str, LoadedSpecification] = {}

    @property
    def enforce(self) -> bool:
        return bool(self._config.get("enforce", False))

    def load(self, kind: str) -> LoadedSpecification:
        if kind in self._cache:
            return self._cache[kind]
        raw_path = self._config.get(kind)
        if not raw_path:
            raise ValueError(f"No specification configured for '{kind}'")
        path = Path(raw_path)
        if not path.is_absolute():
            path = self._root / path
        content = path.read_text(encoding="utf-8")
        spec = LoadedSpecification(
            specification_id=self._field(content, "Specification ID"),
            version=self._field(content, "Version"),
            status=self._field(content, "Status"),
            content=content,
            path=path,
        )
        if self.enforce and spec.status.lower() != "approved":
            raise ValueError(f"Specification {spec.specification_id} is not approved")
        self._cache[kind] = spec
        return spec

    @staticmethod
    def _field(content: str, name: str) -> str:
        match = re.search(rf"\*\*{re.escape(name)}:\*\*\s*([^\r\n]+)", content)
        if not match:
            raise ValueError(f"Specification is missing '{name}' metadata")
        return match.group(1).strip()

    @staticmethod
    def validate_requirement(requirement: Any) -> List[str]:
        errors: List[str] = []
        for field in ("req_id", "title", "description"):
            if not str(getattr(requirement, field, "") or "").strip():
                errors.append(f"{field} is required")
        criteria = getattr(requirement, "acceptance_criteria", None) or []
        if not criteria:
            errors.append("at least one acceptance criterion is required")
        elif any(not str(ac).strip() for ac in criteria):
            errors.append("acceptance criteria must not be empty")
        return errors
