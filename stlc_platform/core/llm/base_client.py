"""
BaseLLMClient ABC
=================
All LLM providers implement this interface. This decouples the test generator
from any specific LLM provider (Ollama, OpenAI, Anthropic, etc.).

Why an ABC instead of a Protocol:
  - We want to enforce implementation at class definition time (fail-fast)
  - Providers share retry logic and JSON repair via base class methods
  - Protocol would allow duck-typing, but ABCs give clearer error messages
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()


# ── JSON Schema for test case output ─────────────────────────────────────────

TESTCASE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "minLength": 10,
            "description": (
                "Copy the mandatory title exactly as given in the prompt. "
                "Do not rephrase or shorten it."
            ),
        },
        "description": {
            "type": "string",
            "minLength": 20,
            "description": (
                "One or two sentences explaining what this test case verifies and why. "
                "Derived from the target acceptance criterion."
            ),
        },
        "preconditions": {
            "type": "string",
            "minLength": 20,
            "description": (
                "Specific system state required before executing this test. "
                "Include account type or configuration, data setup, and login state."
            ),
        },
        "test_type": {
            "type": "string",
            "enum": ["positive", "negative", "edge_case"],
            "description": "The test scenario type as indicated in the prompt.",
        },
        "priority": {
            "type": "string",
            "enum": ["High", "Medium", "Low"],
            "description": "Test priority: High for critical paths, Medium for standard, Low for edge cases.",
        },
        "given": {
            "type": "string",
            "minLength": 15,
            "description": (
                "BDD Given clause: the specific precondition state for this scenario. "
                "One sentence only."
            ),
        },
        "when": {
            "type": "string",
            "minLength": 15,
            "description": (
                "BDD When clause: the specific action the user performs. "
                "One sentence only."
            ),
        },
        "then": {
            "type": "string",
            "minLength": 15,
            "description": (
                "BDD Then clause: the specific observable outcome. "
                "One sentence only."
            ),
        },
        "steps": {
            "type": "array",
            "minItems": 3,
            "description": "Ordered list of test steps. Minimum 3 steps.",
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "minLength": 15,
                        "description": (
                            "What the tester does. Name the exact button, field, value, "
                            "or menu item."
                        ),
                    },
                    "expected_result": {
                        "type": "string",
                        "minLength": 10,
                        "description": (
                            "What the tester observes after the action. "
                            "Name the exact message, UI element, or measured value."
                        ),
                    },
                },
                "required": ["action", "expected_result"],
            },
        },
        "expected_outcome": {
            "type": "string",
            "minLength": 20,
            "description": "Overall pass criterion for the test case.",
        },
        "tags": {
            "type": "array",
            "minItems": 1,
            "description": "Short lowercase hyphenated labels.",
            "items": {"type": "string", "minLength": 2},
        },
        "component": {
            "type": "string",
            "minLength": 5,
            "description": (
                "The specific screen, service, or module being tested. "
                "Use a real name, not a generic label."
            ),
        },
        "estimated_duration": {
            "type": "string",
            "description": "Estimated execution time in minutes as a number string.",
        },
    },
    "required": [
        "title", "description", "preconditions", "test_type",
        "priority", "given", "when", "then",
        "steps", "expected_outcome", "tags", "component",
    ],
}


# ── JSON repair utility ──────────────────────────────────────────────────────

def repair_truncated_json(s: str) -> str:
    """Best-effort repair of JSON truncated mid-stream by token limit."""
    s = s.strip()
    if not s:
        return s

    in_string = False
    escape_next = False
    stack: list[str] = []

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
            elif ch == ']':
                if stack and stack[-1] == '[':
                    stack.pop()

    if in_string:
        s += '"'
    s = re.sub(r',\s*$', '', s.rstrip())
    for opener in reversed(stack):
        s += '}' if opener == '{' else ']'
    return s


def is_hollow(parsed: dict) -> bool:
    """Return True if the parsed response has schema-valid but empty/trivial values."""
    title = parsed.get("title", "").strip()
    steps = parsed.get("steps", [])
    desc = parsed.get("description", "").strip()

    if not title or len(title) < 10:
        return True

    real_steps = [
        s for s in steps
        if isinstance(s, dict) and len(s.get("action", "").strip()) > 15
    ]
    if len(real_steps) < 2:
        return True

    if not desc or len(desc) < 15:
        return True

    return False


# ── Base class ───────────────────────────────────────────────────────────────

class BaseLLMClient(ABC):
    """
    Abstract base class for LLM providers.

    Subclasses must implement:
      - generate(): raw text generation
      - check_connection(): verify provider is reachable
      - list_models(): list available models

    The base class provides:
      - generate_test_case(): structured output with retry + JSON repair
      - JSON schema, repair, and hollow check utilities
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Generate text from the LLM. Returns raw string."""
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        """Verify the LLM provider is reachable."""
        ...

    @abstractmethod
    def list_models(self) -> list:
        """List available models from the provider."""
        ...

    def generate_test_case(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Generate a single test case with retry and JSON repair.

        Retry strategy:
          Attempt 1: base temperature
          Attempt 2: +0.05 temperature if parse error or hollow response
          Hard failure: returns {raw_response: ...} to trigger synthesise_tc()
        """
        base_temp = getattr(self, "temperature", 0.6)
        raw = ""

        for attempt in range(1, 3):
            temp = base_temp if attempt == 1 else min(base_temp + 0.05, 1.0)

            try:
                raw = self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temp,
                    json_schema=TESTCASE_JSON_SCHEMA,
                )
            except Exception as e:
                console.print(f"    [yellow]  attempt {attempt} LLM error: {e}[/yellow]")
                continue

            # Strip <think> blocks (Qwen3 reasoning traces)
            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            # Parse attempt 1: direct
            parsed: dict | None = None
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                pass

            # Parse attempt 2: repair then parse
            if parsed is None:
                repaired = repair_truncated_json(cleaned)
                try:
                    parsed = json.loads(repaired)
                    console.print(f"    [dim]  repaired truncated JSON on attempt {attempt}[/dim]")
                except json.JSONDecodeError as e:
                    console.print(
                        f"    [yellow]  attempt {attempt} parse failed: {e} "
                        f"| raw: {raw[:120]}[/yellow]"
                    )
                    continue

            # Content sanity check
            if is_hollow(parsed):
                console.print(
                    f"    [yellow]  attempt {attempt} hollow response "
                    f"(schema-valid but empty fields)[/yellow]"
                )
                continue

            # Success
            title = parsed.get("title", "?")[:70]
            steps_count = len(parsed.get("steps", []))
            console.print(
                f"    [dim]  parsed OK (attempt {attempt}) | "
                f"steps={steps_count} | title: {title}[/dim]"
            )
            return parsed

        # Both attempts failed
        console.print(
            "    [yellow]  both attempts failed — falling back to synthesise_tc[/yellow]"
        )
        return {"raw_response": raw}

    # Alias for backward compatibility
    def generate_structured(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        return self.generate_test_case(prompt, system_prompt)
