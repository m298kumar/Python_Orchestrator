"""
Tests for Scenario Outline detection and generation.
=====================================================
Validates that FeatureFileGenerator correctly detects parameterizable
test cases and merges them into Scenario Outline + Examples tables.
"""

from __future__ import annotations


from stlc_platform.agents.bdd_agent.feature_generator import FeatureFileGenerator
from stlc_platform.core.contracts import TestCaseArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tc(
    tc_id: str,
    req_id: str = "REQ-001",
    title: str = "Test",
    given: str = "",
    when: str = "",
    then: str = "",
    **kwargs,
) -> TestCaseArtifact:
    """Shorthand factory for TestCaseArtifact."""
    return TestCaseArtifact(
        tc_id=tc_id,
        req_id=req_id,
        title=title,
        description=kwargs.get("description", ""),
        preconditions=kwargs.get("preconditions", ""),
        test_type=kwargs.get("test_type", "functional"),
        priority=kwargs.get("priority", "Medium"),
        given=given,
        when=when,
        then=then,
    )


# ---------------------------------------------------------------------------
# 1. Two TCs with same structure but different quoted values -> Outline
# ---------------------------------------------------------------------------

class TestQuotedValueOutline:
    """Quoted string differences should produce a Scenario Outline."""

    def test_two_cases_become_outline(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='user "admin" is on login page',
                 when='enters password "Pass123"',
                 then='sees the "dashboard" page'),
            _tc("TC-2", given='user "guest" is on login page',
                 when='enters password "Guest456"',
                 then='sees the "welcome" page'),
        ]
        features = gen.generate(cases)
        assert len(features) == 1
        content = features[0].content

        assert "Scenario Outline:" in content
        assert "Scenario:" not in content or "Scenario Outline:" in content.split("Scenario:")[0] is not None
        # Placeholders in steps
        assert "<param_1>" in content
        assert "<param_2>" in content
        # Examples table present
        assert "Examples:" in content
        assert "admin" in content
        assert "guest" in content
        assert "Pass123" in content
        assert "Guest456" in content


# ---------------------------------------------------------------------------
# 2. TCs with different structures stay as separate Scenarios
# ---------------------------------------------------------------------------

class TestDifferentStructuresStaySeparate:
    """Test cases with non-matching skeletons remain individual Scenarios."""

    def test_different_steps_no_outline(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='user is on login page',
                 when='enters valid credentials',
                 then='sees the dashboard'),
            _tc("TC-2", given='user is on settings page',
                 when='clicks save button',
                 then='sees success message'),
        ]
        features = gen.generate(cases)
        assert len(features) == 1
        content = features[0].content

        assert "Scenario Outline:" not in content
        assert "Examples:" not in content


# ---------------------------------------------------------------------------
# 3. Examples table has correct header and rows
# ---------------------------------------------------------------------------

class TestExamplesTable:
    """The rendered Examples table must have correct header + data rows."""

    def test_examples_header_and_rows(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='user "admin" is on login page',
                 when='enters password "Pass123"',
                 then='sees message "Welcome admin"'),
            _tc("TC-2", given='user "editor" is on login page',
                 when='enters password "Edit789"',
                 then='sees message "Welcome editor"'),
            _tc("TC-3", given='user "viewer" is on login page',
                 when='enters password "View000"',
                 then='sees message "Welcome viewer"'),
        ]
        features = gen.generate(cases)
        content = features[0].content

        assert "Examples:" in content
        # Header should list param names
        assert "| param_1 |" in content
        assert "| param_2 |" in content
        assert "| param_3 |" in content
        # All three value rows
        assert "| admin |" in content or "admin" in content
        assert "| editor |" in content or "editor" in content
        assert "| viewer |" in content or "viewer" in content
        # 3 data rows (excluding header)
        examples_section = content.split("Examples:")[1]
        pipe_rows = [
            line.strip()
            for line in examples_section.splitlines()
            if line.strip().startswith("|")
        ]
        # 1 header + 3 data rows = 4
        assert len(pipe_rows) == 4


# ---------------------------------------------------------------------------
# 4. GWT steps use <param> placeholders
# ---------------------------------------------------------------------------

class TestPlaceholdersInSteps:
    """Scenario Outline steps must contain angle-bracket placeholders."""

    def test_placeholders_replace_quoted(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='user "admin" is on login page',
                 when='enters password "Pass123"',
                 then='sees the dashboard'),
            _tc("TC-2", given='user "guest" is on login page',
                 when='enters password "Guest456"',
                 then='sees the dashboard'),
        ]
        features = gen.generate(cases)
        content = features[0].content

        # Steps should use placeholders, not literal values
        assert 'user <param_1> is on login page' in content
        assert 'enters password <param_2>' in content
        # Literal quoted values should NOT appear in steps (only in Examples)
        lines_before_examples = content.split("Examples:")[0]
        assert '"admin"' not in lines_before_examples
        assert '"guest"' not in lines_before_examples


# ---------------------------------------------------------------------------
# 5. Single TC stays a regular Scenario (no outline)
# ---------------------------------------------------------------------------

class TestSingleCaseNoOutline:
    """A lone test case must remain a plain Scenario."""

    def test_single_tc_not_outline(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='user "admin" is on login page',
                 when='enters password "Pass123"',
                 then='sees the dashboard'),
        ]
        features = gen.generate(cases)
        content = features[0].content

        assert "Scenario Outline:" not in content
        assert "Examples:" not in content
        assert "Scenario:" in content


# ---------------------------------------------------------------------------
# 6. Numeric parameterization
# ---------------------------------------------------------------------------

class TestNumericParameterization:
    """Standalone numbers should be parameterized into <value_N>."""

    def test_numeric_values_become_outline(self):
        gen = FeatureFileGenerator()
        cases = [
            _tc("TC-1", given='the cart has 3 items',
                 when='user removes 1 item',
                 then='cart shows 2 items'),
            _tc("TC-2", given='the cart has 5 items',
                 when='user removes 2 item',
                 then='cart shows 3 items'),
        ]
        features = gen.generate(cases)
        content = features[0].content

        assert "Scenario Outline:" in content
        assert "<value_" in content
        assert "Examples:" in content
        # Numeric values in the Examples table
        examples_section = content.split("Examples:")[1]
        assert "3" in examples_section
        assert "5" in examples_section

    def test_numeric_normalize_step_directly(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step("the cart has 10 items worth 99.5 dollars")
        assert "<value_1>" in skeleton
        assert "<value_2>" in skeleton
        assert ("value_1", "10") in params
        assert ("value_2", "99.5") in params


# ---------------------------------------------------------------------------
# 7. Mixed — some outlineable, some not
# ---------------------------------------------------------------------------

class TestMixedOutlineAndRegular:
    """A mix of matching and non-matching TCs under the same req_id."""

    def test_mixed_scenarios(self):
        gen = FeatureFileGenerator()
        cases = [
            # These two share a skeleton -> Outline
            _tc("TC-1", given='user "admin" is on login page',
                 when='enters password "Pass123"',
                 then='sees the dashboard'),
            _tc("TC-2", given='user "guest" is on login page',
                 when='enters password "Guest456"',
                 then='sees the dashboard'),
            # This one has a different structure -> regular Scenario
            _tc("TC-3", given='user is on the registration page',
                 when='fills in all required fields',
                 then='account is created successfully'),
        ]
        features = gen.generate(cases)
        content = features[0].content

        assert "Scenario Outline:" in content
        assert "Examples:" in content
        # The third TC should be a regular Scenario
        # Count occurrences: 1 Scenario Outline + 1 Scenario
        assert features[0].scenario_count == 2


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

class TestNormalizeStepMethod:
    """Unit tests for the _normalize_step helper."""

    def test_quoted_strings_replaced(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step('user "admin" logs in with "secret"')
        assert skeleton == "user <param_1> logs in with <param_2>"
        assert params == [("param_1", "admin"), ("param_2", "secret")]

    def test_single_quoted_strings(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step("user 'admin' logs in")
        assert skeleton == "user <param_1> logs in"
        assert params == [("param_1", "admin")]

    def test_no_params_returns_identity(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step("user clicks the submit button")
        assert skeleton == "user clicks the submit button"
        assert params == []

    def test_mixed_quoted_and_numeric(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step('user "alice" buys 3 apples')
        assert "<param_1>" in skeleton
        assert "<value_1>" in skeleton
        assert ("param_1", "alice") in params
        assert ("value_1", "3") in params

    def test_negative_numbers(self):
        gen = FeatureFileGenerator()
        skeleton, params = gen._normalize_step("balance is -50 dollars")
        assert "<value_1>" in skeleton
        assert ("value_1", "-50") in params
