"""
Step Parser
===========
Extracts unique step patterns from generated feature files and
parameterizes similar steps for step definition generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from stlc_platform.core.contracts import FeatureFileArtifact


@dataclass
class ParsedStep:
    """A single step extracted from a feature file."""

    keyword: str  # "given", "when", "then"
    text: str  # "the user is logged in"
    source_file: str = ""  # "req_ec_001_search_page.feature"


@dataclass
class ParameterizedStep:
    """A step pattern with extracted parameters."""

    keyword: str
    pattern: str  # "user enters {value} in {field}"
    params: List[str] = field(default_factory=list)  # ["value", "field"]
    original_steps: List[ParsedStep] = field(default_factory=list)


class StepParser:
    """
    Extracts and parameterizes steps from Gherkin feature file content.

    Usage:
        parser = StepParser()
        raw_steps = parser.extract_steps(feature_artifacts)
        unique_steps = parser.deduplicate(raw_steps)
        parameterized = parser.parameterize(unique_steps)
    """

    # Regex for Gherkin step keywords
    _STEP_RE = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+)$", re.MULTILINE)

    # Patterns for parameterizable values
    _QUOTED_SINGLE = re.compile(r"'([^']+)'")
    _QUOTED_DOUBLE = re.compile(r'"([^"]+)"')
    _BARE_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\b")

    def extract_steps(self, features: List[FeatureFileArtifact]) -> List[ParsedStep]:
        """
        Parse all Given/When/Then/And/But steps from feature files.

        And/But steps are assigned to the preceding keyword.
        Background steps are included (keyword = "given").
        """
        all_steps: List[ParsedStep] = []

        for feature in features:
            current_keyword = "given"  # default for And before any keyword
            for match in self._STEP_RE.finditer(feature.content):
                keyword_raw = match.group(1).strip()
                text = match.group(2).strip()

                if keyword_raw.lower() in ("and", "but"):
                    keyword = current_keyword
                else:
                    keyword = keyword_raw.lower()
                    current_keyword = keyword

                all_steps.append(
                    ParsedStep(
                        keyword=keyword,
                        text=text,
                        source_file=feature.filename,
                    )
                )

        return all_steps

    def deduplicate(self, steps: List[ParsedStep]) -> List[ParsedStep]:
        """
        Remove duplicate steps (same keyword + same text after normalization).
        Preserves insertion order.
        """
        seen: set = set()
        unique: List[ParsedStep] = []

        for step in steps:
            key = (step.keyword, self._normalize(step.text))
            if key not in seen:
                seen.add(key)
                unique.append(step)

        return unique

    def parameterize(self, steps: List[ParsedStep]) -> List[ParameterizedStep]:
        """
        Group similar steps and replace variable parts with parameters.

        A step is parameterized when:
          1. It contains quoted strings ('...' or "...")
          2. It contains bare numbers
          3. At least 2 steps share the same structure after replacement

        Steps that don't match any group are returned as-is (no params).
        """
        # First, create a parameterized version of each step
        step_signatures: Dict[str, List[Tuple[ParsedStep, str, List[str]]]] = {}

        for step in steps:
            pattern, params = self._extract_params(step.text)
            signature = (step.keyword, pattern)
            sig_key = f"{signature[0]}::{signature[1]}"
            step_signatures.setdefault(sig_key, []).append((step, pattern, params))

        result: List[ParameterizedStep] = []
        seen_patterns: set = set()

        for sig_key, group in step_signatures.items():
            if len(group) >= 2 and group[0][2]:
                # Multiple steps share this pattern AND have params
                pattern = group[0][1]
                params = group[0][2]
                keyword = group[0][0].keyword
                pattern_key = f"{keyword}::{pattern}"

                if pattern_key not in seen_patterns:
                    seen_patterns.add(pattern_key)
                    result.append(
                        ParameterizedStep(
                            keyword=keyword,
                            pattern=pattern,
                            params=params,
                            original_steps=[g[0] for g in group],
                        )
                    )
            else:
                # Keep each step as-is (no parameterization)
                for step, pattern, params in group:
                    pattern_key = f"{step.keyword}::{step.text}"
                    if pattern_key not in seen_patterns:
                        seen_patterns.add(pattern_key)
                        result.append(
                            ParameterizedStep(
                                keyword=step.keyword,
                                pattern=step.text,
                                params=[],
                                original_steps=[step],
                            )
                        )

        return result

    def _extract_params(self, text: str) -> Tuple[str, List[str]]:
        """
        Replace quoted strings and bare numbers with generic named parameters.

        Returns (pattern, param_names).
        Uses generic param names (param1, param2, ...) so that steps differing
        only in quoted values produce the same pattern signature.
        """
        params: List[str] = []
        result = text
        counter = 0

        # Replace single-quoted strings
        for match in self._QUOTED_SINGLE.finditer(text):
            counter += 1
            param_name = f"param{counter}"
            params.append(param_name)
            result = result.replace(match.group(0), f"{{{param_name}}}", 1)

        # Replace double-quoted strings (in the already-modified result)
        for match in list(self._QUOTED_DOUBLE.finditer(result)):
            if "{" not in match.group(0):  # Skip already replaced
                counter += 1
                param_name = f"param{counter}"
                params.append(param_name)
                result = result.replace(match.group(0), f"{{{param_name}}}", 1)

        return (result, params)

    def _normalize(self, text: str) -> str:
        """Normalize step text for comparison."""
        # Lowercase, collapse whitespace
        return re.sub(r"\s+", " ", text.strip().lower())
