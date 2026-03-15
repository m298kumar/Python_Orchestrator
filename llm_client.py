"""
Ollama LLM Client  v2
=====================
Changes from v1:

ENGINE SETTINGS
  - repeat_penalty=1.15   Reduces hallucinated token loops (50x repeated sentences).
                          1.0 = default (no penalty). 1.15 is conservative — high enough
                          to break loops, low enough not to hurt coherence on 7B models.
  - num_predict=2400      Was 1800 — marginal for a 5-step test case.
                          5 steps x (action + expected_result) ~ 700 tokens alone.
                          Add description, preconditions, GWT, outcome, tags = ~500 more.
                          2400 eliminates truncated-JSON repair triggering on normal output.
  - top_k=40, top_p=0.9   Default Ollama top_k is 40; top_p is 0.9 — making these
                          explicit so they don't silently change between Ollama versions.
  - stop sequences        Stops generation at obvious end-of-object patterns so the model
                          cannot continue generating after closing the JSON.

JSON SCHEMA — field descriptions and constraints
  - description fields    Added on every schema property. Ollama passes these to the model
                          as context alongside the format enforcement. The model uses them
                          as inline guidance, reducing empty-string returns.
  - minLength             Added on all prose string fields. Prevents '' passing schema
                          validation. Catches empty description / preconditions / outcome
                          before the response leaves the client.
  - minItems:3 on steps   Prevents the model returning an empty or one-step steps array.

RETRY LOGIC — two distinct failure modes handled separately
  - Parse failure         JSON could not be decoded even after repair.
                          Action: one retry at slightly higher temperature (0.65).
  - Empty content         Parsed successfully but key fields are blank.
                          Action: one retry — model understood the schema but wrote nothing.
  - Hard failure          Both attempts failed.
                          Action: return {raw_response: ...} — triggers synthesise_tc().

PRE-RETURN CONTENT CHECK
  - After successful parse, checks that at least title + steps are non-empty.
  - If hollow, returns raw_response so test_generator falls back to synthesise_tc
    rather than the sanitiser having to patch every single field.
"""
import json
import re
import os
import requests
from typing import Optional, Dict, Any
from rich.console import Console

from config import config

console = Console()


# -- JSON schema: structure + field descriptions + minimum constraints ---------
#
# This schema is passed to Ollama as format= — the model never sees it in the
# prompt. Ollama uses it for two things:
#   1. Structural enforcement: guarantees valid JSON with the right keys/types.
#   2. Field guidance: the description strings are shown to the model alongside
#      the field name and type, acting as lightweight in-schema hints.
#
# minLength and minItems are honoured by Ollama's grammar-based enforcement,
# meaning the model cannot produce an empty string for required prose fields.

TESTCASE_JSON_SCHEMA = {
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
                "Derived from the target acceptance criterion. "
                "Do not copy any instruction text from the prompt."
            ),
        },
        "preconditions": {
            "type": "string",
            "minLength": 20,
            "description": (
                "Specific system state required before executing this test. "
                "Include account type or configuration, data setup, and login state. "
                "One or two sentences — no numbered lists."
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
                "Name the user type and their relevant account or data state. "
                "One sentence only."
            ),
        },
        "when": {
            "type": "string",
            "minLength": 15,
            "description": (
                "BDD When clause: the specific action the user performs. "
                "Name the exact button, field, or UI element interacted with. "
                "One sentence only."
            ),
        },
        "then": {
            "type": "string",
            "minLength": 15,
            "description": (
                "BDD Then clause: the specific observable outcome the system produces. "
                "Name the exact message, UI state, or system change that proves success. "
                "One sentence only."
            ),
        },
        "steps": {
            "type": "array",
            "minItems": 3,
            "description": (
                "Ordered list of test steps. Each step must name a specific UI element "
                "and a specific observable result. Minimum 3 steps, typically 5."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "minLength": 15,
                        "description": (
                            "What the tester does. Name the exact button, field, value, "
                            "or menu item. Never write 'perform the action' or 'trigger the feature'."
                        ),
                    },
                    "expected_result": {
                        "type": "string",
                        "minLength": 10,
                        "description": (
                            "What the tester observes after the action. "
                            "Name the exact message text, UI element, or measured value."
                        ),
                    },
                },
                "required": ["action", "expected_result"],
            },
        },
        "expected_outcome": {
            "type": "string",
            "minLength": 20,
            "description": (
                "Overall pass criterion for the test case. "
                "Describe the specific observable system state that proves the "
                "acceptance criterion is satisfied. Not a repeat of the last step."
            ),
        },
        "tags": {
            "type": "array",
            "minItems": 1,
            "description": "Short lowercase hyphenated labels. Include category, test type, and requirement ID.",
            "items": {
                "type": "string",
                "minLength": 2,
            },
        },
        "component": {
            "type": "string",
            "minLength": 5,
            "description": (
                "The specific screen, service, or module being tested. "
                "Use a real screen name like 'OTP Verification Screen' or "
                "'Order Confirmation Screen' — not a generic label like 'the application'."
            ),
        },
        "estimated_duration": {
            "type": "string",
            "description": "Estimated execution time in minutes as a plain number string, e.g. '5'.",
        },
    },
    "required": [
        "title", "description", "preconditions", "test_type",
        "priority", "given", "when", "then",
        "steps", "expected_outcome", "tags", "component",
    ],
}


# -- JSON repair ---------------------------------------------------------------

def _repair_truncated_json(s: str) -> str:
    """
    Best-effort repair of JSON truncated mid-stream by token limit.
    Closes any open strings, arrays, and objects so json.loads can parse it.
    """
    s = s.strip()
    if not s:
        return s

    in_string   = False
    escape_next = False
    stack       = []  # '{' or '['

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


# -- Content sanity check ------------------------------------------------------

def _is_hollow(parsed: dict) -> bool:
    """
    Return True if the parsed response has the right keys but empty/trivial values.
    This catches the case where Ollama returns a schema-valid but contentless response.
    """
    title = parsed.get("title", "").strip()
    steps = parsed.get("steps", [])
    desc  = parsed.get("description", "").strip()

    # Must have a non-trivial title
    if not title or len(title) < 10:
        return True

    # Must have at least 2 steps with non-trivial actions
    real_steps = [
        s for s in steps
        if isinstance(s, dict) and len(s.get("action", "").strip()) > 15
    ]
    if len(real_steps) < 2:
        return True

    # Must have a non-trivial description
    if not desc or len(desc) < 15:
        return True

    return False


# -- Ollama client -------------------------------------------------------------

class OllamaClient:
    """Client for interacting with local Ollama LLM"""

    def __init__(self):
        self.base_url    = config.ollama.base_url
        self.model       = config.ollama.model
        self.temperature = config.ollama.temperature
        self.num_ctx     = config.ollama.num_ctx
        self.timeout     = config.ollama.timeout
        self.num_predict = config.ollama.num_predict
        self.debug       = os.getenv("DEBUG_LLM", "").lower() in ("1", "true", "yes")

    def check_connection(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def list_models(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        """
        Generate text using Ollama.
        json_schema is passed as format= (not in the prompt text).
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t = temperature if temperature is not None else self.temperature

        payload: Dict[str, Any] = {
            "model":    self.model,
            "messages": messages,
            "stream":   False,
            "options": {
                # --- Quality parameters ---
                "temperature":    t,
                "num_ctx":        self.num_ctx,
                "num_predict":    self.num_predict,  # from OLLAMA_NUM_PREDICT in .env
                "repeat_penalty": 1.15,       # was 1.0 (default); 1.15 kills hallucinated loops
                "top_k":          40,         # explicit — prevents silent Ollama version drift
                "top_p":          0.9,        # explicit — same reason
                # --- Stop sequences ---
                # After the model closes the top-level JSON object it should stop.
                # These patterns cover both clean and slightly garbled endings.
                "stop": ["}\n\n", "}\n```", "} ```"],
            },
        }

        if json_schema is not None:
            payload["format"] = json_schema

        if self.debug:
            console.print(
                f"\n[dim]-- SENDING TO OLLAMA "
                f"(temp={t:.2f} | repeat_penalty=1.15 | num_predict={self.num_predict} | "
                f"format={'schema' if json_schema else 'text'}) --[/dim]"
            )
            console.print(f"[dim]{prompt[:500]}...[/dim]\n")

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()

            if self.debug:
                console.print(f"[dim]-- RAW RESPONSE ({len(content)} chars) --[/dim]")
                console.print(f"[dim]{content[:600]}[/dim]")
                console.print(f"[dim]-- END --[/dim]\n")

            return content

        except requests.Timeout:
            raise TimeoutError(
                f"Ollama timed out after {self.timeout}s. "
                "Increase OLLAMA_TIMEOUT in .env or use a smaller model."
            )
        except requests.ConnectionError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Run: ollama serve"
            )
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e.response.text}")

    def generate_test_case(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Generate a single test case using Ollama structured output.

        Retry strategy — two distinct failure modes:
          Parse failure:    JSON could not be decoded even after repair.
                            Retry once at temperature+0.05 (slightly more varied output).
          Hollow response:  Parsed but key fields are empty/trivial.
                            Retry once at same temperature (model understood schema, just
                            produced no content — prompt is fine, worth one more try).
          Hard failure:     Both attempts failed.
                            Returns {raw_response: ...} to trigger synthesise_tc().
        """
        base_temp = self.temperature

        for attempt in range(1, 3):
            # Bump temperature slightly on retry to avoid getting identical bad output
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

            if self.debug:
                console.print(f"\n[dim]-- RAW ({len(raw)} chars): {raw[:800]}[/dim]\n")

            # Strip <think> blocks (Qwen3 reasoning traces)
            cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            # -- Parse attempt 1: direct --
            parsed = None
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                pass

            # -- Parse attempt 2: repair then parse --
            if parsed is None:
                repaired = _repair_truncated_json(cleaned)
                try:
                    parsed = json.loads(repaired)
                    console.print(f"    [dim]  repaired truncated JSON on attempt {attempt}[/dim]")
                except json.JSONDecodeError as e:
                    console.print(
                        f"    [yellow]  attempt {attempt} parse failed: {e} "
                        f"| raw: {raw[:120]}[/yellow]"
                    )
                    # Parse failed entirely — retry with nudged temperature
                    continue

            # -- Content sanity check --
            if _is_hollow(parsed):
                console.print(
                    f"    [yellow]  attempt {attempt} hollow response "
                    f"(schema-valid but empty fields)[/yellow]"
                )
                # Retry — model understood the schema, just wrote nothing
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
            f"    [yellow]  both attempts failed — falling back to synthesise_tc[/yellow]"
        )
        return {"raw_response": raw if "raw" in dir() else ""}

    # Alias for backward compatibility
    def generate_structured(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        return self.generate_test_case(prompt, system_prompt)

    def pull_model(self, model_name: str) -> bool:
        console.print(f"[cyan]Pulling model: {model_name}...[/cyan]")
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=300,
            )
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("status") == "success":
                        console.print(f"[green]Model {model_name} pulled[/green]")
                        return True
            return True
        except Exception as e:
            console.print(f"[red]Failed to pull model: {e}[/red]")
            return False