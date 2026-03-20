"""
Gherkin Validator
=================
Validates generated Gherkin feature file content without requiring
the behave library. Uses regex-based parsing for portability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class GherkinValidationResult:
    """Result of Gherkin validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    feature_title: str = ""
    scenario_count: int = 0


class GherkinValidator:
    """Validates that generated content is well-formed Gherkin."""

    # Patterns for Gherkin keywords
    _FEATURE_RE = re.compile(r"^\s*Feature:\s*(.+)", re.MULTILINE)
    _BACKGROUND_RE = re.compile(r"^\s*Background:\s*(.*)", re.MULTILINE)
    _SCENARIO_RE = re.compile(r"^\s*Scenario:\s*(.+)", re.MULTILINE)
    _OUTLINE_RE = re.compile(r"^\s*Scenario Outline:\s*(.+)", re.MULTILINE)
    _EXAMPLES_RE = re.compile(r"^\s*Examples:\s*", re.MULTILINE)
    _GIVEN_RE = re.compile(r"^\s*Given\s+(.+)", re.MULTILINE)
    _WHEN_RE = re.compile(r"^\s*When\s+(.+)", re.MULTILINE)
    _THEN_RE = re.compile(r"^\s*Then\s+(.+)", re.MULTILINE)
    _AND_RE = re.compile(r"^\s*And\s+(.+)", re.MULTILINE)
    _BUT_RE = re.compile(r"^\s*But\s+(.+)", re.MULTILINE)
    _TAG_RE = re.compile(r"^\s*@[\w\-]+", re.MULTILINE)
    _TABLE_ROW_RE = re.compile(r"^\s*\|.+\|", re.MULTILINE)

    def validate(self, content: str) -> GherkinValidationResult:
        """
        Validate a Gherkin feature file content string.

        Checks:
          1. Exactly one Feature: line
          2. At least one Scenario or Scenario Outline
          3. Each Scenario has at least When and Then steps
          4. Scenario Outline has matching Examples table
          5. Tags are well-formed (@word_chars)
          6. No empty step text
          7. No duplicate scenario names
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Check Feature
        features = self._FEATURE_RE.findall(content)
        if len(features) == 0:
            errors.append("Missing 'Feature:' keyword")
            return GherkinValidationResult(
                valid=False, errors=errors, warnings=warnings
            )
        if len(features) > 1:
            errors.append(
                f"Multiple 'Feature:' keywords found ({len(features)}). "
                "Expected exactly one per file."
            )

        feature_title = features[0].strip() if features else ""

        # 2. Parse scenarios and outlines
        scenarios = self._parse_scenarios(content)
        outlines = self._parse_outlines(content)
        all_scenarios = scenarios + outlines

        if not all_scenarios:
            errors.append("No Scenario or Scenario Outline found")
            return GherkinValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                feature_title=feature_title,
            )

        # 3. Validate each scenario block
        seen_names: set = set()
        for scenario in all_scenarios:
            name = scenario["name"]
            is_outline = scenario["is_outline"]
            block = scenario["block"]

            # Check for duplicate names
            name_lower = name.strip().lower()
            if name_lower in seen_names:
                warnings.append(f"Duplicate scenario name: '{name.strip()}'")
            seen_names.add(name_lower)

            # Check for When and Then (Given is optional in scenarios
            # if Background provides it)
            has_when = bool(self._WHEN_RE.search(block))
            has_then = bool(self._THEN_RE.search(block))

            if not has_when:
                errors.append(
                    f"Scenario '{name.strip()}' is missing a 'When' step"
                )
            if not has_then:
                errors.append(
                    f"Scenario '{name.strip()}' is missing a 'Then' step"
                )

            # Check for empty step text
            for pattern in [self._GIVEN_RE, self._WHEN_RE, self._THEN_RE,
                            self._AND_RE, self._BUT_RE]:
                for match in pattern.finditer(block):
                    step_text = match.group(1).strip()
                    if not step_text:
                        errors.append(
                            f"Empty step text in scenario '{name.strip()}'"
                        )

            # Scenario Outline must have Examples
            if is_outline:
                has_examples = bool(self._EXAMPLES_RE.search(block))
                if not has_examples:
                    errors.append(
                        f"Scenario Outline '{name.strip()}' is missing "
                        "an 'Examples:' table"
                    )

        # 4. Validate tags
        tag_errors = self._validate_tags(content)
        errors.extend(tag_errors)

        return GherkinValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            feature_title=feature_title,
            scenario_count=len(all_scenarios),
        )

    def validate_content(self, content: str) -> GherkinValidationResult:
        """Alias for validate() for backward compatibility."""
        return self.validate(content)

    def _parse_scenarios(self, content: str) -> List[dict]:
        """Extract Scenario blocks (not Outline) with their content."""
        return self._extract_blocks(content, r"Scenario:", is_outline=False)

    def _parse_outlines(self, content: str) -> List[dict]:
        """Extract Scenario Outline blocks with their content."""
        return self._extract_blocks(
            content, r"Scenario Outline:", is_outline=True
        )

    def _extract_blocks(
        self, content: str, keyword: str, is_outline: bool
    ) -> List[dict]:
        """
        Extract named blocks from Gherkin content.

        A block starts at the keyword line and ends at the next
        Scenario/Scenario Outline/Feature keyword or end of content.
        """
        blocks = []
        pattern = re.compile(
            rf"^\s*{keyword}\s*(.+)", re.MULTILINE
        )
        # Boundary keywords that end a scenario block
        boundary = re.compile(
            r"^\s*(?:Scenario:|Scenario Outline:|Feature:)\s",
            re.MULTILINE,
        )

        matches = list(pattern.finditer(content))
        for i, match in enumerate(matches):
            start = match.start()
            # Find the end of this block
            remaining = content[match.end():]
            boundary_match = boundary.search(remaining)
            if boundary_match:
                end = match.end() + boundary_match.start()
            else:
                end = len(content)

            block_text = content[start:end]
            blocks.append({
                "name": match.group(1),
                "block": block_text,
                "is_outline": is_outline,
            })

        return blocks

    def _validate_tags(self, content: str) -> List[str]:
        """Validate that all tags are well-formed."""
        errors = []
        # Find lines that look like they should be tags but are malformed
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("@"):
                # Tags can be space-separated on one line: @tag1 @tag2
                parts = stripped.split()
                for part in parts:
                    if part.startswith("@") and not re.match(
                        r"^@[\w\-]+$", part
                    ):
                        errors.append(
                            f"Malformed tag: '{part}' "
                            "(tags must be @word_chars only)"
                        )
        return errors
