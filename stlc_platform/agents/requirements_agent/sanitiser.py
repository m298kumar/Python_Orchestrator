"""
Test Case Sanitiser
===================
Validates and cleans LLM-generated test cases, replacing bad fields with
deterministic fallbacks. All rules are configurable.

7-step sanitisation pipeline:
  1. Description — replace if empty/instruction/loop/short
  2. Preconditions — replace if empty/instruction/loop/leakage/short
  3. Steps — filter generic; replace if <3 good steps or all identical results
  4. Expected outcome — replace if trivial/instruction/loop/leakage
  5. Given/When/Then — replace if garbled/bad/empty
  6. Component — resolve via ComponentResolver
  7. Tags — strip garbage, fallback to category+type+req_id
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from stlc_platform.core.contracts import TestCaseArtifact
from stlc_platform.agents.requirements_agent.constants import (
    GENERIC_STEP_FRAGMENTS,
    INSTRUCTION_PHRASES,
    TRIVIAL_OUTCOMES,
)
from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver
from stlc_platform.agents.requirements_agent.synthesiser import (
    make_description,
    make_gwt,
    make_preconditions,
    synthesise_steps,
)


@dataclass
class SanitiserConfig:
    """Configurable sanitisation rules."""

    instruction_phrases: List[str] = field(default_factory=lambda: list(INSTRUCTION_PHRASES))
    trivial_outcomes: Set[str] = field(default_factory=lambda: set(TRIVIAL_OUTCOMES))
    generic_step_fragments: List[str] = field(default_factory=lambda: list(GENERIC_STEP_FRAGMENTS))
    min_description_length: int = 15
    min_precondition_length: int = 20
    min_step_action_length: int = 20
    min_gwt_length: int = 12
    loop_threshold: int = 3
    min_good_steps: int = 3


class TestCaseSanitiser:
    """Validates and cleans test case fields.

    Args:
        config: Sanitisation rules. Defaults to built-in rules.
        component_resolver: ComponentResolver instance. Created with defaults if None.
        post_processors: Optional list of callables that each take and return a TestCaseArtifact.
    """

    def __init__(
        self,
        config: Optional[SanitiserConfig] = None,
        component_resolver: Optional[ComponentResolver] = None,
        post_processors: Optional[List[Callable[[TestCaseArtifact], TestCaseArtifact]]] = None,
    ):
        self._config = config or SanitiserConfig()
        self._resolver = component_resolver or ComponentResolver()
        self._post_processors: List[Callable[[TestCaseArtifact], TestCaseArtifact]] = (
            post_processors or []
        )

    def add_post_processor(
        self, fn: Callable[[TestCaseArtifact], TestCaseArtifact]
    ) -> None:
        """Register a custom post-processor."""
        self._post_processors.append(fn)

    def sanitise(
        self,
        tc: TestCaseArtifact,
        slot: Dict[str, Any],
        requirement: Any,
        classifier: Any = None,
    ) -> TestCaseArtifact:
        """Run the 7-step sanitisation pipeline.

        Args:
            tc: The test case to sanitise (modified in-place via model_copy).
            slot: Slot dict with target_ac, test_type, ac_type.
            requirement: Requirement object.
            classifier: Optional ACClassifier (for re-classification if needed).

        Returns:
            Sanitised TestCaseArtifact.
        """
        ac = slot["target_ac"]
        test_type = slot["test_type"]
        ac_type = slot.get("ac_type", "general")

        # Work with mutable dict, then reconstruct
        data = tc.model_dump()

        # 0. Strip markdown formatting artifacts from all text fields
        data = self._strip_markdown(data)

        # 1. Description
        if (not data["description"]
                or self._is_instruction_text(data["description"])
                or self._has_loop(data["description"])
                or len(data["description"]) < self._config.min_description_length):
            data["description"] = make_description(ac, test_type)

        # 2. Preconditions
        pre = self._clean_numbered_list(data["preconditions"])
        if (not pre
                or self._is_instruction_text(pre)
                or self._has_loop(pre)
                or self._has_python_leakage(pre)
                or len(pre) < self._config.min_precondition_length):
            pre = make_preconditions(
                ac, test_type,
                getattr(requirement, "category", "General"),
                getattr(requirement, "title", ""),
                ac_type,
            )
        data["preconditions"] = pre

        # 3. Steps
        steps = data.get("steps", [])
        good_steps = [
            s for s in steps
            if not self._is_generic_step(s.get("action", "") if isinstance(s, dict) else "")
        ]
        exp_results = [
            (s.get("expected_result", "") if isinstance(s, dict) else "").strip().lower()
            for s in good_steps
            if (s.get("expected_result", "") if isinstance(s, dict) else "").strip()
        ]
        all_identical = len(exp_results) > 1 and len(set(exp_results)) == 1

        if len(good_steps) < self._config.min_good_steps or all_identical:
            synth_steps = synthesise_steps(
                ac, test_type,
                getattr(requirement, "title", ""),
                ac_type,
            )
            data["steps"] = [s.model_dump() for s in synth_steps]
        else:
            data["steps"] = good_steps

        # 4. Expected outcome
        outcome = data.get("expected_outcome", "").strip()
        if (not outcome
                or outcome.lower() in self._config.trivial_outcomes
                or self._is_instruction_text(outcome)
                or self._has_loop(outcome)
                or self._has_python_leakage(outcome)):
            data["expected_outcome"] = ac

        # 5. Given / When / Then
        g_bad = self._gwt_is_bad(data.get("given", ""), data.get("preconditions", ""))
        w_bad = self._gwt_is_bad(data.get("when", ""), data.get("preconditions", ""))
        t_bad = self._gwt_is_bad(data.get("then", ""))

        if g_bad or w_bad or t_bad:
            g, w, t = make_gwt(ac, test_type, getattr(requirement, "title", ""), ac_type)
            if g_bad:
                data["given"] = g
            if w_bad:
                data["when"] = w
            if t_bad:
                data["then"] = t

        # 6. Component
        data["component"] = self._resolver.resolve(
            data.get("component", ""),
            getattr(requirement, "category", ""),
            getattr(requirement, "title", ""),
            ac_text=ac,
        )

        # 7. Tags
        data["tags"] = self._clean_tags(
            data.get("tags", []),
            getattr(requirement, "req_id", "REQ-UNKNOWN"),
            getattr(requirement, "category", "General"),
            test_type,
        )

        # 8. Test level — derive from AC type instead of trusting LLM
        data["test_level"] = self._classify_test_level(ac_type, test_type)

        # Reconstruct as Pydantic model
        result = TestCaseArtifact(**data)

        # Run post-processors
        for processor in self._post_processors:
            result = processor(result)

        return result

    # -- Detection helpers -------------------------------------------------------

    @staticmethod
    def _strip_md_text(text: str) -> str:
        """Strip markdown bold/italic markers and backticks from a string."""
        # Remove ***, **, * markers (bold/italic)
        text = re.sub(r'\*{1,3}([^*]+?)\*{1,3}', r'\1', text)
        # Remove remaining stray asterisks
        text = re.sub(r'(?<!\w)\*+|\*+(?!\w)', '', text)
        # Remove backtick code markers
        text = re.sub(r'`([^`]+)`', r'\1', text)
        return text.strip()

    def _strip_markdown(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Strip markdown artifacts from all text fields in a test case dict."""
        text_fields = [
            "title", "description", "preconditions", "expected_outcome",
            "given", "when", "then", "component",
        ]
        for field in text_fields:
            if field in data and isinstance(data[field], str):
                data[field] = self._strip_md_text(data[field])

        # Clean steps
        steps = data.get("steps", [])
        for step in steps:
            if isinstance(step, dict):
                if "action" in step and isinstance(step["action"], str):
                    step["action"] = self._strip_md_text(step["action"])
                if "expected_result" in step and isinstance(step["expected_result"], str):
                    step["expected_result"] = self._strip_md_text(step["expected_result"])

        # Clean tags — remove entries with markdown/json garbage
        tags = data.get("tags", [])
        if isinstance(tags, list):
            data["tags"] = [
                t for t in tags
                if isinstance(t, str)
                and not re.search(r'[{}\[\]*/\\:"]', t)
                and len(t.strip()) > 1
            ]

        return data

    def _is_instruction_text(self, text: str) -> bool:
        t = text.lower()
        return any(phrase in t for phrase in self._config.instruction_phrases)

    def _has_loop(self, text: str, threshold: int | None = None) -> bool:
        threshold = threshold or self._config.loop_threshold
        parts = re.split(r'[.\n]', text)
        parts = [p.strip().lower()[:60] for p in parts if len(p.strip()) > 15]
        if not parts:
            return False
        counts: dict[str, int] = {}
        for p in parts:
            counts[p] = counts.get(p, 0) + 1
            if counts[p] >= threshold:
                return True
        return False

    def _has_python_leakage(self, text: str) -> bool:
        return bool(
            re.search(r"'description'\s*:", text)
            or re.search(r'"description"\s*:', text)
            or re.search(r'\{.*?\'title\'\s*:', text, re.DOTALL)
        )

    def _is_generic_step(self, action: str) -> bool:
        t = action.strip().lower()
        if len(t) < self._config.min_step_action_length:
            return True
        if re.match(r'^[a-z]+(_[a-z]+)+$', t):
            return True
        return any(t.startswith(frag) for frag in self._config.generic_step_fragments)

    def _clean_numbered_list(self, text: str) -> str:
        text = re.sub(r"(\s*\(\d+\))+\s*$", "", text)
        text = re.sub(r"(\s*\d+\.\s*)+$", "", text)
        return text.strip()

    def _is_garbled(self, val: str) -> bool:
        v = val.strip()
        if re.search(r'\bHig\s+h\b', v, re.I):
            return True
        if re.search(r'nega\s+ti\s+v', v, re.I):
            return True
        if re.search(r'Mediu\s+m\b', v, re.I):
            return True
        if re.search(r'\b[a-z]{2,8}\s[a-z]{1,4}\b', v, re.I) and len(v) < 30:
            words = v.split()
            safe = {
                'the', 'a', 'an', 'is', 'are', 'was', 'to', 'of', 'and', 'or', 'in',
                'on', 'at', 'for', 'not', 'has', 'have', 'been', 'be', 'by', 'with',
                'from', 'test', 'data', 'user', 'app', 'when', 'then', 'given', 'action',
                'screen', 'system', 'customer', 'account',
            }
            if len(words) <= 4 and not any(w.lower() in safe for w in words):
                return True
        return False

    def _gwt_is_bad(self, val: str, preconditions: str = "") -> bool:
        _bad_gwt_words = {"", "setup", "act", "verify", "given", "when", "then"}
        v = val.strip()
        vl = v.lower()
        if not v or vl in _bad_gwt_words:
            return True
        if len(v) < self._config.min_gwt_length:
            return True
        if self._is_instruction_text(v):
            return True
        if "[specific" in vl or "[success" in vl:
            return True
        if self._is_garbled(v):
            return True
        if self._has_loop(v, threshold=2):
            return True
        if self._has_python_leakage(v):
            return True
        if preconditions and len(preconditions) > 20:
            pre_norm = re.sub(r'\s+', ' ', preconditions.strip().lower())
            val_norm = re.sub(r'\s+', ' ', vl)
            if val_norm[:60] in pre_norm or pre_norm[:60] in val_norm:
                return True
        return False

    @staticmethod
    def _classify_test_level(ac_type: str, test_type: str) -> str:
        """Derive test_level from AC type and test type.

        Mapping:
          - ui_behaviour → e2e (requires full UI rendering)
          - security, eligibility → integration (multi-component checks)
          - data_valid → unit (input validation logic)
          - timing → integration (async/timed behaviour)
          - edge_case test_type → integration (boundary across components)
          - general → integration (default for functional tests)
        """
        ac_level_map = {
            "ui_behaviour": "e2e",
            "security": "integration",
            "eligibility": "integration",
            "data_valid": "unit",
            "timing": "integration",
        }
        level = ac_level_map.get(ac_type, "integration")
        # Edge cases typically cross component boundaries
        if test_type == "edge_case" and level == "unit":
            level = "integration"
        return level

    def _clean_tags(
        self,
        tags: List[str],
        req_id: str,
        category: str,
        test_type: str,
    ) -> List[str]:
        clean: List[str] = []
        for tag in tags:
            t = tag.strip().lower()
            if (not t
                    or len(t) > 50
                    or re.fullmatch(r'[\d\s_,:.\-]+', t)
                    or t.startswith('path-')
                    or t.startswith('precondition')
                    or 'expected-outcome' in t
                    or re.search(r'_{3,}', t)
                    or t in ('true', 'false')):
                continue
            clean.append(t)

        if not clean:
            req_tag = re.sub(r"[^a-z0-9-]", "-", req_id.lower())
            cat_tag = category.lower().replace(" ", "-") if category else "general"
            clean = [cat_tag, test_type, req_tag]

        return clean
