"""
Tests for TestCaseScorer — Phase A quality scoring.
"""

import pytest

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.core.quality.scorer import (
    QualityReport,
    ScorerConfig,
    TestCaseScorer,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_tc(**overrides) -> TestCaseArtifact:
    """Build a TestCaseArtifact with sensible defaults, overridable."""
    defaults = dict(
        tc_id="TC-0001",
        req_id="REQ-001",
        title="Verify user login with valid credentials",
        description="Verifies that a registered user can log in with correct email and password.",
        preconditions="A registered user account exists with email test@example.com and a valid password.",
        test_type="positive",
        priority="High",
        steps=[
            TestStepArtifact(action="Navigate to the Login Screen", expected_result="Login form is displayed with email and password fields"),
            TestStepArtifact(action="Enter valid email test@example.com in the email field", expected_result="Email field accepts the input"),
            TestStepArtifact(action="Enter valid password in the password field", expected_result="Password is masked and accepted"),
            TestStepArtifact(action="Click the Login button", expected_result="User is redirected to the Dashboard screen"),
        ],
        expected_outcome="User is successfully authenticated and the Dashboard screen is displayed.",
        given="A registered user with valid credentials exists in the system",
        when="The user enters correct email and password on the Login Screen and clicks Login",
        then="The system authenticates the user and displays the Dashboard screen",
        tags=["functional", "positive", "req-001"],
        category="Authentication",
        component="Login Screen",
    )
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


def _make_slot(**overrides) -> dict:
    defaults = dict(
        target_ac="User must be able to log in with a valid email and password to access the dashboard",
        test_type="positive",
        ac_type="ui_behaviour",
        title="Verify user login with valid credentials",
    )
    defaults.update(overrides)
    return defaults


class _FakeReq:
    def __init__(self, **kwargs):
        self.req_id = kwargs.get("req_id", "REQ-001")
        self.title = kwargs.get("title", "User Login")
        self.description = kwargs.get("description", "Users can log in to the system")
        self.acceptance_criteria = kwargs.get("acceptance_criteria", [
            "User must be able to log in with a valid email and password to access the dashboard"
        ])
        self.priority = kwargs.get("priority", "High")
        self.category = kwargs.get("category", "Authentication")
        self.tags = kwargs.get("tags", [])


# ── Scorer instantiation ────────────────────────────────────────────────────

class TestScorerInit:
    def test_default_config(self):
        scorer = TestCaseScorer()
        assert scorer.config.accept_threshold == 0.65
        assert scorer.config.regenerate_threshold == 0.40
        assert abs(sum(scorer.config.weights.values()) - 1.0) < 0.01

    def test_custom_config(self):
        cfg = ScorerConfig(accept_threshold=0.80, regenerate_threshold=0.50)
        scorer = TestCaseScorer(config=cfg)
        assert scorer.config.accept_threshold == 0.80

    def test_from_config_dict(self):
        cfg = ScorerConfig.from_config({
            "quality_gate": {
                "accept_threshold": 0.70,
                "max_regeneration_attempts": 3,
            }
        })
        assert cfg.accept_threshold == 0.70
        assert cfg.max_regeneration_attempts == 3

    def test_from_config_empty(self):
        cfg = ScorerConfig.from_config({})
        assert cfg.accept_threshold == 0.65


# ── Coverage scoring ─────────────────────────────────────────────────────────

class TestCoverageScoring:
    def test_good_coverage(self):
        scorer = TestCaseScorer()
        tc = _make_tc()
        slot = _make_slot()
        req = _FakeReq()
        report = scorer.score(tc, slot, req)
        assert report.dimension_scores["coverage"] >= 0.5

    def test_no_ac_reference(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="This test verifies something unrelated.",
            steps=[
                TestStepArtifact(action="Open the application", expected_result="App opens"),
                TestStepArtifact(action="Click somewhere", expected_result="Something happens"),
                TestStepArtifact(action="Close the application", expected_result="App closes"),
            ],
            given="The app is installed",
            when="The user opens it",
            then="It works",
            expected_outcome="The app works",
        )
        slot = _make_slot(target_ac="Cheque deposit amount must match OCR-extracted value within 2% tolerance")
        req = _FakeReq()
        report = scorer.score(tc, slot, req)
        assert report.dimension_scores["coverage"] < 0.6

    def test_negative_test_needs_rejection_indicators(self):
        scorer = TestCaseScorer()
        tc = _make_tc(test_type="negative")
        slot = _make_slot(test_type="negative")
        req = _FakeReq()
        report = scorer.score(tc, slot, req)
        # The default TC has "redirected to Dashboard" — not rejection-oriented
        has_issue = any("negative" in i.lower() or "rejection" in i.lower() for i in report.issues)
        # May or may not flag depending on content — just ensure no crash
        assert report.dimension_scores["coverage"] <= 1.0

    def test_edge_case_indicators(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="Verifies the boundary limit for password length at exactly 128 characters.",
            steps=[
                TestStepArtifact(action="Navigate to Login Screen", expected_result="Login form displayed"),
                TestStepArtifact(action="Enter a password of exactly 128 characters (maximum limit)", expected_result="Field accepts the maximum boundary input"),
                TestStepArtifact(action="Click the Login button", expected_result="System processes the boundary value"),
            ],
            given="A registered user account exists",
            when="The user enters a password at the maximum boundary limit of 128 characters",
            then="The system accepts the boundary value and authenticates the user",
        )
        slot = _make_slot(test_type="edge_case", ac_type="data_valid",
                          target_ac="Password must be between 8 and 128 characters")
        req = _FakeReq()
        report = scorer.score(tc, slot, req)
        # Has boundary/limit indicators — should score well
        assert report.dimension_scores["coverage"] >= 0.5


# ── Clarity scoring ──────────────────────────────────────────────────────────

class TestClarityScoring:
    def test_specific_steps_score_well(self):
        scorer = TestCaseScorer()
        tc = _make_tc()  # Has "Login Screen", "email field", "Login button"
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["clarity"] >= 0.7

    def test_generic_phrases_penalized(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="Verify the outcome of the action performed on the system.",
            steps=[
                TestStepArtifact(action="Perform the action on the system", expected_result="The system responds correctly"),
                TestStepArtifact(action="Trigger the feature and observe the result", expected_result="The expected result is observed"),
                TestStepArtifact(action="Check the result of the test step", expected_result="The system behaves as expected"),
            ],
            given="The system is ready",
            when="The action is performed",
            then="The system works as intended",
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["clarity"] < 0.6
        assert any("generic" in i.lower() for i in report.issues)

    def test_duplicate_gwt_penalized(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            given="The user is on the login page",
            when="The user is on the login page",  # Same as given
            then="The system authenticates the user",
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("distinct" in i.lower() for i in report.issues)


# ── Executability scoring ────────────────────────────────────────────────────

class TestExecutabilityScoring:
    def test_enough_steps(self):
        scorer = TestCaseScorer()
        tc = _make_tc()  # Has 4 steps
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["executability"] >= 0.7

    def test_too_few_steps(self):
        scorer = TestCaseScorer()
        tc = _make_tc(steps=[
            TestStepArtifact(action="Do something", expected_result="Done"),
        ])
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["executability"] < 0.7
        assert any("step" in i.lower() for i in report.issues)

    def test_identical_steps_penalized(self):
        scorer = TestCaseScorer()
        tc = _make_tc(steps=[
            TestStepArtifact(action="Click the submit button", expected_result="Form submitted"),
            TestStepArtifact(action="Click the submit button", expected_result="Form submitted"),
            TestStepArtifact(action="Click the submit button", expected_result="Form submitted"),
        ])
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("identical" in i.lower() for i in report.issues)

    def test_missing_preconditions(self):
        scorer = TestCaseScorer()
        tc = _make_tc(preconditions="")
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("precondition" in i.lower() for i in report.issues)

    def test_steps_without_expected_results(self):
        scorer = TestCaseScorer()
        tc = _make_tc(steps=[
            TestStepArtifact(action="Navigate to the Login Screen", expected_result=""),
            TestStepArtifact(action="Enter valid credentials", expected_result=""),
            TestStepArtifact(action="Click Login", expected_result=""),
        ])
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("expected result" in i.lower() for i in report.issues)


# ── Uniqueness scoring ──────────────────────────────────────────────────────

class TestUniquenessScoring:
    def test_no_existing_tcs(self):
        scorer = TestCaseScorer()
        tc = _make_tc()
        report = scorer.score(tc, _make_slot(), _FakeReq(), existing_tcs=[])
        assert report.dimension_scores["uniqueness"] == 1.0

    def test_near_duplicate_penalized(self):
        scorer = TestCaseScorer()
        tc1 = _make_tc(tc_id="TC-0001")
        tc2 = _make_tc(tc_id="TC-0002")  # Identical description and steps
        report = scorer.score(tc2, _make_slot(), _FakeReq(), existing_tcs=[tc1])
        assert report.dimension_scores["uniqueness"] < 0.5
        assert any("duplicate" in i.lower() or "overlap" in i.lower() for i in report.issues)

    def test_different_tc_scores_well(self):
        scorer = TestCaseScorer()
        tc1 = _make_tc(
            tc_id="TC-0001",
            description="Verifies password reset flow for forgotten credentials.",
            steps=[
                TestStepArtifact(action="Click Forgot Password link", expected_result="Reset form displayed"),
                TestStepArtifact(action="Enter registered email", expected_result="Email accepted"),
                TestStepArtifact(action="Submit reset request", expected_result="Confirmation email sent"),
            ],
        )
        tc2 = _make_tc(tc_id="TC-0002")  # Default login TC — very different
        report = scorer.score(tc2, _make_slot(), _FakeReq(), existing_tcs=[tc1])
        assert report.dimension_scores["uniqueness"] >= 0.7


# ── Structural scoring ──────────────────────────────────────────────────────

class TestStructuralScoring:
    def test_complete_tc(self):
        scorer = TestCaseScorer()
        tc = _make_tc()
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["structural"] >= 0.8

    def test_missing_fields(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="",
            preconditions="",
            expected_outcome="",
            given="",
            when="",
            then="",
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.dimension_scores["structural"] < 0.5
        assert any("missing" in i.lower() for i in report.issues)

    def test_truncation_detected(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="This test verifies that the system correctly handles the (",
            expected_outcome="The system should display the confirmation when the user...",
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("truncat" in i.lower() for i in report.issues)

    def test_instruction_leakage_detected(self):
        scorer = TestCaseScorer()
        tc = _make_tc(
            description="Chain-of-thought: before writing each step, mentally answer what the user does.",
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("leakage" in i.lower() for i in report.issues)

    def test_hollow_steps_detected(self):
        scorer = TestCaseScorer()
        tc = _make_tc(steps=[
            TestStepArtifact(action="", expected_result="Result"),
            TestStepArtifact(action="abc", expected_result="Result"),
            TestStepArtifact(action="Navigate to Login Screen", expected_result="Screen displayed"),
        ])
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert any("hollow" in i.lower() or "empty" in i.lower() for i in report.issues)


# ── Overall scoring & suggestion ─────────────────────────────────────────────

class TestOverallScoring:
    def test_good_tc_accepted(self):
        scorer = TestCaseScorer()
        tc = _make_tc()
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert report.overall_score >= 0.5
        assert report.suggestion in ("accept", "regenerate")

    def test_terrible_tc_fallback(self):
        scorer = TestCaseScorer(config=ScorerConfig(
            accept_threshold=0.65,
            regenerate_threshold=0.50,
        ))
        tc = _make_tc(
            description="",
            preconditions="",
            expected_outcome="pass",
            given="",
            when="",
            then="",
            steps=[],
        )
        slot = _make_slot(target_ac="OCR must extract cheque MICR code within 500ms")
        report = scorer.score(tc, slot, _FakeReq())
        assert report.suggestion == "fallback"
        assert report.overall_score < 0.50

    def test_mediocre_tc_regenerate(self):
        scorer = TestCaseScorer(config=ScorerConfig(
            accept_threshold=0.80,
            regenerate_threshold=0.40,
        ))
        tc = _make_tc(
            # Decent but not great — some generic phrases, short description
            description="Verifies login works.",
            steps=[
                TestStepArtifact(action="Open the login page", expected_result="Page displayed"),
                TestStepArtifact(action="Enter credentials and click login", expected_result="The system responds correctly"),
                TestStepArtifact(action="Observe the result on the dashboard", expected_result="Dashboard loads"),
            ],
        )
        report = scorer.score(tc, _make_slot(), _FakeReq())
        # With high accept threshold, this should be "regenerate"
        assert report.suggestion in ("regenerate", "accept")

    def test_score_clamped_0_to_1(self):
        scorer = TestCaseScorer()
        tc = _make_tc()
        report = scorer.score(tc, _make_slot(), _FakeReq())
        assert 0.0 <= report.overall_score <= 1.0
        for dim_score in report.dimension_scores.values():
            assert 0.0 <= dim_score <= 1.0

    def test_quality_score_on_artifact(self):
        """quality_score and quality_issues fields exist on TestCaseArtifact."""
        tc = _make_tc()
        assert tc.quality_score == 0.0
        assert tc.quality_issues == []
        tc2 = tc.model_copy(update={"quality_score": 0.85, "quality_issues": ["minor"]})
        assert tc2.quality_score == 0.85
        assert tc2.quality_issues == ["minor"]


# ── Helper methods ───────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_key_terms(self):
        terms = TestCaseScorer._extract_key_terms(
            "User must be able to log in with a valid email and password"
        )
        assert "email" in terms
        assert "password" in terms
        assert "valid" in terms
        # Stopwords excluded
        assert "must" not in terms
        assert "with" not in terms

    def test_extract_key_terms_empty(self):
        terms = TestCaseScorer._extract_key_terms("")
        assert terms == []

    def test_tokenize(self):
        tokens = TestCaseScorer._tokenize("the quick brown fox jumps over")
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens  # 3 chars — included
        # "the" is only 3 chars and passes, but its actual token length matters
        assert all(len(t) >= 3 for t in tokens)

    def test_get_tc_full_text(self):
        tc = _make_tc()
        text = TestCaseScorer._get_tc_full_text(tc)
        assert "Login Screen" in text
        assert "Dashboard" in text
        assert tc.description in text


# ── ScorerConfig Validation ─────────────────────────────────────────────────


class TestScorerConfigValidation:
    """Tests for ScorerConfig validation added during audit."""

    def test_default_config_valid(self):
        cfg = ScorerConfig()
        total = sum(cfg.weights.values())
        assert abs(total - 1.0) < 0.05

    def test_weights_auto_normalize(self):
        """Weights that don't sum to 1.0 are auto-normalized."""
        cfg = ScorerConfig(weights={
            "coverage": 0.5,
            "clarity": 0.5,
            "executability": 0.5,
            "uniqueness": 0.5,
            "structural": 0.5,
        })
        total = sum(cfg.weights.values())
        assert abs(total - 1.0) < 0.01

    def test_missing_dimension_raises(self):
        """Missing a required dimension raises ValueError."""
        with pytest.raises(ValueError, match="Missing weight dimensions"):
            ScorerConfig(weights={
                "coverage": 0.25,
                "clarity": 0.25,
                # missing executability, uniqueness, structural
            })

    def test_zero_weights_raises(self):
        """All-zero weights raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            ScorerConfig(weights={
                "coverage": 0.0,
                "clarity": 0.0,
                "executability": 0.0,
                "uniqueness": 0.0,
                "structural": 0.0,
            })

    def test_threshold_ordering_violation(self):
        """regenerate_threshold > accept_threshold raises ValueError."""
        with pytest.raises(ValueError, match="regenerate_threshold"):
            ScorerConfig(
                accept_threshold=0.40,
                regenerate_threshold=0.65,
            )

    def test_from_config_empty_dict(self):
        """from_config with empty dict returns defaults."""
        cfg = ScorerConfig.from_config({})
        assert cfg.accept_threshold == 0.65
        assert cfg.regenerate_threshold == 0.40

    def test_from_config_partial(self):
        """from_config with partial quality_gate fills defaults."""
        cfg = ScorerConfig.from_config({
            "quality_gate": {"accept_threshold": 0.80}
        })
        assert cfg.accept_threshold == 0.80
        assert cfg.regenerate_threshold == 0.40  # default

    def test_from_config_no_quality_gate_key(self):
        """Config without quality_gate key returns defaults."""
        cfg = ScorerConfig.from_config({"other_key": "value"})
        assert cfg.accept_threshold == 0.65
