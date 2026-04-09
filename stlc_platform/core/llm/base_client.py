"""
BaseLLMClient ABC
=================
All LLM providers implement this interface. This decouples the test generator
from any specific LLM provider (Ollama, OpenAI, Anthropic, etc.).

Why an ABC instead of a Protocol:
  - We want to enforce implementation at class definition time (fail-fast)
  - Providers share retry logic and JSON repair via base class methods
  - Protocol would allow duck-typing, but ABCs give clearer error messages

Phase C enhancements:
  - Token tracking: last_token_usage() reports input/output tokens per call
  - Response cache: optional LRU cache avoids redundant LLM calls
  - Failure classification: integrated into generate_test_case retry loop
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token counts from a single LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


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
                "BDD When clause: the specific action the user performs. One sentence only."
            ),
        },
        "then": {
            "type": "string",
            "minLength": 15,
            "description": ("BDD Then clause: the specific observable outcome. One sentence only."),
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
        "title",
        "description",
        "preconditions",
        "test_type",
        "priority",
        "given",
        "when",
        "then",
        "steps",
        "expected_outcome",
        "tags",
        "component",
    ],
}


# ── JSON repair utility ──────────────────────────────────────────────────────

_CLOSE_TO_OPEN = {"}": "{", "]": "["}


def _scan_json_structure(s: str):
    """Scan a JSON string tracking bracket nesting and string state.

    Returns a tuple of (in_string, stack) where *in_string* indicates
    whether the scan ended inside a quoted string and *stack* contains
    the still-open bracket characters (``{`` or ``[``).
    """
    in_string = False
    escape_next = False
    stack: list[str] = []

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if in_string:
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in ("{", "["):
            stack.append(ch)
        elif ch in _CLOSE_TO_OPEN:
            if stack and stack[-1] == _CLOSE_TO_OPEN[ch]:
                stack.pop()

    return in_string, stack


def repair_truncated_json(s: str) -> str:
    """Best-effort repair of JSON truncated mid-stream by token limit."""
    s = s.strip()
    if not s:
        return s

    in_string, stack = _scan_json_structure(s)

    if in_string:
        s += '"'
    s = re.sub(r",\s*$", "", s.rstrip())
    for opener in reversed(stack):
        s += "}" if opener == "{" else "]"
    return s


def is_hollow(parsed: dict) -> bool:
    """Return True if the parsed response has schema-valid but empty/trivial values."""
    title = parsed.get("title", "").strip()
    steps = parsed.get("steps", [])
    desc = parsed.get("description", "").strip()

    if not title or len(title) < 10:
        return True

    real_steps = [s for s in steps if isinstance(s, dict) and len(s.get("action", "").strip()) > 15]
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
      - Token tracking via last_token_usage() / accumulated_tokens
      - Optional response cache via set_cache()
    """

    def __init__(self) -> None:
        self._last_token_usage: TokenUsage = TokenUsage()
        self._accumulated_tokens: TokenUsage = TokenUsage()
        self._cache: Optional[Any] = None  # LLMResponseCache
        self._cache_lock = __import__("threading").Lock()

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

    # ── Token tracking ──────────────────────────────────────────────────────

    def last_token_usage(self) -> TokenUsage:
        """Token counts from the most recent generate() call."""
        return self._last_token_usage

    @property
    def accumulated_tokens(self) -> TokenUsage:
        """Accumulated token counts across all generate() calls."""
        return self._accumulated_tokens

    def reset_token_counts(self) -> None:
        """Reset accumulated token counts."""
        self._accumulated_tokens = TokenUsage()

    def _record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from a generate() call. Called by subclasses."""
        self._last_token_usage = TokenUsage(input_tokens, output_tokens)
        self._accumulated_tokens.input_tokens += input_tokens
        self._accumulated_tokens.output_tokens += output_tokens

    # ── Cache ───────────────────────────────────────────────────────────────

    def set_cache(self, cache: Any) -> None:
        """Attach an LLMResponseCache instance."""
        self._cache = cache

    def _check_cache(
        self,
        system_prompt: Optional[str],
        prompt: str,
        base_temp: float,
        use_cache: bool,
    ) -> tuple:
        """Check the response cache. Returns (cache_key, cached_result).

        *cached_result* is a parsed dict on cache hit, or ``None`` on miss.
        *cache_key* is ``None`` when caching is disabled.
        """
        if not use_cache or self._cache is None:
            return None, None
        from stlc_platform.core.llm.cache import LLMResponseCache

        cache_key = LLMResponseCache.cache_key(system_prompt or "", prompt, base_temp)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            try:
                parsed = json.loads(cached)
                if not is_hollow(parsed):
                    console.print("    [dim]  cache hit[/dim]")
                    return cache_key, parsed
            except json.JSONDecodeError:
                pass  # stale cache entry — regenerate
        return cache_key, None

    @staticmethod
    def _parse_and_repair(raw: str, attempt: int):
        """Try to parse raw LLM output as JSON, repairing if needed.

        Returns the parsed dict on success, or ``None`` on failure.
        """
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        try:
            return json.loads(cleaned), cleaned
        except json.JSONDecodeError:
            pass
        repaired = repair_truncated_json(cleaned)
        try:
            parsed = json.loads(repaired)
            console.print(f"    [dim]  repaired truncated JSON on attempt {attempt}[/dim]")
            return parsed, cleaned
        except json.JSONDecodeError as e:
            console.print(
                f"    [yellow]  attempt {attempt} parse failed: {e} | raw: {raw[:120]}[/yellow]"
            )
            return None, cleaned

    def _cache_and_return(self, parsed: dict, cleaned: str, cache_key, attempt: int) -> dict:
        """Cache a successful response and log summary."""
        if cache_key and self._cache is not None:
            with self._cache_lock:
                self._cache.put(cache_key, cleaned)
        title = parsed.get("title", "?")[:70]
        steps_count = len(parsed.get("steps", []))
        console.print(
            f"    [dim]  parsed OK (attempt {attempt}) | steps={steps_count} | title: {title}[/dim]"
        )
        return parsed

    def generate_test_case(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        use_cache: bool = True,
        slot: Optional[Dict[str, Any]] = None,
        requirement: Optional[Any] = None,
    ) -> dict:
        """
        Generate a single test case with classified-retry, JSON repair, and caching.

        Retry strategy (Phase C — classified-retry):
          Attempt 1: base temperature with original prompt
          Attempt 2: classify failure → adapt prompt → retry with adapted prompt
          Hard failure: returns {raw_response: ...} to trigger synthesise_tc()

        When slot and requirement are provided, failures are classified using
        FailureClassifier and the prompt is adapted with failure-specific
        instructions before retry. Without them, falls back to blind retry
        with temperature increase (backward compatible).

        Cache: when enabled, checks cache before calling LLM. Stores
        successful responses for future lookups.
        """
        from stlc_platform.core.llm.failure_classifier import FailureClassifier

        base_temp = getattr(self, "temperature", 0.6)
        raw = ""
        current_prompt = prompt
        classifier = FailureClassifier() if slot is not None else None

        cache_key, cached_result = self._check_cache(
            system_prompt,
            prompt,
            base_temp,
            use_cache,
        )
        if cached_result is not None:
            return cached_result

        def _try_classify_and_adapt(raw_text: str, parsed_tc: Optional[dict]) -> None:
            nonlocal current_prompt
            if classifier is None:
                return
            classification = classifier.classify(raw_text, parsed_tc, slot, requirement)
            if classification:
                current_prompt = classifier.adapt_prompt(prompt, classification, slot)
                console.print(
                    f"    [dim]  failure classified: {classification.failure_type.value} "
                    f"→ adapting prompt[/dim]"
                )

        for attempt in range(1, 3):
            temp = base_temp if attempt == 1 else min(base_temp + 0.05, 1.0)
            try:
                raw = self.generate(
                    prompt=current_prompt,
                    system_prompt=system_prompt,
                    temperature=temp,
                    json_schema=TESTCASE_JSON_SCHEMA,
                )
            except Exception as e:
                console.print(f"    [yellow]  attempt {attempt} LLM error: {e}[/yellow]")
                continue

            success = self._process_attempt(
                raw,
                attempt,
                cache_key,
                _try_classify_and_adapt,
            )
            if success is not None:
                return success

        console.print("    [yellow]  both attempts failed — falling back to synthesise_tc[/yellow]")
        return {"raw_response": raw}

    def _process_attempt(self, raw, attempt, cache_key, classify_fn):
        """Process a single generate attempt. Returns parsed dict on success, None to retry."""
        result = self._parse_and_repair(raw, attempt)
        parsed, cleaned = result
        if parsed is None:
            if attempt == 1:
                classify_fn(raw, None)
            return None

        if is_hollow(parsed):
            console.print(
                f"    [yellow]  attempt {attempt} hollow response "
                f"(schema-valid but empty fields)[/yellow]"
            )
            if attempt == 1:
                classify_fn(raw, parsed)
            return None

        return self._cache_and_return(parsed, cleaned, cache_key, attempt)

    # Alias for backward compatibility
    def generate_structured(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        return self.generate_test_case(prompt, system_prompt)
