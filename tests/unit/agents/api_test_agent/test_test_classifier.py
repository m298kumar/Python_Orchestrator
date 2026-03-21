"""Unit tests for the TestClassifier."""

from __future__ import annotations

import pytest

from stlc_platform.agents.api_test_agent.test_classifier import TestClassifier
from stlc_platform.core.contracts import APITestArtifact


@pytest.fixture
def classifier():
    return TestClassifier()


def _make_test_artifact(test_level: str = "api", **overrides) -> APITestArtifact:
    defaults = {
        "framework": "pytest_requests",
        "language": "python",
        "filename": "test.py",
        "content": "pass",
        "test_level": test_level,
    }
    defaults.update(overrides)
    return APITestArtifact(**defaults)


# ── Test Level Classification ────────────────────────────────────────────────


class TestTestLevelClassification:
    def test_api_level_for_happy_path(self, classifier):
        assert classifier.classify_test_level("happy_path") == "api"

    def test_api_level_for_auth(self, classifier):
        assert classifier.classify_test_level("auth") == "api"

    def test_api_level_for_validation(self, classifier):
        assert classifier.classify_test_level("validation") == "api"

    def test_api_level_for_boundary(self, classifier):
        assert classifier.classify_test_level("boundary") == "api"

    def test_integration_for_crud(self, classifier):
        assert classifier.classify_test_level("crud_sequence") == "integration"

    def test_e2e_for_flow(self, classifier):
        assert classifier.classify_test_level("e2e_flow") == "e2e"

    def test_unknown_defaults_to_api(self, classifier):
        assert classifier.classify_test_level("unknown_type") == "api"


# ── Failure Type Classification ──────────────────────────────────────────────


class TestFailureTypeClassification:
    def test_app_bug_for_happy_path(self, classifier):
        assert classifier.classify_failure_type("happy_path") == "app_bug"

    def test_app_bug_for_validation(self, classifier):
        assert classifier.classify_failure_type("validation") == "app_bug"

    def test_unknown_defaults_to_app_bug(self, classifier):
        assert classifier.classify_failure_type("unknown") == "app_bug"


# ── Pyramid Validation ───────────────────────────────────────────────────────


class TestPyramidValidation:
    def test_valid_pyramid_no_warnings(self, classifier):
        tests = [_make_test_artifact("api") for _ in range(9)]
        tests.append(_make_test_artifact("e2e"))
        result = classifier.validate_pyramid(tests)
        assert result["total"] == 10
        assert len(result["warnings"]) == 0

    def test_warns_when_e2e_exceeds_20_percent(self, classifier):
        tests = [_make_test_artifact("api") for _ in range(3)]
        tests.extend(_make_test_artifact("e2e") for _ in range(3))
        result = classifier.validate_pyramid(tests)
        assert len(result["warnings"]) == 1
        assert "20%" in result["warnings"][0]

    def test_empty_tests_returns_empty(self, classifier):
        result = classifier.validate_pyramid([])
        assert result["total"] == 0
        assert len(result["warnings"]) == 0

    def test_distribution_counts(self, classifier):
        tests = [
            _make_test_artifact("api"),
            _make_test_artifact("api"),
            _make_test_artifact("integration"),
        ]
        result = classifier.validate_pyramid(tests)
        assert result["distribution"]["api"] == 2
        assert result["distribution"]["integration"] == 1
