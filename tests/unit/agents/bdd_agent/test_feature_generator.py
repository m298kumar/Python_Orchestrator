"""Tests for FeatureFileGenerator."""

import pytest
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.agents.bdd_agent.feature_generator import FeatureFileGenerator
from stlc_platform.agents.bdd_agent.gherkin_validator import GherkinValidator


@pytest.fixture
def generator():
    return FeatureFileGenerator()


@pytest.fixture
def validator():
    return GherkinValidator()


def _make_tc(**overrides) -> TestCaseArtifact:
    """Create a TestCaseArtifact with sensible defaults."""
    defaults = {
        "tc_id": "TC-0001",
        "req_id": "REQ-001",
        "title": "Test case title",
        "description": "Test description",
        "preconditions": "System is ready",
        "test_type": "positive",
        "priority": "High",
        "steps": [
            TestStepArtifact(action="Do something", expected_result="Something happens"),
        ],
        "expected_outcome": "Expected outcome achieved",
        "given": "A user on the page",
        "when": "The user performs an action",
        "then": "The system responds correctly",
        "tags": ["test-tag"],
        "category": "Functional",
        "component": "Test Component",
    }
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


class TestGroupByRequirement:
    def test_single_requirement_group(self, generator):
        tcs = [_make_tc(tc_id="TC-1"), _make_tc(tc_id="TC-2")]
        groups = generator._group_by_requirement(tcs)
        assert len(groups) == 1
        assert "REQ-001" in groups
        assert len(groups["REQ-001"]) == 2

    def test_multiple_requirement_groups(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", req_id="REQ-001"),
            _make_tc(tc_id="TC-2", req_id="REQ-002"),
            _make_tc(tc_id="TC-3", req_id="REQ-001"),
        ]
        groups = generator._group_by_requirement(tcs)
        assert len(groups) == 2
        assert len(groups["REQ-001"]) == 2
        assert len(groups["REQ-002"]) == 1

    def test_preserves_insertion_order(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", req_id="REQ-B"),
            _make_tc(tc_id="TC-2", req_id="REQ-A"),
        ]
        groups = generator._group_by_requirement(tcs)
        assert list(groups.keys()) == ["REQ-B", "REQ-A"]


class TestBackgroundExtraction:
    def test_shared_given_becomes_background(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", given="A logged-in user"),
            _make_tc(tc_id="TC-2", given="A logged-in user"),
            _make_tc(tc_id="TC-3", given="A logged-in user"),
        ]
        bg = generator._extract_background(tcs)
        assert bg == "A logged-in user"

    def test_no_background_when_givens_differ(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", given="A logged-in user"),
            _make_tc(tc_id="TC-2", given="An anonymous user"),
            _make_tc(tc_id="TC-3", given="A suspended user"),
        ]
        bg = generator._extract_background(tcs)
        assert bg is None

    def test_no_background_for_single_tc(self, generator):
        tcs = [_make_tc(tc_id="TC-1")]
        bg = generator._extract_background(tcs)
        assert bg is None

    def test_background_threshold_over_50_percent(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", given="Shared given"),
            _make_tc(tc_id="TC-2", given="Shared given"),
            _make_tc(tc_id="TC-3", given="Different given"),
        ]
        # 2/3 = 66% > 50%
        bg = generator._extract_background(tcs)
        assert bg == "Shared given"


class TestScenarioGeneration:
    def test_scenario_has_gwt(self, generator):
        tc = _make_tc(
            given="A user",
            when="The user clicks",
            then="Result is shown",
        )
        scenario = generator._build_scenario(tc)
        assert scenario["given"] == "A user"
        assert scenario["when"] == "The user clicks"
        assert scenario["then"] == "Result is shown"

    def test_scenario_tags_include_test_type(self, generator):
        tc = _make_tc(test_type="negative", priority="Medium")
        scenario = generator._build_scenario(tc)
        assert "@negative" in scenario["tags"]
        assert "@medium_priority" in scenario["tags"]

    def test_background_given_is_skipped(self, generator):
        tc = _make_tc(given="A logged-in user")
        scenario = generator._build_scenario(tc, background_given="A logged-in user")
        assert scenario["given"] == ""


class TestFeatureFileGeneration:
    def test_generates_one_feature_per_req(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1", req_id="REQ-001"),
            _make_tc(tc_id="TC-2", req_id="REQ-002"),
        ]
        features = generator.generate(tcs)
        assert len(features) == 2
        assert features[0].req_id == "REQ-001"
        assert features[1].req_id == "REQ-002"

    def test_feature_has_valid_gherkin(self, generator, validator):
        tcs = [
            _make_tc(tc_id="TC-1"),
            _make_tc(tc_id="TC-2", test_type="negative", title="Negative test"),
        ]
        features = generator.generate(tcs)
        for ff in features:
            result = validator.validate(ff.content)
            assert result.valid, f"Invalid Gherkin in {ff.filename}: {result.errors}"

    def test_feature_filename_is_safe(self, generator):
        tc = _make_tc(component="My Special Page!!")
        features = generator.generate([tc])
        fname = features[0].filename
        assert fname.endswith(".feature")
        assert " " not in fname
        assert "!" not in fname

    def test_feature_scenario_count(self, generator):
        tcs = [
            _make_tc(tc_id="TC-1"),
            _make_tc(tc_id="TC-2", title="Second test"),
        ]
        features = generator.generate(tcs)
        assert features[0].scenario_count == 2


class TestGwtFallback:
    def test_empty_given_falls_back_to_preconditions(self, generator):
        tc = _make_tc(given="", preconditions="System is ready")
        scenario = generator._build_scenario(tc)
        assert scenario["given"] == "System is ready"

    def test_empty_when_falls_back_to_steps(self, generator):
        tc = _make_tc(
            when="",
            steps=[
                TestStepArtifact(action="First step", expected_result=""),
                TestStepArtifact(action="Second step", expected_result=""),
            ],
        )
        scenario = generator._build_scenario(tc)
        assert scenario["when"] == "Second step"

    def test_empty_then_falls_back_to_expected_outcome(self, generator):
        tc = _make_tc(then="", expected_outcome="Order is confirmed")
        scenario = generator._build_scenario(tc)
        assert scenario["then"] == "Order is confirmed"


class TestEscaping:
    def test_hash_prefix_stripped(self, generator):
        result = generator._escape_gherkin("# Some title")
        assert not result.startswith("#")

    def test_unicode_replaced(self, generator):
        result = generator._escape_gherkin("Test \u2014 with em-dash")
        assert "\u2014" not in result
        assert "--" in result
