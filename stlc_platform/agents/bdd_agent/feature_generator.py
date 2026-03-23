"""
Feature File Generator
======================
Converts TestCaseArtifact lists into Gherkin .feature files.
Groups test cases by requirement, extracts Background from shared
preconditions, and renders using Jinja2 templates.

Supports automatic Scenario Outline detection: when multiple test cases
under the same requirement share the same step skeleton but differ in
quoted-string or numeric values, they are merged into a single
Scenario Outline with an Examples table.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from stlc_platform.core.contracts import FeatureFileArtifact, TestCaseArtifact

# Regex patterns for parameterizable values
_QUOTED_RE = re.compile(r"""(?:"([^"]*?)"|'([^']*?)')""")
_NUMBER_RE = re.compile(r"(?<![a-zA-Z_])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_])")


# -- Paths --
_BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"
_DEFAULT_OVERRIDES = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "config"
    / "prompt_overrides"
    / "bdd"
)


class FeatureFileGenerator:
    """
    Generates Gherkin .feature files from TestCaseArtifact lists.

    One feature file is produced per unique req_id. Each test case
    becomes a Scenario (or Scenario Outline if parameterizable).
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        override_dir: Optional[Path] = None,
    ):
        loaders = []
        override = override_dir or _DEFAULT_OVERRIDES
        if override.is_dir():
            loaders.append(FileSystemLoader(str(override)))
        builtin = template_dir or _BUILTIN_TEMPLATES
        loaders.append(FileSystemLoader(str(builtin)))

        self._env = Environment(
            loader=ChoiceLoader(loaders),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate(
        self, test_cases: List[TestCaseArtifact]
    ) -> List[FeatureFileArtifact]:
        """Generate one FeatureFileArtifact per unique req_id."""
        groups = self._group_by_requirement(test_cases)
        features = []
        for req_id, cases in groups.items():
            feature = self._build_feature(req_id, cases)
            features.append(feature)
        return features

    def _group_by_requirement(
        self, test_cases: List[TestCaseArtifact]
    ) -> Dict[str, List[TestCaseArtifact]]:
        """Group test cases by req_id, preserving insertion order."""
        groups: Dict[str, List[TestCaseArtifact]] = OrderedDict()
        for tc in test_cases:
            groups.setdefault(tc.req_id, []).append(tc)
        return groups

    def _build_feature(
        self, req_id: str, cases: List[TestCaseArtifact]
    ) -> FeatureFileArtifact:
        """Build a complete feature file from grouped test cases."""
        # Feature-level info from first test case
        first = cases[0]
        feature_title = self._derive_feature_title(first)
        feature_description = first.description or ""

        # Feature-level tags
        feature_tags = [f"@{self._sanitize_tag(req_id)}"]

        # Extract Background (shared Given)
        background = self._extract_background(cases)

        # Detect outlines and build scenarios
        scenarios = self._detect_outlines(cases, background)

        # Render template
        template = self._env.get_template("feature.j2")
        content = template.render(
            feature_tags=feature_tags,
            feature_title=feature_title,
            feature_description=feature_description,
            background=background,
            scenarios=scenarios,
        )

        filename = self._make_filename(req_id, feature_title)

        return FeatureFileArtifact(
            req_id=req_id,
            filename=filename,
            content=content,
            scenario_count=len(scenarios),
            tags=[t.lstrip("@") for t in feature_tags],
        )

    def _derive_feature_title(self, tc: TestCaseArtifact) -> str:
        """Derive a feature title from the first test case's component or category."""
        # Use component if available, otherwise category, otherwise req_id
        if tc.component:
            return tc.component
        if tc.category:
            return tc.category
        return tc.req_id

    def _extract_background(
        self, cases: List[TestCaseArtifact]
    ) -> Optional[str]:
        """
        Extract a shared Background Given step if >50% of scenarios
        share the same Given text (after normalization).
        """
        if len(cases) < 2:
            return None

        given_texts = []
        for tc in cases:
            given = self._get_given(tc).strip()
            if given:
                given_texts.append(given)

        if not given_texts:
            return None

        # Count occurrences of each Given (case-insensitive)
        from collections import Counter

        counts = Counter(g.lower() for g in given_texts)
        most_common_lower, count = counts.most_common(1)[0]

        # Need >50% agreement
        if count <= len(cases) / 2:
            return None

        # Return the original-cased version
        for g in given_texts:
            if g.lower() == most_common_lower:
                return g
        return None

    # -- Scenario Outline detection ------------------------------------------

    def _normalize_step(
        self,
        text: str,
        counter: Optional[Dict[str, int]] = None,
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Replace parameterizable values in a step with placeholders.

        Returns ``(skeleton, params)`` where *skeleton* has ``<param_N>``
        or ``<value_N>`` placeholders and *params* is a list of
        ``(placeholder_name, original_value)`` pairs.

        An optional *counter* dict (keys ``"p"`` and ``"v"``) can be
        passed to keep numbering unique across multiple calls (e.g.
        across Given / When / Then of the same test case).
        """
        params: List[Tuple[str, str]] = []
        if counter is None:
            counter = {"p": 0, "v": 0}

        def _replace_quoted(m: re.Match) -> str:
            val = m.group(1) if m.group(1) is not None else m.group(2)
            counter["p"] += 1
            name = f"param_{counter['p']}"
            params.append((name, val))
            return f"<{name}>"

        skeleton = _QUOTED_RE.sub(_replace_quoted, text)

        def _replace_number(m: re.Match) -> str:
            counter["v"] += 1
            name = f"value_{counter['v']}"
            params.append((name, m.group(0)))
            return f"<{name}>"

        skeleton = _NUMBER_RE.sub(_replace_number, skeleton)
        return skeleton, params

    def _detect_outlines(
        self,
        cases: List[TestCaseArtifact],
        background_given: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Group test cases by step skeleton.  Groups with 2+ members become
        a single Scenario Outline; singletons stay as regular Scenarios.
        """
        # Build per-TC metadata: skeleton key + extracted params
        KeyType = Tuple[str, str, str]
        groups: Dict[KeyType, List[Tuple[TestCaseArtifact, List[Tuple[str, str]]]]] = (
            OrderedDict()
        )

        for tc in cases:
            # Use a shared counter so param names are unique across G/W/T
            ctr: Dict[str, int] = {"p": 0, "v": 0}
            given_skel, given_params = self._normalize_step(self._get_given(tc), ctr)
            when_skel, when_params = self._normalize_step(self._get_when(tc), ctr)
            then_skel, then_params = self._normalize_step(self._get_then(tc), ctr)
            key: KeyType = (given_skel, when_skel, then_skel)
            all_params = given_params + when_params + then_params
            groups.setdefault(key, []).append((tc, all_params))

        scenarios: List[Dict[str, Any]] = []
        for key, members in groups.items():
            # Only merge into an outline when there are 2+ members AND
            # the skeleton actually extracted parameters to vary.
            has_params = any(len(params) > 0 for _, params in members)
            if len(members) >= 2 and has_params:
                # Merge into a Scenario Outline
                scenarios.append(
                    self._build_outline(key, members, background_given)
                )
            else:
                # Regular scenarios (either single or identical with no params)
                for tc, _ in members:
                    scenarios.append(
                        self._build_scenario(tc, background_given=background_given)
                    )
        return scenarios

    def _build_outline(
        self,
        skeleton_key: Tuple[str, str, str],
        members: List[Tuple[TestCaseArtifact, List[Tuple[str, str]]]],
        background_given: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a Scenario Outline dict from a group of matching test cases."""
        given_skel, when_skel, then_skel = skeleton_key
        first_tc, first_params = members[0]

        # Derive param names from first member (all members share same skeleton)
        param_names = [p[0] for p in first_params]

        # Build Examples rows
        examples_rows: List[str] = []
        for _, params in members:
            vals = [p[1] for p in params]
            row = "| " + " | ".join(vals) + " |"
            examples_rows.append(row)

        examples_header = "| " + " | ".join(param_names) + " |" if param_names else ""

        # Split skeleton steps
        given_main, given_ands = self._split_step(given_skel)
        when_main, when_ands = self._split_step(when_skel)
        then_main, then_ands = self._split_step(then_skel)

        # Skip Given if Background covers it
        skip_given = False
        if background_given and given_main:
            if given_main.lower().strip() == background_given.lower().strip():
                skip_given = True

        tags = self._scenario_tags(first_tc)

        # Build a combined title from the first TC
        title = first_tc.title

        return {
            "name": self._escape_gherkin(title),
            "tags": tags,
            "given": self._escape_gherkin(given_main) if not skip_given else "",
            "and_givens": [self._escape_gherkin(g) for g in given_ands] if not skip_given else [],
            "when": self._escape_gherkin(when_main),
            "and_whens": [self._escape_gherkin(w) for w in when_ands],
            "then": self._escape_gherkin(then_main),
            "and_thens": [self._escape_gherkin(t) for t in then_ands],
            "is_outline": True,
            "examples_header": examples_header,
            "examples_rows": examples_rows,
        }

    # -- Single scenario builder ---------------------------------------------

    def _build_scenario(
        self,
        tc: TestCaseArtifact,
        background_given: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a scenario dict for template rendering."""
        given = self._get_given(tc)
        when_text = self._get_when(tc)
        then_text = self._get_then(tc)

        # Split multi-sentence steps into main + And steps
        given_main, given_ands = self._split_step(given)
        when_main, when_ands = self._split_step(when_text)
        then_main, then_ands = self._split_step(then_text)

        # If Background covers the Given, skip it in the scenario
        skip_given = False
        if background_given and given_main:
            if given_main.lower().strip() == background_given.lower().strip():
                skip_given = True

        # Tags for this scenario
        tags = self._scenario_tags(tc)

        return {
            "name": self._escape_gherkin(tc.title),
            "tags": tags,
            "given": self._escape_gherkin(given_main) if not skip_given else "",
            "and_givens": [self._escape_gherkin(g) for g in given_ands] if not skip_given else [],
            "when": self._escape_gherkin(when_main),
            "and_whens": [self._escape_gherkin(w) for w in when_ands],
            "then": self._escape_gherkin(then_main),
            "and_thens": [self._escape_gherkin(t) for t in then_ands],
            "is_outline": False,
            "examples_header": "",
            "examples_rows": [],
        }

    def _get_given(self, tc: TestCaseArtifact) -> str:
        """Get Given text, falling back to preconditions or steps."""
        if tc.given and tc.given.strip():
            return tc.given.strip()
        if tc.preconditions and tc.preconditions.strip():
            return tc.preconditions.strip()
        if tc.steps:
            return tc.steps[0].action
        return "the system is in the expected initial state"

    def _get_when(self, tc: TestCaseArtifact) -> str:
        """Get When text, falling back to steps."""
        if tc.when and tc.when.strip():
            return tc.when.strip()
        if tc.steps and len(tc.steps) > 1:
            return tc.steps[1].action
        return "the user performs the action"

    def _get_then(self, tc: TestCaseArtifact) -> str:
        """Get Then text, falling back to expected outcome or steps."""
        if tc.then and tc.then.strip():
            return tc.then.strip()
        if tc.expected_outcome and tc.expected_outcome.strip():
            return tc.expected_outcome.strip()
        if tc.steps:
            last = tc.steps[-1]
            return last.expected_result or last.action
        return "the expected outcome is observed"

    def _split_step(self, text: str) -> Tuple[str, List[str]]:
        """
        Split a compound step into main + And parts.

        Splits on ' and ' (case-insensitive) only when it looks like
        a separate clause (preceded by comma or is sentence boundary).
        Also splits on explicit newlines.
        """
        if not text:
            return ("", [])

        # Split on newlines first
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) > 1:
            return (lines[0], lines[1:])

        # For single-line, don't split -- keep as one step
        return (text, [])

    def _scenario_tags(self, tc: TestCaseArtifact) -> List[str]:
        """Generate tags for a scenario."""
        tags = []
        if tc.test_type:
            tags.append(f"@{self._sanitize_tag(tc.test_type)}")
        if tc.priority:
            tags.append(f"@{self._sanitize_tag(tc.priority)}_priority")
        if tc.category:
            tags.append(f"@{self._sanitize_tag(tc.category)}")
        return tags

    def _sanitize_tag(self, text: str) -> str:
        """Make text safe for use as a Gherkin tag."""
        # Replace spaces, special chars with underscores
        tag = re.sub(r"[^a-zA-Z0-9_\-]", "_", text.strip())
        # Collapse multiple underscores
        tag = re.sub(r"_+", "_", tag).strip("_")
        return tag.lower() if tag else "unknown"

    def _escape_gherkin(self, text: str) -> str:
        """Sanitize text for valid Gherkin output."""
        if not text:
            return ""
        # Remove control characters except newline
        text = re.sub(r"[\x00-\x09\x0b-\x1f]", "", text)
        # Strip leading # (comment marker in Gherkin)
        text = text.lstrip("#").strip()
        # Replace em-dash and other problematic chars with ASCII
        text = text.replace("\u2014", "--").replace("\u2013", "-")
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        return text.strip()

    def _make_filename(self, req_id: str, title: str) -> str:
        """Generate a safe .feature filename."""
        # Combine req_id and title
        raw = f"{req_id}_{title}"
        # Slugify
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
        # Cap at 60 chars for reasonable filenames
        if len(slug) > 60:
            slug = slug[:60].rstrip("_")
        return f"{slug}.feature"
