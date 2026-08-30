"""Tests for the prompt renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest
from stlc_platform.agents.requirements_agent.prompts import PromptRenderer


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    title: str = "User Login Feature"
    description: str = "User should be able to log in with valid credentials"
    category: str = "Authentication"
    acceptance_criteria: List[str] = field(
        default_factory=lambda: [
            "User can login with valid credentials",
            "System displays error for invalid password",
        ]
    )


class TestRenderSystemPrompt:
    """Test system prompt rendering."""

    def test_default_no_domain(self):
        renderer = PromptRenderer()
        result = renderer.render_system_prompt()
        assert "software application" in result
        assert "RULE 1" in result
        assert "RULE 7" in result

    def test_with_domain(self):
        renderer = PromptRenderer()
        result = renderer.render_system_prompt(domain="healthcare")
        assert "healthcare application" in result

    def test_contains_all_rules(self):
        renderer = PromptRenderer()
        result = renderer.render_system_prompt()
        for i in range(1, 8):
            assert f"RULE {i}" in result

    def test_approved_specification_is_injected_as_guardrail(self):
        renderer = PromptRenderer(guardrail_text="MUST preserve requirement traceability.")
        result = renderer.render_system_prompt()
        assert "APPROVED TEST-CASE GENERATION SPECIFICATION" in result
        assert "MUST preserve requirement traceability" in result

    def test_no_hardcoded_domain_terms(self):
        """System prompt should not contain banking/cheque/deposit references."""
        renderer = PromptRenderer()
        result = renderer.render_system_prompt()
        assert "cheque" not in result.lower()
        assert "deposit" not in result.lower()
        assert "banking" not in result.lower()

    def test_platform_verbs_web(self):
        renderer = PromptRenderer(
            platform_verbs={
                "web": {"click": "click", "navigate": "navigate to", "page_loads": "page loads"},
            }
        )
        result = renderer.render_system_prompt(tech_stack={"platform": "web"})
        assert "Click" in result or "click" in result

    def test_platform_verbs_mobile(self):
        renderer = PromptRenderer(
            platform_verbs={
                "mobile": {
                    "click": "tap",
                    "navigate": "navigate to",
                    "page_loads": "screen appears",
                },
            }
        )
        result = renderer.render_system_prompt(tech_stack={"platform": "mobile"})
        assert "Tap" in result or "tap" in result


class TestRenderTypeHints:
    """Test type-specific hint rendering for all combinations."""

    @pytest.fixture
    def renderer(self):
        return PromptRenderer()

    @pytest.mark.parametrize("test_type", ["positive", "negative", "edge_case"])
    @pytest.mark.parametrize(
        "ac_type", ["eligibility", "ui_behaviour", "timing", "data_valid", "security", "general"]
    )
    def test_all_combinations(self, renderer, test_type, ac_type):
        """All 18 test_type × ac_type combinations must render valid hints."""
        hints = renderer.render_type_hints(
            test_type=test_type,
            ac_type=ac_type,
            ac="User must complete verification within 5 minutes of starting the process",
            feature="User Verification",
            nav_target="Verification",
        )
        assert "desc" in hints
        assert "pre" in hints
        assert "steps" in hints
        assert "outcome" in hints
        assert len(hints["desc"]) > 10
        assert len(hints["steps"]) > 20

    def test_hints_contain_ac_text(self, renderer):
        ac = "Password must be at least 8 characters"
        hints = renderer.render_type_hints(
            "positive", "data_valid", ac=ac, feature="Login", nav_target="Login"
        )
        assert "8 character" in hints["desc"] or "Password" in hints["desc"]


class TestRenderFewShotBlock:
    """Test few-shot example block rendering."""

    @pytest.fixture
    def renderer(self):
        return PromptRenderer()

    def test_empty_examples(self, renderer):
        result = renderer.render_few_shot_block([])
        assert result == ""

    def test_single_example(self, renderer):
        examples = [
            {
                "test_type": "positive",
                "ac_type": "general",
                "description": "Test description",
                "preconditions": "Test preconditions",
                "given": "Given clause",
                "when": "When clause",
                "then": "Then clause",
                "steps": [
                    {"action": "Step 1 action", "expected_result": "Step 1 result"},
                    {"action": "Step 2 action", "expected_result": "Step 2 result"},
                ],
                "expected_outcome": "Expected outcome",
                "component": "Login Screen",
            }
        ]
        result = renderer.render_few_shot_block(examples)
        assert "EXAMPLE 1" in result
        assert "FEW-SHOT" in result
        assert "Test description" in result

    def test_two_examples(self, renderer):
        examples = [
            {"test_type": "positive", "ac_type": "general", "description": "Desc 1", "steps": []},
            {"test_type": "negative", "ac_type": "security", "description": "Desc 2", "steps": []},
        ]
        result = renderer.render_few_shot_block(examples)
        assert "EXAMPLE 1" in result
        assert "EXAMPLE 2" in result

    def test_max_two_examples(self, renderer):
        examples = [
            {"test_type": "positive", "description": f"Desc {i}", "steps": []} for i in range(5)
        ]
        result = renderer.render_few_shot_block(examples)
        assert "EXAMPLE 3" not in result


class TestRenderUserPrompt:
    """Test full user prompt rendering."""

    @pytest.fixture
    def renderer(self):
        return PromptRenderer()

    def test_basic_render(self, renderer):
        req = MockRequirement()
        slot = {
            "test_type": "positive",
            "target_ac": "User can login with valid credentials",
            "title": "Verify -- User can login",
            "ac_type": "general",
        }
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=3,
        )
        assert "REQ-001" in result
        assert "User Login Feature" in result
        assert "Verify -- User can login" in result
        assert "CHAIN-OF-THOUGHT" in result

    def test_gherkin_format(self, renderer):
        req = MockRequirement()
        slot = {
            "test_type": "positive",
            "target_ac": "AC text",
            "title": "Title",
            "ac_type": "general",
        }
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=1,
            tc_format="gherkin",
        )
        assert "GIVEN / WHEN / THEN" in result

    def test_standard_format(self, renderer):
        req = MockRequirement()
        slot = {
            "test_type": "positive",
            "target_ac": "AC text",
            "title": "Title",
            "ac_type": "general",
        }
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=1,
            tc_format="standard",
        )
        assert "GIVEN / WHEN / THEN" not in result

    def test_no_hardcoded_domains(self, renderer):
        """User prompt should not contain hardcoded domain references."""
        req = MockRequirement()
        slot = {
            "test_type": "positive",
            "target_ac": "AC text",
            "title": "Title",
            "ac_type": "general",
        }
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=1,
        )
        assert "cheque" not in result.lower()
        assert "patient registration" not in result.lower()

    def test_with_context(self, renderer):
        req = MockRequirement()
        slot = {"test_type": "negative", "target_ac": "AC", "title": "T", "ac_type": "security"}
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=1,
            context="Related requirement about password policy",
        )
        assert "RELATED REQUIREMENTS" in result

    def test_all_test_types(self, renderer):
        req = MockRequirement()
        for tt in ["positive", "negative", "edge_case"]:
            slot = {"test_type": tt, "target_ac": "AC text", "title": "Title", "ac_type": "general"}
            result = renderer.render_user_prompt(
                requirement=req,
                slot=slot,
                test_number=1,
                total=1,
            )
            assert len(result) > 100  # Non-trivial prompt


class TestOverrideMechanism:
    """Test template override from external directory."""

    def test_override_system_prompt(self, tmp_path):
        override_dir = tmp_path / "overrides"
        override_dir.mkdir()
        (override_dir / "system_prompt.j2").write_text(
            "Custom system prompt for {{ app_description }}. Domain: {{ domain }}."
        )

        renderer = PromptRenderer(override_dir=override_dir)
        result = renderer.render_system_prompt(domain="testing")
        assert "Custom system prompt" in result
        assert "testing application" in result
        # Original RULE content should NOT be present
        assert "RULE 1" not in result
