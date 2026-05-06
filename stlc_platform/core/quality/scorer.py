"""
Test Case Quality Scorer
========================
Scores each generated test case on 5 dimensions (0.0-1.0) and recommends
an action: accept, regenerate, or fallback.

All scoring is deterministic — no LLM calls. This enables the quality gate
in the generator to decide whether to keep, retry, or synthesise.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from stlc_platform.core.contracts import TestCaseArtifact


def _load_scorer_heuristics_config():
    """Load scorer heuristics configuration from YAML file."""
    config_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "config",
        "test_generation_heuristics.yaml",
    )
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        generic_phrases = config.get(
            "generic_phrases",
            [
                "the system responds correctly",
                "the system behaves as expected",
                "the expected result is observed",
                "the action is performed",
                "perform the action",
                "trigger the feature",
                "verify the outcome",
                "check the result",
                "observe the result",
                "the test passes",
                "the test is successful",
                "complete the action",
                "do the action",
                "execute the test step",
                "the system works as intended",
                "ensure the system",
                "the system should",
                "appropriate message is displayed",
                "relevant data is shown",
                "proper validation occurs",
            ],
        )

        instruction_leak_patterns = config.get(
            "instruction_leak_patterns",
            [
                "chain-of-thought",
                "mentally answer",
                "before writing each step",
                "fill each field",
                "copy this exactly",
                "replace the example",
                "one sentence explaining",
                "be concrete",
                "no vague",
                "json",
                "```",
            ],
        )

        return {
            "generic_phrases": generic_phrases,
            "instruction_leak_patterns": instruction_leak_patterns,
        }
    except Exception as e:
        # Fallback to hardcoded values if config loading fails
        print(f"Warning: Failed to load scorer heuristics config: {e}. Using fallback values.")
        return {
            "generic_phrases": [
                "the system responds correctly",
                "the system behaves as expected",
                "the expected result is observed",
                "the action is performed",
                "perform the action",
                "trigger the feature",
                "verify the outcome",
                "check the result",
                "observe the result",
                "the test passes",
                "the test is successful",
                "complete the action",
                "do the action",
                "execute the test step",
                "the system works as intended",
                "ensure the system",
                "the system should",
                "appropriate message is displayed",
                "relevant data is shown",
                "proper validation occurs",
            ],
            "instruction_leak_patterns": [
                "chain-of-thought",
                "mentally answer",
                "before writing each step",
                "fill each field",
                "copy this exactly",
                "replace the example",
                "one sentence explaining",
                "be concrete",
                "no vague",
                "json",
                "```",
            ],
        }


# Load scorer heuristics configuration
_SCORER_HEURISTICS_CONFIG = _load_scorer_heuristics_config()
_GENERIC_PHRASES = _SCORER_HEURISTICS_CONFIG["generic_phrases"]
_INSTRUCTION_LEAK_PATTERNS = _SCORER_HEURISTICS_CONFIG["instruction_leak_patterns"]

_TRUNCATION_MARKERS = (":", "(", "{", "...", ",", "\\")


@dataclass
class QualityReport:
    """Result of scoring a single test case."""

    overall_score: float = 0.0
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    suggestion: str = "accept"  # "accept" | "regenerate" | "fallback"


@dataclass
class ScorerConfig:
    """Configurable thresholds and weights for the quality scorer."""

    accept_threshold: float = 0.65
    regenerate_threshold: float = 0.40
    max_regeneration_attempts: int = 2
    auto_example_threshold: float = 0.80
    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "coverage": 0.25,
            "clarity": 0.20,
            "executability": 0.20,
            "uniqueness": 0.15,
            "structural": 0.20,
        }
    )
    generic_phrases: Optional[List[str]] = None

    _REQUIRED_DIMENSIONS = {"coverage", "clarity", "executability", "uniqueness", "structural"}

    def __post_init__(self) -> None:
        """Validate config after construction."""
        # Ensure all 5 dimensions are present
        missing = self._REQUIRED_DIMENSIONS - set(self.weights.keys())
        if missing:
            raise ValueError(f"Missing weight dimensions: {missing}")

        # Normalize weights if they don't sum to ~1.0
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("Weight values must be positive and sum > 0")
        if not (0.95 <= total <= 1.05):
            # Auto-normalize instead of rejecting
            self.weights = {k: v / total for k, v in self.weights.items()}

        # Validate threshold ordering
        if self.regenerate_threshold > self.accept_threshold:
            raise ValueError(
                f"regenerate_threshold ({self.regenerate_threshold}) must be "
                f"<= accept_threshold ({self.accept_threshold})"
            )

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "ScorerConfig":
        """Build from a quality_gate config dict."""
        qg = cfg.get("quality_gate", {})
        if not qg:
            return cls()
        return cls(
            accept_threshold=qg.get("accept_threshold", 0.65),
            regenerate_threshold=qg.get("regenerate_threshold", 0.40),
            max_regeneration_attempts=qg.get("max_regeneration_attempts", 2),
            auto_example_threshold=qg.get("auto_example_threshold", 0.80),
            weights=qg.get("weights", cls.__dataclass_fields__["weights"].default_factory()),
            generic_phrases=qg.get("generic_phrases"),
        )


class TestCaseScorer:
    """Scores a test case across 5 quality dimensions."""

    def __init__(self, config: Optional[ScorerConfig] = None):
        self._config = config or ScorerConfig()
        self._generic_phrases = self._config.generic_phrases or _GENERIC_PHRASES

    @property
    def config(self) -> ScorerConfig:
        return self._config

    def score(
        self,
        tc: TestCaseArtifact,
        slot: Dict[str, str],
        requirement: Any,
        existing_tcs: Optional[List[TestCaseArtifact]] = None,
    ) -> QualityReport:
        """Score a test case and recommend an action.

        Args:
            tc: The test case to score.
            slot: Slot dict with target_ac, test_type, ac_type.
            requirement: Requirement object with acceptance_criteria, title, etc.
            existing_tcs: Previously generated TCs in this batch (for uniqueness).

        Returns:
            QualityReport with scores, issues, and suggestion.
        """
        issues: List[str] = []

        coverage = self._score_coverage(tc, slot, requirement, issues)
        clarity = self._score_clarity(tc, issues)
        executability = self._score_executability(tc, issues)
        uniqueness = self._score_uniqueness(tc, existing_tcs or [], issues)
        structural = self._score_structural(tc, issues)

        dimensions = {
            "coverage": coverage,
            "clarity": clarity,
            "executability": executability,
            "uniqueness": uniqueness,
            "structural": structural,
        }

        weights = self._config.weights
        overall = sum(dimensions[dim] * weights.get(dim, 0.0) for dim in dimensions)

        if overall >= self._config.accept_threshold:
            suggestion = "accept"
        elif overall >= self._config.regenerate_threshold:
            suggestion = "regenerate"
        else:
            suggestion = "fallback"

        return QualityReport(
            overall_score=round(overall, 3),
            dimension_scores={k: round(v, 3) for k, v in dimensions.items()},
            issues=issues,
            suggestion=suggestion,
        )

    # ── Dimension scorers ────────────────────────────────────────────────────

    def _score_coverage(
        self,
        tc: TestCaseArtifact,
        slot: Dict[str, str],
        requirement: Any,
        issues: List[str],
    ) -> float:
        """Does the TC reference the target AC and exercise the correct test_type?"""
        score = 1.0
        ac_text = slot.get("target_ac", "")
        test_type = slot.get("test_type", "")

        # Extract key terms from AC (words >= 4 chars, not stopwords)
        ac_terms = self._extract_key_terms(ac_text)
        if not ac_terms:
            return 0.5  # Can't evaluate without AC terms

        # Check how many AC terms appear in description + steps + GWT
        tc_text = self._get_tc_full_text(tc).lower()
        matched = sum(1 for term in ac_terms if term in tc_text)
        term_coverage = matched / len(ac_terms) if ac_terms else 0

        if term_coverage < 0.15:
            issues.append(
                f"TC does not reference target AC (only {matched}/{len(ac_terms)} key terms found)"
            )
            score -= 0.5
        elif term_coverage < 0.3:
            issues.append(f"Weak AC reference ({matched}/{len(ac_terms)} key terms)")
            score -= 0.25

        # Check test_type alignment
        if test_type == "negative":
            negative_indicators = [
                "invalid",
                "reject",
                "error",
                "fail",
                "denied",
                "block",
                "incorrect",
                "wrong",
                "missing",
                "without",
            ]
            if not any(ind in tc_text for ind in negative_indicators):
                issues.append("Negative test case lacks rejection/error indicators")
                score -= 0.25
        elif test_type == "edge_case":
            edge_indicators = [
                "boundary",
                "limit",
                "maximum",
                "minimum",
                "exact",
                "threshold",
                "zero",
                "empty",
                "overflow",
            ]
            if not any(ind in tc_text for ind in edge_indicators):
                issues.append("Edge case lacks boundary/limit indicators")
                score -= 0.15

        # Check expected_outcome references AC
        outcome_lower = tc.expected_outcome.lower() if tc.expected_outcome else ""
        outcome_terms = sum(1 for term in ac_terms if term in outcome_lower)
        if outcome_terms == 0 and ac_terms:
            issues.append("Expected outcome does not reference AC terms")
            score -= 0.1

        return max(0.0, score)

    def _score_clarity(
        self,
        tc: TestCaseArtifact,
        issues: List[str],
    ) -> float:
        """Are steps specific (named elements, data values) vs generic?"""
        score = 1.0

        # If there's barely any text, clarity is inherently low
        tc_text_lower = self._get_tc_full_text(tc).lower()
        if len(tc_text_lower.strip()) < 50:
            issues.append("Insufficient text content to assess clarity")
            return 0.2
        generic_count = sum(1 for phrase in self._generic_phrases if phrase in tc_text_lower)
        if generic_count >= 3:
            issues.append(f"Contains {generic_count} generic phrases")
            score -= 0.4
        elif generic_count >= 1:
            issues.append(f"Contains {generic_count} generic phrase(s)")
            score -= 0.15 * generic_count

        # Check GWT distinctness — given/when/then should not be identical
        gwt = [
            (tc.given or "").strip().lower(),
            (tc.when or "").strip().lower(),
            (tc.then or "").strip().lower(),
        ]
        gwt_non_empty = [g for g in gwt if g]
        if len(gwt_non_empty) >= 2 and len(set(gwt_non_empty)) < len(gwt_non_empty):
            issues.append("GWT clauses are not distinct from each other")
            score -= 0.3

        # Steps should contain concrete nouns (screen names, button names, field names)
        step_texts = [s.action for s in tc.steps]
        has_specific = any(
            re.search(
                r"(button|field|screen|page|menu|dropdown|checkbox|input|link|tab|icon|modal|dialog)",
                s,
                re.I,
            )
            for s in step_texts
        )
        if step_texts and not has_specific:
            issues.append("Steps lack specific UI element references")
            score -= 0.15

        # Check description is substantive
        if tc.description and len(tc.description) < 30:
            issues.append("Description is too brief")
            score -= 0.1

        return max(0.0, score)

    def _score_executability(
        self,
        tc: TestCaseArtifact,
        issues: List[str],
    ) -> float:
        """Are there enough non-trivial steps with verifiable results?"""
        score = 1.0

        # Step count
        step_count = len(tc.steps)
        if step_count < 2:
            issues.append(f"Only {step_count} step(s) — need at least 2")
            score -= 0.6
        elif step_count < 3:
            issues.append(f"Only {step_count} step(s) — need at least 3")
            score -= 0.4

        # Steps with expected_result
        steps_with_result = sum(
            1 for s in tc.steps if s.expected_result and len(s.expected_result.strip()) > 5
        )
        if step_count > 0:
            result_ratio = steps_with_result / step_count
            if result_ratio < 0.5:
                issues.append(f"Only {steps_with_result}/{step_count} steps have expected results")
                score -= 0.25

        # Preconditions should be actionable
        if not tc.preconditions or len(tc.preconditions.strip()) < 15:
            issues.append("Preconditions are missing or too brief")
            score -= 0.15

        # Steps should not all be identical
        if step_count >= 2:
            actions = [s.action.strip().lower()[:50] for s in tc.steps]
            if len(set(actions)) == 1:
                issues.append("All steps have identical actions")
                score -= 0.3

        return max(0.0, score)

    def _max_jaccard_similarity(
        self,
        target_terms: set,
        existing_tcs: List[TestCaseArtifact],
        extract_text: callable,
    ) -> float:
        """Compute maximum Jaccard similarity between target terms and existing TCs."""
        max_sim = 0.0
        for other in existing_tcs:
            other_text = extract_text(other)
            if not other_text:
                continue
            other_terms = set(self._tokenize(other_text))
            if not other_terms:
                continue
            intersection = target_terms & other_terms
            union = target_terms | other_terms
            jaccard = len(intersection) / len(union) if union else 0
            max_sim = max(max_sim, jaccard)
        return max_sim

    def _score_uniqueness(
        self,
        tc: TestCaseArtifact,
        existing_tcs: List[TestCaseArtifact],
        issues: List[str],
    ) -> float:
        """Is this TC sufficiently different from already-generated TCs?"""
        if not existing_tcs:
            return 1.0

        tc_desc = tc.description.lower().strip()
        if not tc_desc:
            return 0.5

        # Use term overlap (Jaccard similarity) as a lightweight proxy
        tc_terms = set(self._tokenize(tc_desc))
        if not tc_terms:
            return 0.5

        max_similarity = self._max_jaccard_similarity(
            tc_terms, existing_tcs, lambda o: o.description.lower().strip()
        )

        # Also check step-level similarity for near-duplicates
        tc_steps_text = " ".join(s.action.lower() for s in tc.steps)
        tc_step_terms = set(self._tokenize(tc_steps_text))

        if tc_step_terms:
            step_sim = self._max_jaccard_similarity(
                tc_step_terms,
                existing_tcs,
                lambda o: " ".join(s.action.lower() for s in o.steps),
            )
            max_similarity = max(max_similarity, step_sim)

        if max_similarity > 0.85:
            issues.append(f"Near-duplicate of existing TC (similarity: {max_similarity:.0%})")
            return 0.1
        elif max_similarity > 0.70:
            issues.append(f"High overlap with existing TC (similarity: {max_similarity:.0%})")
            return 0.4
        elif max_similarity > 0.55:
            return 0.7

        return 1.0

    def _score_structural(
        self,
        tc: TestCaseArtifact,
        issues: List[str],
    ) -> float:
        """All fields present, no truncation markers, no instruction leakage."""
        score = 1.0

        # Required fields presence and minimum length
        field_checks = {
            "description": (tc.description, 10),
            "preconditions": (tc.preconditions, 10),
            "expected_outcome": (tc.expected_outcome, 5),
            "given": (tc.given, 5),
            "when": (tc.when, 5),
            "then": (tc.then, 5),
        }
        missing = []
        for fname, (fval, min_len) in field_checks.items():
            if not fval or len(fval.strip()) < min_len:
                missing.append(fname)

        if missing:
            issues.append(f"Missing or too short: {', '.join(missing)}")
            score -= 0.1 * len(missing)

        # Truncation detection
        all_text = self._get_tc_full_text(tc)
        truncated = False
        if all_text.rstrip().endswith(_TRUNCATION_MARKERS):
            truncated = True
        if all_text.count("(") > all_text.count(")"):
            truncated = True
        if all_text.count("'") % 2 == 1:
            truncated = True
        if truncated:
            issues.append("Truncated output detected")
            score -= 0.3

        # Instruction leakage detection
        all_lower = all_text.lower()
        leaked = [pat for pat in _INSTRUCTION_LEAK_PATTERNS if pat in all_lower]
        if leaked:
            issues.append(f"Instruction leakage: {', '.join(leaked[:3])}")
            score -= 0.3

        # Check for hollow/empty steps
        empty_steps = sum(1 for s in tc.steps if not s.action.strip() or len(s.action.strip()) < 5)
        if empty_steps > 0:
            issues.append(f"{empty_steps} hollow/empty step(s)")
            score -= 0.15 * min(empty_steps, 3)

        return max(0.0, score)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_key_terms(text: str) -> List[str]:
        """Extract meaningful terms (>= 4 chars, not stopwords) from text."""
        stopwords = {
            "the",
            "this",
            "that",
            "with",
            "from",
            "have",
            "will",
            "shall",
            "should",
            "must",
            "been",
            "being",
            "were",
            "when",
            "then",
            "than",
            "they",
            "them",
            "their",
            "there",
            "here",
            "what",
            "which",
            "where",
            "into",
            "also",
            "each",
            "only",
            "such",
            "same",
            "more",
            "some",
            "upon",
            "does",
            "your",
            "after",
            "before",
            "between",
            "through",
            "about",
            "given",
            "able",
            "user",
            "system",
        }
        words = re.findall(r"[a-z]{4,}", text.lower())
        return [w for w in words if w not in stopwords]

    @staticmethod
    def _get_tc_full_text(tc: TestCaseArtifact) -> str:
        """Concatenate all text fields of a TC for analysis."""
        parts = [
            tc.description or "",
            tc.preconditions or "",
            tc.expected_outcome or "",
            tc.given or "",
            tc.when or "",
            tc.then or "",
        ]
        for step in tc.steps:
            parts.append(step.action or "")
            parts.append(step.expected_result or "")
        return " ".join(parts)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace tokenizer with minimum length filter."""
        return [w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if len(w) >= 3]
