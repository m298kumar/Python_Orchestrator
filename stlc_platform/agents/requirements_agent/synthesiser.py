"""
Test Case Synthesiser
=====================
Deterministic fallback generators for when LLM output fails or is insufficient.
Produces TestCaseArtifact / TestStepArtifact objects directly.

Extracted from legacy test_generator.py — all logic is domain-agnostic.
"""

from __future__ import annotations

import re
from typing import Any, List, Tuple

from stlc_platform.agents.requirements_agent.constants import (
    GENERIC_STEP_FRAGMENTS,
    ac_to_title,
)
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact


def _is_generic_step(action: str) -> bool:
    """Return True if a step action is too vague to be useful."""
    t = action.strip().lower()
    if len(t) < 20:
        return True
    if re.match(r"^[a-z]+(_[a-z]+)+$", t):
        return True
    return any(t.startswith(frag) for frag in GENERIC_STEP_FRAGMENTS)


def _has_loop(text: str, threshold: int = 3) -> bool:
    """Detect repeated sentences — hallucinated loops."""
    parts = re.split(r"[.\n]", text)
    parts = [p.strip().lower()[:60] for p in parts if len(p.strip()) > 15]
    if not parts:
        return False
    counts: dict[str, int] = {}
    for p in parts:
        counts[p] = counts.get(p, 0) + 1
        if counts[p] >= threshold:
            return True
    return False


def make_gwt(
    ac: str,
    test_type: str,
    req_title: str,
    ac_type: str = "general",
) -> Tuple[str, str, str]:
    """Generate Given/When/Then from AC and test type.

    Returns:
        Tuple of (given, when, then) strings.
    """
    ac = ac.strip()
    feature = req_title[:60] if req_title else "this feature"

    if test_type == "positive":
        given = f"An eligible user who meets all requirements for {feature} is logged in"
        when = f"The user performs the specific action to exercise: {ac[:100]}"
        then = f"The system displays the observable result described in: {ac[:100]}"
    elif test_type == "negative":
        if ac_type == "ui_behaviour":
            given = f"A test account where the condition for {ac[:60]} is NOT met"
            when = "The user attempts to trigger the UI behaviour without satisfying its condition"
            then = "The system handles the unhappy path correctly with an accurate fallback state"
        elif ac_type == "timing":
            given = f"A test environment simulating a delay beyond the limit in: {ac[:60]}"
            when = "The timed event exceeds the specified time limit"
            then = "The system detects the timeout and displays the correct error or fallback"
        elif ac_type == "data_valid":
            given = f"A test account with an invalid value prepared for: {ac[:60]}"
            when = "The user submits the invalid value"
            then = "The system rejects the input and displays an accurate validation error message"
        elif ac_type == "security":
            given = f"A test account attempting to bypass the security control in: {ac[:60]}"
            when = "The user attempts the bypass action"
            then = "The security control blocks the attempt with the correct rejection message"
        else:
            given = f"A user who does not meet eligibility criteria for {feature}"
            when = f"The user attempts the restricted action: {ac[:80]}"
            then = "The system blocks the action and displays the correct rejection message"
    else:
        given = f"Test data configured at exactly the boundary value for: {ac[:80]}"
        when = "The boundary-condition action is executed"
        then = "System accepts the limit value and rejects the value one unit beyond it"

    return given, when, then


def make_description(ac: str, test_type: str) -> str:
    """Generate a description from AC and test type."""
    labels = {
        "positive": "Positive test -- verifies that",
        "negative": "Negative test -- verifies correct rejection when",
        "edge_case": "Boundary test -- verifies enforcement at the exact limit of",
    }
    return f"{labels.get(test_type, 'Test --')} {ac.strip()}"


def make_preconditions(
    ac: str,
    test_type: str,
    category: str,
    req_title: str = "",
    ac_type: str = "general",
) -> str:
    """Generate preconditions from AC and test type."""
    feature = req_title[:60] if req_title else category
    base = "Application installed; tester has valid login credentials for a test account"

    if test_type == "positive":
        return f"Test account meets all eligibility criteria for {feature}; {base}"
    elif test_type == "negative":
        if ac_type == "ui_behaviour":
            return f"Test account configured so the triggering condition for {ac[:60]} is absent; {base}"
        elif ac_type == "timing":
            return f"Test environment configured to simulate delay beyond the limit in: {ac[:60]}; {base}"
        elif ac_type == "data_valid":
            return f"Test data prepared with an invalid boundary value for: {ac[:60]}; {base}"
        elif ac_type == "security":
            return f"Test account configured for bypass attempt of security control in: {ac[:60]}; {base}"
        else:
            return (
                f"Test account configured to be ineligible for {feature} "
                f"(fails one or more eligibility criteria); {base}"
            )
    else:
        return f"Test data set at exactly the boundary value for: {ac[:60]}; {base}"


def synthesise_steps(
    ac: str,
    test_type: str,
    req_title: str = "",
    ac_type: str = "general",
) -> List[TestStepArtifact]:
    """Generate deterministic test steps when LLM fails.

    Returns:
        List of TestStepArtifact objects (always 5 steps).
    """
    ac = ac.strip()
    feature = req_title[:60] if req_title else "the relevant feature"

    def _step(action: str, expected: str) -> TestStepArtifact:
        return TestStepArtifact(action=action, expected_result=expected)

    if test_type == "positive":
        if ac_type == "timing":
            return [
                _step("Log in and navigate to the relevant screen", "Screen loads correctly"),
                _step(
                    f"Trigger the timed event described in: {ac[:70]}",
                    "System begins processing; timer started",
                ),
                _step(
                    "Measure elapsed time from trigger to completion",
                    f"Event completes within the limit: {ac[:60]}",
                ),
                _step(
                    "Record the measured time in the test evidence",
                    "Elapsed time is within the required limit",
                ),
                _step(
                    "Verify no timeout error is shown",
                    "System shows the success state; no timeout message",
                ),
            ]
        elif ac_type == "data_valid":
            return [
                _step(
                    "Log in and navigate to the relevant input form",
                    "Form is displayed with the relevant fields",
                ),
                _step(
                    f"Enter the valid boundary value for: {ac[:70]}",
                    "System accepts the input without inline error",
                ),
                _step(
                    "Submit or trigger validation", "System processes the valid value successfully"
                ),
                _step(
                    f"Clear the field and enter an invalid value for: {ac[:60]}",
                    "System displays an inline validation error",
                ),
                _step(
                    "Verify the error message text is accurate",
                    "Error message correctly describes the validation rule",
                ),
            ]
        else:
            return [
                _step("Log in with valid credentials", "Home screen loads without errors"),
                _step(f"Navigate to the section for {feature}", "Relevant screen is displayed"),
                _step(
                    f"Perform the action that exercises: {ac[:80]}",
                    "System accepts the input correctly",
                ),
                _step(
                    "Verify the observable result matches the acceptance criterion",
                    f"Result matches: {ac[:80]}",
                ),
                _step(
                    "Navigate away and return to confirm persistence",
                    "State is saved; no error banners",
                ),
            ]

    elif test_type == "negative":
        if ac_type == "ui_behaviour":
            return [
                _step(
                    "Log in with test account where the triggering condition is absent",
                    "Home screen loads; condition is not active",
                ),
                _step("Navigate to the relevant screen", "Screen loads"),
                _step(
                    f"Attempt to trigger the UI behaviour described in: {ac[:70]}",
                    "System does not show the behaviour incorrectly",
                ),
                _step(
                    "Verify the fallback or error state is shown",
                    "System shows the correct fallback message or state",
                ),
                _step(
                    "Attempt to proceed past the fallback state",
                    "System handles the unhappy path cleanly",
                ),
            ]
        elif ac_type == "timing":
            return [
                _step(
                    "Configure test environment to simulate delay exceeding the time limit",
                    "Delay condition is active",
                ),
                _step("Log in and navigate to the relevant screen", "Screen loads"),
                _step(
                    f"Trigger the timed event described in: {ac[:70]}",
                    "Processing begins; timer running",
                ),
                _step(
                    "Allow the time limit to be exceeded without the expected event",
                    "System detects the timeout",
                ),
                _step(
                    "Observe the timeout error or fallback state",
                    "System displays the correct timeout message",
                ),
            ]
        elif ac_type == "data_valid":
            return [
                _step("Log in and navigate to the relevant form", "Form is displayed"),
                _step(
                    f"Enter an invalid value that violates: {ac[:70]}",
                    "System detects the invalid input",
                ),
                _step("Submit or attempt to proceed", "System rejects the invalid value"),
                _step(
                    "Read the validation error message shown",
                    "Error message accurately describes the rule violation",
                ),
                _step(
                    "Attempt to bypass validation via back button or direct navigation",
                    "System maintains the block; no invalid data saved",
                ),
            ]
        else:
            return [
                _step(
                    "Log in with an ineligible test account",
                    "Home screen loads; ineligibility condition is active",
                ),
                _step(f"Navigate to the section for {feature}", "Screen loads"),
                _step(
                    f"Attempt the action blocked by: {ac[:80]}",
                    "System detects the ineligibility condition",
                ),
                _step(
                    "Read the rejection message displayed on screen",
                    "Correct rejection message is shown",
                ),
                _step(
                    "Attempt to bypass the block via back button or direct navigation",
                    "System maintains the block; no data saved",
                ),
            ]

    else:  # edge_case
        return [
            _step(
                f"Set test data at exactly the boundary value for: {ac[:70]}",
                "Boundary test data is confirmed in the environment",
            ),
            _step(
                "Log in and navigate to the relevant screen",
                "Screen loads; boundary test data is visible",
            ),
            _step(
                "Execute the action at the exact boundary value",
                "System accepts the boundary value without error",
            ),
            _step(
                "Record the outcome shown on screen", f"Outcome matches the requirement: {ac[:70]}"
            ),
            _step(
                "Repeat the action with a value one unit beyond the boundary",
                "System rejects the out-of-bounds value with an error message",
            ),
        ]


def extract_steps(
    raw_steps: list,
    ac: str,
    test_type: str,
    req_title: str = "",
    ac_type: str = "general",
) -> List[TestStepArtifact]:
    """Extract valid steps from raw LLM output, falling back to synthesis.

    Args:
        raw_steps: List of dicts with action/expected_result or strings.
        ac: Target acceptance criterion.
        test_type: Test type (positive/negative/edge_case).
        req_title: Requirement title.
        ac_type: AC classification type.

    Returns:
        List of TestStepArtifact objects.
    """
    seen: set[str] = set()
    real: List[TestStepArtifact] = []

    for s in raw_steps:
        if isinstance(s, dict):
            action = s.get("action", "").strip()
            result = s.get("expected_result", "").strip()
        elif isinstance(s, str):
            action, result = s.strip(), ""
        else:
            continue

        if not action or action in seen or _is_generic_step(action):
            continue
        if _has_loop(action):
            continue

        seen.add(action)
        real.append(TestStepArtifact(action=action, expected_result=result))

    return real if len(real) >= 2 else synthesise_steps(ac, test_type, req_title, ac_type)


def synthesise_tc(
    requirement: Any,
    slot: dict,
    tc_counter: int,
) -> TestCaseArtifact:
    """Generate a complete deterministic test case when LLM fails entirely.

    Args:
        requirement: Requirement object with req_id, title, category, etc.
        slot: Slot dict with test_type, target_ac, title, ac_type.
        tc_counter: Current TC counter for ID generation.

    Returns:
        A complete TestCaseArtifact.
    """
    ac = slot["target_ac"]
    test_type = slot["test_type"]
    ac_type = slot.get("ac_type", "general")
    title = slot.get("title", ac_to_title(ac, test_type))

    given, when, then = make_gwt(ac, test_type, requirement.title, ac_type)
    description = make_description(ac, test_type)
    preconditions = make_preconditions(
        ac, test_type, requirement.category, requirement.title, ac_type
    )
    steps = synthesise_steps(ac, test_type, requirement.title, ac_type)

    priority_map = {"positive": "High", "negative": "Medium", "edge_case": "Low"}

    tc_id = f"TC-{tc_counter:04d}"
    req_id = requirement.req_id if hasattr(requirement, "req_id") else "REQ-UNKNOWN"
    cat = requirement.category if hasattr(requirement, "category") else "General"
    req_tag = re.sub(r"[^a-z0-9-]", "-", req_id.lower())
    cat_tag = cat.lower().replace(" ", "-") if cat else "general"

    return TestCaseArtifact(
        tc_id=tc_id,
        req_id=req_id,
        title=title,
        description=description,
        preconditions=preconditions,
        test_type=test_type,
        priority=priority_map.get(test_type, "Medium"),
        steps=steps,
        expected_outcome=ac,
        tags=[cat_tag, test_type, req_tag],
        category=cat,
        component="Application Screen",  # Resolved later by sanitiser
        given=given,
        when=when,
        then=then,
        estimated_duration="5",
    )


def clean_duration(val: Any) -> str:
    """Clean and normalize test duration values."""
    s = str(val).strip().upper()
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if m:
        total = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        return str(total) if total > 0 else "5"
    digits = re.sub(r"[^\d]", "", s)
    return digits if digits and 0 < int(digits) < 500 else "5"
