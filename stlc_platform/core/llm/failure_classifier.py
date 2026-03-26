"""
LLM Failure Classifier
======================
Classifies LLM output failures into categories and recommends prompt
adaptation strategies. Used by the quality-gated generation loop to
make intelligent retry decisions instead of blind retries.

Failure types:
  - TRUNCATION: JSON cut off mid-field (repair_truncated_json had to close brackets)
  - HOLLOW: Schema-valid but empty/generic content
  - OFF_TOPIC: Response doesn't reference the target acceptance criterion
  - REPETITIVE: Same phrases repeated across steps or GWT clauses
  - SCHEMA_VIOLATION: Missing required fields or wrong types
  - INSTRUCTION_LEAKAGE: Prompt instructions appear in the response

Each failure type maps to a specific prompt adaptation strategy.
"""

from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


class FailureType(Enum):
    """Categories of LLM output failures."""

    TRUNCATION = "truncation"
    HOLLOW = "hollow"
    OFF_TOPIC = "off_topic"
    REPETITIVE = "repetitive"
    SCHEMA_VIOLATION = "schema_violation"
    INSTRUCTION_LEAKAGE = "instruction_leakage"


@dataclass
class FailureClassification:
    """Result of classifying an LLM failure."""

    failure_type: FailureType
    confidence: float  # 0.0 - 1.0
    details: str  # human-readable explanation
    adaptation: str  # recommended prompt change


# ── Instruction leakage patterns ────────────────────────────────────────────

_LEAKAGE_PATTERNS: List[str] = [
    "chain-of-thought",
    "mentally answer",
    "before writing each step",
    "think step by step",
    "fill each field below",
    "mandatory title",
    "copy this exactly",
    "do not copy the field label",
    "write test case",
    "acceptance criterion",
    "gherkin section",
    "target acceptance criterion",
]

# ── Generic / hollow phrases ────────────────────────────────────────────────

_HOLLOW_INDICATORS: List[str] = [
    "the system responds correctly",
    "the system behaves as expected",
    "perform the action",
    "the action is performed",
    "verify the outcome",
    "observe the result",
    "check the result",
    "the test passes",
    "execute the test step",
    "the system works",
    "appropriate message",
    "relevant data",
    "proper validation",
]

# Precompiled regex for hollow phrase matching (avoids O(N×M) per-field loop)
_HOLLOW_PATTERN = re.compile("|".join(re.escape(p) for p in _HOLLOW_INDICATORS))

# Stopwords for AC term extraction (module-level constant, not recreated per call)
_STOPWORDS: Set[str] = {
    "the", "and", "for", "that", "this", "with", "from", "will",
    "shall", "must", "should", "when", "then", "given", "user", "system",
}

# Text fields to check for content quality (shared across multiple checks)
_TEXT_FIELDS = ("description", "preconditions", "expected_outcome", "given", "when", "then")

# ── Prompt adaptation instructions per failure type ────────────────────────

_ADAPTATION_INSTRUCTIONS = {
    FailureType.TRUNCATION: (
        "\n\nIMPORTANT: Keep your response CONCISE. Use short sentences. "
        "Do not exceed 3 steps. Each field should be 1-2 sentences maximum. "
        "Ensure the JSON is complete and properly closed."
    ),
    FailureType.HOLLOW: (
        "\n\nIMPORTANT: DO NOT leave fields empty or use generic phrases. "
        "Every field must contain SPECIFIC content derived from the acceptance "
        "criterion. Name exact UI elements, data values, and error messages. "
        "Generic phrases like 'the system responds correctly' are NOT acceptable."
    ),
    FailureType.REPETITIVE: (
        "\n\nIMPORTANT: Each step MUST be UNIQUE. Do not repeat the same "
        "action or expected result across steps. Each step should test a "
        "different aspect of the acceptance criterion. "
        "Given/When/Then must each be distinct from each other."
    ),
    FailureType.SCHEMA_VIOLATION: (
        "\n\nIMPORTANT: Your response MUST be valid JSON with ALL required fields: "
        "title, description, preconditions, test_type, priority, given, when, then, "
        "steps (array of {action, expected_result}), expected_outcome, tags, component. "
        "Do not omit any field."
    ),
    FailureType.INSTRUCTION_LEAKAGE: (
        "\n\nIMPORTANT: DO NOT include any of these instructions in your response. "
        "Your response should contain ONLY the test case data, not meta-instructions "
        "about how to write it."
    ),
}


class FailureClassifier:
    """
    Classifies LLM output failures and recommends adaptations.

    Usage:
        classifier = FailureClassifier()
        result = classifier.classify(raw_response, parsed_tc, slot, requirement)
        if result:
            adapted_prompt = classifier.adapt_prompt(original_prompt, result)
    """

    def classify(
        self,
        raw_response: str,
        parsed_tc: Optional[Dict[str, Any]],
        slot: Dict[str, Any],
        requirement: Any,
    ) -> Optional[FailureClassification]:
        """
        Classify an LLM output failure.

        Args:
            raw_response: The raw string from the LLM.
            parsed_tc: The parsed test case dict (None if parsing failed).
            slot: The slot dict with test_type, target_ac, etc.
            requirement: The requirement object.

        Returns:
            FailureClassification if a problem is detected, None if output is OK.
        """
        # Check in priority order — return the first (most severe) failure found
        checks = [
            self._check_truncation,
            self._check_schema_violation,
            self._check_instruction_leakage,
            self._check_hollow,
            self._check_off_topic,
            self._check_repetitive,
        ]

        for check in checks:
            result = check(raw_response, parsed_tc, slot, requirement)
            if result:
                return result

        return None

    def adapt_prompt(
        self,
        original_prompt: str,
        classification: FailureClassification,
        slot: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Adapt the prompt based on the failure classification.

        Args:
            original_prompt: The original prompt text.
            classification: The failure classification result.
            slot: Optional slot dict (needed for OFF_TOPIC to inject AC text).

        Returns the modified prompt with failure-specific instructions appended.
        """
        ft = classification.failure_type

        # OFF_TOPIC needs dynamic AC injection, handle separately
        if ft == FailureType.OFF_TOPIC:
            ac = (slot or {}).get("target_ac", "")
            return (
                original_prompt
                + f"\n\nCRITICAL: Your response MUST verify this specific criterion:\n"
                f"  \"{ac}\"\n"
                "Reference this criterion in your description, steps, and expected outcome. "
                "Do NOT generate a test for a different requirement."
            )

        # All other types use static instruction text from dispatch table
        instruction = _ADAPTATION_INSTRUCTIONS.get(ft)
        if instruction:
            return original_prompt + instruction

        return original_prompt

    # ── Individual failure checks ───────────────────────────────────────────

    def _check_truncation(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect JSON truncation (unclosed brackets, cut-off strings)."""
        if not raw or not raw.strip():
            return None

        stripped = raw.strip()

        # Count open/close brackets
        open_braces = stripped.count("{") - stripped.count("}")
        open_brackets = stripped.count("[") - stripped.count("]")

        if open_braces > 0 or open_brackets > 0:
            return FailureClassification(
                failure_type=FailureType.TRUNCATION,
                confidence=0.9,
                details=f"Unclosed brackets: {open_braces} braces, {open_brackets} brackets",
                adaptation="shorten_prompt",
            )

        # Check for string that ends abruptly (no closing quote before bracket)
        if stripped and stripped[-1] not in ("}", "]"):
            if len(stripped) > 100:  # only flag substantial responses
                return FailureClassification(
                    failure_type=FailureType.TRUNCATION,
                    confidence=0.7,
                    details="Response doesn't end with closing bracket",
                    adaptation="shorten_prompt",
                )

        return None

    def _check_schema_violation(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect missing required fields in parsed output."""
        if parsed is None:
            return FailureClassification(
                failure_type=FailureType.SCHEMA_VIOLATION,
                confidence=1.0,
                details="Response could not be parsed as JSON",
                adaptation="add_schema_instruction",
            )

        required = {
            "title", "description", "preconditions", "steps",
            "expected_outcome", "given", "when", "then",
        }
        missing = required - set(parsed.keys())
        if missing:
            return FailureClassification(
                failure_type=FailureType.SCHEMA_VIOLATION,
                confidence=0.9,
                details=f"Missing fields: {', '.join(sorted(missing))}",
                adaptation="add_schema_instruction",
            )

        # Check steps is a non-empty array
        steps = parsed.get("steps", [])
        if not isinstance(steps, list) or len(steps) < 2:
            return FailureClassification(
                failure_type=FailureType.SCHEMA_VIOLATION,
                confidence=0.8,
                details=f"Steps should be array with >= 2 items, got {type(steps).__name__} len={len(steps) if isinstance(steps, list) else 'N/A'}",
                adaptation="add_schema_instruction",
            )

        return None

    def _check_instruction_leakage(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect prompt instructions appearing in the response."""
        if parsed is None:
            return None

        # Check all text fields for leakage patterns
        all_text = " ".join(str(parsed.get(f, "")) for f in _TEXT_FIELDS).lower()

        leaked: List[str] = []
        for pattern in _LEAKAGE_PATTERNS:
            if pattern in all_text:
                leaked.append(pattern)

        if leaked:
            return FailureClassification(
                failure_type=FailureType.INSTRUCTION_LEAKAGE,
                confidence=0.85,
                details=f"Instruction text found in output: {', '.join(leaked[:3])}",
                adaptation="add_no_leakage_instruction",
            )

        return None

    def _check_hollow(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect schema-valid but semantically empty/generic output."""
        if parsed is None:
            return None

        hollow_count = 0
        total_checked = 0

        for field_name in ("description", "preconditions", "expected_outcome"):
            value = str(parsed.get(field_name, "")).lower().strip()
            if not value or len(value) < 15:
                hollow_count += 1
                total_checked += 1
                continue
            total_checked += 1
            if _HOLLOW_PATTERN.search(value):
                hollow_count += 1

        # Check steps for generic content
        steps = parsed.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    action = str(step.get("action", "")).lower()
                    if _HOLLOW_PATTERN.search(action):
                        hollow_count += 1
                    total_checked += 1

        if total_checked > 0 and hollow_count / max(total_checked, 1) >= 0.4:
            return FailureClassification(
                failure_type=FailureType.HOLLOW,
                confidence=min(0.5 + hollow_count * 0.1, 0.95),
                details=f"{hollow_count}/{total_checked} fields contain generic/empty content",
                adaptation="add_specificity_instruction",
            )

        return None

    def _check_off_topic(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect response that doesn't reference the target AC."""
        if parsed is None:
            return None

        ac = slot.get("target_ac", "")
        if not ac or len(ac) < 10:
            return None

        # Extract key terms from AC (words > 3 chars, not stopwords)
        ac_terms: Set[str] = {
            word for word in re.findall(r"[a-zA-Z]{4,}", ac.lower())
            if word not in _STOPWORDS
        }

        if len(ac_terms) < 3:
            return None

        # Check how many AC terms appear in text fields of the response
        all_text = " ".join(str(parsed.get(f, "")) for f in _TEXT_FIELDS).lower()
        found = sum(1 for t in ac_terms if t in all_text)
        coverage = found / len(ac_terms)

        if coverage < 0.2:
            return FailureClassification(
                failure_type=FailureType.OFF_TOPIC,
                confidence=0.8,
                details=f"Only {found}/{len(ac_terms)} AC terms found in response ({coverage:.0%} coverage)",
                adaptation="repeat_ac_at_end",
            )

        return None

    def _check_repetitive(
        self, raw: str, parsed: Optional[Dict], slot: Dict, req: Any,
    ) -> Optional[FailureClassification]:
        """Detect repeated steps or identical GWT clauses."""
        if parsed is None:
            return None

        # Check for duplicate steps
        steps = parsed.get("steps", [])
        if isinstance(steps, list) and len(steps) >= 3:
            actions = [
                str(s.get("action", "")).strip().lower()
                for s in steps if isinstance(s, dict)
            ]
            unique_actions = set(actions)
            if len(actions) > 0 and len(unique_actions) < len(actions) * 0.6:
                return FailureClassification(
                    failure_type=FailureType.REPETITIVE,
                    confidence=0.85,
                    details=f"Only {len(unique_actions)} unique actions out of {len(actions)} steps",
                    adaptation="add_uniqueness_instruction",
                )

        # Check for identical GWT clauses
        gwt = [
            str(parsed.get("given", "")).strip().lower(),
            str(parsed.get("when", "")).strip().lower(),
            str(parsed.get("then", "")).strip().lower(),
        ]
        gwt_filled = [g for g in gwt if g]
        if len(gwt_filled) >= 2 and len(set(gwt_filled)) < len(gwt_filled):
            return FailureClassification(
                failure_type=FailureType.REPETITIVE,
                confidence=0.9,
                details="Given/When/Then clauses contain duplicates",
                adaptation="add_uniqueness_instruction",
            )

        return None
