"""
Coverage Tracker
================
Analyzes test case coverage against requirement acceptance criteria.
Identifies uncovered ACs, weak coverage (single TC or low quality),
and provides a coverage report for pipeline decision-making.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

# Stopwords excluded from keyword matching (aligned with failure_classifier.py)
_STOPWORDS: Set[str] = {
    "the",
    "and",
    "for",
    "that",
    "this",
    "with",
    "from",
    "will",
    "shall",
    "must",
    "should",
    "when",
    "then",
    "given",
    "user",
    "system",
}

# Minimum keyword overlap ratio for a TC to "cover" an AC
_DEFAULT_MATCH_THRESHOLD = 0.5


def _load_coverage_config() -> Dict[str, Any]:
    """Load coverage settings from test_generation_heuristics.yaml."""
    from pathlib import Path

    cfg_path = Path("config/test_generation_heuristics.yaml")
    if not cfg_path.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return data.get("coverage", {})
    except Exception:
        return {}


@dataclass
class CoverageEntry:
    """Coverage data for a single acceptance criterion."""

    req_id: str
    ac_index: int
    ac_text: str
    test_case_ids: List[str] = field(default_factory=list)
    coverage_types: Set[str] = field(default_factory=set)  # positive, negative, edge_case
    avg_quality_score: float = 0.0


@dataclass
class CoverageReport:
    """Overall coverage analysis result."""

    entries: List[CoverageEntry] = field(default_factory=list)
    overall_coverage: float = 0.0  # % of ACs with >= 1 TC
    weak_entries: List[CoverageEntry] = field(default_factory=list)  # only 1 TC or low quality
    uncovered_entries: List[CoverageEntry] = field(default_factory=list)  # 0 TCs
    total_requirements: int = 0
    total_acs: int = 0
    total_test_cases: int = 0


class CoverageTracker:
    """
    Analyzes test case coverage against requirement acceptance criteria.

    Usage:
        tracker = CoverageTracker(weak_quality_threshold=0.5)
        report = tracker.analyze(requirements, test_cases)
        if report.uncovered_entries:
            # Re-generate for uncovered ACs
    """

    def __init__(
        self,
        weak_quality_threshold: float | None = None,
        min_coverage_types: int | None = None,
        match_threshold: float | None = None,
    ):
        cfg = _load_coverage_config()
        self._match_threshold = (
            match_threshold
            if match_threshold is not None
            else float(cfg.get("match_threshold", _DEFAULT_MATCH_THRESHOLD))
        )
        self._weak_quality_threshold = (
            weak_quality_threshold
            if weak_quality_threshold is not None
            else float(cfg.get("weak_quality_threshold", 0.5))
        )
        self._min_coverage_types = (
            min_coverage_types
            if min_coverage_types is not None
            else int(cfg.get("min_coverage_types", 1))
        )

    def _build_ac_entry(
        self,
        req_id: str,
        ac_idx: int,
        ac_text: str,
        matching_tcs: List[Any],
    ) -> CoverageEntry:
        """Build a CoverageEntry for a single acceptance criterion."""
        entry = CoverageEntry(req_id=req_id, ac_index=ac_idx, ac_text=ac_text)
        quality_scores: List[float] = []
        for tc in matching_tcs:
            if self._match_tc_to_ac(tc, ac_text):
                entry.test_case_ids.append(getattr(tc, "tc_id", ""))
                test_type = getattr(tc, "test_type", "").lower()
                if test_type:
                    entry.coverage_types.add(test_type)
                quality_scores.append(getattr(tc, "quality_score", 0.0))
        if quality_scores:
            entry.avg_quality_score = sum(quality_scores) / len(quality_scores)
        return entry

    def _classify_entries(self, report: CoverageReport) -> int:
        """Classify entries into uncovered/weak and return covered count."""
        covered_count = 0
        for entry in report.entries:
            if not entry.test_case_ids:
                report.uncovered_entries.append(entry)
            else:
                covered_count += 1
                if (
                    len(entry.test_case_ids) == 1
                    or entry.avg_quality_score < self._weak_quality_threshold
                ):
                    report.weak_entries.append(entry)
        return covered_count

    def analyze(
        self,
        requirements: List[Any],
        test_cases: List[Any],
    ) -> CoverageReport:
        """
        Analyze coverage of requirements by test cases.

        Matching strategy:
        1. Match TC.req_id to requirement.req_id
        2. For each AC in the requirement, check if any TC references it
           (using keyword overlap between AC text and TC description/steps/GWT)

        Args:
            requirements: List of requirement objects with req_id, acceptance_criteria
            test_cases: List of TestCaseArtifact objects with req_id, quality_score, test_type

        Returns:
            CoverageReport with entries, coverage %, weak/uncovered lists
        """
        report = CoverageReport(
            total_requirements=len(requirements),
            total_test_cases=len(test_cases),
        )

        if not requirements:
            return report

        # Group test cases by req_id for efficient lookup
        tc_by_req: Dict[str, List[Any]] = {}
        for tc in test_cases:
            rid = getattr(tc, "req_id", "")
            tc_by_req.setdefault(rid, []).append(tc)

        all_entries: List[CoverageEntry] = []

        for req in requirements:
            req_id = getattr(req, "req_id", "")
            acs = getattr(req, "acceptance_criteria", []) or []
            matching_tcs = tc_by_req.get(req_id, [])

            for ac_idx, ac_text in enumerate(acs):
                entry = self._build_ac_entry(req_id, ac_idx, ac_text, matching_tcs)
                all_entries.append(entry)

        report.entries = all_entries
        report.total_acs = len(all_entries)

        covered_count = self._classify_entries(report)
        report.overall_coverage = (covered_count / len(all_entries) * 100.0) if all_entries else 0.0

        logger.info(
            "Coverage analysis: %.1f%% (%d/%d ACs covered), %d weak, %d uncovered",
            report.overall_coverage,
            covered_count,
            report.total_acs,
            len(report.weak_entries),
            len(report.uncovered_entries),
        )

        return report

    def _match_tc_to_ac(self, tc: Any, ac_text: str) -> bool:
        """Check if a test case covers a specific acceptance criterion using keyword overlap."""
        ac_terms = self._extract_key_terms(ac_text)
        if not ac_terms:
            # AC too short / no meaningful terms — consider it covered by any matching TC
            return True

        tc_text = self._extract_tc_text(tc)
        tc_terms = self._extract_key_terms(tc_text)

        if not tc_terms:
            return False

        overlap = ac_terms & tc_terms
        ratio = len(overlap) / len(ac_terms)
        return ratio >= self._match_threshold

    def _extract_tc_text(self, tc: Any) -> str:
        """Extract all text from a test case for matching."""
        parts: List[str] = []

        for attr in ("title", "description", "expected_outcome", "given", "when", "then"):
            val = getattr(tc, attr, "")
            if val:
                parts.append(val)

        # Extract step actions and expected results
        steps = getattr(tc, "steps", []) or []
        for step in steps:
            action = getattr(step, "action", "")
            expected = getattr(step, "expected_result", "")
            if action:
                parts.append(action)
            if expected:
                parts.append(expected)

        return " ".join(parts)

    def _extract_key_terms(self, text: str) -> Set[str]:
        """Extract meaningful terms (4+ chars, not stopwords) from text."""
        return {
            word for word in re.findall(r"[a-zA-Z]{4,}", text.lower()) if word not in _STOPWORDS
        }
