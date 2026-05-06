"""
Tests for FailureClassifier — Phase C failure classification.
"""

import pytest
from stlc_platform.core.llm.failure_classifier import (
    FailureClassification,
    FailureClassifier,
    FailureType,
)


class MockReq:
    req_id = "REQ-001"
    title = "User Login"
    description = "The system shall allow users to log in."


SLOT = {
    "test_type": "positive",
    "target_ac": "User can log in with valid email and password",
    "ac_type": "general",
}


@pytest.fixture
def classifier():
    return FailureClassifier()


# ── Truncation ──────────────────────────────────────────────────────────────


class TestTruncation:
    def test_unclosed_braces_detected(self, classifier):
        raw = '{"title": "Test", "description": "Desc", "steps": [{"action": "Do'
        result = classifier.classify(raw, None, SLOT, MockReq())
        # Should detect truncation or schema violation
        assert result is not None
        assert result.failure_type in (FailureType.TRUNCATION, FailureType.SCHEMA_VIOLATION)

    def test_valid_json_not_truncated(self, classifier):
        raw = '{"title": "Test"}'
        parsed = {
            "title": "Test",
            "description": "Valid description text here",
            "preconditions": "User is logged in already",
            "steps": [
                {"action": "Click button", "expected_result": "Result shown"},
                {"action": "Check output", "expected_result": "Output correct"},
            ],
            "expected_outcome": "Everything works fine",
            "given": "User is on page",
            "when": "User clicks the button",
            "then": "Result is displayed",
        }
        result = classifier._check_truncation(raw, parsed, SLOT, MockReq())
        assert result is None


# ── Schema Violation ────────────────────────────────────────────────────────


class TestSchemaViolation:
    def test_none_parsed_detected(self, classifier):
        result = classifier._check_schema_violation("raw", None, SLOT, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.SCHEMA_VIOLATION

    def test_missing_fields_detected(self, classifier):
        parsed = {"title": "Test"}  # missing many fields
        result = classifier._check_schema_violation("raw", parsed, SLOT, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.SCHEMA_VIOLATION
        assert "Missing fields" in result.details

    def test_complete_fields_pass(self, classifier):
        parsed = {
            "title": "T",
            "description": "D",
            "preconditions": "P",
            "steps": [
                {"action": "a", "expected_result": "e"},
                {"action": "b", "expected_result": "f"},
            ],
            "expected_outcome": "E",
            "given": "G",
            "when": "W",
            "then": "T",
        }
        result = classifier._check_schema_violation("raw", parsed, SLOT, MockReq())
        assert result is None

    def test_empty_steps_detected(self, classifier):
        parsed = {
            "title": "T",
            "description": "D",
            "preconditions": "P",
            "steps": [],
            "expected_outcome": "E",
            "given": "G",
            "when": "W",
            "then": "T",
        }
        result = classifier._check_schema_violation("raw", parsed, SLOT, MockReq())
        assert result is not None


# ── Instruction Leakage ─────────────────────────────────────────────────────


class TestInstructionLeakage:
    def test_leakage_detected(self, classifier):
        parsed = {
            "description": "Before writing each step, mentally answer the question.",
            "preconditions": "P",
            "expected_outcome": "E",
            "given": "G",
            "when": "W",
            "then": "T",
        }
        result = classifier._check_instruction_leakage("raw", parsed, SLOT, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.INSTRUCTION_LEAKAGE

    def test_clean_output_passes(self, classifier):
        parsed = {
            "description": "Verifies user login with valid credentials.",
            "preconditions": "User account exists",
            "expected_outcome": "Login succeeds",
            "given": "User on page",
            "when": "User logs in",
            "then": "Dashboard shown",
        }
        result = classifier._check_instruction_leakage("raw", parsed, SLOT, MockReq())
        assert result is None


# ── Hollow ──────────────────────────────────────────────────────────────────


class TestHollow:
    def test_generic_content_detected(self, classifier):
        parsed = {
            "description": "the system responds correctly to the action",
            "preconditions": "perform the action and observe the result",
            "expected_outcome": "the system behaves as expected",
            "steps": [
                {"action": "perform the action", "expected_result": "verify the outcome"},
                {"action": "check the result", "expected_result": "the test passes"},
            ],
            "given": "G",
            "when": "W",
            "then": "T",
        }
        result = classifier._check_hollow("raw", parsed, SLOT, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.HOLLOW

    def test_specific_content_passes(self, classifier):
        parsed = {
            "description": "Verifies that a registered user can log in with email test@example.com and a valid password",
            "preconditions": "A registered user account exists with email test@example.com",
            "expected_outcome": "User is redirected to the dashboard after successful login",
            "steps": [
                {
                    "action": "Navigate to login page at /auth/login",
                    "expected_result": "Login form displayed",
                },
                {
                    "action": "Enter test@example.com in email field",
                    "expected_result": "Email accepted",
                },
            ],
            "given": "G",
            "when": "W",
            "then": "T",
        }
        result = classifier._check_hollow("raw", parsed, SLOT, MockReq())
        assert result is None


# ── Off Topic ───────────────────────────────────────────────────────────────


class TestOffTopic:
    def test_unrelated_content_detected(self, classifier):
        parsed = {
            "title": "Test payment processing",
            "description": "Verifies payment gateway integration with Stripe",
            "preconditions": "Payment method configured",
            "steps": [{"action": "Enter credit card", "expected_result": "Card accepted"}],
            "expected_outcome": "Payment processed successfully",
            "given": "Card on file",
            "when": "User pays",
            "then": "Receipt shown",
        }
        slot = {
            "test_type": "positive",
            "target_ac": "User can log in with valid email and password credentials to access dashboard",
        }
        result = classifier._check_off_topic("raw", parsed, slot, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.OFF_TOPIC

    def test_relevant_content_passes(self, classifier):
        parsed = {
            "title": "Test login",
            "description": "Verifies user login with valid email and password",
            "preconditions": "User account with email exists",
            "steps": [{"action": "Enter email", "expected_result": "Email field populated"}],
            "expected_outcome": "User logged in with valid credentials",
            "given": "User has email",
            "when": "Enters password",
            "then": "Login success",
        }
        result = classifier._check_off_topic("raw", parsed, SLOT, MockReq())
        assert result is None


# ── Repetitive ──────────────────────────────────────────────────────────────


class TestRepetitive:
    def test_duplicate_steps_detected(self, classifier):
        parsed = {
            "steps": [
                {"action": "Click the login button", "expected_result": "Button clicked"},
                {"action": "Click the login button", "expected_result": "Button clicked"},
                {"action": "Click the login button", "expected_result": "Button clicked"},
                {"action": "Click the login button", "expected_result": "Button clicked"},
            ],
            "given": "A",
            "when": "B",
            "then": "C",
        }
        result = classifier._check_repetitive("raw", parsed, SLOT, MockReq())
        assert result is not None
        assert result.failure_type == FailureType.REPETITIVE

    def test_duplicate_gwt_detected(self, classifier):
        parsed = {
            "steps": [
                {"action": "Step 1", "expected_result": "R1"},
                {"action": "Step 2", "expected_result": "R2"},
            ],
            "given": "User is on the login page",
            "when": "User is on the login page",
            "then": "User is on the login page",
        }
        result = classifier._check_repetitive("raw", parsed, SLOT, MockReq())
        assert result is not None

    def test_unique_steps_pass(self, classifier):
        parsed = {
            "steps": [
                {"action": "Navigate to login page", "expected_result": "Form displayed"},
                {"action": "Enter email address", "expected_result": "Email accepted"},
                {"action": "Click login button", "expected_result": "Redirect to dashboard"},
            ],
            "given": "User on login page",
            "when": "User enters credentials",
            "then": "User sees dashboard",
        }
        result = classifier._check_repetitive("raw", parsed, SLOT, MockReq())
        assert result is None


# ── Prompt Adaptation ───────────────────────────────────────────────────────


class TestPromptAdaptation:
    def test_truncation_adaptation(self, classifier):
        fc = FailureClassification(FailureType.TRUNCATION, 0.9, "test", "shorten")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "CONCISE" in adapted
        assert "original prompt" in adapted

    def test_hollow_adaptation(self, classifier):
        fc = FailureClassification(FailureType.HOLLOW, 0.8, "test", "add_specificity")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "DO NOT leave fields empty" in adapted

    def test_off_topic_adaptation(self, classifier):
        fc = FailureClassification(FailureType.OFF_TOPIC, 0.8, "test", "repeat_ac")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "CRITICAL" in adapted

    def test_repetitive_adaptation(self, classifier):
        fc = FailureClassification(FailureType.REPETITIVE, 0.85, "test", "unique")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "UNIQUE" in adapted

    def test_schema_adaptation(self, classifier):
        fc = FailureClassification(FailureType.SCHEMA_VIOLATION, 0.9, "test", "schema")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "valid JSON" in adapted

    def test_leakage_adaptation(self, classifier):
        fc = FailureClassification(FailureType.INSTRUCTION_LEAKAGE, 0.85, "test", "no_leak")
        adapted = classifier.adapt_prompt("original prompt", fc)
        assert "DO NOT include" in adapted


# ── Full Classification Flow ────────────────────────────────────────────────


class TestFullClassification:
    def test_good_output_returns_none(self, classifier):
        raw = '{"title": "ok"}'
        parsed = {
            "title": "Verify user login with valid credentials",
            "description": "Verifies that a user can log in with a valid email and password",
            "preconditions": "A user account exists with email and password",
            "steps": [
                {"action": "Navigate to login page", "expected_result": "Login form displayed"},
                {"action": "Enter valid email", "expected_result": "Email field populated"},
                {
                    "action": "Enter valid password and click login",
                    "expected_result": "User logged in",
                },
            ],
            "expected_outcome": "User is logged in and sees dashboard",
            "given": "User has a valid account with email and password",
            "when": "User enters valid email and password on login page",
            "then": "User is authenticated and redirected to dashboard",
            "tags": ["auth", "positive"],
            "component": "Login Screen",
        }
        result = classifier.classify(raw, parsed, SLOT, MockReq())
        assert result is None

    def test_classify_returns_most_severe(self, classifier):
        """When multiple failures exist, returns the first (most severe)."""
        result = classifier.classify("", None, SLOT, MockReq())
        # Empty raw + None parsed → schema violation (checked before hollow)
        assert result is not None
        assert result.failure_type == FailureType.SCHEMA_VIOLATION
