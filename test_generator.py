"""
Test Case Generator  v10
=======================
Key improvements over v9:

1. AC TYPE CLASSIFIER  (_classify_ac)
   Classifies each acceptance criterion into one of 6 types before any prompt is built:
     eligibility   - who is/isn't allowed to use the feature
     ui_behaviour  - a visible element, screen state, or displayed content
     timing        - a time limit, deadline, or performance threshold
     data_valid    - a validation rule on a field or submitted value
     security      - auth, encryption, certificate, session-control rule
     general       - anything else

2. TYPE-SPECIFIC PROMPTS  (_build_prompt)
   Every type gets its own description, precondition, step, and outcome hints.
   Steps now explicitly ask the model: "name the exact button/field/value the
   tester interacts with" - not "perform the action required by {AC}".

3. TYPE-SPECIFIC NEGATIVE FRAMING
   Negative for ui_behaviour = unhappy path (condition not met, element absent).
   Negative for timing = exceed the time limit.
   Negative for data_valid = submit invalid boundary value.
   Negative for eligibility = ineligible user (original behaviour, still correct here).
   Negative for security = attempt to bypass the control.

4. CHAIN-OF-THOUGHT INSTRUCTION
   Embedded in every prompt - instructs the model to name the concrete action
   and observable evidence before writing each step.

5. STRICTER SANITISER
   Loop detection: if any field contains a phrase repeated 3+ times, the field
   is discarded and replaced deterministically.
   Snake_case field content is discarded.
   Python dict / JSON leakage is discarded.
"""
import re
from typing import List, Optional
from dataclasses import dataclass, field
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from config import config
from llm_client import OllamaClient
from requirements_reader import Requirement

console = Console()


# -- Data classes --------------------------------------------------------------

@dataclass
class TestStep:
    action: str
    expected_result: str


@dataclass
class TestCase:
    tc_id: str
    req_id: str
    title: str
    description: str
    preconditions: str
    test_type: str
    priority: str
    steps: List[TestStep] = field(default_factory=list)
    expected_outcome: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = ""
    component: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    estimated_duration: str = "5"


# -- System prompt -------------------------------------------------------------

def _build_system_prompt(domain: str = "") -> str:
    """
    Build a domain-aware system prompt.
    domain is derived at runtime from requirement data — never hardcoded.
    Falls back to generic 'software application' if nothing is provided.
    """
    app_description = f"the {domain} application" if domain else "this software application"
    return f"""\
You are a senior QA engineer with 10 years of experience writing executable test cases \
for {app_description}.
Your output is handed directly to a junior tester who has never seen the application. \
They must be able to execute every step without asking a question.

MANDATORY RULES — violating any rule will cause the test to be rejected:

RULE 1 — SPECIFIC ACTIONS ONLY
  Every step action must name: the exact button label, field name, menu item, or UI element.
  WRONG: "Perform the action required by the acceptance criterion"
  WRONG: "Trigger the feature and observe the result"
  RIGHT: "Tap the 'Submit Deposit' button on the Deposit Review screen"
  RIGHT: "Enter '1234567' in the Cheque Number field and tap outside the field"

RULE 2 — SPECIFIC OBSERVABLE RESULTS ONLY
  Every step expected_result must name: the exact message text, screen name, badge state,
  measured value, or UI element that proves the step succeeded.
  WRONG: "System responds correctly"
  WRONG: "The outcome is as expected"
  RIGHT: "Error message 'Cheque number must be exactly 6 digits' appears below the field"
  RIGHT: "Green tick icon appears next to the Amount field; Submit button becomes active"

RULE 3 — NO REPETITION
  Do NOT repeat any sentence, phrase, or clause more than once in your entire response.
  Each step action must be distinct from every other step action.

RULE 4 — TITLE MUST BE COPIED EXACTLY
  Copy the mandatory title from the prompt into the title field character-for-character.
  Do not rephrase, shorten, or reorder any words.

RULE 5 — NO INSTRUCTION TEXT IN OUTPUT
  Do not copy any prompt instruction, field label, or placeholder text into your output.
  Your output fields must contain only specific test content.

RULE 6 — PROSE FIELDS ARE ONE OR TWO SENTENCES
  description, preconditions, expected_outcome, given, when, then — one or two sentences each.
  No numbered lists, no bullet points, no multi-paragraph blocks in these fields.

RULE 7 — COMPONENT IS A SPECIFIC SCREEN NAME
  The component field must name the specific screen, service, or module being tested.
  WRONG: "the application"  |  WRONG: "mobile app"  |  WRONG: "the system"
  RIGHT: "OTP Verification Screen"  |  RIGHT: "Order Confirmation Screen"
"""


def _infer_domain(requirements) -> str:
    """
    Infer a plain-English domain label from the requirement set.
    Uses category names — no hardcoded domain strings.
    Examples: ['Patient Registration', 'Clinical Records'] -> 'healthcare'
              ['Product Catalogue', 'Checkout'] -> 'retail e-commerce'
              ['Account Onboarding', 'Transaction Processing'] -> 'financial services'
    Falls back to first requirement's title if categories are sparse.
    """
    if not requirements:
        return ""
    cats = []
    for r in requirements:
        if hasattr(r, 'category') and r.category:
            cats.append(r.category.lower())
        elif hasattr(r, 'title') and r.title:
            cats.append(r.title.lower())
    combined = " ".join(cats)
    # Detect domain from combined category text — keyword-based, no hardcoding
    if any(k in combined for k in ['cheque','banking','deposit','rcd','micr','clearing']):
        return "mobile banking"
    if any(k in combined for k in ['patient','clinical','ehr','prescription','pharmacy','diagnosis']):
        return "healthcare"
    if any(k in combined for k in ['product','cart','checkout','inventory','catalogue','order','shipping']):
        return "retail e-commerce"
    if any(k in combined for k in ['policy','claim','premium','underwriting','insur']):
        return "insurance"
    if any(k in combined for k in ['student','course','enrol','grade','curriculum','lms']):
        return "education"
    if any(k in combined for k in ['ticket','incident','asset','sla','helpdesk','itil']):
        return "IT service management"
    # Generic fallback — use the first category as the domain label
    first_cat = cats[0].title() if cats else ""
    return first_cat if first_cat else ""


# -- Few-shot block builder ----------------------------------------------------

def _build_few_shot_block(examples: list) -> str:
    """
    Format 1-2 retrieved approved TCs as a concrete few-shot block for injection
    into the user prompt.

    WHY THIS WORKS:
      7B models are pattern matchers, not rule followers. Showing one correct example
      of a test case with specific actions, expected results, and a real component name
      gives the model a template to fill — it substitutes values from the current
      requirement instead of generating from its own prior.

      This replaces: "RULE 1: Every step must name a specific action..."
      With:          "Here is an example of a correct test case. Follow this pattern."

    Returns empty string if no examples available (graceful degradation).
    """
    if not examples:
        return ""

    lines = [
        "\n── FEW-SHOT EXAMPLES ───────────────────────────────────────────────",
        "Study the pattern in these approved test cases before writing yours.",
        "Your test case must follow the same level of specificity.",
        "Substitute values from the TARGET ACCEPTANCE CRITERION above — do not copy these examples.\n",
    ]

    for idx, ex in enumerate(examples[:2], 1):
        lines.append(f"EXAMPLE {idx}  [{ex.get('test_type','')} | {ex.get('ac_type','')}]")
        lines.append(f"  description:   {ex.get('description','')[:120]}")
        lines.append(f"  preconditions: {ex.get('preconditions','')[:120]}")
        lines.append(f"  given: {ex.get('given','')[:100]}")
        lines.append(f"  when:  {ex.get('when','')[:100]}")
        lines.append(f"  then:  {ex.get('then','')[:100]}")
        lines.append("  steps:")
        for i, step in enumerate(ex.get("steps", [])[:5], 1):
            if isinstance(step, dict):
                a = step.get("action", "")[:100]
                r = step.get("expected_result", "")[:100]
                lines.append(f"    {i}. {a}")
                lines.append(f"       -> {r}")
        lines.append(f"  expected_outcome: {ex.get('expected_outcome','')[:120]}")
        lines.append(f"  component: {ex.get('component','')}")
        if idx < len(examples[:2]):
            lines.append("")

    lines.append("── END EXAMPLES ────────────────────────────────────────────────────\n")
    return "\n".join(lines)


# -- AC Type Classifier --------------------------------------------------------

def _classify_ac(ac):
    """
    Classify an acceptance criterion into one of 6 types.
    Uses keyword matching - no LLM call needed.
    Returns one of: eligibility, ui_behaviour, timing, data_valid, security, general
    """
    a = ac.lower()

    # Security / auth — domain-agnostic: these concepts appear in banking, healthcare,
    # retail, insurance, etc. Banking-specific terms (uv-reactive, fraud team, cheque)
    # are removed — they won't appear in other domains and don't need to be here.
    if any(k in a for k in [
        'biometric', 'otp', 'certificate pinning', 'screenshot',
        'screen recording', 'rooted', 'jailbreak', 'session timeout', 'session hard',
        'encrypt', 'hash', 'auth token', 're-authenticate', 're-verify',
        'ssl', 'tls', 'certificate', 'pinning', 'security feature',
        'multi-factor', 'mfa', '2fa', 'two-factor', 'access token',
        'tamper', 'intrusion', 'anomaly detection', 'fraud detection',
    ]):
        return 'security'

    # Timing / performance — checked FIRST so time-based eligibility ACs like
    # "customers older than 90 days" classify as timing, not eligibility.
    if any(k in a for k in [
        'within ', 'seconds', 'minutes', 'hours', 'days', 'timeout', 't+1', 't+2', 't+3',
        'millisecond', 'latency', 'cutoff', 'business hours',
        'sla', 'response time', 'no longer than', 'at most',
    ]):
        return 'timing'

    # Eligibility / access gating — broad domain-agnostic coverage
    if any(k in a for k in [
        'eligible', 'ineligible', 'eligibility', 'enrolled', 'enroll',
        'not allowed', 'not permitted', 'access denied', 'unauthorised', 'unauthorized',
        'restricted to', 'only allowed', 'must be a member', 'membership required',
        'tier ', ' tier', 'subscription', 'licence required', 'license required',
        'only users', 'only customers', 'only agents', 'only staff', 'only admin',
        'must present', 'must provide valid', 'requires role', 'must have role',
        'must hold', 'requires permission', 'requires a valid',
    ]):
        return 'eligibility'

    # Data validation — domain-agnostic field/value constraints
    if any(k in a for k in [
        'validated', 'validation', 'format validated', 'digits',
        'numeric', 'date picker', 'future dates', 'minimum',
        'exactly', '> 100', '< 40%', '< 75%', '>85%', '>95%',
        'confidence score', 'dpi', 'characters', 'contrast ratio', 'blur',
        'inline error', 'must not exceed', 'must be between', 'required format',
        'allowed values', 'cannot be empty', 'max length', 'min length',
        'alphanumeric', 'maximum', 'field is required', 'mandatory field',
    ]):
        return 'data_valid'

    # UI behaviour — visible states, elements, text, indicators
    # Generic keywords only; domain-specific ones like 'cheque-shaped' are fine
    # because they won't appear in other domains and do no harm if they do.
    if any(k in a for k in [
        'shown', 'displayed', 'visible', 'appears', 'prompt', 'button',
        'overlay', 'badge', 'spinner', 'indicator', 'launches', 'screen',
        'message', 'notification', 'banner', 'toast', 'alert', 'highlight',
        'colour', 'color', 'icon', 'label', 'shows', 'listed', 'accessible',
        'pre-populated', 'paginated', 'sorted', 'search by', 'deep link',
        'toggle', 'thumbnail', 'pinch-to-zoom', 'colour-coded', 'landscape',
        'overlay guide', 'sequential flow', 'auto-capture', 'brightness',
        'focus quality',
    ]):
        return 'ui_behaviour'

    return 'general'


# -- Title pre-generation ------------------------------------------------------

_TYPE_VERB = {
    "positive":  "Verify",
    "negative":  "Validate rejection when",
    "edge_case": "Confirm boundary for",
}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "should", "must", "will", "that",
    "which", "when", "where", "and", "or", "of", "to", "in", "on",
    "for", "with", "be", "has", "have", "by", "from", "as",
}


def _ac_to_title(ac, test_type):
    verb = _TYPE_VERB.get(test_type, "Verify")
    text = ac.strip().rstrip(".")
    words = text.split()
    condensed = " ".join(w for w in words if w.lower() not in _STOPWORDS)
    condensed = re.sub(r"\s+", " ", condensed).strip()
    if len(condensed) < 15:
        condensed = text
    if len(condensed) > 70:
        condensed = condensed[:70].rsplit(" ", 1)[0]
    return f"{verb} -- {condensed}"


def _build_slot_plan(requirement, max_tc, include_negative, include_edge):
    if include_negative and include_edge:
        pattern = ["positive", "negative", "edge_case"]
    elif include_negative:
        pattern = ["positive", "negative"]
    elif include_edge:
        pattern = ["positive", "edge_case"]
    else:
        pattern = ["positive"]

    acs = requirement.acceptance_criteria or [requirement.description[:120]]
    slots = []
    seen_titles = set()

    for i in range(max_tc):
        test_type  = pattern[i % len(pattern)]
        target_ac  = acs[i % len(acs)]
        ac_type    = _classify_ac(target_ac)
        title      = _ac_to_title(target_ac, test_type)

        original = title
        suffix = 2
        while title.lower()[:50] in seen_titles:
            title = f"{original} ({suffix})"
            suffix += 1

        seen_titles.add(title.lower()[:50])
        slots.append({
            "test_type": test_type,
            "target_ac": target_ac,
            "title":     title,
            "ac_type":   ac_type,
        })

    return slots


# -- Type-specific hint builders -----------------------------------------------

_COT_INSTRUCTION = """\
CHAIN-OF-THOUGHT REQUIREMENT - before writing each step, mentally answer:
  a) What is the exact button, field, menu item, or UI element the tester interacts with?
  b) What specific value does the tester enter, select, or measure?
  c) What exact text, icon, badge, or screen state confirms the step succeeded?
Use those concrete answers directly in your step text. Do not write generic phrases
like "perform the action", "trigger the feature", or "verify the outcome"."""


def _hints_positive(ac, ac_type, feature, nav_target):
    if ac_type == 'ui_behaviour':
        return dict(
            desc=(
                f"Verifies that the UI behaviour is displayed correctly for an eligible user: {ac[:90]}."
            ),
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed on device; tester has valid credentials."
            ),
            steps=(
                f"1. Open the application and log in with valid credentials"
                f" -> Home screen loads, no error banners\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads; relevant UI area is visible\n"
                f"3. Perform the specific interaction that triggers this behaviour"
                f" - name the exact button, tab, or action the tester performs"
                f" -> Name the specific UI element, text, or state that appears\n"
                f"4. Verify the displayed content matches: {ac[:80]}"
                f" -> Content matches the acceptance criterion exactly\n"
                f"5. Navigate away and return to verify the state persists"
                f" -> UI state is consistent; no regression"
            ),
            outcome=(
                f"The specific UI element or message described in the acceptance criterion "
                f"is visible and correct: {ac[:100]}."
            ),
        )

    elif ac_type == 'timing':
        return dict(
            desc=(f"Verifies that the timing constraint is met under normal conditions: {ac[:90]}."),
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed; device clock synchronised; stopwatch or timer ready."
            ),
            steps=(
                f"1. Log in with valid credentials and navigate to the {nav_target} screen"
                f" -> Screen loads correctly\n"
                f"2. Identify the event that starts the time window - name the specific"
                f" trigger action for: {ac[:60]}"
                f" -> Confirm the trigger moment is recorded\n"
                f"3. Perform the trigger action and start timing immediately"
                f" -> System begins processing; timer is running\n"
                f"4. Observe and record when the expected event occurs"
                f" - name the specific UI change or notification that signals completion"
                f" -> Event occurs; elapsed time is noted\n"
                f"5. Compare elapsed time against the requirement: {ac[:60]}"
                f" -> Elapsed time is within the required limit"
            ),
            outcome=(
                f"The timed event occurs within the limit specified: {ac[:100]}. "
                f"Elapsed time is recorded in the test evidence."
            ),
        )

    elif ac_type == 'data_valid':
        return dict(
            desc=(
                f"Verifies that the data validation rule accepts a valid value "
                f"and correctly enforces the constraint: {ac[:90]}."
            ),
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed; test data prepared with valid and invalid boundary values."
            ),
            steps=(
                f"1. Log in and navigate to the {nav_target} screen"
                f" -> Relevant form or input field is displayed\n"
                f"2. Enter a value that satisfies the rule - name the specific field"
                f" and the exact valid boundary value from: {ac[:60]}"
                f" -> System accepts the input; no validation error shown\n"
                f"3. Submit or confirm the action"
                f" -> System processes the valid value successfully\n"
                f"4. Clear the field and enter a value that VIOLATES the rule"
                f" - name the specific invalid value"
                f" -> System displays an inline validation error\n"
                f"5. Read and verify the error message text"
                f" -> Error message text correctly describes the validation rule: {ac[:60]}"
            ),
            outcome=(
                f"The system accepts the valid boundary value and correctly rejects "
                f"the invalid value with an appropriate error message, per: {ac[:100]}."
            ),
        )

    elif ac_type == 'security':
        return dict(
            desc=(
                f"Verifies that the security control is active and enforced "
                f"under normal operating conditions: {ac[:90]}."
            ),
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed; security test environment configured."
            ),
            steps=(
                f"1. Log in with valid credentials"
                f" -> Home screen loads; session is established\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads; relevant security control is active\n"
                f"3. Trigger the security-controlled action - name the specific"
                f" action that activates the control described in: {ac[:60]}"
                f" -> Security control engages as expected\n"
                f"4. Observe and verify the specific security behaviour"
                f" - name what the tester sees or measures that proves the control is active"
                f" -> The security behaviour matches: {ac[:80]}\n"
                f"5. Attempt to proceed without satisfying the security requirement"
                f" -> System blocks the attempt; no sensitive action is completed"
            ),
            outcome=(
                f"The security control is active and correctly enforced as described: {ac[:100]}."
            ),
        )

    elif ac_type == 'eligibility':
        return dict(
            desc=(
                f"Verifies that an eligible user can successfully access and use "
                f"the feature as described: {ac[:90]}."
            ),
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed; tester has valid credentials."
            ),
            steps=(
                f"1. Open the application and log in with an ELIGIBLE test account"
                f" -> Home screen loads; account eligibility flags are set correctly\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads; the feature is accessible to this account\n"
                f"3. Perform the action relevant to this eligibility rule"
                f" - name the specific button or step that exercises the rule: {ac[:60]}"
                f" -> System recognises the account as eligible and allows the action\n"
                f"4. Confirm the success state"
                f" -> System shows the expected confirmation or next step for an eligible user\n"
                f"5. Verify no eligibility error or block message appears"
                f" -> Screen shows the positive outcome described in: {ac[:60]}"
            ),
            outcome=(
                f"The eligible user can complete the action described without restriction: {ac[:100]}."
            ),
        )

    else:
        return dict(
            desc=f"Verifies that {ac[:90]} works correctly for an eligible user under normal conditions.",
            pre=(
                f"Test account meets all eligibility criteria for {feature}; "
                f"application installed; tester has valid credentials."
            ),
            steps=(
                f"1. Open the application and log in with valid credentials"
                f" -> Home screen loads without errors\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> The relevant screen is displayed\n"
                f"3. Perform the specific action required by this acceptance criterion"
                f" - name the exact button or input the tester uses to exercise: {ac[:60]}"
                f" -> System accepts the input and processes it correctly\n"
                f"4. Verify the result matches the acceptance criterion: {ac[:80]}"
                f" -> System displays the correct outcome\n"
                f"5. Navigate away and return to confirm state persistence"
                f" -> State is saved; no error banners displayed"
            ),
            outcome=f"System correctly completes the action as described in: {ac[:100]}.",
        )


def _hints_negative(ac, ac_type, feature, nav_target):
    if ac_type == 'ui_behaviour':
        return dict(
            desc=(
                f"Verifies the system handles the unhappy path correctly when the condition "
                f"required for this UI behaviour is NOT met: {ac[:90]}."
            ),
            pre=(
                f"Test account configured so the condition described in the AC is deliberately"
                f" not satisfied; application installed; tester logged in."
            ),
            steps=(
                f"1. Log in with a test account where the condition for this AC is NOT met"
                f" -> Home screen loads; the triggering condition is absent\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads\n"
                f"3. Attempt to trigger the UI behaviour described in: {ac[:60]}"
                f" without satisfying its precondition"
                f" - name the specific action taken -> System should NOT show the behaviour\n"
                f"4. Observe what the system actually displays"
                f" -> System shows the correct fallback state or error message\n"
                f"5. Verify no incorrect or partial UI state is shown"
                f" -> System handles the unhappy path cleanly with no partial render"
            ),
            outcome=(
                f"When the required condition is not met, the UI does not incorrectly "
                f"display the element described in: {ac[:100]}. Fallback state is correct."
            ),
        )

    elif ac_type == 'timing':
        return dict(
            desc=(
                f"Verifies the system handles the scenario where the time limit "
                f"is exceeded: {ac[:90]}."
            ),
            pre=(
                f"Test environment configured to simulate a delay exceeding the limit in: {ac[:60]}; "
                f"application installed; tester logged in."
            ),
            steps=(
                f"1. Log in and navigate to the {nav_target} screen"
                f" -> Screen loads\n"
                f"2. Configure or simulate a delay that will exceed the time limit"
                f" described in: {ac[:60]}"
                f" -> Delay condition is confirmed in the test environment\n"
                f"3. Trigger the timed event - name the specific action"
                f" -> Processing begins; timer is running\n"
                f"4. Allow the time limit to be exceeded without the expected event occurring"
                f" -> System detects the timeout condition\n"
                f"5. Observe and verify the system timeout behaviour"
                f" - name the specific error message, alert, or fallback state shown"
                f" -> System displays the correct timeout error or fallback"
            ),
            outcome=(
                f"When the time limit is exceeded, the system correctly detects the timeout "
                f"and displays an appropriate error or fallback state, per: {ac[:100]}."
            ),
        )

    elif ac_type == 'data_valid':
        return dict(
            desc=(
                f"Verifies the system correctly rejects a value that violates "
                f"the validation rule: {ac[:90]}."
            ),
            pre=(
                f"Test account active; test data prepared with an invalid value "
                f"that violates the constraint in: {ac[:60]}; application installed."
            ),
            steps=(
                f"1. Log in and navigate to the {nav_target} screen"
                f" -> Relevant form or input field is displayed\n"
                f"2. Enter a value that violates the rule described in: {ac[:60]}"
                f" - name the specific invalid value (wrong format, out of range, forbidden character)"
                f" -> System may show an inline error immediately or on submit\n"
                f"3. Submit or attempt to proceed"
                f" -> System rejects the invalid value\n"
                f"4. Read the validation error message displayed on screen"
                f" -> Error message accurately describes the rule violation\n"
                f"5. Attempt to bypass the validation (e.g. back button, direct navigation)"
                f" -> System maintains the block; no invalid data is saved"
            ),
            outcome=(
                f"The system correctly rejects the invalid input and displays an accurate "
                f"validation error message, per: {ac[:100]}."
            ),
        )

    elif ac_type == 'security':
        return dict(
            desc=(
                f"Verifies the security control correctly blocks an attempt to bypass it: {ac[:90]}."
            ),
            pre=(
                f"Test environment configured for bypass attempt; application installed; "
                f"tester logged in with a non-privileged account."
            ),
            steps=(
                f"1. Log in with a test account that does NOT satisfy the security requirement"
                f" -> Home screen loads\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads\n"
                f"3. Attempt to perform the security-controlled action without satisfying"
                f" the control described in: {ac[:60]}"
                f" - name the specific bypass action attempted"
                f" -> System detects the attempted bypass\n"
                f"4. Read the error, warning, or block message displayed"
                f" -> Correct security rejection message is shown\n"
                f"5. Verify no sensitive action was completed and no data was written"
                f" -> System state is unchanged; audit log records the attempt"
            ),
            outcome=(
                f"The security control correctly blocks the bypass attempt with an appropriate "
                f"rejection message, per: {ac[:100]}."
            ),
        )

    else:
        return dict(
            desc=(
                f"Verifies the system correctly blocks an ineligible user "
                f"attempting: {ac[:90]}."
            ),
            pre=(
                f"Test account configured to be ineligible for {feature} "
                f"(fails one or more eligibility criteria); application installed; tester logged in."
            ),
            steps=(
                f"1. Log in with an INELIGIBLE test account"
                f" -> Home screen loads; ineligibility condition is active\n"
                f"2. Navigate to the {nav_target} screen"
                f" -> Screen loads\n"
                f"3. Attempt the action that the eligibility rule blocks"
                f" - name the specific button or step the tester tries: {ac[:60]}"
                f" -> System detects the ineligibility condition\n"
                f"4. Read the rejection or error message displayed on screen"
                f" - note the exact message text shown"
                f" -> Correct rejection message is displayed\n"
                f"5. Attempt to bypass the block (e.g. back button, direct navigation)"
                f" -> System maintains the block; no data is saved or partially committed"
            ),
            outcome=(
                f"The system correctly rejects the ineligible user with the appropriate "
                f"error message, per: {ac[:100]}."
            ),
        )


def _hints_edge(ac, ac_type, feature, nav_target):
    if ac_type == 'data_valid':
        return dict(
            desc=(
                f"Verifies the system enforces the exact boundary defined by "
                f"the validation rule: {ac[:90]}."
            ),
            pre=(
                f"Test data prepared at exactly the boundary value defined in: {ac[:60]}; "
                f"and at one unit beyond the boundary; application installed; tester logged in."
            ),
            steps=(
                f"1. Log in and navigate to the {nav_target} screen"
                f" -> Input field is displayed\n"
                f"2. Enter the value at EXACTLY the boundary - name the specific field"
                f" and the exact boundary value from: {ac[:60]}"
                f" -> System accepts the boundary value without error\n"
                f"3. Submit or trigger validation"
                f" -> System processes the exact boundary value correctly\n"
                f"4. Clear the field and enter a value ONE UNIT BEYOND the boundary"
                f" - name the exact out-of-bounds value used"
                f" -> System rejects the out-of-bounds value with an error message\n"
                f"5. Verify the error message text is correct"
                f" -> Error correctly describes the boundary that was exceeded"
            ),
            outcome=(
                f"System accepts the exact boundary value and rejects the value one unit "
                f"beyond it with an accurate error message, per: {ac[:100]}."
            ),
        )

    elif ac_type == 'timing':
        return dict(
            desc=(
                f"Verifies the system behaviour exactly at the time boundary described: {ac[:90]}."
            ),
            pre=(
                f"Test environment configured to trigger events at exactly the time boundary in: {ac[:60]}; "
                f"application installed; tester logged in; timer ready."
            ),
            steps=(
                f"1. Log in and navigate to the {nav_target} screen"
                f" -> Screen loads\n"
                f"2. Configure the test environment to reach the time limit exactly"
                f" - name the specific mechanism used to control timing for: {ac[:60]}"
                f" -> Timing condition is confirmed\n"
                f"3. Trigger the timed event and start the timer"
                f" -> System begins processing\n"
                f"4. Observe the system behaviour AT the exact boundary time"
                f" - record what the system displays at the limit"
                f" -> System handles the boundary moment correctly\n"
                f"5. Exceed the limit by one unit and observe the change"
                f" -> System transitions to the correct timeout or expiry state"
            ),
            outcome=(
                f"System behaves correctly at exactly the time boundary and transitions "
                f"to the timeout state when exceeded, per: {ac[:100]}."
            ),
        )

    else:
        return dict(
            desc=(
                f"Verifies system boundary enforcement at the exact limit described in: {ac[:90]}."
            ),
            pre=(
                f"Test data configured at exactly the boundary value for: {ac[:60]}; "
                f"application installed; tester logged in."
            ),
            steps=(
                f"1. Configure test data at exactly the boundary value described in: {ac[:60]}"
                f" -> Test data is set precisely at the boundary\n"
                f"2. Log in and navigate to the {nav_target} screen"
                f" -> Screen loads; boundary test data is visible\n"
                f"3. Execute the boundary action - name the specific button or step"
                f" the tester performs at the exact limit value"
                f" -> System processes the boundary value correctly\n"
                f"4. Observe and record the outcome displayed on screen"
                f" - name the specific message, state, or value shown"
                f" -> Outcome matches the requirement at the boundary: {ac[:60]}\n"
                f"5. Repeat with a value one unit beyond the boundary"
                f" -> System correctly rejects or handles the out-of-bounds value"
            ),
            outcome=(
                f"System correctly accepts the exact boundary value and rejects "
                f"values beyond it, per: {ac[:100]}."
            ),
        )


# -- Prompt builder ------------------------------------------------------------

_TYPE_CONTEXT = {
    "positive": (
        "SCENARIO TYPE: Positive / Happy Path -- test that the feature works correctly "
        "for a valid, eligible user with correct inputs."
    ),
    "negative": (
        "SCENARIO TYPE: Negative / Error Handling -- test the system's response when "
        "the expected condition is NOT met, an ineligible user attempts access, "
        "or invalid input is submitted. Verify the exact error message and that no "
        "data is written."
    ),
    "edge_case": (
        "SCENARIO TYPE: Edge Case / Boundary -- test exactly at the numeric limit, "
        "time threshold, or constraint stated in the AC. Verify both: the boundary "
        "value is accepted, and a value one unit beyond is rejected."
    ),
}


def _build_prompt(requirement, slot, test_number, total, context, tc_format, examples=None):
    """
    Build the user prompt for one test case slot.
    examples: retrieved TC dicts from tc_examples collection for few-shot injection.
    """
    all_ac_text = (
        "\n".join(f"  AC{i+1}: {ac}" for i, ac in enumerate(requirement.acceptance_criteria))
        if requirement.acceptance_criteria else "  (none specified)"
    )
    context_block = (
        f"\nRELATED REQUIREMENTS (context only):\n{context}\n"
        if context else ""
    )
    # Few-shot block — present when examples retrieved from ChromaDB
    few_shot_block = _build_few_shot_block(examples or [])

    ac       = slot["target_ac"]
    tt       = slot["test_type"]
    ac_type  = slot.get("ac_type", _classify_ac(ac))
    feature  = requirement.title[:60]
    nav_target = requirement.category[:40] if requirement.category else requirement.title[:40]

    if tt == "positive":
        h = _hints_positive(ac, ac_type, feature, nav_target)
    elif tt == "negative":
        h = _hints_negative(ac, ac_type, feature, nav_target)
    else:
        h = _hints_edge(ac, ac_type, feature, nav_target)

    if tt == "positive":
        gwt_hint = (
            f'given: "An eligible user who meets all requirements for {feature} is logged in"\n'
            f'when: "The user performs the specific action to exercise: {ac[:70]}"\n'
            f'then: "The system responds with the observable result described in: {ac[:70]}"'
        )
    elif tt == "negative":
        neg_when = {
            'ui_behaviour': f"The condition for {ac[:60]} is not met and the user attempts the action",
            'timing':       f"The timed event exceeds the limit described in: {ac[:60]}",
            'data_valid':   f"The user enters a value that violates the rule in: {ac[:60]}",
            'security':     f"The user attempts to bypass the security control in: {ac[:60]}",
        }.get(ac_type, f"An ineligible user attempts the action blocked by: {ac[:60]}")
        gwt_hint = (
            f'given: "A test account is configured for the unhappy path of: {feature}"\n'
            f'when: "{neg_when}"\n'
            f'then: "The system correctly rejects or handles the failure case with an accurate message"'
        )
    else:
        gwt_hint = (
            f'given: "Test data is set at exactly the boundary value for: {ac[:60]}"\n'
            f'when: "The boundary-condition action is executed"\n'
            f'then: "System accepts the boundary value and rejects values beyond it"'
        )

    cat_tag = requirement.category.lower().replace(" ", "-") if requirement.category else "general"
    req_tag = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())

    gherkin_section = ""
    if tc_format == "gherkin":
        gherkin_section = f"\nGIVEN / WHEN / THEN -- fill exactly as shown:\n{gwt_hint}\n"

    ac_type_label = {
        'eligibility':  'eligibility rule',
        'ui_behaviour': 'UI behaviour',
        'timing':       'timing/performance constraint',
        'data_valid':   'data validation rule',
        'security':     'security control',
        'general':      'general requirement',
    }.get(ac_type, 'requirement')

    return f"""Write test case {test_number} of {total} for this requirement.

REQUIREMENT {requirement.req_id}: {requirement.title}
{requirement.description}

ALL ACCEPTANCE CRITERIA:
{all_ac_text}

TARGET ACCEPTANCE CRITERION (type: {ac_type_label}):
  {ac}

{_TYPE_CONTEXT[tt]}
{context_block}
{few_shot_block}
{_COT_INSTRUCTION}

MANDATORY TITLE -- copy this exactly into the title field:
  {slot['title']}

Fill each field below with content specific to this requirement and AC.
Do not copy the field label text into your answer.
{gherkin_section}
description:      {h['desc']}
preconditions:    {h['pre']}
steps:
{h['steps']}
expected_outcome: {h['outcome']}
component:        Name the specific screen or service relevant to this requirement
                  (e.g. "Patient Registration Screen", "Order Confirmation Screen",
                  "OTP Verification Screen") -- not a generic app name
tags:             ["{cat_tag}", "{tt}", "{req_tag}"]"""


# -- Sanitiser helpers ---------------------------------------------------------

_INSTRUCTION_PHRASES = [
    "one sentence explaining",
    "what this test verifies and why it matters",
    "specific system state and test data needed",
    "account type, amounts, flags, time values",
    "be concrete",
    "no vague",
    "replace the example content",
    "fill each field",
    "copy this exactly",
    "setup -> act -> verify",
    "steps must progress logically",
    "the exact observable result",
    "chain-of-thought",
    "before writing each step",
    "mentally answer",
]

_TRIVIAL_OUTCOMES = {
    "true", "false", "pass", "fail", "passed", "failed",
    "valid rejection", "valid", "success", "n/a", "none",
    "expected outcome", "the test passes", "the test fails",
    "success confirmation screen is displayed",
    "system accepts the input and processes the action without error",
    "correct boundary behaviour confirmed",
    "system processes the boundary value without crashing or silent failure",
    "system correctly rejects or blocks the out-of-bounds value",
    "home screen loads successfully without errors",
    "system detects the ineligibility condition",
}

_GENERIC_STEP_FRAGMENTS = [
    "perform the action",
    "perform the valid action required",
    "perform the specific action",        # catches: "Perform the specific action to exercise:"
    "perform the specific action required",
    "trigger the feature",
    "verify the outcome",
    "check the result",
    "observe the result",
    "step description",
    "expected result",
    "execute the test step",
    "complete the action",
    "do the action",
]

# Generic screen-name suffixes — domain-agnostic patterns that map
# category/title fragments to a UI component type.
# Keys are generic: 'form', 'list', 'dashboard', 'settings' etc.
# These are NOT domain-specific — they work for banking, healthcare, retail, etc.
_COMPONENT_SUFFIX_MAP = {
    # Navigation / layout patterns
    "home":          "Home Screen",
    "dashboard":     "Dashboard",
    "landing":       "Landing Screen",
    "menu":          "Navigation Menu",
    # Interaction patterns
    "form":          "Entry Form",
    "entry":         "Entry Form",
    "input":         "Input Form",
    "search":        "Search Screen",
    "filter":        "Filter Screen",
    "upload":        "Upload Screen",
    # Auth / access
    "login":         "Login Screen",
    "auth":          "Authentication Screen",
    "verification":  "Verification Screen",
    "onboarding":    "Onboarding Screen",
    "registration":  "Registration Screen",
    "enrollment":    "Enrollment Screen",
    # Data views
    "history":       "History Screen",
    "list":          "List Screen",
    "detail":        "Detail Screen",
    "summary":       "Summary Screen",
    "report":        "Report Screen",
    "review":        "Review Screen",
    # Transactional
    "confirmation":  "Confirmation Screen",
    "payment":       "Payment Screen",
    "checkout":      "Checkout Screen",
    "submission":    "Submission Screen",
    # Support
    "notification":  "Notification Centre",
    "alert":         "Alert Screen",
    "settings":      "Settings Screen",
    "profile":       "Profile Screen",
    "support":       "Help & Support Screen",
    "dispute":       "Dispute Screen",
    # Processing
    "processing":    "Processing Screen",
    "capture":       "Capture Screen",
    "camera":        "Camera Screen",
    "scan":          "Scan Screen",
    # Compliance / risk
    "compliance":    "Compliance Screen",
    "regulatory":    "Compliance Screen",
    "risk":          "Risk Management Screen",
    "security":      "Security Settings Screen",
    "audit":         "Audit Log Screen",
}


def _resolve_component(raw, category, req_title="", ac_text="", vector_store=None):
    """
    Derive a specific screen or service name.

    Priority order:
    1. LLM returned something specific and non-generic — keep it.
    2. ChromaDB domain_vocab lookup (dynamic, domain-agnostic) — NEW.
    3. Static _COMPONENT_SUFFIX_MAP keyword match (generic fallback).
    4. Construct from category or req_title.
    """
    _GENERIC_NAMES = {
        "mobile banking app", "the application", "this application",
        "the app", "the system", "the platform", "the software",
        "generic app", "the product",
    }

    # 1. LLM returned something useful — keep it
    raw_clean = raw.strip()
    if (raw_clean
            and len(raw_clean) > 15
            and "specific screen" not in raw_clean.lower()
            and "not a generic" not in raw_clean.lower()
            and not any(g in raw_clean.lower() for g in _GENERIC_NAMES)):
        return raw_clean

    # 2. ChromaDB domain_vocab lookup — uses real screen names extracted from requirements
    if vector_store is not None:
        try:
            result = vector_store.lookup_component(category, req_title, ac_text)
            if result:
                return result
        except Exception:
            pass  # graceful degradation — fall through to static map

    # 3. Static suffix map keyword match
    for source in [category, req_title]:
        s = source.strip().lower()
        for key, val in _COMPONENT_SUFFIX_MAP.items():
            if key in s:
                prefix = " ".join(w.capitalize() for w in source.strip().split())
                if len(prefix) > len(key) + 3:
                    return f"{prefix} Screen"
                return val

    # 4. Construct from category or req_title
    if category.strip():
        return f"{' '.join(w.capitalize() for w in category.strip().split())} Screen"
    if req_title.strip():
        return f"{req_title[:40].strip()} Screen"

    return "Application Screen"


def _is_instruction_text(text):
    t = text.lower()
    return any(phrase in t for phrase in _INSTRUCTION_PHRASES)


def _has_loop(text, threshold=3):
    """Detect repeated sentences - hallucinated loops."""
    parts = re.split(r'[.\n]', text)
    parts = [p.strip().lower()[:60] for p in parts if len(p.strip()) > 15]
    if not parts:
        return False
    counts = {}
    for p in parts:
        counts[p] = counts.get(p, 0) + 1
        if counts[p] >= threshold:
            return True
    return False


def _has_python_leakage(text):
    return bool(re.search(r"'description'\s*:", text) or
                re.search(r'"description"\s*:', text) or
                re.search(r'\{.*?\'title\'\s*:', text, re.DOTALL))


def _is_generic_step(action):
    t = action.strip().lower()
    if len(t) < 20:
        return True
    if re.match(r'^[a-z]+(_[a-z]+)+$', t):
        return True
    return any(t.startswith(frag) for frag in _GENERIC_STEP_FRAGMENTS)


def _clean_numbered_list(text):
    text = re.sub(r"(\s*\(\d+\))+\s*$", "", text)
    text = re.sub(r"(\s*\d+\.\s*)+$", "", text)
    return text.strip()


def _make_gwt(ac, test_type, req_title):
    ac      = ac.strip()
    feature = req_title[:60] if req_title else "this feature"
    ac_type = _classify_ac(ac)

    if test_type == "positive":
        given = f"An eligible user who meets all requirements for {feature} is logged in"
        when  = f"The user performs the specific action to exercise: {ac[:100]}"
        then  = f"The system displays the observable result described in: {ac[:100]}"
    elif test_type == "negative":
        if ac_type == 'ui_behaviour':
            given = f"A test account where the condition for {ac[:60]} is NOT met"
            when  = "The user attempts to trigger the UI behaviour without satisfying its condition"
            then  = "The system handles the unhappy path correctly with an accurate fallback state"
        elif ac_type == 'timing':
            given = f"A test environment simulating a delay beyond the limit in: {ac[:60]}"
            when  = "The timed event exceeds the specified time limit"
            then  = "The system detects the timeout and displays the correct error or fallback"
        elif ac_type == 'data_valid':
            given = f"A test account with an invalid value prepared for: {ac[:60]}"
            when  = "The user submits the invalid value"
            then  = "The system rejects the input and displays an accurate validation error message"
        elif ac_type == 'security':
            given = f"A test account attempting to bypass the security control in: {ac[:60]}"
            when  = "The user attempts the bypass action"
            then  = "The security control blocks the attempt with the correct rejection message"
        else:
            given = f"A user who does not meet eligibility criteria for {feature}"
            when  = f"The user attempts the restricted action: {ac[:80]}"
            then  = "The system blocks the action and displays the correct rejection message"
    else:
        given = f"Test data configured at exactly the boundary value for: {ac[:80]}"
        when  = "The boundary-condition action is executed"
        then  = "System accepts the limit value and rejects the value one unit beyond it"

    return given, when, then


def _make_description(ac, test_type):
    labels = {
        "positive":  "Positive test -- verifies that",
        "negative":  "Negative test -- verifies correct rejection when",
        "edge_case": "Boundary test -- verifies enforcement at the exact limit of",
    }
    return f"{labels.get(test_type, 'Test --')} {ac.strip()}"


def _make_preconditions(ac, test_type, category, req_title=""):
    feature = req_title[:60] if req_title else category
    base    = "Application installed; tester has valid login credentials for a test account"
    ac_type = _classify_ac(ac)

    if test_type == "positive":
        return f"Test account meets all eligibility criteria for {feature}; {base}"
    elif test_type == "negative":
        if ac_type == 'ui_behaviour':
            return f"Test account configured so the triggering condition for {ac[:60]} is absent; {base}"
        elif ac_type == 'timing':
            return f"Test environment configured to simulate delay beyond the limit in: {ac[:60]}; {base}"
        elif ac_type == 'data_valid':
            return f"Test data prepared with an invalid boundary value for: {ac[:60]}; {base}"
        elif ac_type == 'security':
            return f"Test account configured for bypass attempt of security control in: {ac[:60]}; {base}"
        else:
            return (
                f"Test account configured to be ineligible for {feature} "
                f"(fails one or more eligibility criteria); {base}"
            )
    else:
        return f"Test data set at exactly the boundary value for: {ac[:60]}; {base}"


def _sanitise_tc(tc, slot, requirement, vector_store=None):
    ac        = slot["target_ac"]
    test_type = slot["test_type"]

    # 1. Description
    if (not tc.description
            or _is_instruction_text(tc.description)
            or _has_loop(tc.description)
            or len(tc.description) < 15):
        tc.description = _make_description(ac, test_type)
        console.print("    [dim]    post: replaced bad description[/dim]")

    # 2. Preconditions
    pre = _clean_numbered_list(tc.preconditions)
    if (not pre
            or _is_instruction_text(pre)
            or _has_loop(pre)
            or _has_python_leakage(pre)
            or len(pre) < 20):
        pre = _make_preconditions(ac, test_type, requirement.category, requirement.title)
        console.print("    [dim]    post: replaced bad preconditions[/dim]")
    tc.preconditions = pre

    # 3. Steps
    good_steps = [s for s in tc.steps if not _is_generic_step(s.action)]
    exp_results = [s.expected_result.strip().lower() for s in good_steps if s.expected_result.strip()]
    all_identical = len(exp_results) > 1 and len(set(exp_results)) == 1
    if len(good_steps) < 3 or all_identical:
        ac_type = slot.get("ac_type", _classify_ac(ac))
        tc.steps = _synthesise_steps(ac, test_type, requirement.title, ac_type)
        console.print("    [dim]    post: replaced generic/short steps[/dim]")
    else:
        tc.steps = good_steps

    # 4. Expected outcome
    outcome = tc.expected_outcome.strip()
    if (not outcome
            or outcome.lower() in _TRIVIAL_OUTCOMES
            or _is_instruction_text(outcome)
            or _has_loop(outcome)
            or _has_python_leakage(outcome)):
        tc.expected_outcome = ac
        console.print("    [dim]    post: replaced trivial expected_outcome[/dim]")

    # 5. Given / When / Then
    _bad_gwt_words = {"", "setup", "act", "verify", "given", "when", "then"}

    def _is_garbled(val):
        v = val.strip()
        if re.search(r'\bHig\s+h\b', v, re.I):       return True
        if re.search(r'nega\s+ti\s+v', v, re.I):     return True
        if re.search(r'Mediu\s+m\b', v, re.I):       return True
        if re.search(r'\b[a-z]{2,8}\s[a-z]{1,4}\b', v, re.I) and len(v) < 30:
            words = v.split()
            safe = {'the','a','an','is','are','was','to','of','and','or','in','on','at','for',
                    'not','has','have','been','be','by','with','from','test','data','user','app',
                    'when','then','given','action','screen','system','customer','account'}
            if len(words) <= 4 and not any(w.lower() in safe for w in words):
                return True
        return False

    def _gwt_is_bad(val, preconditions=""):
        v  = val.strip()
        vl = v.lower()
        if not v or vl in _bad_gwt_words:         return True
        if len(v) < 12:                            return True
        if _is_instruction_text(v):                return True
        if "[specific" in vl or "[success" in vl: return True
        if _is_garbled(v):                         return True
        if _has_loop(v, threshold=2):              return True
        if _has_python_leakage(v):                 return True
        if preconditions and len(preconditions) > 20:
            pre_norm = re.sub(r'\s+', ' ', preconditions.strip().lower())
            val_norm = re.sub(r'\s+', ' ', vl)
            if val_norm[:60] in pre_norm or pre_norm[:60] in val_norm:
                return True
        return False

    g_bad = _gwt_is_bad(tc.given, tc.preconditions)
    w_bad = _gwt_is_bad(tc.when,  tc.preconditions)
    t_bad = _gwt_is_bad(tc.then)

    if g_bad or w_bad or t_bad:
        g, w, t = _make_gwt(ac, test_type, requirement.title)
        if g_bad: tc.given = g
        if w_bad: tc.when  = w
        if t_bad: tc.then  = t
        console.print("    [dim]    post: filled missing/garbled Given/When/Then[/dim]")

    # 6. Component — uses ChromaDB vocab lookup when vector_store is available
    tc.component = _resolve_component(
        tc.component, requirement.category, requirement.title,
        ac_text=ac, vector_store=vector_store,
    )

    # 7. Tags - strip garbage
    clean_tags = []
    for tag in tc.tags:
        t = tag.strip().lower()
        if (not t
                or len(t) > 50
                or re.fullmatch(r'[\d\s_,:.\-]+', t)
                or t.startswith('path-')
                or t.startswith('precondition')
                or 'expected-outcome' in t
                or re.search(r'_{3,}', t)
                or t in ('true', 'false')):
            continue
        clean_tags.append(t)
    if not clean_tags:
        req_tag  = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())
        cat_tag  = requirement.category.lower().replace(" ", "-") if requirement.category else "general"
        clean_tags = [cat_tag, test_type, req_tag]
    tc.tags = clean_tags

    return tc


# -- Step synthesis ------------------------------------------------------------

def _synthesise_steps(ac, test_type, req_title="", ac_type=""):
    if not ac_type:
        ac_type = _classify_ac(ac)
    ac      = ac.strip()
    feature = req_title[:60] if req_title else "the relevant feature"

    if test_type == "positive":
        if ac_type == 'timing':
            return [
                TestStep("Log in and navigate to the relevant screen", "Screen loads correctly"),
                TestStep(f"Trigger the timed event described in: {ac[:70]}", "System begins processing; timer started"),
                TestStep("Measure elapsed time from trigger to completion", f"Event completes within the limit: {ac[:60]}"),
                TestStep("Record the measured time in the test evidence", "Elapsed time is within the required limit"),
                TestStep("Verify no timeout error is shown", "System shows the success state; no timeout message"),
            ]
        elif ac_type == 'data_valid':
            return [
                TestStep("Log in and navigate to the relevant input form", "Form is displayed with the relevant fields"),
                TestStep(f"Enter the valid boundary value for: {ac[:70]}", "System accepts the input without inline error"),
                TestStep("Submit or trigger validation", "System processes the valid value successfully"),
                TestStep(f"Clear the field and enter an invalid value for: {ac[:60]}", "System displays an inline validation error"),
                TestStep("Verify the error message text is accurate", "Error message correctly describes the validation rule"),
            ]
        else:
            return [
                TestStep("Log in with valid credentials", "Home screen loads without errors"),
                TestStep(f"Navigate to the section for {feature}", "Relevant screen is displayed"),
                TestStep(f"Perform the action that exercises: {ac[:80]}", "System accepts the input correctly"),
                TestStep("Verify the observable result matches the acceptance criterion", f"Result matches: {ac[:80]}"),
                TestStep("Navigate away and return to confirm persistence", "State is saved; no error banners"),
            ]

    elif test_type == "negative":
        if ac_type == 'ui_behaviour':
            return [
                TestStep("Log in with test account where the triggering condition is absent", "Home screen loads; condition is not active"),
                TestStep("Navigate to the relevant screen", "Screen loads"),
                TestStep(f"Attempt to trigger the UI behaviour described in: {ac[:70]}", "System does not show the behaviour incorrectly"),
                TestStep("Verify the fallback or error state is shown", "System shows the correct fallback message or state"),
                TestStep("Attempt to proceed past the fallback state", "System handles the unhappy path cleanly"),
            ]
        elif ac_type == 'timing':
            return [
                TestStep("Configure test environment to simulate delay exceeding the time limit", "Delay condition is active"),
                TestStep("Log in and navigate to the relevant screen", "Screen loads"),
                TestStep(f"Trigger the timed event described in: {ac[:70]}", "Processing begins; timer running"),
                TestStep("Allow the time limit to be exceeded without the expected event", "System detects the timeout"),
                TestStep("Observe the timeout error or fallback state", "System displays the correct timeout message"),
            ]
        elif ac_type == 'data_valid':
            return [
                TestStep("Log in and navigate to the relevant form", "Form is displayed"),
                TestStep(f"Enter an invalid value that violates: {ac[:70]}", "System detects the invalid input"),
                TestStep("Submit or attempt to proceed", "System rejects the invalid value"),
                TestStep("Read the validation error message shown", "Error message accurately describes the rule violation"),
                TestStep("Attempt to bypass validation via back button or direct navigation", "System maintains the block; no invalid data saved"),
            ]
        else:
            return [
                TestStep("Log in with an ineligible test account", "Home screen loads; ineligibility condition is active"),
                TestStep(f"Navigate to the section for {feature}", "Screen loads"),
                TestStep(f"Attempt the action blocked by: {ac[:80]}", "System detects the ineligibility condition"),
                TestStep("Read the rejection message displayed on screen", "Correct rejection message is shown"),
                TestStep("Attempt to bypass the block via back button or direct navigation", "System maintains the block; no data saved"),
            ]

    else:
        return [
            TestStep(f"Set test data at exactly the boundary value for: {ac[:70]}", "Boundary test data is confirmed in the environment"),
            TestStep("Log in and navigate to the relevant screen", "Screen loads; boundary test data is visible"),
            TestStep("Execute the action at the exact boundary value", "System accepts the boundary value without error"),
            TestStep("Record the outcome shown on screen", f"Outcome matches the requirement: {ac[:70]}"),
            TestStep("Repeat the action with a value one unit beyond the boundary", "System rejects the out-of-bounds value with an error message"),
        ]


def _extract_steps(raw_steps, ac, test_type, req_title="", ac_type=""):
    if not ac_type:
        ac_type = _classify_ac(ac)
    seen = set()
    real = []
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
        real.append(TestStep(action=action, expected_result=result))
    return real if len(real) >= 2 else _synthesise_steps(ac, test_type, req_title, ac_type)


# -- Duration cleanup ----------------------------------------------------------

def _clean_duration(val):
    s = str(val).strip().upper()
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if m:
        total = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        return str(total) if total > 0 else "5"
    digits = re.sub(r"[^\d]", "", s)
    return digits if digits and 0 < int(digits) < 500 else "5"


# -- Generator -----------------------------------------------------------------

class TestCaseGenerator:

    def __init__(self, llm_client, vector_store=None, domain: str = ""):
        self.llm          = llm_client
        self.vector_store = vector_store
        self._tc_counter  = 0
        # domain is set lazily in generate_for_all, or can be passed explicitly.
        # It drives the system prompt — never hardcoded inside this class.
        self._domain      = domain

    def generate_for_requirement(self, requirement, max_tests=None):
        max_tc = max_tests or config.max_test_cases_per_requirement

        # Build system prompt from whatever domain was inferred/supplied.
        # Falls back to generic wording if domain is empty.
        system_prompt = _build_system_prompt(self._domain)

        context = ""
        if self.vector_store:
            try:
                context = self.vector_store.get_context_for_requirement(requirement)
            except Exception:
                pass

        slots = _build_slot_plan(
            requirement=requirement,
            max_tc=max_tc,
            include_negative=config.include_negative_tests,
            include_edge=config.include_edge_cases,
        )

        results = []

        for i, slot in enumerate(slots):
            ac_type_label = slot.get("ac_type", "general")
            test_type     = slot["test_type"]
            ac_text       = slot["target_ac"]

            # ── Retrieve few-shot examples from ChromaDB ───────────────────
            # Each slot gets 1-2 approved TCs of the same ac_type + test_type.
            # These are injected into the prompt so the model has a concrete
            # pattern to follow — not just abstract rules.
            examples = []
            if self.vector_store:
                try:
                    examples = self.vector_store.retrieve_examples(
                        ac_text=ac_text,
                        ac_type=ac_type_label,
                        test_type=test_type,
                        n=2,
                    )
                except Exception:
                    pass
            # ──────────────────────────────────────────────────────────────

            console.print(
                f"    [dim]({i+1}/{max_tc}) {test_type:10s} "
                f"[{ac_type_label}] | examples={len(examples)} | "
                f"AC: {ac_text[:45]}...[/dim]"
            )

            prompt = _build_prompt(
                requirement=requirement,
                slot=slot,
                test_number=i + 1,
                total=max_tc,
                context=context,
                tc_format=config.test_case_format,
                examples=examples,
            )

            tc = None
            for attempt in range(1, 3):
                try:
                    raw = self.llm.generate_test_case(
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    tc = self._parse(raw, requirement, slot)
                except Exception as e:
                    console.print(f"    [yellow]  attempt {attempt} error: {e}[/yellow]")
                if tc:
                    break

            if not tc:
                tc = self._synthesise_tc(requirement, slot)
                console.print(
                    f"    [yellow]  ~ {test_type:10s} -> {tc.title[:65]} (synthesised)[/yellow]"
                )

            # Pass vector_store for dynamic component lookup
            tc = _sanitise_tc(tc, slot, requirement, vector_store=self.vector_store)

            results.append(tc)
            console.print(
                f"    [green]  ✓ {test_type:10s} [{ac_type_label}] -> {tc.title[:60]}[/green]"
            )

        return results

    def generate_for_all(self, requirements):
        # Infer domain from the full requirement set once, before any LLM calls.
        if not self._domain:
            self._domain = _infer_domain(requirements)
        if self._domain:
            console.print(f"[cyan]Domain detected: [bold]{self._domain}[/bold][/cyan]")

        # Extract screen/field vocab from requirements and store in ChromaDB.
        # This populates the domain_vocab collection used by _resolve_component()
        # for dynamic lookup instead of the hardcoded _COMPONENT_SUFFIX_MAP.
        if self.vector_store:
            try:
                n_vocab = self.vector_store.extract_and_store_vocab(requirements)
                stats = self.vector_store.stats
                console.print(
                    f"[cyan]ChromaDB:[/cyan] "
                    f"vocab={stats['domain_vocab']} | "
                    f"examples={stats['tc_examples']} | "
                    f"reqs={stats['requirements']}"
                )
            except Exception as e:
                console.print(f"[yellow]Vocab extraction skipped: {e}[/yellow]")

        all_tc = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Generating...", total=len(requirements))
            for req in requirements:
                progress.update(task, description=f"[cyan]{req.req_id} -- {req.title[:45]}...")
                try:
                    tcs = self.generate_for_requirement(req)
                    all_tc.extend(tcs)
                    console.print(f"  [green]✅ {req.req_id}[/green]: {len(tcs)} test case(s)")
                except Exception as e:
                    console.print(f"  [red]ERR {req.req_id}: {e}[/red]")
                progress.advance(task)

        console.print(
            f"\n[bold green]{len(all_tc)} test cases "
            f"from {len(requirements)} requirements[/bold green]"
        )
        return all_tc

    def _parse(self, raw, requirement, slot):
        if not raw or "raw_response" in raw:
            return None

        if "test_cases" in raw and isinstance(raw["test_cases"], list) and raw["test_cases"]:
            item = raw["test_cases"][0]
        elif "title" in raw:
            item = raw
        else:
            return None

        if not isinstance(item, dict):
            return None

        self._tc_counter += 1
        ac_type = slot.get("ac_type", _classify_ac(slot["target_ac"]))

        steps = _extract_steps(
            raw_steps=item.get("steps", []),
            ac=slot["target_ac"],
            test_type=slot["test_type"],
            req_title=requirement.title,
            ac_type=ac_type,
        )

        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,;\s]+", tags) if t.strip()]
        tags = [t for t in tags if len(t) > 1 and not _is_instruction_text(t)]
        if not tags:
            req_tag = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())
            tags = [
                requirement.category.lower().replace(" ", "-"),
                slot["test_type"],
                req_tag,
            ]

        return TestCase(
            tc_id=f"TC-{self._tc_counter:04d}",
            req_id=requirement.req_id,
            title=slot["title"],
            description=item.get("description", "").strip(),
            preconditions=item.get("preconditions", "").strip(),
            test_type=slot["test_type"],
            priority=item.get("priority", requirement.priority),
            steps=steps,
            expected_outcome=item.get("expected_outcome", "").strip(),
            tags=tags,
            category=requirement.category,
            component=item.get("component", "").strip(),
            given=item.get("given", "").strip(),
            when=item.get("when", "").strip(),
            then=item.get("then", "").strip(),
            estimated_duration=_clean_duration(item.get("estimated_duration", "5")),
        )

    def _synthesise_tc(self, requirement, slot):
        self._tc_counter += 1
        ac      = slot["target_ac"]
        tt      = slot["test_type"]
        ac_type = slot.get("ac_type", _classify_ac(ac))
        g, w, t = _make_gwt(ac, tt, requirement.title)
        req_tag = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())
        return TestCase(
            tc_id=f"TC-{self._tc_counter:04d}",
            req_id=requirement.req_id,
            title=slot["title"],
            description=_make_description(ac, tt),
            preconditions=_make_preconditions(ac, tt, requirement.category, requirement.title),
            test_type=tt,
            priority=requirement.priority,
            steps=_synthesise_steps(ac, tt, requirement.title, ac_type),
            expected_outcome=ac,
            tags=[requirement.category.lower().replace(" ", "-"), tt, req_tag, "synthesised"],
            category=requirement.category,
            component=_resolve_component("", requirement.category, requirement.title),
            given=g,
            when=w,
            then=t,
        )

    def _fallback_test_case(self, requirement):
        acs  = requirement.acceptance_criteria or [requirement.description[:120]]
        slot = {
            "test_type": "positive",
            "target_ac": acs[0],
            "title":     _ac_to_title(acs[0], "positive"),
            "ac_type":   _classify_ac(acs[0]),
        }
        return [self._synthesise_tc(requirement, slot)]