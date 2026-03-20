"""
Validation Gate Script
======================
Runs after each stage to verify the codebase is robust and error-free.

Usage:
    python scripts/validate_stage.py --stage 0
    python scripts/validate_stage.py --stage 1
    python scripts/validate_stage.py --stage 0 --verbose

Each stage runs cumulative checks (all previous stage checks + its own).
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path


# ── Helpers ──────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent
_PASS = 0
_FAIL = 0
_VERBOSE = False


def _run(label: str, cmd: list[str], cwd: str = None, allow_fail: bool = False) -> bool:
    """Run a command, print pass/fail, return success bool."""
    global _PASS, _FAIL

    if _VERBOSE:
        print(f"\n  > {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or str(_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0
    except FileNotFoundError:
        if allow_fail:
            print(f"  SKIP  {label} (command not found)")
            return True
        ok = False
        result = None
    except subprocess.TimeoutExpired:
        ok = False
        result = None

    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}")
        if result and _VERBOSE:
            if result.stdout:
                print(f"    stdout: {result.stdout[:500]}")
            if result.stderr:
                print(f"    stderr: {result.stderr[:500]}")

    return ok


def _check_import(label: str, import_statement: str) -> bool:
    """Check that a Python import succeeds."""
    return _run(
        label,
        [sys.executable, "-c", import_statement],
    )


# ── Stage Checks ────────────────────────────────────────────────────────────

def check_stage_0():
    """Foundation — structure, imports, contracts, config."""
    print("\n--- Stage 0: Foundation & Project Structure ---")

    # 1. Package importable
    _check_import(
        "stlc_platform package imports",
        "from stlc_platform import __version__, __stage__",
    )

    # 2. Core contracts importable
    _check_import(
        "Contracts import",
        "from stlc_platform.core.contracts import RequirementArtifact, TestCaseArtifact, PipelineRunArtifact",
    )

    # 3. BaseAgent importable
    _check_import(
        "BaseAgent import",
        "from stlc_platform.core.base_agent import BaseAgent, AgentResult, ValidationResult",
    )

    # 4. Config loader importable
    _check_import(
        "Config loader import",
        "from stlc_platform.core.config_loader import config, load_config",
    )

    # 5. LLM abstraction importable
    _check_import(
        "LLM base client import",
        "from stlc_platform.core.llm.base_client import BaseLLMClient, TESTCASE_JSON_SCHEMA",
    )
    _check_import(
        "Ollama client import",
        "from stlc_platform.core.llm.ollama_client import OllamaClient",
    )

    # 6. Storage importable
    _check_import(
        "ChromaDB store import",
        "from stlc_platform.core.storage.chroma_store import RequirementsVectorStore",
    )

    # 7. Requirements reader importable
    _check_import(
        "Requirements reader import",
        "from stlc_platform.agents.requirements_agent.reader import RequirementsReader, Requirement",
    )

    # 8. Exporters importable
    _check_import(
        "Exporters import",
        "from stlc_platform.exporters.exporters import CSVExporter, ZephyrScaleExporter, JSONReportExporter",
    )

    # 9. Config YAML exists
    yaml_path = _ROOT / "config" / "stlc_config.yaml"
    global _PASS, _FAIL
    if yaml_path.exists():
        _PASS += 1
        print("  PASS  stlc_config.yaml exists")
    else:
        _FAIL += 1
        print("  FAIL  stlc_config.yaml missing")

    # 10. Config JSON Schema exists
    schema_path = _ROOT / "config" / "stlc_config.schema.json"
    if schema_path.exists():
        _PASS += 1
        print("  PASS  stlc_config.schema.json exists")
    else:
        _FAIL += 1
        print("  FAIL  stlc_config.schema.json missing")

    # 11. pyproject.toml exists
    pyproject_path = _ROOT / "pyproject.toml"
    if pyproject_path.exists():
        _PASS += 1
        print("  PASS  pyproject.toml exists")
    else:
        _FAIL += 1
        print("  FAIL  pyproject.toml missing")

    # 12. Utils module importable
    _check_import(
        "Utils module import",
        "from stlc_platform.core.utils import find_project_root, slugify, deep_merge, safe_filename",
    )

    # 13. Migration script importable
    _check_import(
        "Migration script import",
        (
            "import sys; sys.path.insert(0, 'scripts'); "
            "from migrate import get_current_versions; "
            "v = get_current_versions(); "
            "assert len(v) >= 8"
        ),
    )

    # 14. Contract schema validation (instantiate with test data)
    _check_import(
        "Contract instantiation",
        (
            "from stlc_platform.core.contracts import RequirementArtifact, TestCaseArtifact, TestStepArtifact; "
            "r = RequirementArtifact(req_id='REQ-001', title='Test', description='Desc'); "
            "t = TestCaseArtifact("
            "  tc_id='TC-001', req_id='REQ-001', title='Test TC', "
            "  description='Desc', preconditions='Pre', test_type='positive', "
            "  priority='High', steps=[TestStepArtifact(action='Click button', expected_result='Page loads')]"
            ")"
        ),
    )

    # 15. Unit tests
    test_dir = _ROOT / "tests" / "unit"
    if test_dir.exists():
        _run(
            "Unit tests (pytest)",
            [sys.executable, "-m", "pytest", str(test_dir), "-v", "--tb=short", "-q"],
        )

    # 16. Integration tests
    integration_dir = _ROOT / "tests" / "integration"
    if integration_dir.exists() and list(integration_dir.glob("test_*.py")):
        _run(
            "Integration tests (pytest)",
            [sys.executable, "-m", "pytest", str(integration_dir), "-v", "--tb=short", "-q"],
        )

    # 17. Lint check (ruff)
    _run(
        "Lint check (ruff)",
        [sys.executable, "-m", "ruff", "check", "stlc_platform/", "--select=E,F", "--ignore=E501,E402"],
        allow_fail=True,
    )

    # 18. Type check (mypy) — allow_fail for gradual adoption
    _run(
        "Type check (mypy)",
        [sys.executable, "-m", "mypy", "stlc_platform/", "--ignore-missing-imports", "--no-error-summary"],
        allow_fail=True,
    )


def check_stage_1():
    """Domain-Agnostic Test Generation."""
    check_stage_0()  # Cumulative
    print("\n--- Stage 1: Domain-Agnostic Test Generation ---")

    # 1. LLM factory importable with all providers
    _check_import(
        "LLM factory import",
        "from stlc_platform.core.llm import create_llm_client, OllamaClient, OpenAIClient, AnthropicClient",
    )

    # 2. OpenAI client importable
    _check_import(
        "OpenAI client import",
        "from stlc_platform.core.llm.openai_client import OpenAIClient",
    )

    # 3. Anthropic client importable
    _check_import(
        "Anthropic client import",
        "from stlc_platform.core.llm.anthropic_client import AnthropicClient",
    )

    # 4. AC Classifier importable
    _check_import(
        "AC Classifier import",
        "from stlc_platform.agents.requirements_agent.classifier import ACClassifier, ClassificationResult",
    )

    # 5. Sanitiser importable
    _check_import(
        "Sanitiser import",
        "from stlc_platform.agents.requirements_agent.sanitiser import TestCaseSanitiser, SanitiserConfig",
    )

    # 6. Synthesiser importable
    _check_import(
        "Synthesiser import",
        "from stlc_platform.agents.requirements_agent.synthesiser import make_gwt, synthesise_steps, extract_steps",
    )

    # 7. Component resolver importable
    _check_import(
        "Component resolver import",
        "from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver",
    )

    # 8. Prompt renderer importable
    _check_import(
        "Prompt renderer import",
        "from stlc_platform.agents.requirements_agent.prompts import PromptRenderer",
    )

    # 9. Tech stack importable
    _check_import(
        "Tech stack import",
        "from stlc_platform.agents.requirements_agent.tech_stack import TechStackContext",
    )

    # 10. Domain detector importable
    _check_import(
        "Domain detector import",
        "from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector",
    )

    # 11. Generator importable
    _check_import(
        "Generator import",
        "from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator",
    )

    # 12. Agent importable
    _check_import(
        "Agent import",
        "from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent",
    )

    # 13. Package __init__ exports all classes
    _check_import(
        "Package exports",
        (
            "from stlc_platform.agents.requirements_agent import "
            "TestGenerationAgent, TestCaseGenerator, ACClassifier, "
            "ComponentResolver, DomainDetector, PromptRenderer, "
            "TestCaseSanitiser, TechStackContext"
        ),
    )

    # 14. Factory dispatches correctly
    _check_import(
        "Factory dispatch - ollama",
        (
            "from stlc_platform.core.llm import create_llm_client; "
            "from stlc_platform.core.llm.ollama_client import OllamaClient; "
            "c = create_llm_client('ollama'); "
            "assert isinstance(c, OllamaClient)"
        ),
    )

    # 15. Multi-domain classifier check
    _check_import(
        "Multi-domain classifier",
        (
            "from stlc_platform.agents.requirements_agent.classifier import ACClassifier; "
            "c = ACClassifier(); "
            "assert c.classify('must authenticate via OTP').ac_type == 'security'; "
            "assert c.classify('response within 3 seconds').ac_type == 'timing'; "
            "assert c.classify('field must be validated').ac_type == 'data_valid'"
        ),
    )

    # 16. Template completeness check
    global _PASS, _FAIL
    template_dir = _ROOT / "stlc_platform" / "agents" / "requirements_agent" / "prompts" / "templates"
    required_templates = ["system_prompt.j2", "user_prompt.j2", "few_shot_block.j2"]
    all_found = True
    for t in required_templates:
        if not (template_dir / t).exists():
            all_found = False
            break
    if all_found:
        _PASS += 1
        print(f"  PASS  Template files exist ({len(required_templates)} required)")
    else:
        _FAIL += 1
        print("  FAIL  Missing required template files")

    # 17. No hardcoded domain terms in requirements_agent/
    _run(
        "No hardcoded domain terms",
        [
            sys.executable, "-c",
            (
                "import pathlib, re; "
                "agent_dir = pathlib.Path('stlc_platform/agents/requirements_agent'); "
                "bad = []; "
                "[bad.append(f'{p.name}:{i+1}: {line.strip()}') "
                " for p in agent_dir.rglob('*.py') if 'test' not in p.name "
                " for i, line in enumerate(p.read_text().splitlines()) "
                " if any(term in line.lower() for term in "
                "   ['mobile banking app', 'patient registration screen', 'cheque-shaped'])"
                "]; "
                "assert len(bad) == 0, f'Found hardcoded terms: {bad}'"
            ),
        ],
    )

    # 18. Fixture files exist
    fixtures_dir = _ROOT / "tests" / "fixtures"
    fixture_files = [
        "requirements_ecommerce.json",
        "requirements_healthcare.json",
        "requirements_banking.json",
    ]
    fixtures_ok = all((fixtures_dir / f).exists() for f in fixture_files)
    if fixtures_ok:
        _PASS += 1
        print(f"  PASS  Domain fixture files exist ({len(fixture_files)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing domain fixture files")

    # 19. Integration tests
    integration_dir = _ROOT / "tests" / "integration"
    if integration_dir.exists() and list(integration_dir.glob("test_stage1*.py")):
        _run(
            "Stage 1 integration tests",
            [sys.executable, "-m", "pytest", str(integration_dir), "-v", "--tb=short", "-q"],
        )


def check_stage_2():
    """BDD Automation Code Generator."""
    check_stage_1()
    print("\n--- Stage 2: BDD Automation Code Generator ---")
    print("  SKIP  Stage 2 checks not yet implemented")


def check_stage_3():
    """Web Crawler & API Test Generator."""
    check_stage_2()
    print("\n--- Stage 3: Web Crawler & API Test Generator ---")
    print("  SKIP  Stage 3 checks not yet implemented")


def check_stage_4():
    """Agent Orchestration & Integration."""
    check_stage_3()
    print("\n--- Stage 4: Agent Orchestration & Integration ---")
    print("  SKIP  Stage 4 checks not yet implemented")


def check_stage_5():
    """Frontend UI."""
    check_stage_4()
    print("\n--- Stage 5: Frontend UI ---")
    print("  SKIP  Stage 5 checks not yet implemented")


# ── Main ─────────────────────────────────────────────────────────────────────

STAGE_CHECKS = {
    0: check_stage_0,
    1: check_stage_1,
    2: check_stage_2,
    3: check_stage_3,
    4: check_stage_4,
    5: check_stage_5,
}


def main():
    global _VERBOSE

    parser = argparse.ArgumentParser(description="STLC Platform Validation Gate")
    parser.add_argument(
        "--stage", "-s", type=int, required=True, choices=range(6),
        help="Stage number to validate (0-5)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show command output")
    args = parser.parse_args()

    _VERBOSE = args.verbose

    print(f"=== STLC Platform Validation Gate — Stage {args.stage} ===")

    STAGE_CHECKS[args.stage]()

    print(f"\n=== Results: {_PASS} passed, {_FAIL} failed ===")

    if _FAIL > 0:
        print("VALIDATION FAILED")
        sys.exit(1)
    else:
        print("VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
