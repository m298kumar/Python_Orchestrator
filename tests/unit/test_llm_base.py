"""
Tests for LLM abstraction layer.
"""

import json
from typing import Optional
from unittest.mock import patch

import pytest

from stlc_platform.core.llm.base_client import (
    BaseLLMClient,
    TokenUsage,
    TESTCASE_JSON_SCHEMA,
    repair_truncated_json,
    is_hollow,
)


class TestRepairTruncatedJson:
    def test_complete_json_unchanged(self):
        s = '{"title": "test", "steps": []}'
        assert json.loads(repair_truncated_json(s)) == json.loads(s)

    def test_unclosed_string(self):
        s = '{"title": "test'
        result = repair_truncated_json(s)
        parsed = json.loads(result)
        assert parsed["title"] == "test"

    def test_unclosed_array(self):
        s = '{"steps": [{"action": "click"}'
        result = repair_truncated_json(s)
        parsed = json.loads(result)
        assert "steps" in parsed

    def test_unclosed_object(self):
        s = '{"title": "test"'
        result = repair_truncated_json(s)
        parsed = json.loads(result)
        assert parsed["title"] == "test"

    def test_trailing_comma_removed(self):
        s = '{"a": 1, "b": 2,'
        result = repair_truncated_json(s)
        parsed = json.loads(result)
        assert parsed["b"] == 2

    def test_empty_string(self):
        assert repair_truncated_json("") == ""


class TestIsHollow:
    def test_good_response(self):
        parsed = {
            "title": "Verify user login with valid credentials",
            "description": "This test verifies that users can log in successfully",
            "steps": [
                {"action": "Navigate to the login page at /login", "expected_result": "Form loads"},
                {"action": "Enter username 'admin' in the field", "expected_result": "Username shown"},
                {"action": "Click the Sign In button to submit", "expected_result": "Dashboard loads"},
            ],
        }
        assert is_hollow(parsed) is False

    def test_empty_title(self):
        assert is_hollow({"title": "", "description": "desc", "steps": []}) is True

    def test_short_title(self):
        assert is_hollow({"title": "short", "description": "desc", "steps": []}) is True

    def test_empty_steps(self):
        assert is_hollow({
            "title": "A sufficiently long title here",
            "description": "A good description text",
            "steps": [],
        }) is True

    def test_trivial_step_actions(self):
        assert is_hollow({
            "title": "A sufficiently long title here",
            "description": "A good description text",
            "steps": [{"action": "do", "expected_result": "done"}],
        }) is True


class TestTestcaseJsonSchema:
    def test_schema_has_required_fields(self):
        assert "required" in TESTCASE_JSON_SCHEMA
        required = TESTCASE_JSON_SCHEMA["required"]
        assert "title" in required
        assert "steps" in required
        assert "description" in required

    def test_schema_steps_have_min_items(self):
        steps_schema = TESTCASE_JSON_SCHEMA["properties"]["steps"]
        assert steps_schema["minItems"] == 3


class TestBaseLLMClientABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseLLMClient()


# ── Concrete stub for testing generate_test_case ──────────────────────────


class _StubLLM(BaseLLMClient):
    """Minimal concrete LLM for testing base class behaviour."""

    def __init__(self, responses=None):
        super().__init__()
        self.temperature = 0.4
        self._responses = list(responses or [])
        self._call_count = 0

    def generate(self, prompt, system_prompt=None, temperature=None, json_schema=None):
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = ""
        self._call_count += 1
        if isinstance(resp, Exception):
            raise resp
        return resp

    def check_connection(self):
        return True

    def list_models(self):
        return ["stub"]


# ── Token Tracking ─────────────────────────────────────────────────────────


class TestTokenTracking:
    def test_initial_token_usage_zero(self):
        llm = _StubLLM()
        assert llm.last_token_usage().total_tokens == 0
        assert llm.accumulated_tokens.total_tokens == 0

    def test_record_tokens_updates_both(self):
        llm = _StubLLM()
        llm._record_tokens(100, 50)
        assert llm.last_token_usage().input_tokens == 100
        assert llm.last_token_usage().output_tokens == 50
        assert llm.accumulated_tokens.total_tokens == 150

    def test_accumulated_tokens_add_up(self):
        llm = _StubLLM()
        llm._record_tokens(100, 50)
        llm._record_tokens(200, 100)
        assert llm.accumulated_tokens.input_tokens == 300
        assert llm.accumulated_tokens.output_tokens == 150
        assert llm.last_token_usage().input_tokens == 200  # last call only

    def test_reset_token_counts(self):
        llm = _StubLLM()
        llm._record_tokens(100, 50)
        llm.reset_token_counts()
        assert llm.accumulated_tokens.total_tokens == 0


# ── Classified-Retry Loop ─────────────────────────────────────────────────


_GOOD_TC = json.dumps({
    "title": "Verify user login with valid credentials works correctly",
    "description": "Validates that a registered user can log in with valid email and password",
    "preconditions": "A user account exists with email test@example.com",
    "test_type": "positive",
    "priority": "High",
    "given": "A registered user exists with valid credentials",
    "when": "The user enters valid email and password on login page",
    "then": "The user is authenticated and sees the dashboard",
    "steps": [
        {"action": "Navigate to the login page at /auth/login", "expected_result": "Login form displayed with email and password fields"},
        {"action": "Enter test@example.com in the email field", "expected_result": "Email field shows the entered value"},
        {"action": "Enter valid password and click the Login button", "expected_result": "User is redirected to dashboard page"},
    ],
    "expected_outcome": "User is successfully logged in and dashboard is displayed",
    "tags": ["auth", "positive"],
    "component": "Login Screen",
})

_SLOT = {"test_type": "positive", "target_ac": "User can log in with valid email and password"}


class TestClassifiedRetry:
    def test_good_response_returns_on_first_attempt(self):
        llm = _StubLLM(responses=[_GOOD_TC])
        result = llm.generate_test_case("prompt", slot=_SLOT)
        assert "raw_response" not in result
        assert result["title"].startswith("Verify user login")
        assert llm._call_count == 1

    def test_first_fail_second_success(self):
        """Failure on attempt 1 → classified → adapted prompt → success."""
        llm = _StubLLM(responses=["not json at all", _GOOD_TC])
        result = llm.generate_test_case("prompt", slot=_SLOT)
        assert "raw_response" not in result
        assert llm._call_count == 2

    def test_both_fail_returns_raw(self):
        llm = _StubLLM(responses=["bad", "also bad"])
        result = llm.generate_test_case("prompt", slot=_SLOT)
        assert "raw_response" in result

    def test_hollow_response_triggers_retry(self):
        """Hollow JSON on attempt 1 triggers classified retry."""
        hollow = json.dumps({"title": "T", "steps": []})
        llm = _StubLLM(responses=[hollow, _GOOD_TC])
        result = llm.generate_test_case("prompt", slot=_SLOT)
        assert "raw_response" not in result
        assert llm._call_count == 2

    def test_backward_compat_no_slot(self):
        """Without slot/requirement, falls back to blind retry (no crash)."""
        llm = _StubLLM(responses=["bad json", _GOOD_TC])
        result = llm.generate_test_case("prompt")
        assert "raw_response" not in result


# ── Context Window Management ──────────────────────────────────────────────


class TestContextWindowManagement:
    def test_prompt_trimmed_when_over_budget(self):
        from stlc_platform.agents.requirements_agent.prompts import PromptRenderer

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "The system shall allow users to log in."
            acceptance_criteria = ["User can log in with valid email and password"]
            category = "Auth"

        slot = {"test_type": "positive", "target_ac": "User can log in with valid email", "title": "Test Login", "ac_type": "general"}
        renderer = PromptRenderer()

        # Very small budget should trigger trimming
        small = renderer.render_user_prompt(
            requirement=MockReq(), slot=slot, test_number=1, total=1,
            context="Some extra context about related features",
            examples=[{"title": "Example TC", "steps": [{"action": "a", "expected_result": "e"}]}],
            max_prompt_tokens=50,  # very tight budget
        )

        # Full budget should include everything
        full = renderer.render_user_prompt(
            requirement=MockReq(), slot=slot, test_number=1, total=1,
            context="Some extra context about related features",
            examples=[{"title": "Example TC", "steps": [{"action": "a", "expected_result": "e"}]}],
            max_prompt_tokens=100000,  # plenty of room
        )

        # The trimmed version should be shorter
        assert len(small) < len(full)

    def test_no_trimming_without_budget(self):
        from stlc_platform.agents.requirements_agent.prompts import PromptRenderer

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "The system shall allow users to log in."
            acceptance_criteria = ["User can log in"]
            category = "Auth"

        slot = {"test_type": "positive", "target_ac": "User can log in", "title": "Test", "ac_type": "general"}
        renderer = PromptRenderer()

        # Without max_prompt_tokens, no trimming
        result1 = renderer.render_user_prompt(
            requirement=MockReq(), slot=slot, test_number=1, total=1,
            context="context",
        )
        result2 = renderer.render_user_prompt(
            requirement=MockReq(), slot=slot, test_number=1, total=1,
            context="context",
            max_prompt_tokens=None,
        )
        assert result1 == result2
