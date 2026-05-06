"""Tests for the test case sanitiser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from stlc_platform.agents.requirements_agent.sanitiser import (
    SanitiserConfig,
    TestCaseSanitiser,
)
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    title: str = "User Login"
    description: str = "User should be able to log in"
    category: str = "Authentication"
    acceptance_criteria: List[str] = field(
        default_factory=lambda: ["User can login with valid creds"]
    )


def _make_tc(**overrides) -> TestCaseArtifact:
    """Create a TestCaseArtifact with defaults that can be overridden."""
    defaults = dict(
        tc_id="TC-0001",
        req_id="REQ-001",
        title="Verify -- User can login",
        description="Positive test -- verifies that user can login with valid credentials",
        preconditions="Application installed; tester has valid login credentials for test account setup",
        test_type="positive",
        priority="High",
        steps=[
            TestStepArtifact(
                action="Open the application and navigate to login screen",
                expected_result="Login screen is displayed",
            ),
            TestStepArtifact(
                action="Enter valid username 'testuser' in the username field",
                expected_result="Username is accepted",
            ),
            TestStepArtifact(
                action="Enter valid password and click the Login button",
                expected_result="User is logged in successfully",
            ),
        ],
        expected_outcome="User is successfully logged in and sees the home dashboard",
        tags=["authentication", "positive", "req-001"],
        category="Authentication",
        component="Login Screen",
        given="An eligible user with valid credentials is on the login page",
        when="The user enters valid credentials and clicks Login",
        then="The system logs the user in and displays the home dashboard",
        estimated_duration="5",
    )
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


def _make_slot(**overrides) -> dict:
    defaults = {
        "test_type": "positive",
        "target_ac": "User can login with valid credentials and see the home dashboard",
        "title": "Verify -- User can login",
        "ac_type": "general",
    }
    defaults.update(overrides)
    return defaults


class TestSanitiserDetectionHelpers:
    """Test individual detection methods."""

    def test_is_instruction_text(self):
        s = TestCaseSanitiser()
        assert s._is_instruction_text("one sentence explaining the test purpose") is True
        assert s._is_instruction_text("User logs in successfully") is False

    def test_has_loop(self):
        s = TestCaseSanitiser()
        looped = "The system works.\nThe system works.\nThe system works."
        assert s._has_loop(looped) is True
        assert s._has_loop("Unique sentence one. Different sentence two.") is False

    def test_has_python_leakage(self):
        s = TestCaseSanitiser()
        assert s._has_python_leakage("{'title': 'bad'}") is True
        assert s._has_python_leakage("User logs in") is False

    def test_is_generic_step(self):
        s = TestCaseSanitiser()
        assert s._is_generic_step("Perform the action") is True
        assert s._is_generic_step("Click the Submit button on the Registration form") is False
        assert s._is_generic_step("short") is True

    def test_is_garbled(self):
        s = TestCaseSanitiser()
        assert s._is_garbled("Hig h") is True
        assert s._is_garbled("nega ti v e") is True
        assert s._is_garbled("Valid given clause text") is False

    def test_gwt_is_bad_empty(self):
        s = TestCaseSanitiser()
        assert s._gwt_is_bad("") is True
        assert s._gwt_is_bad("given") is True
        assert s._gwt_is_bad("short") is True

    def test_gwt_is_bad_instruction(self):
        s = TestCaseSanitiser()
        assert s._gwt_is_bad("Fill each field with concrete values") is True

    def test_gwt_is_bad_valid(self):
        s = TestCaseSanitiser()
        assert s._gwt_is_bad("An eligible user is logged in with valid credentials") is False


class TestSanitiserPipeline:
    """Test the full 7-step sanitisation pipeline."""

    def test_good_tc_passes_through(self):
        """A well-formed TC should not be changed."""
        s = TestCaseSanitiser()
        tc = _make_tc()
        slot = _make_slot()
        req = MockRequirement()

        result = s.sanitise(tc, slot, req)
        assert result.description == tc.description
        assert result.preconditions == tc.preconditions
        assert len(result.steps) == 3  # Original steps kept
        assert result.expected_outcome == tc.expected_outcome

    def test_bad_description_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(description="fill each field with values")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert "Positive test" in result.description

    def test_short_description_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(description="too short")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert len(result.description) > 15

    def test_bad_preconditions_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(preconditions="{'title': 'leaked json'}")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert (
            "eligibility" in result.preconditions.lower()
            or "installed" in result.preconditions.lower()
        )

    def test_generic_steps_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(
            steps=[
                TestStepArtifact(action="Perform the action", expected_result="Check result"),
                TestStepArtifact(action="Trigger the feature", expected_result="Observe"),
            ]
        )
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert len(result.steps) == 5  # Synthesised steps

    def test_trivial_outcome_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(expected_outcome="pass")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert result.expected_outcome != "pass"

    def test_garbled_gwt_replaced(self):
        s = TestCaseSanitiser()
        tc = _make_tc(given="Hig h", when="nega ti v e", then="Mediu m")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert "Hig h" not in result.given
        assert len(result.given) > 20

    def test_garbage_tags_cleaned(self):
        s = TestCaseSanitiser()
        tc = _make_tc(tags=["123", "path-to-file", "___", "true", "valid-tag"])
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert "valid-tag" in result.tags
        assert "123" not in result.tags
        assert "true" not in result.tags

    def test_empty_tags_get_fallback(self):
        s = TestCaseSanitiser()
        tc = _make_tc(tags=[])
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert len(result.tags) >= 2  # At least category + test_type

    def test_component_resolved(self):
        s = TestCaseSanitiser()
        tc = _make_tc(component="the application")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert result.component != "the application"


class TestPostProcessors:
    """Test custom post-processor pipeline."""

    def test_post_processor_called(self):
        def uppercase_title(tc: TestCaseArtifact) -> TestCaseArtifact:
            data = tc.model_dump()
            data["title"] = data["title"].upper()
            return TestCaseArtifact(**data)

        s = TestCaseSanitiser(post_processors=[uppercase_title])
        tc = _make_tc()
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert result.title == tc.title.upper()

    def test_multiple_post_processors(self):
        calls = []

        def processor_a(tc):
            calls.append("a")
            return tc

        def processor_b(tc):
            calls.append("b")
            return tc

        s = TestCaseSanitiser(post_processors=[processor_a, processor_b])
        s.sanitise(_make_tc(), _make_slot(), MockRequirement())
        assert calls == ["a", "b"]

    def test_add_post_processor(self):
        calls = []
        s = TestCaseSanitiser()
        s.add_post_processor(lambda tc: (calls.append("called"), tc)[1])
        s.sanitise(_make_tc(), _make_slot(), MockRequirement())
        assert "called" in calls


class TestCustomConfig:
    """Test configurable sanitisation rules."""

    def test_custom_instruction_phrases(self):
        config = SanitiserConfig(instruction_phrases=["custom bad phrase"])
        s = TestCaseSanitiser(config=config)
        assert s._is_instruction_text("this has custom bad phrase in it") is True
        assert s._is_instruction_text("fill each field") is False  # Default phrase not matched

    def test_custom_trivial_outcomes(self):
        config = SanitiserConfig(trivial_outcomes={"custom_trivial"})
        s = TestCaseSanitiser(config=config)
        tc = _make_tc(expected_outcome="custom_trivial")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert result.expected_outcome != "custom_trivial"

    def test_custom_min_lengths(self):
        config = SanitiserConfig(min_description_length=50)
        s = TestCaseSanitiser(config=config)
        tc = _make_tc(description="Short but valid description")
        result = s.sanitise(tc, _make_slot(), MockRequirement())
        assert result.description != "Short but valid description"
