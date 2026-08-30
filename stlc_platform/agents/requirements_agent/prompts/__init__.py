"""
Prompt Renderer
===============
Manages all prompt templates for test case generation.

Templates are Jinja2 with a two-layer override mechanism:
  1. User overrides in config/prompt_overrides/ (highest priority)
  2. Built-in templates in prompts/templates/ (fallback)

Usage:
    renderer = PromptRenderer()
    system = renderer.render_system_prompt(domain="healthcare", tech_stack={...})
    hints = renderer.render_type_hints("positive", "ui_behaviour", ac="...", feature="...", nav_target="...")
    prompt = renderer.render_user_prompt(requirement=..., slot=..., ...)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2

from stlc_platform.agents.requirements_agent.constants import COT_INSTRUCTION, TYPE_CONTEXT
from stlc_platform.agents.requirements_agent.prompts._hints import (
    get_gwt_hint,
    get_hints,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptRenderer:
    """Renders all prompt templates for test case generation.

    Args:
        template_dir: Path to built-in templates. Defaults to prompts/templates/.
        override_dir: Path to user override templates. Defaults to config/prompt_overrides/.
        platform_verbs: Optional dict of platform-specific verbs for tech stack awareness.
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        override_dir: Optional[Path] = None,
        platform_verbs: Optional[Dict[str, Dict[str, str]]] = None,
        guardrail_text: str = "",
    ):
        builtin_dir = template_dir or _TEMPLATES_DIR
        loaders: list[jinja2.BaseLoader] = []

        if override_dir and override_dir.exists():
            loaders.append(jinja2.FileSystemLoader(str(override_dir)))
        loaders.append(jinja2.FileSystemLoader(str(builtin_dir)))

        self._env = jinja2.Environment(
            loader=jinja2.ChoiceLoader(loaders),
            undefined=jinja2.Undefined,  # Silent substitution for missing vars
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._platform_verbs = platform_verbs or {}
        self._guardrail_text = guardrail_text.strip()

    def render_system_prompt(
        self,
        domain: str = "",
        tech_stack: Optional[Dict[str, str]] = None,
    ) -> str:
        """Render the system prompt for the LLM.

        Args:
            domain: Application domain (e.g., "healthcare", "retail e-commerce").
            tech_stack: Tech stack config dict (platform, frontend, backend, etc.).

        Returns:
            Complete system prompt string.
        """
        template = self._env.get_template("system_prompt.j2")

        platform = (tech_stack or {}).get("platform", "web")
        verbs = self._platform_verbs.get(platform, {})

        rendered = template.render(
            domain=domain,
            app_description=f"the {domain} application" if domain else "this software application",
            tech_stack=tech_stack or {},
            platform=platform,
            click_verb=verbs.get("click", "click"),
            navigate_verb=verbs.get("navigate", "navigate to"),
            page_loads_verb=verbs.get("page_loads", "page loads"),
        )
        if self._guardrail_text:
            rendered += (
                "\n\nAPPROVED TEST-CASE GENERATION SPECIFICATION "
                "(normative guardrail; follow all MUST and MUST NOT rules):\n"
                f"{self._guardrail_text}"
            )
        return rendered

    def render_type_hints(
        self,
        test_type: str,
        ac_type: str,
        ac: str,
        feature: str,
        nav_target: str,
    ) -> Dict[str, str]:
        """Render type-specific hints for prompt injection.

        Args:
            test_type: One of 'positive', 'negative', 'edge_case'.
            ac_type: One of 'eligibility', 'ui_behaviour', 'timing', 'data_valid', 'security', 'general'.
            ac: The acceptance criterion text.
            feature: Feature/requirement title (truncated).
            nav_target: Navigation target (category or title).

        Returns:
            Dict with keys: desc, pre, steps, outcome.
        """
        # Try file-based override first
        template_path = f"type_hints/{test_type}/{ac_type}.j2"
        try:
            template = self._env.get_template(template_path)
            rendered = template.render(
                ac=ac,
                feature=feature,
                nav_target=nav_target,
                ac_short=ac[:90],
                ac_60=ac[:60],
                ac_70=ac[:70],
                ac_80=ac[:80],
                ac_100=ac[:100],
            )
            # Parse rendered template (expected format: key: value per line)
            return self._parse_hints(rendered)
        except jinja2.TemplateNotFound:
            pass

        # Fall back to programmatic hints
        return get_hints(test_type, ac_type, ac, feature, nav_target)

    def render_few_shot_block(self, examples: List[Dict[str, Any]]) -> str:
        """Render the few-shot examples block.

        Args:
            examples: List of approved test case dicts from ChromaDB.

        Returns:
            Formatted few-shot block string, or empty string if no examples.
        """
        if not examples:
            return ""

        template = self._env.get_template("few_shot_block.j2")
        return template.render(examples=examples[:2])

    def render_feedback_block(self, feedback_constraints: Optional[List[Any]] = None) -> str:
        """Render the feedback constraints block.

        Args:
            feedback_constraints: List of AgentFeedbackArtifact objects.

        Returns:
            Formatted feedback block string, or empty string if no feedback.
        """
        if not feedback_constraints:
            return ""

        template = self._env.get_template("feedback_block.j2")
        return template.render(feedback_constraints=feedback_constraints)

    def render_user_prompt(
        self,
        requirement: Any,
        slot: Dict[str, Any],
        test_number: int,
        total: int,
        context: str = "",
        tc_format: str = "gherkin",
        examples: Optional[List[Dict[str, Any]]] = None,
        tech_stack: Optional[Dict[str, str]] = None,
        feedback_constraints: Optional[List[Any]] = None,
        max_prompt_tokens: Optional[int] = None,
    ) -> str:
        """Render the complete user prompt for one test case slot.

        Args:
            requirement: Requirement object with req_id, title, etc.
            slot: Slot dict with test_type, target_ac, title, ac_type.
            test_number: Current test number (1-based).
            total: Total test cases for this requirement.
            context: Related requirements context string.
            tc_format: Test case format ('gherkin' or 'standard').
            examples: Few-shot examples from ChromaDB.
            tech_stack: Tech stack config for verb substitution.
            feedback_constraints: List of AgentFeedbackArtifact objects.
            max_prompt_tokens: Max approximate token budget. If the rendered
                prompt exceeds this, sections are progressively trimmed:
                few_shot_block → context_block → AC list truncation.

        Returns:
            Complete user prompt string.
        """
        template = self._env.get_template("user_prompt.j2")

        ac = slot["target_ac"]
        tt = slot["test_type"]
        ac_type = slot.get("ac_type", "general")
        feature = getattr(requirement, "title", "")[:60]
        nav_target = (
            getattr(requirement, "category", "")[:40] or getattr(requirement, "title", "")[:40]
        )

        # Get type-specific hints
        hints = self.render_type_hints(tt, ac_type, ac, feature, nav_target)

        # Get GWT hint
        gwt_hint = get_gwt_hint(tt, ac_type, ac, feature)

        # Build AC text
        acs = getattr(requirement, "acceptance_criteria", [])
        all_ac_text = (
            "\n".join(f"  AC{i + 1}: {a}" for i, a in enumerate(acs))
            if acs
            else "  (none specified)"
        )

        # Few-shot block
        few_shot_block = self.render_few_shot_block(examples or [])

        # Context block
        context_block = f"\nRELATED REQUIREMENTS (context only):\n{context}\n" if context else ""

        # Feedback block — inject learned constraints from user feedback
        feedback_block = self.render_feedback_block(feedback_constraints)

        # AC type label
        ac_type_label = {
            "eligibility": "eligibility rule",
            "ui_behaviour": "UI behaviour",
            "timing": "timing/performance constraint",
            "data_valid": "data validation rule",
            "security": "security control",
            "general": "general requirement",
        }.get(ac_type, "requirement")

        # Tags
        cat_tag = getattr(requirement, "category", "").lower().replace(" ", "-") or "general"
        req_tag = re.sub(r"[^a-z0-9-]", "-", getattr(requirement, "req_id", "REQ-UNKNOWN").lower())

        # Gherkin section
        gherkin_section = ""
        if tc_format == "gherkin":
            gherkin_section = f"\nGIVEN / WHEN / THEN -- fill exactly as shown:\n{gwt_hint}\n"

        rendered = template.render(
            requirement=requirement,
            slot=slot,
            test_number=test_number,
            total=total,
            all_ac_text=all_ac_text,
            context_block=context_block,
            feedback_block=feedback_block,
            few_shot_block=few_shot_block,
            cot_instruction=COT_INSTRUCTION,
            type_context=TYPE_CONTEXT.get(tt, ""),
            hints=hints,
            gwt_hint=gwt_hint,
            gherkin_section=gherkin_section,
            ac=ac,
            ac_type_label=ac_type_label,
            cat_tag=cat_tag,
            req_tag=req_tag,
            tt=tt,
        )

        # ── Context Window Management (Phase C) ────────────────────────────
        # Progressive trimming if the prompt exceeds the token budget.
        # Approximation: 1 token ≈ 4 characters (conservative for English).
        if max_prompt_tokens is not None and max_prompt_tokens > 0:
            est_tokens = len(rendered) // 4

            if est_tokens > max_prompt_tokens:
                # Build shared render params once; override only what changes
                render_params: Dict[str, Any] = {
                    "requirement": requirement,
                    "slot": slot,
                    "test_number": test_number,
                    "total": total,
                    "all_ac_text": all_ac_text,
                    "context_block": context_block,
                    "feedback_block": feedback_block,
                    "few_shot_block": few_shot_block,
                    "cot_instruction": COT_INSTRUCTION,
                    "type_context": TYPE_CONTEXT.get(tt, ""),
                    "hints": hints,
                    "gwt_hint": gwt_hint,
                    "gherkin_section": gherkin_section,
                    "ac": ac,
                    "ac_type_label": ac_type_label,
                    "cat_tag": cat_tag,
                    "req_tag": req_tag,
                    "tt": tt,
                }

                # Trim 1: Remove few-shot block
                if few_shot_block:
                    render_params["few_shot_block"] = ""
                    rendered = template.render(**render_params)
                    est_tokens = len(rendered) // 4

                # Trim 2: Remove context block
                if est_tokens > max_prompt_tokens and context_block:
                    render_params["context_block"] = ""
                    rendered = template.render(**render_params)
                    est_tokens = len(rendered) // 4

                # Trim 3: Truncate AC list to target AC only
                if est_tokens > max_prompt_tokens:
                    render_params["all_ac_text"] = f"  AC: {ac}"
                    rendered = template.render(**render_params)

        return rendered

    def _parse_hints(self, rendered: str) -> Dict[str, str]:
        """Parse a rendered hints template into a dict."""
        result = {"desc": "", "pre": "", "steps": "", "outcome": ""}
        current_key = None
        lines: list[str] = []

        for line in rendered.split("\n"):
            for key in result:
                if line.startswith(f"{key}:"):
                    if current_key and lines:
                        result[current_key] = "\n".join(lines).strip()
                        lines = []
                    current_key = key
                    lines.append(line[len(key) + 1 :].strip())
                    break
            else:
                if current_key:
                    lines.append(line)

        if current_key and lines:
            result[current_key] = "\n".join(lines).strip()

        return result
