"""
Constants
=========
Shared constants used across the requirements agent modules.
Extracted from the legacy test_generator.py — all domain-agnostic.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

# -- Title generation ----------------------------------------------------------

TYPE_VERB: Dict[str, str] = {
    "positive":  "Verify",
    "negative":  "Validate rejection when",
    "edge_case": "Confirm boundary for",
}

STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "are", "should", "must", "will", "that",
    "which", "when", "where", "and", "or", "of", "to", "in", "on",
    "for", "with", "be", "has", "have", "by", "from", "as",
}


# -- Chain-of-thought instruction ----------------------------------------------

COT_INSTRUCTION: str = """\
CHAIN-OF-THOUGHT REQUIREMENT - before writing each step, mentally answer:
  a) What is the exact button, field, menu item, or UI element the tester interacts with?
  b) What specific value does the tester enter, select, or measure?
  c) What exact text, icon, badge, or screen state confirms the step succeeded?
Use those concrete answers directly in your step text. Do not write generic phrases
like "perform the action", "trigger the feature", or "verify the outcome"."""


# -- Type context prompts -------------------------------------------------------

TYPE_CONTEXT: Dict[str, str] = {
    "positive": (
        "This is a POSITIVE test case — verify the happy path works as specified. "
        "All preconditions are met; the user is eligible and the system is in a valid state."
    ),
    "negative": (
        "This is a NEGATIVE test case — verify the system correctly rejects or handles "
        "an invalid condition. The precondition that normally makes the feature work is "
        "deliberately broken or absent."
    ),
    "edge_case": (
        "This is a BOUNDARY / EDGE CASE test — verify the system enforces the exact limit. "
        "Test at the boundary value itself, then one unit beyond it."
    ),
}


# -- Sanitiser constants --------------------------------------------------------

INSTRUCTION_PHRASES: List[str] = [
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

TRIVIAL_OUTCOMES: Set[str] = {
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

GENERIC_STEP_FRAGMENTS: List[str] = [
    "perform the action",
    "perform the valid action required",
    "perform the specific action",
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

# -- Component suffix map -------------------------------------------------------

DEFAULT_COMPONENT_SUFFIX_MAP: Dict[str, str] = {
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

# Configurable generic app names for component resolution
DEFAULT_GENERIC_APP_NAMES: Set[str] = {
    "the application", "this application",
    "the app", "the system", "the platform", "the software",
    "generic app", "the product",
}


# -- Utility helpers used by multiple modules -----------------------------------

def ac_to_title(ac: str, test_type: str) -> str:
    """Generate a test case title from an acceptance criterion.

    Args:
        ac: The acceptance criterion text.
        test_type: One of 'positive', 'negative', 'edge_case'.

    Returns:
        A formatted title string like "Verify -- condensed AC text".
    """
    verb = TYPE_VERB.get(test_type, "Verify")
    text = ac.strip().rstrip(".")
    words = text.split()
    condensed = " ".join(w for w in words if w.lower() not in STOPWORDS)
    condensed = re.sub(r"\s+", " ", condensed).strip()
    if len(condensed) < 15:
        condensed = text
    if len(condensed) > 70:
        condensed = condensed[:70].rsplit(" ", 1)[0]
    return f"{verb} -- {condensed}"
