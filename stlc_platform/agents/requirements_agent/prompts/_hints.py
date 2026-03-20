"""
Type-Specific Hint Builders
============================
Extracted from legacy test_generator.py hint functions.
These serve as programmatic defaults when no .j2 template override exists.

All hints are parameterized — no domain-specific content.
"""

from __future__ import annotations

from typing import Dict


def get_hints(
    test_type: str,
    ac_type: str,
    ac: str,
    feature: str,
    nav_target: str,
) -> Dict[str, str]:
    """Get type-specific hints for prompt injection.

    Returns dict with keys: desc, pre, steps, outcome.
    """
    if test_type == "positive":
        return _hints_positive(ac, ac_type, feature, nav_target)
    elif test_type == "negative":
        return _hints_negative(ac, ac_type, feature, nav_target)
    else:
        return _hints_edge(ac, ac_type, feature, nav_target)


def get_gwt_hint(test_type: str, ac_type: str, ac: str, feature: str) -> str:
    """Get Given/When/Then hint text for the prompt."""
    if test_type == "positive":
        return (
            f'given: "An eligible user who meets all requirements for {feature} is logged in"\n'
            f'when: "The user performs the specific action to exercise: {ac[:70]}"\n'
            f'then: "The system responds with the observable result described in: {ac[:70]}"'
        )
    elif test_type == "negative":
        neg_when = {
            'ui_behaviour': f"The condition for {ac[:60]} is not met and the user attempts the action",
            'timing': f"The timed event exceeds the limit described in: {ac[:60]}",
            'data_valid': f"The user enters a value that violates the rule in: {ac[:60]}",
            'security': f"The user attempts to bypass the security control in: {ac[:60]}",
        }.get(ac_type, f"An ineligible user attempts the action blocked by: {ac[:60]}")
        return (
            f'given: "A test account is configured for the unhappy path of: {feature}"\n'
            f'when: "{neg_when}"\n'
            f'then: "The system correctly rejects or handles the failure case with an accurate message"'
        )
    else:
        return (
            f'given: "Test data is set at exactly the boundary value for: {ac[:60]}"\n'
            f'when: "The boundary-condition action is executed"\n'
            f'then: "System accepts the boundary value and rejects values beyond it"'
        )


# -- Positive hints ------------------------------------------------------------

def _hints_positive(ac: str, ac_type: str, feature: str, nav_target: str) -> Dict[str, str]:
    if ac_type == 'ui_behaviour':
        return dict(
            desc=f"Verifies that the UI behaviour is displayed correctly for an eligible user: {ac[:90]}.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed on device; tester has valid credentials.",
            steps=(
                f"1. Open the application and log in with valid credentials -> Home screen loads, no error banners\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads; relevant UI area is visible\n"
                f"3. Perform the specific interaction that triggers this behaviour - name the exact button, tab, or action the tester performs -> Name the specific UI element, text, or state that appears\n"
                f"4. Verify the displayed content matches: {ac[:80]} -> Content matches the acceptance criterion exactly\n"
                f"5. Navigate away and return to verify the state persists -> UI state is consistent; no regression"
            ),
            outcome=f"The specific UI element or message described in the acceptance criterion is visible and correct: {ac[:100]}.",
        )
    elif ac_type == 'timing':
        return dict(
            desc=f"Verifies that the timing constraint is met under normal conditions: {ac[:90]}.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed; device clock synchronised; stopwatch or timer ready.",
            steps=(
                f"1. Log in with valid credentials and navigate to the {nav_target} screen -> Screen loads correctly\n"
                f"2. Identify the event that starts the time window - name the specific trigger action for: {ac[:60]} -> Confirm the trigger moment is recorded\n"
                f"3. Perform the trigger action and start timing immediately -> System begins processing; timer is running\n"
                f"4. Observe and record when the expected event occurs - name the specific UI change or notification that signals completion -> Event occurs; elapsed time is noted\n"
                f"5. Compare elapsed time against the requirement: {ac[:60]} -> Elapsed time is within the required limit"
            ),
            outcome=f"The timed event occurs within the limit specified: {ac[:100]}. Elapsed time is recorded in the test evidence.",
        )
    elif ac_type == 'data_valid':
        return dict(
            desc=f"Verifies that the data validation rule accepts a valid value and correctly enforces the constraint: {ac[:90]}.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed; test data prepared with valid and invalid boundary values.",
            steps=(
                f"1. Log in and navigate to the {nav_target} screen -> Relevant form or input field is displayed\n"
                f"2. Enter a value that satisfies the rule - name the specific field and the exact valid boundary value from: {ac[:60]} -> System accepts the input; no validation error shown\n"
                f"3. Submit or confirm the action -> System processes the valid value successfully\n"
                f"4. Clear the field and enter a value that VIOLATES the rule - name the specific invalid value -> System displays an inline validation error\n"
                f"5. Read and verify the error message text -> Error message text correctly describes the validation rule: {ac[:60]}"
            ),
            outcome=f"The system accepts the valid boundary value and correctly rejects the invalid value with an appropriate error message, per: {ac[:100]}.",
        )
    elif ac_type == 'security':
        return dict(
            desc=f"Verifies that the security control is active and enforced under normal operating conditions: {ac[:90]}.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed; security test environment configured.",
            steps=(
                f"1. Log in with valid credentials -> Home screen loads; session is established\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads; relevant security control is active\n"
                f"3. Trigger the security-controlled action - name the specific action that activates the control described in: {ac[:60]} -> Security control engages as expected\n"
                f"4. Observe and verify the specific security behaviour - name what the tester sees or measures that proves the control is active -> The security behaviour matches: {ac[:80]}\n"
                f"5. Attempt to proceed without satisfying the security requirement -> System blocks the attempt; no sensitive action is completed"
            ),
            outcome=f"The security control is active and correctly enforced as described: {ac[:100]}.",
        )
    elif ac_type == 'eligibility':
        return dict(
            desc=f"Verifies that an eligible user can successfully access and use the feature as described: {ac[:90]}.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed; tester has valid credentials.",
            steps=(
                f"1. Open the application and log in with an ELIGIBLE test account -> Home screen loads; account eligibility flags are set correctly\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads; the feature is accessible to this account\n"
                f"3. Perform the action relevant to this eligibility rule - name the specific button or step that exercises the rule: {ac[:60]} -> System recognises the account as eligible and allows the action\n"
                f"4. Confirm the success state -> System shows the expected confirmation or next step for an eligible user\n"
                f"5. Verify no eligibility error or block message appears -> Screen shows the positive outcome described in: {ac[:60]}"
            ),
            outcome=f"The eligible user can complete the action described without restriction: {ac[:100]}.",
        )
    else:  # general
        return dict(
            desc=f"Verifies that {ac[:90]} works correctly for an eligible user under normal conditions.",
            pre=f"Test account meets all eligibility criteria for {feature}; application installed; tester has valid credentials.",
            steps=(
                f"1. Open the application and log in with valid credentials -> Home screen loads without errors\n"
                f"2. Navigate to the {nav_target} screen -> The relevant screen is displayed\n"
                f"3. Perform the specific action required by this acceptance criterion - name the exact button or input the tester uses to exercise: {ac[:60]} -> System accepts the input and processes it correctly\n"
                f"4. Verify the result matches the acceptance criterion: {ac[:80]} -> System displays the correct outcome\n"
                f"5. Navigate away and return to confirm state persistence -> State is saved; no error banners displayed"
            ),
            outcome=f"System correctly completes the action as described in: {ac[:100]}.",
        )


# -- Negative hints ------------------------------------------------------------

def _hints_negative(ac: str, ac_type: str, feature: str, nav_target: str) -> Dict[str, str]:
    if ac_type == 'ui_behaviour':
        return dict(
            desc=f"Verifies the system handles the unhappy path correctly when the condition required for this UI behaviour is NOT met: {ac[:90]}.",
            pre="Test account configured so the condition described in the AC is deliberately not satisfied; application installed; tester logged in.",
            steps=(
                f"1. Log in with a test account where the condition for this AC is NOT met -> Home screen loads; the triggering condition is absent\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads\n"
                f"3. Attempt to trigger the UI behaviour described in: {ac[:60]} without satisfying its precondition - name the specific action taken -> System should NOT show the behaviour\n"
                f"4. Observe what the system actually displays -> System shows the correct fallback state or error message\n"
                f"5. Verify no incorrect or partial UI state is shown -> System handles the unhappy path cleanly with no partial render"
            ),
            outcome=f"When the required condition is not met, the UI does not incorrectly display the element described in: {ac[:100]}. Fallback state is correct.",
        )
    elif ac_type == 'timing':
        return dict(
            desc=f"Verifies the system handles the scenario where the time limit is exceeded: {ac[:90]}.",
            pre=f"Test environment configured to simulate a delay exceeding the limit in: {ac[:60]}; application installed; tester logged in.",
            steps=(
                f"1. Log in and navigate to the {nav_target} screen -> Screen loads\n"
                f"2. Configure or simulate a delay that will exceed the time limit described in: {ac[:60]} -> Delay condition is confirmed in the test environment\n"
                f"3. Trigger the timed event - name the specific action -> Processing begins; timer is running\n"
                f"4. Allow the time limit to be exceeded without the expected event occurring -> System detects the timeout condition\n"
                f"5. Observe and verify the system timeout behaviour - name the specific error message, alert, or fallback state shown -> System displays the correct timeout error or fallback"
            ),
            outcome=f"When the time limit is exceeded, the system correctly detects the timeout and displays an appropriate error or fallback state, per: {ac[:100]}.",
        )
    elif ac_type == 'data_valid':
        return dict(
            desc=f"Verifies the system correctly rejects a value that violates the validation rule: {ac[:90]}.",
            pre=f"Test account active; test data prepared with an invalid value that violates the constraint in: {ac[:60]}; application installed.",
            steps=(
                f"1. Log in and navigate to the {nav_target} screen -> Relevant form or input field is displayed\n"
                f"2. Enter a value that violates the rule described in: {ac[:60]} - name the specific invalid value -> System may show an inline error immediately or on submit\n"
                f"3. Submit or attempt to proceed -> System rejects the invalid value\n"
                f"4. Read the validation error message displayed on screen -> Error message accurately describes the rule violation\n"
                f"5. Attempt to bypass the validation (e.g. back button, direct navigation) -> System maintains the block; no invalid data is saved"
            ),
            outcome=f"The system correctly rejects the invalid input and displays an accurate validation error message, per: {ac[:100]}.",
        )
    elif ac_type == 'security':
        return dict(
            desc=f"Verifies the security control correctly blocks an attempt to bypass it: {ac[:90]}.",
            pre="Test environment configured for bypass attempt; application installed; tester logged in with a non-privileged account.",
            steps=(
                f"1. Log in with a test account that does NOT satisfy the security requirement -> Home screen loads\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads\n"
                f"3. Attempt to perform the security-controlled action without satisfying the control described in: {ac[:60]} - name the specific bypass action attempted -> System detects the attempted bypass\n"
                f"4. Read the error, warning, or block message displayed -> Correct security rejection message is shown\n"
                f"5. Verify no sensitive action was completed and no data was written -> System state is unchanged; audit log records the attempt"
            ),
            outcome=f"The security control correctly blocks the bypass attempt with an appropriate rejection message, per: {ac[:100]}.",
        )
    else:  # eligibility / general
        return dict(
            desc=f"Verifies the system correctly blocks an ineligible user attempting: {ac[:90]}.",
            pre=f"Test account configured to be ineligible for {feature} (fails one or more eligibility criteria); application installed; tester logged in.",
            steps=(
                f"1. Log in with an INELIGIBLE test account -> Home screen loads; ineligibility condition is active\n"
                f"2. Navigate to the {nav_target} screen -> Screen loads\n"
                f"3. Attempt the action that the eligibility rule blocks - name the specific button or step the tester tries: {ac[:60]} -> System detects the ineligibility condition\n"
                f"4. Read the rejection or error message displayed on screen - note the exact message text shown -> Correct rejection message is displayed\n"
                f"5. Attempt to bypass the block (e.g. back button, direct navigation) -> System maintains the block; no data is saved or partially committed"
            ),
            outcome=f"The system correctly rejects the ineligible user with the appropriate error message, per: {ac[:100]}.",
        )


# -- Edge case hints -----------------------------------------------------------

def _hints_edge(ac: str, ac_type: str, feature: str, nav_target: str) -> Dict[str, str]:
    if ac_type == 'data_valid':
        return dict(
            desc=f"Verifies the system enforces the exact boundary defined by the validation rule: {ac[:90]}.",
            pre=f"Test data prepared at exactly the boundary value defined in: {ac[:60]}; and at one unit beyond the boundary; application installed; tester logged in.",
            steps=(
                f"1. Log in and navigate to the {nav_target} screen -> Input field is displayed\n"
                f"2. Enter the value at EXACTLY the boundary - name the specific field and the exact boundary value from: {ac[:60]} -> System accepts the boundary value without error\n"
                f"3. Submit or trigger validation -> System processes the exact boundary value correctly\n"
                f"4. Clear the field and enter a value ONE UNIT BEYOND the boundary - name the exact out-of-bounds value used -> System rejects the out-of-bounds value with an error message\n"
                f"5. Verify the error message text is correct -> Error correctly describes the boundary that was exceeded"
            ),
            outcome=f"System accepts the exact boundary value and rejects the value one unit beyond it with an accurate error message, per: {ac[:100]}.",
        )
    elif ac_type == 'timing':
        return dict(
            desc=f"Verifies the system behaviour exactly at the time boundary described: {ac[:90]}.",
            pre=f"Test environment configured to trigger events at exactly the time boundary in: {ac[:60]}; application installed; tester logged in; timer ready.",
            steps=(
                f"1. Log in and navigate to the {nav_target} screen -> Screen loads\n"
                f"2. Configure the test environment to reach the time limit exactly - name the specific mechanism used to control timing for: {ac[:60]} -> Timing condition is confirmed\n"
                f"3. Trigger the timed event and start the timer -> System begins processing\n"
                f"4. Observe the system behaviour AT the exact boundary time - record what the system displays at the limit -> System handles the boundary moment correctly\n"
                f"5. Exceed the limit by one unit and observe the change -> System transitions to the correct timeout or expiry state"
            ),
            outcome=f"System behaves correctly at exactly the time boundary and transitions to the timeout state when exceeded, per: {ac[:100]}.",
        )
    else:  # general
        return dict(
            desc=f"Verifies system boundary enforcement at the exact limit described in: {ac[:90]}.",
            pre=f"Test data configured at exactly the boundary value for: {ac[:60]}; application installed; tester logged in.",
            steps=(
                f"1. Configure test data at exactly the boundary value described in: {ac[:60]} -> Test data is set precisely at the boundary\n"
                f"2. Log in and navigate to the {nav_target} screen -> Screen loads; boundary test data is visible\n"
                f"3. Execute the boundary action - name the specific button or step the tester performs at the exact limit value -> System processes the boundary value correctly\n"
                f"4. Observe and record the outcome displayed on screen - name the specific message, state, or value shown -> Outcome matches the requirement at the boundary: {ac[:60]}\n"
                f"5. Repeat with a value one unit beyond the boundary -> System correctly rejects or handles the out-of-bounds value"
            ),
            outcome=f"System correctly accepts the exact boundary value and rejects values beyond it, per: {ac[:100]}.",
        )
