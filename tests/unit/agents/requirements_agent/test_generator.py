"""Tests for the TestCaseGenerator class."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest
from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator
from stlc_platform.core.contracts import TestCaseArtifact


@dataclass
class MockRequirement:
    req_id: str = "REQ-001"
    title: str = "User Login Feature"
    description: str = "User should be able to log in with valid credentials"
    category: str = "Authentication"
    priority: str = "High"
    acceptance_criteria: List[str] = field(default_factory=lambda: [
        "User can login with valid credentials",
        "System displays error for invalid password",
    ])


class MockLLMClient:
    """Mock LLM client that returns distinct canned responses to survive dedup."""

    _SCENARIOS = [
        {
            "title": "Verify successful login with valid credentials",
            "description": "Test that login works correctly with valid credentials",
            "preconditions": "User has a valid account",
            "steps": [
                {"action": "Navigate to login page", "expected_result": "Login page loads"},
                {"action": "Enter valid username", "expected_result": "Username field populated"},
                {"action": "Enter valid password", "expected_result": "Password field populated"},
                {"action": "Click login button", "expected_result": "Dashboard loads"},
            ],
            "expected_outcome": "User is logged in successfully",
            "component": "Login Screen",
            "given": "A valid user account exists",
            "when": "The user enters valid credentials and clicks login",
            "then": "The user is redirected to the dashboard",
            "priority": "High",
            "tags": ["authentication", "positive", "req-001"],
        },
        {
            "title": "Verify error banner for wrong password",
            "description": "System rejects incorrect password with clear alert",
            "preconditions": "User account exists but wrong password used",
            "steps": [
                {"action": "Open authentication page", "expected_result": "Form renders"},
                {"action": "Type wrong password", "expected_result": "Password field filled"},
                {"action": "Click sign-in button", "expected_result": "Error banner appears"},
            ],
            "expected_outcome": "Red error banner shows invalid password message",
            "component": "Error Handler",
            "given": "A registered user with incorrect password",
            "when": "User attempts authentication with bad credentials",
            "then": "Error notification displayed and login blocked",
            "priority": "High",
            "tags": ["auth", "negative"],
        },
        {
            "title": "Verify password recovery email delivery",
            "description": "Forgotten password triggers recovery email to user",
            "preconditions": "Email server configured and user registered",
            "steps": [
                {"action": "Click forgot password link", "expected_result": "Recovery form shown"},
                {"action": "Enter registered email", "expected_result": "Email field validated"},
                {"action": "Submit recovery request", "expected_result": "Confirmation displayed"},
            ],
            "expected_outcome": "Recovery email sent within 30 seconds",
            "component": "Password Recovery",
            "given": "A registered user who forgot their password",
            "when": "User requests password recovery via email",
            "then": "Reset link delivered to registered email address",
            "priority": "Medium",
            "tags": ["recovery", "positive"],
        },
        {
            "title": "Verify account lockout after failed attempts",
            "description": "Multiple failed logins trigger temporary account freeze",
            "preconditions": "Security policy requires lockout after 5 failures",
            "steps": [
                {"action": "Attempt login with wrong password 5 times", "expected_result": "Counter increments"},
                {"action": "Try sixth login attempt", "expected_result": "Account locked message"},
                {"action": "Wait 15 minutes and retry", "expected_result": "Login succeeds"},
            ],
            "expected_outcome": "Account temporarily frozen then auto-unlocked",
            "component": "Security Module",
            "given": "A user who has exhausted login attempts",
            "when": "Sixth consecutive failed authentication occurs",
            "then": "Account locked for 15 minutes with notification",
            "priority": "High",
            "tags": ["security", "edge_case"],
        },
        {
            "title": "Verify session timeout after inactivity",
            "description": "Idle session expires after configured period",
            "preconditions": "Session timeout set to 30 minutes",
            "steps": [
                {"action": "Login and remain idle 31 minutes", "expected_result": "Timer expires"},
                {"action": "Navigate to protected page", "expected_result": "Redirect to login"},
                {"action": "Check session cookie", "expected_result": "Cookie invalidated"},
            ],
            "expected_outcome": "Session destroyed and user redirected to login",
            "component": "Session Manager",
            "given": "An authenticated user with expired session",
            "when": "User acts after 30 minute inactivity",
            "then": "Session terminated and login page shown",
            "priority": "Medium",
            "tags": ["session", "timeout"],
        },
        {
            "title": "Verify TOTP multi-factor authentication",
            "description": "Second factor requested after primary credential check",
            "preconditions": "MFA enabled with TOTP configured for user",
            "steps": [
                {"action": "Complete primary login", "expected_result": "MFA challenge shown"},
                {"action": "Enter TOTP code", "expected_result": "Code verified successfully"},
                {"action": "Confirm MFA approval", "expected_result": "Full access granted"},
            ],
            "expected_outcome": "Two-factor verification completed",
            "component": "MFA Gateway",
            "given": "A user with TOTP multi-factor enabled",
            "when": "User enters primary credentials and TOTP code",
            "then": "Full application access after MFA verification",
            "priority": "High",
            "tags": ["mfa", "security"],
        },
    ]

    def __init__(self, response=None):
        self._response = response
        self._call_count = 0

    def generate_test_case(self, prompt, system_prompt=None, **kwargs):
        if self._response is not None:
            return self._response
        scenario = self._SCENARIOS[self._call_count % len(self._SCENARIOS)].copy()
        self._call_count += 1
        scenario.setdefault("estimated_duration", "5")
        return scenario


class TestSlotPlan:
    """Test slot plan generation."""

    @pytest.fixture
    def generator(self):
        return TestCaseGenerator(llm_client=MockLLMClient())

    def test_slot_count(self, generator):
        req = MockRequirement()
        slots = generator._build_slot_plan(req, max_tc=3, include_negative=True, include_edge=True)
        assert len(slots) == 3

    def test_pattern_positive_negative_edge(self, generator):
        req = MockRequirement()
        slots = generator._build_slot_plan(req, max_tc=3, include_negative=True, include_edge=True)
        assert slots[0]["test_type"] == "positive"
        assert slots[1]["test_type"] == "negative"
        assert slots[2]["test_type"] == "edge_case"

    def test_pattern_positive_only(self, generator):
        req = MockRequirement()
        slots = generator._build_slot_plan(req, max_tc=3, include_negative=False, include_edge=False)
        assert all(s["test_type"] == "positive" for s in slots)

    def test_pattern_positive_negative(self, generator):
        req = MockRequirement()
        slots = generator._build_slot_plan(req, max_tc=4, include_negative=True, include_edge=False)
        types = [s["test_type"] for s in slots]
        assert types == ["positive", "negative", "positive", "negative"]

    def test_slot_has_all_keys(self, generator):
        req = MockRequirement()
        slots = generator._build_slot_plan(req, max_tc=1, include_negative=False, include_edge=False)
        slot = slots[0]
        assert "test_type" in slot
        assert "target_ac" in slot
        assert "title" in slot
        assert "ac_type" in slot

    def test_unique_titles(self, generator):
        req = MockRequirement(acceptance_criteria=["Same AC text"] * 5)
        slots = generator._build_slot_plan(req, max_tc=3, include_negative=True, include_edge=True)
        titles = [s["title"].lower()[:50] for s in slots]
        # All slots with same AC should still get unique-ish titles (different test_type verbs)
        assert len(set(titles)) == len(titles)

    def test_cycles_across_acs(self, generator):
        req = MockRequirement(acceptance_criteria=["AC1", "AC2", "AC3"])
        slots = generator._build_slot_plan(req, max_tc=6, include_negative=True, include_edge=True)
        acs = [s["target_ac"] for s in slots]
        assert acs == ["AC1", "AC2", "AC3", "AC1", "AC2", "AC3"]


class TestParse:
    """Test _parse method for LLM output parsing."""

    @pytest.fixture
    def generator(self):
        return TestCaseGenerator(llm_client=MockLLMClient())

    def test_parse_valid_response(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "Login works", "title": "Test", "ac_type": "general"}
        raw = {
            "title": "Test",
            "description": "Verify login works",
            "preconditions": "Valid account",
            "steps": [
                {"action": "Step 1", "expected_result": "Result 1"},
                {"action": "Step 2", "expected_result": "Result 2"},
            ],
            "expected_outcome": "Login successful",
            "given": "G",
            "when": "W",
            "then": "T",
        }
        tc = generator._parse(raw, req, slot)
        assert tc is not None
        assert isinstance(tc, TestCaseArtifact)
        assert tc.req_id == "REQ-001"
        assert tc.test_type == "positive"

    def test_parse_none_input(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "AC", "title": "T", "ac_type": "general"}
        assert generator._parse(None, req, slot) is None

    def test_parse_raw_response_error(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "AC", "title": "T", "ac_type": "general"}
        assert generator._parse({"raw_response": "error"}, req, slot) is None

    def test_parse_test_cases_array(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "AC", "title": "T", "ac_type": "general"}
        raw = {
            "test_cases": [{
                "title": "T",
                "description": "D",
                "steps": [
                    {"action": "A1", "expected_result": "R1"},
                    {"action": "A2", "expected_result": "R2"},
                ],
            }]
        }
        tc = generator._parse(raw, req, slot)
        assert tc is not None

    def test_parse_increments_counter(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "AC", "title": "T", "ac_type": "general"}
        raw = {"title": "T", "description": "D", "steps": [
            {"action": "A1", "expected_result": "R1"},
            {"action": "A2", "expected_result": "R2"},
        ]}
        tc1 = generator._parse(raw, req, slot)
        tc2 = generator._parse(raw, req, slot)
        assert tc1.tc_id != tc2.tc_id


class TestSynthesise:
    """Test _synthesise_tc fallback method."""

    @pytest.fixture
    def generator(self):
        return TestCaseGenerator(llm_client=MockLLMClient())

    def test_synthesise_returns_artifact(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "User can login", "title": "Test", "ac_type": "general"}
        tc = generator._synthesise_tc(req, slot)
        assert isinstance(tc, TestCaseArtifact)
        assert tc.req_id == "REQ-001"
        assert len(tc.steps) >= 2

    def test_synthesise_has_gwt(self, generator):
        req = MockRequirement()
        slot = {"test_type": "positive", "target_ac": "User can login", "title": "Test", "ac_type": "general"}
        tc = generator._synthesise_tc(req, slot)
        assert tc.given != ""
        assert tc.when != ""
        assert tc.then != ""

    def test_synthesise_tags_include_synthesised(self, generator):
        req = MockRequirement()
        slot = {"test_type": "negative", "target_ac": "Error on invalid", "title": "Test", "ac_type": "general"}
        tc = generator._synthesise_tc(req, slot)
        assert "synthesised" in tc.tags


class TestGenerateForRequirement:
    """Test full generation flow with mocked LLM."""

    def test_basic_generation(self):
        llm = MockLLMClient()
        gen = TestCaseGenerator(llm_client=llm)
        req = MockRequirement()
        results = gen.generate_for_requirement(req, max_tests=2, include_negative=False, include_edge=False)
        assert len(results) == 2
        assert all(isinstance(tc, TestCaseArtifact) for tc in results)

    def test_llm_failure_falls_back_to_synthesis(self):
        """When LLM returns None, generator falls back to synthesis."""
        class FailingLLM:
            def generate_test_case(self, prompt, system_prompt=None, **kwargs):
                return None
        llm = FailingLLM()
        gen = TestCaseGenerator(llm_client=llm)
        req = MockRequirement()
        results = gen.generate_for_requirement(req, max_tests=1, include_negative=False, include_edge=False)
        assert len(results) == 1
        assert "synthesised" in results[0].tags

    def test_negative_and_edge_included(self):
        llm = MockLLMClient()
        gen = TestCaseGenerator(llm_client=llm)
        req = MockRequirement()
        results = gen.generate_for_requirement(
            req, max_tests=3, include_negative=True, include_edge=True,
        )
        types = {tc.test_type for tc in results}
        assert "positive" in types
        assert "negative" in types
        assert "edge_case" in types


class TestGenerateForAll:
    """Test generate_for_all with domain detection."""

    def test_domain_detection(self):
        llm = MockLLMClient()
        gen = TestCaseGenerator(llm_client=llm)
        reqs = [
            MockRequirement(req_id="REQ-001", category="Patient Registration"),
            MockRequirement(req_id="REQ-002", category="Clinical Records"),
        ]
        results = gen.generate_for_all(reqs, max_tests=1, include_negative=False, include_edge=False)
        assert gen._domain == "healthcare"
        # AC-aware: each MockRequirement has 2 ACs, effective_max = max(1, 2) = 2 per req
        assert len(results) == 4

    def test_explicit_domain_not_overridden(self):
        llm = MockLLMClient()
        gen = TestCaseGenerator(llm_client=llm, domain="fintech")
        reqs = [MockRequirement(category="Patient Registration")]
        gen.generate_for_all(reqs, max_tests=1, include_negative=False, include_edge=False)
        assert gen._domain == "fintech"
