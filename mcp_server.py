"""
MCP Server — AI Test Case Orchestrator
=======================================
Exposes the orchestrator pipeline as MCP tools so any MCP client
(Claude Desktop, CI pipeline, another LLM agent) can:

  - Parse requirements files
  - Generate test cases with full RAG context
  - Validate a test case and get a structured issue list
  - Repair a specific field in a failing test case
  - Store an approved test case as a few-shot example
  - Query ChromaDB stats and stored examples

WHY THIS MATTERS FOR REDUCING POST-PROCESSING:
  The repair_test_case tool re-prompts the LLM with the SPECIFIC FIELD that
  failed and the SPECIFIC ISSUE — not a blind full-TC retry.
  "Your expected_outcome field is trivial — write a specific observable outcome
  for this acceptance criterion: {ac}" gets a much better result than
  silently replacing the field with deterministic text.

  The store_approved_tc tool closes the feedback loop:
  Human reviews output → marks good TCs → they become few-shot examples →
  next run generates better output from the start.

SETUP:
  pip install mcp
  python mcp_server.py              # starts stdio MCP server

CLAUDE DESKTOP CONFIG (claude_desktop_config.json):
  {
    "mcpServers": {
      "test-orchestrator": {
        "command": "python",
        "args": ["/path/to/test_orchestrator/mcp_server.py"],
        "env": {
          "OLLAMA_MODEL": "phi4-mini:3.8b"
        }
      }
    }
  }

DIRECT CLI USAGE (for testing without an MCP client):
  python mcp_server.py --tool validate-tc --input output/test_cases.csv --tc-id TC-0016
  python mcp_server.py --tool store-example --input output/test_cases.csv --tc-id TC-0002
  python mcp_server.py --tool stats
"""

import sys
import os
import json
import re
import csv
import click

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__) or ".")

# Pydantic patch must be first
#import pydantic_v1_patch
#pydantic_v1_patch.apply()

from rich.console import Console
console = Console()


# ── Lazy imports (avoid loading chromadb/llm until a tool is actually called) ──

def _get_store():
    from chroma_store import RequirementsVectorStore
    store = RequirementsVectorStore()
    store.initialize()
    return store


def _get_llm():
    from llm_client import OllamaClient
    return OllamaClient()


def _get_generator(llm, store):
    from test_generator import TestCaseGenerator
    return TestCaseGenerator(llm_client=llm, vector_store=store)


# ── Validation helpers (used by both MCP tool and CLI) ────────────────────────

def _validate_tc_dict(tc: dict) -> dict:
    """
    Validate a test case dict and return a structured result.
    Returns:
      {
        "passed": bool,
        "issues": [{"field": str, "severity": "error"|"warning", "detail": str}],
        "score": int   # 0-100, 100 = perfect
      }
    This replaces the silent sanitiser with an INSPECTABLE checker.
    The caller can see exactly which fields failed and why.
    """
    import re

    issues = []

    def _has_loop(text, threshold=3):
        parts = re.split(r'[.\n]', str(text))
        parts = [p.strip().lower()[:60] for p in parts if len(p.strip()) > 15]
        counts = {}
        for p in parts:
            counts[p] = counts.get(p, 0) + 1
            if counts[p] >= threshold:
                return True
        return False

    _GENERIC_FRAGMENTS = [
        "perform the action", "perform the specific action",
        "trigger the feature", "verify the outcome", "check the result",
        "observe the result", "perform the valid action",
        "execute the test step", "complete the action",
    ]

    _TRIVIAL_OUTCOMES = {
        "true", "false", "pass", "fail", "passed", "failed",
        "valid rejection", "valid", "success", "n/a", "none",
        "expected outcome", "the test passes", "the test fails",
        "system accepts the input", "correct boundary behaviour confirmed",
    }

    _GENERIC_APPS = {
        "the application", "the app", "the system", "the platform",
        "mobile banking app", "the software", "generic app", "the product",
    }

    # Title
    title = tc.get("title", "").strip()
    if not title or len(title) < 10:
        issues.append({"field": "title", "severity": "error",
                        "detail": "Title is empty or too short"})

    # Description
    desc = tc.get("description", "").strip()
    if not desc or len(desc) < 20:
        issues.append({"field": "description", "severity": "error",
                        "detail": "Description is empty or too short (<20 chars)"})
    elif _has_loop(desc):
        issues.append({"field": "description", "severity": "error",
                        "detail": "Description contains repeated sentences (hallucinated loop)"})

    # Preconditions
    pre = tc.get("preconditions", "").strip()
    if not pre or len(pre) < 20:
        issues.append({"field": "preconditions", "severity": "warning",
                        "detail": "Preconditions is empty or too short"})

    # Steps
    steps = tc.get("steps", [])
    if not steps or len(steps) < 3:
        issues.append({"field": "steps", "severity": "error",
                        "detail": f"Only {len(steps)} step(s) — minimum 3 required"})
    else:
        generic_count = 0
        loop_count    = 0
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            action = step.get("action", "").strip().lower()
            result = step.get("expected_result", "").strip()

            if len(action) < 15 or any(action.startswith(f) for f in _GENERIC_FRAGMENTS):
                generic_count += 1
            if _has_loop(action) or _has_loop(result):
                loop_count += 1
            if not result or len(result) < 10:
                issues.append({
                    "field": f"steps[{i}].expected_result",
                    "severity": "warning",
                    "detail": f"Step {i+1} has empty or trivial expected_result",
                })

        if generic_count > 0:
            issues.append({
                "field": "steps",
                "severity": "error",
                "detail": (
                    f"{generic_count} step(s) contain generic phrases like "
                    f"'perform the action' or 'trigger the feature'. "
                    f"Each step must name the exact button, field, or UI element."
                ),
            })
        if loop_count > 0:
            issues.append({
                "field": "steps",
                "severity": "error",
                "detail": f"{loop_count} step(s) contain repeated/looping sentences",
            })

    # Expected outcome
    outcome = tc.get("expected_outcome", "").strip()
    if not outcome or outcome.lower() in _TRIVIAL_OUTCOMES or len(outcome) < 20:
        issues.append({
            "field": "expected_outcome",
            "severity": "error",
            "detail": (
                f"Expected outcome is trivial or empty: '{outcome[:60]}'. "
                f"Must describe the specific observable system state that proves the AC is satisfied."
            ),
        })
    elif _has_loop(outcome):
        issues.append({"field": "expected_outcome", "severity": "error",
                        "detail": "Expected outcome contains repeated sentences"})

    # GWT
    for field in ["given", "when", "then"]:
        val = tc.get(field, "").strip()
        if not val or len(val) < 12:
            issues.append({"field": field, "severity": "warning",
                            "detail": f"{field.title()} is empty or too short"})

    # Component
    comp = tc.get("component", "").strip()
    if not comp or comp.lower() in _GENERIC_APPS or len(comp) < 5:
        issues.append({
            "field": "component",
            "severity": "warning",
            "detail": (
                f"Component is generic or missing: '{comp}'. "
                f"Should name a specific screen like 'OTP Verification Screen'."
            ),
        })

    # Score: start at 100, deduct per issue
    deductions = sum(15 if i["severity"] == "error" else 5 for i in issues)
    score = max(0, 100 - deductions)

    return {
        "passed": score >= 75 and not any(i["severity"] == "error" for i in issues),
        "issues": issues,
        "score": score,
    }


def _repair_tc_field(tc: dict, field: str, issue_detail: str, ac_text: str, llm) -> str:
    """
    Re-prompt the LLM to repair a SINGLE failing field.
    Returns the repaired field value as a string.

    This is surgical repair — not a blind full-TC retry.
    The model is told exactly which field failed and exactly what is wrong.
    """
    from llm_client import OllamaClient

    FIELD_PROMPTS = {
        "description": (
            "Write ONE sentence describing what this test case verifies. "
            "Do not copy any instruction text. "
            "Base it on this acceptance criterion: {ac}"
        ),
        "preconditions": (
            "Write ONE or TWO sentences describing the specific system state "
            "and test data required before executing this test case. "
            "Name the account type and login state. "
            "Acceptance criterion: {ac}"
        ),
        "expected_outcome": (
            "Write ONE or TWO sentences describing the specific observable "
            "system state that proves this acceptance criterion is satisfied. "
            "Name the exact message, screen, badge, or measured value visible to the tester. "
            "Do NOT write 'pass', 'fail', 'system accepts', or any other trivial phrase. "
            "Acceptance criterion: {ac}"
        ),
        "steps": (
            "Write exactly 5 numbered test steps for a {test_type} test of this acceptance criterion: {ac}\n"
            "Each step MUST:\n"
            "  - name the EXACT button label, field name, or UI element the tester interacts with\n"
            "  - include a '-> Expected: [specific observable result]' for each action\n"
            "Do NOT write 'perform the action', 'trigger the feature', or any generic phrase.\n"
            "Respond with numbered steps only — no JSON, no preamble."
        ),
    }

    template = FIELD_PROMPTS.get(field)
    if not template:
        return ""

    prompt = (
        f"The following field in a test case has this problem:\n"
        f"  Field: {field}\n"
        f"  Issue: {issue_detail}\n"
        f"  Current value: {json.dumps(tc.get(field,''))[:200]}\n\n"
        + template.format(
            ac=ac_text[:200],
            test_type=tc.get("test_type", "positive"),
        )
        + "\n\nRespond with ONLY the corrected field value — no JSON wrapping, no explanation."
    )

    system = (
        "You are a senior QA engineer writing specific, executable test case content. "
        "Always name exact UI elements, exact error messages, and exact observable outcomes. "
        "Never use placeholders or generic phrases."
    )

    try:
        result = llm.generate(prompt=prompt, system_prompt=system, temperature=0.5)
        # Strip any JSON wrapping the model might add
        result = re.sub(r'^[`"\s{]+|[`"\s}]+$', '', result.strip())
        return result
    except Exception as e:
        return f"[repair failed: {e}]"


def _load_tc_from_csv(csv_path: str, tc_id: str) -> dict | None:
    """Load a single TC dict from the output CSV by TC ID."""
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("TC ID", "").strip() == tc_id:
                # Reconstruct steps from pipe-separated text
                steps = []
                raw_steps = row.get("Steps", "")
                for chunk in raw_steps.split("\n"):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    if "| Expected:" in chunk:
                        parts = chunk.split("| Expected:", 1)
                        action = re.sub(r"^\d+\.\s*", "", parts[0]).strip()
                        result = parts[1].strip()
                    else:
                        action = re.sub(r"^\d+\.\s*", "", chunk).strip()
                        result = ""
                    if action:
                        steps.append({"action": action, "expected_result": result})

                return {
                    "tc_id":            row.get("TC ID", ""),
                    "req_id":           row.get("Requirement ID", ""),
                    "title":            row.get("Title", ""),
                    "description":      row.get("Description", ""),
                    "preconditions":    row.get("Preconditions", ""),
                    "test_type":        row.get("Test Type", ""),
                    "priority":         row.get("Priority", ""),
                    "category":         row.get("Category", ""),
                    "component":        row.get("Component", ""),
                    "steps":            steps,
                    "expected_outcome": row.get("Expected Outcome", ""),
                    "given":            row.get("Given", ""),
                    "when":             row.get("When", ""),
                    "then":             row.get("Then", ""),
                    "tags":             [t.strip() for t in row.get("Tags","").split(",") if t.strip()],
                }
    return None


# ── MCP Server ────────────────────────────────────────────────────────────────

def _run_mcp_server():
    """Start the FastMCP server (stdio transport for Claude Desktop)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        console.print("[red]mcp package not installed. Run: pip install mcp[/red]")
        sys.exit(1)

    mcp = FastMCP("test-orchestrator")

    @mcp.tool()
    def chromadb_stats() -> dict:
        """
        Return counts for all three ChromaDB collections.
        Tells you how many requirements, approved examples, and vocab terms are stored.
        """
        store = _get_store()
        return store.stats

    @mcp.tool()
    def list_examples(ac_type: str = "", test_type: str = "") -> dict:
        """
        List approved TC examples stored in the tc_examples collection.
        Filter by ac_type (eligibility|ui_behaviour|timing|data_valid|security|general)
        and/or test_type (positive|negative|edge_case).
        """
        store = _get_store()
        count = store.get_example_count(ac_type=ac_type, test_type=test_type)
        return {
            "count": count,
            "filter": {"ac_type": ac_type, "test_type": test_type},
            "message": (
                f"{count} example(s) stored"
                + (f" for {ac_type}/{test_type}" if ac_type or test_type else "")
            ),
        }

    @mcp.tool()
    def validate_test_case(tc_json: str) -> dict:
        """
        Validate a test case JSON string and return a structured issue report.
        Returns: { passed: bool, score: int (0-100), issues: [{field, severity, detail}] }

        Use this BEFORE storing an example or AFTER generation to inspect quality.
        A score >= 75 with no errors means the TC is ready to use.
        """
        try:
            tc = json.loads(tc_json)
        except json.JSONDecodeError as e:
            return {"passed": False, "score": 0, "issues": [
                {"field": "json", "severity": "error", "detail": f"Invalid JSON: {e}"}
            ]}
        return _validate_tc_dict(tc)

    @mcp.tool()
    def repair_test_case(
        tc_json: str,
        field: str,
        issue_detail: str,
        ac_text: str,
    ) -> dict:
        """
        Repair a SINGLE failing field in a test case using a targeted LLM re-prompt.
        
        Parameters:
          tc_json:      The full test case as a JSON string
          field:        Which field to repair: description|preconditions|expected_outcome|steps
          issue_detail: The specific problem (from validate_test_case issues list)
          ac_text:      The acceptance criterion this test case covers

        Returns: { field: str, original: str, repaired: str, validation: dict }
        
        Why targeted repair beats full retry:
          A full retry regenerates all 15 fields and might fix one while breaking others.
          Targeted repair sends a focused prompt for exactly the failing field.
        """
        try:
            tc = json.loads(tc_json)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}"}

        llm = _get_llm()
        original = tc.get(field, "")
        repaired_value = _repair_tc_field(tc, field, issue_detail, ac_text, llm)

        # Apply the repair
        if field == "steps":
            # Parse the plain-text numbered steps back into step dicts
            step_lines = [l.strip() for l in repaired_value.split("\n") if l.strip()]
            steps = []
            for line in step_lines:
                line = re.sub(r"^\d+[\.\)]\s*", "", line)
                if "-> Expected:" in line:
                    a, r = line.split("-> Expected:", 1)
                    steps.append({"action": a.strip(), "expected_result": r.strip()})
                elif "->" in line:
                    a, r = line.split("->", 1)
                    steps.append({"action": a.strip(), "expected_result": r.strip()})
                else:
                    steps.append({"action": line, "expected_result": ""})
            tc[field] = steps
        else:
            tc[field] = repaired_value

        # Re-validate after repair
        validation = _validate_tc_dict(tc)

        return {
            "field":      field,
            "original":   str(original)[:200],
            "repaired":   repaired_value[:300] if field != "steps" else f"{len(tc.get('steps',[]))} steps",
            "tc_updated": tc,
            "validation": validation,
        }

    @mcp.tool()
    def store_approved_tc(
        tc_json: str,
        ac_type: str,
        test_type: str,
        domain: str = "",
    ) -> dict:
        """
        Store an approved test case as a few-shot example in ChromaDB.

        This is the FEEDBACK LOOP that makes the system improve over time:
          1. Run the orchestrator and get output TCs
          2. Review the output — find TCs with good, specific, executable steps
          3. Call this tool with those TCs
          4. On the NEXT run, the model retrieves these as few-shot examples
          5. Output quality improves without any retraining

        Parameters:
          tc_json:   The approved test case as a JSON string
          ac_type:   One of: eligibility|ui_behaviour|timing|data_valid|security|general
          test_type: One of: positive|negative|edge_case
          domain:    Optional domain label (e.g. "mobile banking", "healthcare")

        The tool first validates the TC — rejects anything with errors.
        """
        try:
            tc = json.loads(tc_json)
        except json.JSONDecodeError as e:
            return {"stored": False, "error": f"Invalid JSON: {e}"}

        # Validate before storing — don't let bad examples in
        validation = _validate_tc_dict(tc)
        if not validation["passed"]:
            return {
                "stored": False,
                "error": "TC did not pass validation — fix issues before storing as an example",
                "validation": validation,
            }

        store = _get_store()
        doc_id = store.store_approved_tc(
            tc_dict=tc,
            ac_type=ac_type,
            test_type=test_type,
            domain=domain,
        )

        stats = store.stats
        return {
            "stored":  True,
            "doc_id":  doc_id,
            "ac_type": ac_type,
            "test_type": test_type,
            "stats_after": stats,
            "message": (
                f"Stored as example {doc_id}. "
                f"Total examples: {stats['tc_examples']}. "
                f"Will be retrieved as few-shot context in the next run."
            ),
        }

    @mcp.tool()
    def retrieve_examples(
        ac_text: str,
        ac_type: str,
        test_type: str,
        n: int = 2,
    ) -> dict:
        """
        Retrieve the n closest approved TC examples for a given AC type and test type.
        Useful for inspecting what few-shot context the model will see during generation.

        Parameters:
          ac_text:   The acceptance criterion text to find examples for
          ac_type:   One of: eligibility|ui_behaviour|timing|data_valid|security|general
          test_type: One of: positive|negative|edge_case
          n:         Number of examples to retrieve (default 2)
        """
        store = _get_store()
        examples = store.retrieve_examples(
            ac_text=ac_text,
            ac_type=ac_type,
            test_type=test_type,
            n=n,
        )
        return {
            "count": len(examples),
            "examples": [
                {
                    "title":            ex.get("title", "")[:80],
                    "test_type":        ex.get("test_type", ""),
                    "ac_type":          ex.get("ac_type", ""),
                    "similarity":       ex.get("_similarity", 0),
                    "component":        ex.get("component", ""),
                    "expected_outcome": ex.get("expected_outcome", "")[:120],
                    "step_count":       len(ex.get("steps", [])),
                }
                for ex in examples
            ],
        }

    @mcp.tool()
    def domain_vocab_summary(category: str = "") -> dict:
        """
        Show extracted screen names and UI element names from the domain_vocab collection.
        Optionally filter by requirement category.
        Useful for checking what component names the dynamic lookup will return.
        """
        store = _get_store()
        vocab = store.get_domain_vocab_summary(category=category)
        return {
            "category_filter": category or "all",
            "screen_count": len(vocab["screens"]),
            "element_count": len(vocab["elements"]),
            "screens": sorted(vocab["screens"]),
            "elements": sorted(vocab["elements"]),
        }

    console.print("[cyan]Starting MCP server (stdio)...[/cyan]")
    console.print("[dim]Connect via Claude Desktop or any MCP client.[/dim]")
    mcp.run(transport="stdio")


# ── CLI mode (for testing without an MCP client) ──────────────────────────────

@click.group()
def cli():
    """Test Orchestrator MCP tools — CLI mode for testing."""
    pass


@cli.command("stats")
def cli_stats():
    """Show ChromaDB collection counts."""
    store = _get_store()
    s = store.stats
    console.print(f"[bold]ChromaDB Stats:[/bold]")
    console.print(f"  requirements: {s['requirements']}")
    console.print(f"  tc_examples:  {s['tc_examples']}")
    console.print(f"  domain_vocab: {s['domain_vocab']}")


@cli.command("validate-tc")
@click.option("--input", "-i", "csv_path", required=True, help="Path to test_cases.csv")
@click.option("--tc-id", required=True, help="TC ID to validate (e.g. TC-0016)")
def cli_validate(csv_path, tc_id):
    """Validate a test case from the output CSV and show issues."""
    tc = _load_tc_from_csv(csv_path, tc_id)
    if not tc:
        console.print(f"[red]{tc_id} not found in {csv_path}[/red]")
        return
    result = _validate_tc_dict(tc)
    console.print(f"\n[bold]{tc_id}[/bold] — score: {result['score']}/100 | passed: {result['passed']}")
    if result["issues"]:
        for issue in result["issues"]:
            colour = "red" if issue["severity"] == "error" else "yellow"
            console.print(f"  [{colour}]{issue['severity'].upper()}[/{colour}] {issue['field']}: {issue['detail']}")
    else:
        console.print("  [green]No issues — ready to use.[/green]")


@cli.command("repair-tc")
@click.option("--input", "-i", "csv_path", required=True, help="Path to test_cases.csv")
@click.option("--tc-id", required=True, help="TC ID to repair")
@click.option("--field", required=True,
              type=click.Choice(["description","preconditions","expected_outcome","steps"]),
              help="Field to repair")
@click.option("--ac", "ac_text", required=True, help="The acceptance criterion text")
def cli_repair(csv_path, tc_id, field, ac_text):
    """Repair a single field in a test case using a targeted LLM re-prompt."""
    tc = _load_tc_from_csv(csv_path, tc_id)
    if not tc:
        console.print(f"[red]{tc_id} not found in {csv_path}[/red]")
        return

    validation = _validate_tc_dict(tc)
    issue = next((i for i in validation["issues"] if i["field"] == field), None)
    issue_detail = issue["detail"] if issue else f"{field} needs improvement"

    console.print(f"[cyan]Repairing {field} for {tc_id}...[/cyan]")
    llm = _get_llm()
    repaired = _repair_tc_field(tc, field, issue_detail, ac_text, llm)

    console.print(f"\n[bold]Original:[/bold]\n  {str(tc.get(field,''))[:200]}")
    console.print(f"\n[bold]Repaired:[/bold]\n  {repaired[:300]}")


@cli.command("store-example")
@click.option("--input", "-i", "csv_path", required=True, help="Path to test_cases.csv")
@click.option("--tc-id", required=True, help="TC ID to store as example")
@click.option("--ac-type", required=True,
              type=click.Choice(["eligibility","ui_behaviour","timing","data_valid","security","general"]))
@click.option("--test-type", default=None,
              type=click.Choice(["positive","negative","edge_case"]),
              help="Override test type (default: read from CSV)")
@click.option("--domain", default="", help="Optional domain label")
def cli_store(csv_path, tc_id, ac_type, test_type, domain):
    """
    Store an approved TC from the output CSV as a few-shot example in ChromaDB.

    WORKFLOW:
      1. Run: python orchestrator.py --requirements ... --format both
      2. Open output/test_cases.csv and review
      3. Find a TC with good, specific, executable steps
      4. Run: python mcp_server.py store-example -i output/test_cases.csv --tc-id TC-0002 --ac-type eligibility
      5. Next run will use this TC as a few-shot example for eligibility tests
    """
    tc = _load_tc_from_csv(csv_path, tc_id)
    if not tc:
        console.print(f"[red]{tc_id} not found in {csv_path}[/red]")
        return

    # Validate first
    validation = _validate_tc_dict(tc)
    if not validation["passed"]:
        console.print(f"[yellow]TC has issues (score {validation['score']}/100):[/yellow]")
        for issue in validation["issues"]:
            console.print(f"  {issue['severity'].upper()} {issue['field']}: {issue['detail']}")
        if not click.confirm("Store anyway?", default=False):
            return

    store = _get_store()
    doc_id = store.store_approved_tc(
        tc_dict=tc,
        ac_type=ac_type,
        test_type=test_type or tc.get("test_type", "positive"),
        domain=domain,
    )
    stats = store.stats
    console.print(f"[green]Stored: {doc_id}[/green] — total examples: {stats['tc_examples']}")


@cli.command("list-examples")
@click.option("--ac-type", default="", help="Filter by AC type")
@click.option("--test-type", default="", help="Filter by test type")
def cli_list_examples(ac_type, test_type):
    """List approved examples stored in ChromaDB."""
    store = _get_store()
    count = store.get_example_count(ac_type=ac_type, test_type=test_type)
    console.print(
        f"[bold]{count}[/bold] example(s) stored"
        + (f" matching {ac_type}/{test_type}" if ac_type or test_type else "")
    )


@cli.command("vocab")
@click.option("--category", default="", help="Filter by requirement category")
def cli_vocab(category):
    """Show extracted domain vocabulary (screen names, UI elements)."""
    store = _get_store()
    vocab = store.get_domain_vocab_summary(category=category)
    console.print(f"\n[bold]Screens ({len(vocab['screens'])}):[/bold]")
    for s in sorted(vocab["screens"]):
        console.print(f"  {s}")
    console.print(f"\n[bold]UI Elements ({len(vocab['elements'])}):[/bold]")
    for e in sorted(vocab["elements"])[:30]:
        console.print(f"  {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # If no arguments, start as MCP server (stdio)
    # If arguments provided, run CLI mode
    if len(sys.argv) == 1:
        _run_mcp_server()
    else:
        cli()
