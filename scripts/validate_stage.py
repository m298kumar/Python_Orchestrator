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

    global _PASS, _FAIL

    # 1. BDD Agent importable
    _check_import(
        "BDD Agent import",
        "from stlc_platform.agents.bdd_agent import BDDAgent, FeatureFileGenerator, GherkinValidator, StepDefinitionGenerator, StepParser",
    )

    # 2. Feature generator importable
    _check_import(
        "Feature generator import",
        "from stlc_platform.agents.bdd_agent.feature_generator import FeatureFileGenerator",
    )

    # 3. Gherkin validator importable
    _check_import(
        "Gherkin validator import",
        "from stlc_platform.agents.bdd_agent.gherkin_validator import GherkinValidator, GherkinValidationResult",
    )

    # 4. Step parser importable
    _check_import(
        "Step parser import",
        "from stlc_platform.agents.bdd_agent.step_parser import StepParser, ParsedStep, ParameterizedStep",
    )

    # 5. Step def generator importable
    _check_import(
        "Step def generator import",
        "from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator",
    )

    # 6. Jinja2 templates exist
    template_dir = _ROOT / "stlc_platform" / "agents" / "bdd_agent" / "templates"
    required_templates = ["feature.j2", "behave_steps.py.j2", "pytest_bdd_steps.py.j2"]
    all_found = all((template_dir / t).exists() for t in required_templates)
    if all_found:
        _PASS += 1
        print(f"  PASS  BDD templates exist ({len(required_templates)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing BDD template files")

    # 7. Test case fixtures for BDD exist
    fixtures_dir = _ROOT / "tests" / "fixtures"
    bdd_fixtures = [
        "test_cases_ecommerce.json",
        "test_cases_healthcare.json",
        "test_cases_banking.json",
    ]
    fixtures_ok = all((fixtures_dir / f).exists() for f in bdd_fixtures)
    if fixtures_ok:
        _PASS += 1
        print(f"  PASS  BDD test case fixtures exist ({len(bdd_fixtures)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing BDD test case fixture files")

    # 8. BDDAgent can execute end-to-end (smoke test)
    _check_import(
        "BDD Agent smoke test",
        (
            "from stlc_platform.agents.bdd_agent import BDDAgent; "
            "from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact; "
            "agent = BDDAgent(); "
            "tc = TestCaseArtifact("
            "  tc_id='TC-001', req_id='REQ-001', title='Smoke test', "
            "  description='Smoke', preconditions='Ready', test_type='positive', "
            "  priority='High', steps=[TestStepArtifact(action='Do it', expected_result='Done')], "
            "  given='the system is ready', when='the user acts', then='the result is correct'"
            "); "
            "r = agent.execute({'test_cases': [tc]}, {'framework': 'behave'}); "
            "assert r.success, f'BDD Agent failed: {r.errors}'"
        ),
    )

    # 9. Generated step defs are valid Python (ast.parse)
    _check_import(
        "Step def syntax check",
        (
            "import ast; "
            "from stlc_platform.agents.bdd_agent import BDDAgent; "
            "from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact; "
            "agent = BDDAgent(); "
            "tc = TestCaseArtifact("
            "  tc_id='TC-001', req_id='REQ-001', title='Syntax check', "
            "  description='Test', preconditions='Ready', test_type='positive', "
            "  priority='High', steps=[TestStepArtifact(action='Click', expected_result='OK')], "
            "  given='the user is logged in', when='the user clicks submit', then='the result is shown'"
            "); "
            "r = agent.execute({'test_cases': [tc]}, {'framework': 'behave'}); "
            "[ast.parse(sd.content) for sd in r.artifacts['step_definitions']]"
        ),
    )

    # 10. Behave and Pytest-BDD both supported
    _check_import(
        "Framework support (behave + pytest_bdd)",
        (
            "from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator; "
            "b = StepDefinitionGenerator(framework='behave'); "
            "p = StepDefinitionGenerator(framework='pytest_bdd'); "
            "assert b.framework == 'behave'; "
            "assert p.framework == 'pytest_bdd'"
        ),
    )

    # 11. No hardcoded domain terms in bdd_agent/
    _run(
        "No hardcoded domain terms in BDD agent",
        [
            sys.executable, "-c",
            (
                "import pathlib; "
                "agent_dir = pathlib.Path('stlc_platform/agents/bdd_agent'); "
                "bad = []; "
                "[bad.append(f'{p.name}:{i+1}: {line.strip()}') "
                " for p in agent_dir.rglob('*.py') if 'test' not in p.name "
                " for i, line in enumerate(p.read_text().splitlines()) "
                " if any(term in line.lower() for term in "
                "   ['mobile banking', 'patient registration', 'cheque-shaped'])"
                "]; "
                "assert len(bad) == 0, f'Found hardcoded terms: {bad}'"
            ),
        ],
    )

    # 12. Stage 2 integration tests pass
    integration_dir = _ROOT / "tests" / "integration"
    stage2_tests = list(integration_dir.glob("test_stage2*.py"))
    if stage2_tests:
        _run(
            "Stage 2 integration tests",
            [sys.executable, "-m", "pytest", str(integration_dir / "test_stage2_validation.py"),
             "-v", "--tb=short", "-q"],
        )


def check_stage_3():
    """Web Crawler & API Test Generator (Phase 1: Crawler Agent)."""
    check_stage_2()
    print("\n--- Stage 3: Web Crawler & API Test Generator ---")

    global _PASS, _FAIL

    # 1. CrawlerAgent package importable
    _check_import(
        "Crawler Agent package import",
        "from stlc_platform.agents.crawler_agent import CrawlerAgent, PageParser, SiteModelBuilder, DiscrepancyDetector",
    )

    # 2. PageParser importable
    _check_import(
        "PageParser import",
        "from stlc_platform.agents.crawler_agent.page_parser import PageParser",
    )

    # 3. SiteModelBuilder importable
    _check_import(
        "SiteModelBuilder import",
        "from stlc_platform.agents.crawler_agent.site_model_builder import SiteModelBuilder",
    )

    # 4. DiscrepancyDetector importable
    _check_import(
        "DiscrepancyDetector import",
        "from stlc_platform.agents.crawler_agent.discrepancy_detector import DiscrepancyDetector",
    )

    # 5. New contracts importable (DiscrepancyArtifact, DiscrepancyReportArtifact)
    _check_import(
        "Discrepancy contracts import",
        "from stlc_platform.core.contracts import DiscrepancyArtifact, DiscrepancyReportArtifact",
    )

    # 6. HTML fixture files exist (4 files)
    fixtures_dir = _ROOT / "tests" / "fixtures" / "html_pages"
    html_fixtures = ["login.html", "dashboard.html", "product_list.html", "checkout.html"]
    all_exist = all((fixtures_dir / f).exists() for f in html_fixtures)
    if all_exist:
        _PASS += 1
        print(f"  PASS  HTML fixture files exist ({len(html_fixtures)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing HTML fixture files")

    # 7. Site model fixture exists
    site_model_fixture = _ROOT / "tests" / "fixtures" / "site_model_ecommerce.json"
    if site_model_fixture.exists():
        _PASS += 1
        print("  PASS  site_model_ecommerce.json exists")
    else:
        _FAIL += 1
        print("  FAIL  site_model_ecommerce.json missing")

    # 8. CrawlerAgent smoke test (parse HTML, verify success)
    _check_import(
        "CrawlerAgent smoke test",
        (
            "from stlc_platform.agents.crawler_agent import CrawlerAgent; "
            "agent = CrawlerAgent(); "
            "html_pages = {'http://localhost/test': '<html><head><title>Test</title></head>"
            "<body><form><input name=\"email\" type=\"text\"><button type=\"submit\">Go</button></form></body></html>'}; "
            "r = agent.execute({'html_pages': html_pages}, {}); "
            "assert r.success, f'CrawlerAgent failed: {r.errors}'; "
            "assert r.metadata['total_pages'] == 1; "
            "assert r.metadata['total_elements'] > 0"
        ),
    )

    # 9. Discrepancy detection smoke test
    _check_import(
        "Discrepancy detection smoke test",
        (
            "from stlc_platform.agents.crawler_agent import CrawlerAgent; "
            "from stlc_platform.core.contracts import RequirementArtifact; "
            "agent = CrawlerAgent(); "
            "html = {'http://localhost/login': '<html><head><title>Login</title></head>"
            "<body><form><input name=\"username\"><button>Sign In</button></form></body></html>'}; "
            "reqs = [RequirementArtifact(req_id=\"REQ-T\", title=\"Login\", description=\"Login page\", "
            "acceptance_criteria=[\"User clicks Sign In button\"], priority=\"High\")]; "
            "r = agent.execute({'html_pages': html, 'requirements': reqs}, {}); "
            "assert r.success; "
            "assert 'discrepancy_report' in r.artifacts; "
            "assert 'gate_decision' in r.metadata"
        ),
    )

    # 10. No hardcoded domain terms in crawler_agent/
    _run(
        "No hardcoded domain terms in crawler agent",
        [
            sys.executable, "-c",
            (
                "import pathlib; "
                "agent_dir = pathlib.Path('stlc_platform/agents/crawler_agent'); "
                "bad = []; "
                "[bad.append(f'{p.name}:{i+1}: {line.strip()}') "
                " for p in agent_dir.rglob('*.py') if 'test' not in p.name "
                " for i, line in enumerate(p.read_text().splitlines()) "
                " if any(term in line.lower() for term in "
                "   ['mobile banking', 'patient registration', 'cheque-shaped'])"
                "]; "
                "assert len(bad) == 0, f'Found hardcoded terms: {bad}'"
            ),
        ],
    )

    # 11. Stage 3 unit tests pass
    unit_test_dir = _ROOT / "tests" / "unit" / "agents" / "crawler_agent"
    if unit_test_dir.exists():
        _run(
            "Stage 3 unit tests",
            [sys.executable, "-m", "pytest", str(unit_test_dir), "-v", "--tb=short", "-q"],
        )

    # 12. Stage 3 integration tests pass
    integration_dir = _ROOT / "tests" / "integration"
    stage3_test = integration_dir / "test_stage3_validation.py"
    if stage3_test.exists():
        _run(
            "Stage 3 integration tests",
            [sys.executable, "-m", "pytest", str(stage3_test), "-v", "--tb=short", "-q"],
        )

    # ── Phase 2: API Discovery + API Test Generator ──────────────────────

    # 13. APITestAgent package importable
    _check_import(
        "APITestAgent package import",
        "from stlc_platform.agents.api_test_agent import APITestAgent, OpenAPIParser, APITestGenerator, TestClassifier",
    )

    # 14. OpenAPIParser importable
    _check_import(
        "OpenAPIParser import",
        "from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser",
    )

    # 15. APITestGenerator importable
    _check_import(
        "APITestGenerator import",
        "from stlc_platform.agents.api_test_agent.test_generator import APITestGenerator",
    )

    # 16. TestClassifier importable
    _check_import(
        "TestClassifier import",
        "from stlc_platform.agents.api_test_agent.test_classifier import TestClassifier",
    )

    # 17. Enhanced API contracts (new v1.1 fields)
    _check_import(
        "Enhanced API contracts",
        (
            "from stlc_platform.core.contracts import APIEndpointArtifact, APITestArtifact; "
            "e = APIEndpointArtifact(path='/test', method='GET', operation_id='getTest', tags=['test']); "
            "t = APITestArtifact(framework='pytest_requests', language='python', filename='test.py', "
            "  content='pass', test_level='api', failure_type='app_bug')"
        ),
    )

    # 18. Jinja2 templates exist
    template_dir = _ROOT / "stlc_platform" / "agents" / "api_test_agent" / "templates"
    templates = ["pytest_requests.py.j2", "conftest.py.j2"]
    all_found = all((template_dir / t).exists() for t in templates)
    if all_found:
        _PASS += 1
        print(f"  PASS  API test templates exist ({len(templates)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing API test template files")

    # 19. OpenAPI fixture files exist
    api_fixtures = ["openapi_petstore.json", "swagger_petstore.json", "openapi_minimal.json"]
    fixtures_dir = _ROOT / "tests" / "fixtures"
    api_fixtures_ok = all((fixtures_dir / f).exists() for f in api_fixtures)
    if api_fixtures_ok:
        _PASS += 1
        print(f"  PASS  OpenAPI fixture files exist ({len(api_fixtures)} files)")
    else:
        _FAIL += 1
        print("  FAIL  Missing OpenAPI fixture files")

    # 20. APITestAgent smoke test (parse OpenAPI -> generate tests -> ast.parse)
    _check_import(
        "APITestAgent smoke test",
        (
            "import ast, json; "
            "from stlc_platform.agents.api_test_agent import APITestAgent; "
            "spec = {'openapi': '3.0.0', 'info': {'title': 'Test'}, "
            "'paths': {'/health': {'get': {'operationId': 'healthCheck', "
            "'responses': {'200': {'description': 'OK', 'content': {'application/json': "
            "{'schema': {'type': 'object', 'properties': {'status': {'type': 'string'}}}}}}}}}}}; "
            "r = APITestAgent().execute({'openapi_spec': spec}, {}); "
            "assert r.success, f'Agent failed: {r.errors}'; "
            "[ast.parse(t.content) for t in r.artifacts['test_files']]"
        ),
    )

    # 21. Generated tests have correct marks
    _check_import(
        "Generated tests have pytest marks",
        (
            "from stlc_platform.agents.api_test_agent import APITestAgent; "
            "spec = {'openapi': '3.0.0', 'info': {'title': 'T'}, "
            "'paths': {'/x': {'get': {'operationId': 'getX', "
            "'responses': {'200': {'description': 'OK'}}}}}}; "
            "r = APITestAgent().execute({'openapi_spec': spec}, {}); "
            "content = r.artifacts['test_files'][0].content; "
            "assert '@pytest.mark.api' in content; "
            "assert '# failure_type:' in content"
        ),
    )

    # 22. No hardcoded domain terms in api_test_agent/
    _run(
        "No hardcoded domain terms in API test agent",
        [
            sys.executable, "-c",
            (
                "import pathlib; "
                "agent_dir = pathlib.Path('stlc_platform/agents/api_test_agent'); "
                "bad = []; "
                "[bad.append(f'{p.name}:{i+1}: {line.strip()}') "
                " for p in agent_dir.rglob('*.py') if 'test' not in p.name "
                " for i, line in enumerate(p.read_text().splitlines()) "
                " if any(term in line.lower() for term in "
                "   ['mobile banking', 'patient registration', 'cheque-shaped'])"
                "]; "
                "assert len(bad) == 0, f'Found hardcoded terms: {bad}'"
            ),
        ],
    )

    # 23. Phase 2 unit tests pass
    api_unit_dir = _ROOT / "tests" / "unit" / "agents" / "api_test_agent"
    if api_unit_dir.exists():
        _run(
            "Phase 2 unit tests",
            [sys.executable, "-m", "pytest", str(api_unit_dir), "-v", "--tb=short", "-q"],
        )

    # 24. Phase 2 integration tests pass
    stage3p2_test = integration_dir / "test_stage3p2_validation.py"
    if stage3p2_test.exists():
        _run(
            "Phase 2 integration tests",
            [sys.executable, "-m", "pytest", str(stage3p2_test), "-v", "--tb=short", "-q"],
        )

    # ── Phase 3: Multi-Framework + Cross-Stage ───────────────────────────

    # 25. REST Assured template exists
    ra_template = _ROOT / "stlc_platform" / "agents" / "api_test_agent" / "templates" / "rest_assured.java.j2"
    if ra_template.exists():
        _PASS += 1
        print("  PASS  REST Assured template exists")
    else:
        _FAIL += 1
        print("  FAIL  REST Assured template missing")

    # 26. Karate template exists
    karate_template = _ROOT / "stlc_platform" / "agents" / "api_test_agent" / "templates" / "karate.feature.j2"
    if karate_template.exists():
        _PASS += 1
        print("  PASS  Karate template exists")
    else:
        _FAIL += 1
        print("  FAIL  Karate template missing")

    # 27. 3 frameworks in SUPPORTED_FRAMEWORKS
    _check_import(
        "3 frameworks in SUPPORTED_FRAMEWORKS",
        (
            "from stlc_platform.agents.api_test_agent.test_generator import SUPPORTED_FRAMEWORKS; "
            "assert len(SUPPORTED_FRAMEWORKS) == 3, f'Expected 3, got {len(SUPPORTED_FRAMEWORKS)}'; "
            "assert 'rest_assured' in SUPPORTED_FRAMEWORKS; "
            "assert 'karate' in SUPPORTED_FRAMEWORKS"
        ),
    )

    # 28. REST Assured smoke test (heuristic syntax check)
    _check_import(
        "REST Assured smoke test",
        (
            "from stlc_platform.agents.api_test_agent import APITestAgent; "
            "spec = {'openapi': '3.0.0', 'info': {'title': 'T'}, "
            "'paths': {'/x': {'get': {'operationId': 'getX', "
            "'responses': {'200': {'description': 'OK'}}}}}}; "
            "r = APITestAgent().execute({'openapi_spec': spec}, {'framework': 'rest_assured'}); "
            "assert r.success; "
            "c = r.artifacts['test_files'][0].content; "
            "assert 'import io.restassured' in c; "
            "assert '@Test' in c; "
            "assert 'given()' in c"
        ),
    )

    # 29. Karate smoke test (heuristic syntax check)
    _check_import(
        "Karate smoke test",
        (
            "from stlc_platform.agents.api_test_agent import APITestAgent; "
            "spec = {'openapi': '3.0.0', 'info': {'title': 'T'}, "
            "'paths': {'/x': {'get': {'operationId': 'getX', "
            "'responses': {'200': {'description': 'OK'}}}}}}; "
            "r = APITestAgent().execute({'openapi_spec': spec}, {'framework': 'karate'}); "
            "assert r.success; "
            "c = r.artifacts['test_files'][0].content; "
            "assert 'Feature:' in c; "
            "assert 'Scenario:' in c; "
            "assert 'Given path' in c"
        ),
    )

    # 30. Test pyramid E2E < 20% on petstore
    _check_import(
        "Test pyramid E2E < 20%",
        (
            "import json; "
            "from stlc_platform.agents.api_test_agent import APITestAgent; "
            "spec = json.loads(open('tests/fixtures/openapi_petstore.json').read()); "
            "r = APITestAgent().execute({'openapi_spec': spec}, {}); "
            "d = r.metadata['test_level_distribution']; "
            "total = sum(d.values()); "
            "e2e = d.get('e2e', 0); "
            "assert e2e / total < 0.2, f'E2E ratio too high: {e2e}/{total}'"
        ),
    )

    # 31. Phase 3 cross-stage integration tests pass
    stage3p3_test = integration_dir / "test_stage3p3_validation.py"
    if stage3p3_test.exists():
        _run(
            "Phase 3 integration tests",
            [sys.executable, "-m", "pytest", str(stage3p3_test), "-v", "--tb=short", "-q"],
        )

    # 32. Lint check on api_test_agent
    _run(
        "Lint check on api_test_agent",
        [sys.executable, "-m", "ruff", "check",
         "stlc_platform/agents/api_test_agent/", "--select=E,F", "--ignore=E501,E402"],
        allow_fail=True,
    )


def check_stage_4():
    """Agent Orchestration & Integration."""
    check_stage_3()
    print("\n--- Stage 4: Agent Orchestration & Integration ---")

    global _PASS, _FAIL

    # 1. Pipeline package importable
    _check_import(
        "Pipeline package import",
        "from stlc_platform.pipeline import PipelineDAG, PipelineOrchestrator, ArtifactStore, AgentRegistry, load_pipeline",
    )

    # 2. DAG module importable
    _check_import(
        "DAG module import",
        "from stlc_platform.pipeline.dag import PipelineDAG, StageNode",
    )

    # 3. Orchestrator importable
    _check_import(
        "Orchestrator import",
        "from stlc_platform.pipeline.orchestrator import PipelineOrchestrator, StageResult",
    )

    # 4. ArtifactStore importable
    _check_import(
        "ArtifactStore import",
        "from stlc_platform.pipeline.artifact_store import ArtifactStore, ArtifactResolver",
    )

    # 5. AgentRegistry default has 4+ agents
    _check_import(
        "AgentRegistry default has 4+ agents",
        (
            "from stlc_platform.pipeline.agent_registry import AgentRegistry; "
            "r = AgentRegistry.default(); "
            "caps = r.list_agents(); "
            "assert len(caps) >= 4, f'Expected 4+, got {len(caps)}'"
        ),
    )

    # 6. CLI entry point importable
    _check_import(
        "CLI entry point import",
        "from stlc_platform.cli import main",
    )

    # 7. Pipeline YAML fixture exists
    full_stlc = _ROOT / "config" / "pipelines" / "full_stlc.yaml"
    if full_stlc.exists():
        _PASS += 1
        print("  PASS  full_stlc.yaml pipeline config exists")
    else:
        _FAIL += 1
        print("  FAIL  full_stlc.yaml pipeline config missing")

    # 8. DAG cycle detection works (smoke test)
    _check_import(
        "DAG cycle detection smoke test",
        (
            "from stlc_platform.pipeline.dag import PipelineDAG, StageNode; "
            "dag = PipelineDAG([StageNode(stage_id='a', agent_id='x', depends_on=['b']), "
            "StageNode(stage_id='b', agent_id='x', depends_on=['a'])]); "
            "errors = dag.validate(); "
            "assert len(errors) == 1; "
            "assert 'cycle' in errors[0].lower()"
        ),
    )

    # 9. AgentResult has duration_seconds field
    _check_import(
        "AgentResult has duration_seconds",
        (
            "from stlc_platform.core.base_agent import AgentResult; "
            "r = AgentResult(success=True, duration_seconds=1.5, tokens_used=100); "
            "assert r.duration_seconds == 1.5; "
            "assert r.tokens_used == 100"
        ),
    )

    # 10. PipelineRunArtifact has stages_skipped field
    _check_import(
        "PipelineRunArtifact has stages_skipped",
        (
            "from stlc_platform.core.contracts import PipelineRunArtifact; "
            "p = PipelineRunArtifact(run_id='t', pipeline_name='t', stages_skipped=['x']); "
            "assert p.stages_skipped == ['x']; "
            "assert p.schema_version == '1.1'"
        ),
    )

    # 11. Stage 4 unit tests pass
    unit_dir = _ROOT / "tests" / "unit" / "pipeline"
    if unit_dir.exists():
        _run(
            "Stage 4 unit tests",
            [sys.executable, "-m", "pytest", str(unit_dir), "-v", "--tb=short", "-q"],
        )

    # 12. Stage 4 Phase 1 integration tests pass
    integration_dir = _ROOT / "tests" / "integration"
    stage4_test = integration_dir / "test_stage4p1_validation.py"
    if stage4_test.exists():
        _run(
            "Stage 4 Phase 1 integration tests",
            [sys.executable, "-m", "pytest", str(stage4_test), "-v", "--tb=short", "-q"],
        )

    # ── Phase 2 checks ───────────────────────────────────────────────────

    # 13. SkillLoader importable
    _check_import(
        "SkillLoader import",
        "from stlc_platform.pipeline.skill_loader import SkillLoader",
    )

    # 14. Common skill files exist
    skills_dir = _ROOT / "config" / "skills" / "common"
    skill_files_exist = (
        skills_dir.is_dir()
        and (skills_dir / "coding_standards.yaml").exists()
        and (skills_dir / "test_design_principles.yaml").exists()
    )
    if skill_files_exist:
        _PASS += 1
        print("  PASS  Common skill files exist")
    else:
        _FAIL += 1
        print("  FAIL  Common skill files missing")

    # 15. Agents declare required_skills
    _check_import(
        "Agents declare required_skills",
        (
            "from stlc_platform.pipeline.agent_registry import AgentRegistry; "
            "r = AgentRegistry.default(); "
            "caps = r.list_agents(); "
            "assert all(len(c.required_skills) >= 1 for c in caps), "
            "'All agents should declare at least 1 required_skill'"
        ),
    )

    # 16. ModelRouter importable
    _check_import(
        "ModelRouter import",
        "from stlc_platform.pipeline.model_router import ModelRouter, ModelTier",
    )

    # 17. Router selects tier smoke test
    _check_import(
        "Router selects tier smoke test",
        (
            "from stlc_platform.pipeline.model_router import ModelRouter; "
            "from stlc_platform.core.base_agent import AgentCapabilities; "
            "r = ModelRouter.default(); "
            "c = AgentCapabilities(agent_id='t', agent_version='1.0', default_model_tier='standard'); "
            "tier = r.select_tier(c); "
            "assert tier.name == 'standard'"
        ),
    )

    # 18. ProfileLoader importable
    _check_import(
        "ProfileLoader import",
        "from stlc_platform.pipeline.profile_loader import ProfileLoader, ExecutionProfile",
    )

    # 19. Profile YAML files exist
    profiles_dir = _ROOT / "config" / "profiles"
    profiles_exist = (
        profiles_dir.is_dir()
        and (profiles_dir / "smoke.yaml").exists()
        and (profiles_dir / "regression.yaml").exists()
        and (profiles_dir / "targeted.yaml").exists()
    )
    if profiles_exist:
        _PASS += 1
        print("  PASS  Profile YAML files exist (smoke, regression, targeted)")
    else:
        _FAIL += 1
        print("  FAIL  Profile YAML files missing")

    # 20. Config profile merge smoke test
    _check_import(
        "Config profile merge smoke test",
        (
            "from stlc_platform.core.config_loader import deep_merge, load_config_yaml; "
            "base = {'a': {'b': 1}}; "
            "overlay = {'a': {'c': 2}}; "
            "result = deep_merge(base, overlay); "
            "assert result == {'a': {'b': 1, 'c': 2}}; "
            "cfg = load_config_yaml(profile='web'); "
            "assert cfg['crawler']['max_depth'] == 5"
        ),
    )

    # 21. AgentFeedbackArtifact importable
    _check_import(
        "AgentFeedbackArtifact import",
        (
            "from stlc_platform.core.contracts import AgentFeedbackArtifact; "
            "f = AgentFeedbackArtifact(agent_id='test', message='hi'); "
            "assert f.schema_version == '1.0'"
        ),
    )

    # 22. FeedbackStore importable
    _check_import(
        "FeedbackStore import",
        "from stlc_platform.pipeline.feedback_store import FeedbackStore",
    )

    # 23. GitHub Actions workflow exists
    gh_workflow = _ROOT / ".github" / "workflows" / "stlc_ci.yml"
    if gh_workflow.exists():
        _PASS += 1
        print("  PASS  GitHub Actions workflow exists")
    else:
        _FAIL += 1
        print("  FAIL  GitHub Actions workflow missing")

    # 24. CLI --profile option recognized
    _check_import(
        "CLI --profile option recognized",
        (
            "from click.testing import CliRunner; "
            "from stlc_platform.cli import main; "
            "runner = CliRunner(); "
            "result = runner.invoke(main, ['run', '--help']); "
            "assert '--profile' in result.output"
        ),
    )

    # 25. Stage 4 Phase 2 unit tests pass
    _run(
        "Stage 4 Phase 2 unit tests",
        [
            sys.executable, "-m", "pytest",
            str(_ROOT / "tests" / "unit" / "pipeline" / "test_skill_loader.py"),
            str(_ROOT / "tests" / "unit" / "pipeline" / "test_profile_loader.py"),
            str(_ROOT / "tests" / "unit" / "pipeline" / "test_config_profiles.py"),
            str(_ROOT / "tests" / "unit" / "pipeline" / "test_model_router.py"),
            str(_ROOT / "tests" / "unit" / "pipeline" / "test_feedback_store.py"),
            "-v", "--tb=short", "-q",
        ],
    )

    # 26. Stage 4 Phase 2 integration tests pass
    stage4p2_test = integration_dir / "test_stage4p2_validation.py"
    if stage4p2_test.exists():
        _run(
            "Stage 4 Phase 2 integration tests",
            [sys.executable, "-m", "pytest", str(stage4p2_test), "-v", "--tb=short", "-q"],
        )


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
