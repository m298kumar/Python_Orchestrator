"""Tests for StepParser."""

import pytest
from stlc_platform.core.contracts import FeatureFileArtifact
from stlc_platform.agents.bdd_agent.step_parser import StepParser, ParsedStep


@pytest.fixture
def parser():
    return StepParser()


def _make_feature(content: str, filename: str = "test.feature") -> FeatureFileArtifact:
    return FeatureFileArtifact(
        req_id="REQ-001",
        filename=filename,
        content=content,
        scenario_count=1,
    )


SAMPLE_FEATURE = """\
Feature: Sample

  Scenario: Basic scenario
    Given A user on the page
    When The user enters 'hello' in the search field
    Then Results are displayed

  Scenario: Another scenario
    Given A user on the page
    And The user is logged in
    When The user enters 'world' in the search field
    Then Results are displayed
    And Results contain at least 1 item
"""


class TestExtractSteps:
    def test_extracts_all_step_types(self, parser):
        feature = _make_feature(SAMPLE_FEATURE)
        steps = parser.extract_steps([feature])
        keywords = {s.keyword for s in steps}
        assert "given" in keywords
        assert "when" in keywords
        assert "then" in keywords

    def test_and_assigned_to_preceding_keyword(self, parser):
        feature = _make_feature(SAMPLE_FEATURE)
        steps = parser.extract_steps([feature])
        # "And The user is logged in" follows "Given", so keyword = "given"
        and_step = [s for s in steps if "logged in" in s.text]
        assert len(and_step) == 1
        assert and_step[0].keyword == "given"

    def test_source_file_populated(self, parser):
        feature = _make_feature(SAMPLE_FEATURE, filename="my_test.feature")
        steps = parser.extract_steps([feature])
        assert all(s.source_file == "my_test.feature" for s in steps)

    def test_extracts_from_multiple_features(self, parser):
        f1 = _make_feature(SAMPLE_FEATURE, "f1.feature")
        f2 = _make_feature("""\
Feature: Another

  Scenario: Simple
    Given A different context
    When Action taken
    Then Expected result
""", "f2.feature")
        steps = parser.extract_steps([f1, f2])
        sources = {s.source_file for s in steps}
        assert "f1.feature" in sources
        assert "f2.feature" in sources


class TestDeduplication:
    def test_exact_duplicates_removed(self, parser):
        steps = [
            ParsedStep(keyword="given", text="A user on the page"),
            ParsedStep(keyword="given", text="A user on the page"),
        ]
        unique = parser.deduplicate(steps)
        assert len(unique) == 1

    def test_case_insensitive_dedup(self, parser):
        steps = [
            ParsedStep(keyword="given", text="A User On The Page"),
            ParsedStep(keyword="given", text="a user on the page"),
        ]
        unique = parser.deduplicate(steps)
        assert len(unique) == 1

    def test_different_keywords_kept_separate(self, parser):
        steps = [
            ParsedStep(keyword="given", text="Something"),
            ParsedStep(keyword="when", text="Something"),
        ]
        unique = parser.deduplicate(steps)
        assert len(unique) == 2


class TestParameterization:
    def test_quoted_strings_parameterized(self, parser):
        steps = [
            ParsedStep(keyword="when", text="The user enters 'hello' in the search field"),
            ParsedStep(keyword="when", text="The user enters 'world' in the search field"),
        ]
        result = parser.parameterize(steps)
        parameterized = [s for s in result if s.params]
        assert len(parameterized) == 1
        assert "{" in parameterized[0].pattern

    def test_single_step_not_parameterized(self, parser):
        steps = [
            ParsedStep(keyword="given", text="A user with name 'Alice'"),
        ]
        result = parser.parameterize(steps)
        assert len(result) == 1
        # Single step should not be parameterized
        assert result[0].pattern == "A user with name 'Alice'"

    def test_no_quotes_no_params(self, parser):
        steps = [
            ParsedStep(keyword="given", text="A logged-in user"),
        ]
        result = parser.parameterize(steps)
        assert len(result) == 1
        assert result[0].params == []
