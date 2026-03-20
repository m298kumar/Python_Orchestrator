"""Tests for the deterministic test case synthesiser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.agents.requirements_agent.synthesiser import (
    clean_duration,
    extract_steps,
    make_description,
    make_gwt,
    make_preconditions,
    synthesise_steps,
    synthesise_tc,
)


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    title: str = "User Login"
    description: str = "User should be able to log in"
    category: str = "Authentication"
    acceptance_criteria: List[str] = field(default_factory=lambda: ["User can login with valid creds"])


class TestMakeGWT:
    """Test Given/When/Then generation."""

    def test_positive(self):
        g, w, t = make_gwt("User can log in", "positive", "Login Feature")
        assert "eligible user" in g.lower()
        assert "exercise" in w.lower()
        assert "observable result" in t.lower()

    def test_negative_ui_behaviour(self):
        g, w, t = make_gwt("Button displays success", "negative", "Feature", "ui_behaviour")
        assert "NOT met" in g

    def test_negative_timing(self):
        g, w, t = make_gwt("Response within 3s", "negative", "Feature", "timing")
        assert "delay" in g.lower()

    def test_negative_data_valid(self):
        g, w, t = make_gwt("Field must be numeric", "negative", "Feature", "data_valid")
        assert "invalid" in g.lower()

    def test_negative_security(self):
        g, w, t = make_gwt("Must use MFA", "negative", "Feature", "security")
        assert "bypass" in g.lower()

    def test_negative_general(self):
        g, w, t = make_gwt("Some criterion", "negative", "Feature", "general")
        assert "eligibility" in g.lower()

    def test_edge_case(self):
        g, w, t = make_gwt("Max 100 chars", "edge_case", "Feature")
        assert "boundary" in g.lower()


class TestMakeDescription:
    def test_positive(self):
        d = make_description("user can login", "positive")
        assert "Positive test" in d
        assert "user can login" in d

    def test_negative(self):
        d = make_description("invalid input", "negative")
        assert "Negative test" in d

    def test_edge_case(self):
        d = make_description("max 100", "edge_case")
        assert "Boundary test" in d


class TestMakePreconditions:
    def test_positive(self):
        p = make_preconditions("AC text", "positive", "Auth", "Login")
        assert "eligibility" in p.lower()
        assert "Login" in p

    def test_negative_types(self):
        for ac_type in ["ui_behaviour", "timing", "data_valid", "security", "general"]:
            p = make_preconditions("AC text", "negative", "Cat", "Title", ac_type)
            assert len(p) > 30


class TestSynthesiseSteps:
    def test_returns_five_steps(self):
        for tt in ["positive", "negative", "edge_case"]:
            steps = synthesise_steps("Some AC", tt, "Title", "general")
            assert len(steps) == 5
            assert all(isinstance(s, TestStepArtifact) for s in steps)

    def test_positive_timing(self):
        steps = synthesise_steps("Response within 3s", "positive", "Feature", "timing")
        assert any("timer" in s.action.lower() or "time" in s.action.lower() for s in steps)

    def test_negative_data_valid(self):
        steps = synthesise_steps("Must be numeric", "negative", "Feature", "data_valid")
        assert any("invalid" in s.action.lower() for s in steps)


class TestExtractSteps:
    def test_valid_steps_kept(self):
        raw = [
            {"action": "Log in with valid credentials to the app", "expected_result": "Home loads"},
            {"action": "Navigate to the settings screen in the app", "expected_result": "Settings shown"},
            {"action": "Click save button on the settings page", "expected_result": "Settings saved"},
        ]
        steps = extract_steps(raw, "AC", "positive", "Title")
        assert len(steps) == 3

    def test_generic_steps_filtered(self):
        raw = [
            {"action": "Perform the action", "expected_result": "Result"},
            {"action": "Trigger the feature", "expected_result": "Result"},
        ]
        steps = extract_steps(raw, "AC", "positive", "Title")
        assert len(steps) == 5  # Fell back to synthesis

    def test_string_steps_handled(self):
        raw = ["Log in with valid credentials to the test account", "Navigate to the dashboard screen"]
        steps = extract_steps(raw, "AC", "positive", "Title")
        assert len(steps) >= 2


class TestSynthesiseTC:
    def test_returns_valid_artifact(self):
        req = MockRequirement()
        slot = {
            "test_type": "positive",
            "target_ac": "User can log in with valid credentials",
            "title": "Verify -- User can log in",
            "ac_type": "general",
        }
        tc = synthesise_tc(req, slot, 1)
        assert isinstance(tc, TestCaseArtifact)
        assert tc.tc_id == "TC-0001"
        assert tc.req_id == "REQ-001"
        assert len(tc.steps) == 5
        assert tc.test_type == "positive"


class TestCleanDuration:
    def test_iso_format(self):
        assert clean_duration("PT1H30M") == "90"

    def test_minutes_only(self):
        assert clean_duration("PT5M") == "5"

    def test_plain_number(self):
        assert clean_duration("10") == "10"

    def test_invalid_defaults_to_5(self):
        assert clean_duration("unknown") == "5"

    def test_zero_defaults_to_5(self):
        assert clean_duration("0") == "5"
