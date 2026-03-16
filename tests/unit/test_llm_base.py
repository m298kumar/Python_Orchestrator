"""
Tests for LLM abstraction layer.
"""

import json
import pytest

from stlc_platform.core.llm.base_client import (
    BaseLLMClient,
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
