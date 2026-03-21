"""
Test Classifier
===============
Assigns test_level and failure_type to generated API tests.
Validates test pyramid distribution (e2e should be < 20%).

This is separated from the generator so it can be reused by the
Stage 4 pipeline orchestrator for aggregate reporting.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from stlc_platform.core.contracts import APITestArtifact


# Test types → test levels
_LEVEL_MAP: Dict[str, str] = {
    "happy_path": "api",
    "auth": "api",
    "validation": "api",
    "boundary": "api",
    "schema_validation": "api",
    "crud_sequence": "integration",
    "e2e_flow": "e2e",
}

# Test types → default failure types
_FAILURE_TYPE_MAP: Dict[str, str] = {
    "happy_path": "app_bug",
    "auth": "app_bug",
    "validation": "app_bug",
    "boundary": "app_bug",
    "schema_validation": "app_bug",
    "crud_sequence": "app_bug",
    "e2e_flow": "app_bug",
}


class TestClassifier:
    """Classify generated API tests by level and failure type."""

    def classify_test_level(self, test_type: str) -> str:
        """
        Map a test type to a test pyramid level.

        Returns:
            "api", "integration", or "e2e".
        """
        return _LEVEL_MAP.get(test_type, "api")

    def classify_failure_type(self, test_type: str) -> str:
        """
        Map a test type to a default failure classification.

        Returns:
            "app_bug", "test_bug", or "env_issue".
        """
        return _FAILURE_TYPE_MAP.get(test_type, "app_bug")

    def validate_pyramid(
        self, tests: List[APITestArtifact]
    ) -> Dict[str, Any]:
        """
        Validate that the test distribution respects the test pyramid.

        Rules:
          - E2E tests should be < 20% of total tests.

        Returns:
            Dict with counts, percentages, and warnings.
        """
        if not tests:
            return {
                "total": 0,
                "distribution": {},
                "percentages": {},
                "warnings": [],
            }

        counts = Counter(t.test_level for t in tests)
        total = len(tests)
        percentages = {
            level: round(count / total * 100, 1)
            for level, count in counts.items()
        }

        warnings: List[str] = []
        e2e_pct = percentages.get("e2e", 0.0)
        if e2e_pct > 20.0:
            warnings.append(
                f"E2E tests are {e2e_pct}% of total — exceeds 20% guideline. "
                "Consider moving some tests to API or integration level."
            )

        return {
            "total": total,
            "distribution": dict(counts),
            "percentages": percentages,
            "warnings": warnings,
        }
