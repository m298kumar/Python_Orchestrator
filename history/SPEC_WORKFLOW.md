# STLC Automation Platform — Specification Workflow Model

> Version: 1.1
> Created: 2026-03-15
> Updated: 2026-03-20
> Status: DRAFT
>
> Changelog v1.1: Incorporated community insights from industry practitioners
> (RAG retrieval, test pyramid guardrails, failure classification, domain
> knowledge skill files, tiered model routing, execution profiles, CI hooks).

---

## Workflow Principles

1. **Sequential Gating** — Each stage has entry criteria, deliverables, and exit criteria. A stage cannot begin until the previous stage's exit criteria are met.
2. **Backward Compatibility** — Improving an earlier stage must not break downstream stages. Agents communicate through versioned artifact contracts.
3. **Validation at Every Gate** — After each stage: run unit tests, integration tests, linting, and type checks. All must pass before proceeding.
4. **Incremental Deployment** — Each completed stage produces a usable, standalone capability.
5. **Contract-Driven** — Agents exchange data via defined schemas (JSON/YAML). Changing a schema requires a version bump and backward-compatible migration.
6. **Test Pyramid Integrity** — AI-generated tests must respect the test pyramid: most checks stay at unit/API levels, E2E tests focus on real business journeys, not tiny validations. The goal is coverage that ships faster, not more tests.
7. **Institutional Knowledge Over Instructions** — Each agent loads domain-specific context (skill files, data catalogs, conventions) at runtime rather than relying purely on generic prompts. This transforms a generic agent into a domain-aware specialist.
8. **Failure Classification** — When tests fail, the system classifies failures as app bugs vs test bugs and refuses to mask broken product behavior by adjusting the test.

---

## Stage Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Stage 0: Foundation & Project Restructure                      │
│  ─────────────────────────────────────────                      │
│  Restructure codebase, add CI validation, define contracts      │
├─────────────────────────────────────────────────────────────────┤
│  Stage 1: Domain-Agnostic Test Generation Engine                │
│  ───────────────────────────────────────────────                │
│  Remove hardcoded domain logic, pluggable LLM, tech-stack aware │
├─────────────────────────────────────────────────────────────────┤
│  Stage 2: BDD Automation Code Generator Agent                   │
│  ────────────────────────────────────────────                   │
│  Feature files, step definitions, project scaffolding           │
├─────────────────────────────────────────────────────────────────┤
│  Stage 3: Web Crawler & API Test Generator Agents               │
│  ────────────────────────────────────────────────               │
│  Crawl web apps, discover APIs, generate API tests              │
├─────────────────────────────────────────────────────────────────┤
│  Stage 4: Agent Orchestration & Integration Layer               │
│  ────────────────────────────────────────────────               │
│  Pipeline DAG, inter-agent communication, unified config        │
├─────────────────────────────────────────────────────────────────┤
│  Stage 5: Frontend UI                                           │
│  ────────────────────────────────────────────────               │
│  Web dashboard, real-time pipeline control, test case browser   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stage 0: Foundation & Project Restructure

### Purpose
Establish the project structure, testing infrastructure, CI validation pipeline, and artifact contracts that all subsequent stages build upon.

### Entry Criteria
- Existing v10 orchestrator code is functional
- Git repository initialized

### Tasks

#### 0.1 — Project Structure Reorganization
Restructure from flat files into a modular package layout:
```
Python_Orchestrator/
├── stlc_platform/                    # Main package
│   ├── __init__.py
│   ├── core/                         # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── base_agent.py             # BaseAgent ABC
│   │   ├── contracts.py              # Pydantic models for all artifacts
│   │   ├── config_loader.py          # Unified config from stlc_config.yaml
│   │   ├── llm/                      # LLM abstraction layer
│   │   │   ├── __init__.py
│   │   │   ├── base_client.py        # BaseLLMClient ABC
│   │   │   └── ollama_client.py      # Current llm_client.py refactored
│   │   ├── storage/                  # ChromaDB abstraction
│   │   │   ├── __init__.py
│   │   │   └── chroma_store.py       # Current chroma_store.py refactored
│   │   └── utils.py                  # Shared utilities
│   │
│   ├── agents/                       # All agents live here
│   │   ├── __init__.py
│   │   ├── requirements_agent/       # Stage 1: requirement parsing + TC gen
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── reader.py             # Current requirements_reader.py
│   │   │   ├── generator.py          # Current test_generator.py
│   │   │   └── prompts/              # Externalized prompt templates
│   │   │       ├── system.j2
│   │   │       └── templates/
│   │   │
│   │   ├── bdd_agent/                # Stage 2: BDD code generation
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── feature_generator.py
│   │   │   ├── step_def_generator.py
│   │   │   ├── scaffolder.py
│   │   │   └── templates/            # Jinja2 templates per language
│   │   │
│   │   ├── crawler_agent/            # Stage 3A: web crawling
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   ├── crawler.py
│   │   │   ├── page_analyzer.py
│   │   │   └── pom_generator.py
│   │   │
│   │   └── api_test_agent/           # Stage 3B: API test generation
│   │       ├── __init__.py
│   │       ├── agent.py
│   │       ├── api_discoverer.py
│   │       ├── test_generator.py
│   │       └── templates/
│   │
│   ├── pipeline/                     # Stage 4: orchestration
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # DAG-based pipeline runner
│   │   ├── pipeline_config.py
│   │   └── artifact_store.py
│   │
│   ├── exporters/                    # Output formatters
│   │   ├── __init__.py
│   │   └── exporters.py
│   │
│   └── api/                          # Stage 5: FastAPI backend
│       ├── __init__.py
│       ├── main.py
│       ├── routes/
│       └── websocket.py
│
├── tests/                            # All tests mirror src structure
│   ├── unit/
│   │   ├── core/
│   │   ├── agents/
│   │   │   ├── requirements_agent/
│   │   │   ├── bdd_agent/
│   │   │   ├── crawler_agent/
│   │   │   └── api_test_agent/
│   │   └── pipeline/
│   ├── integration/
│   │   ├── test_stage1_validation.py
│   │   ├── test_stage2_validation.py
│   │   ├── test_stage3_validation.py
│   │   └── test_pipeline_e2e.py
│   └── conftest.py                   # Shared fixtures
│
├── config/
│   ├── stlc_config.yaml              # Master config file
│   ├── stlc_config.schema.json       # JSON Schema for validation
│   ├── profiles/                     # Execution profiles (Stage 4)
│   │   ├── smoke.yaml
│   │   ├── targeted.yaml
│   │   └── regression.yaml
│   └── skills/                       # Domain knowledge skill files (Stage 4)
│       ├── common/
│       │   ├── coding_standards.yaml
│       │   └── test_design_principles.yaml
│       └── {domain}/                 # User-created per domain
│           ├── data_catalog.yaml
│           └── locator_conventions.yaml
│
├── frontend/                         # Stage 5: React app
│
├── history/                          # Conversation & decision log
│   ├── conversation_log.md
│   └── SPEC_WORKFLOW.md              # This file
│
├── scripts/
│   ├── validate_stage.py             # Validation gate runner
│   └── migrate.py                    # Data/config migration helper
│
├── pyproject.toml                    # Project metadata, deps, tool config
├── README.md
└── .github/
    └── workflows/
        └── ci.yml                    # CI pipeline
```

#### 0.2 — Artifact Contracts (Pydantic Models)
Define the data schemas that flow between agents in `core/contracts.py`:

```
RequirementArtifact       — output of requirements parsing
TestCaseArtifact          — output of test case generation (includes test_level field)
FeatureFileArtifact       — output of BDD agent
StepDefinitionArtifact    — output of BDD agent
SiteModelArtifact         — output of web crawler (includes discrepancies)
APIModelArtifact          — output of API discovery
APITestArtifact           — output of API test generator (includes failure_type metadata)
DiscrepancyReportArtifact — output of discrepancy detector (Stage 3, pre-test-gen gate)
PipelineRunArtifact       — metadata about a pipeline execution
AgentFeedbackArtifact     — stored corrections/learnings for feedback persistence (Stage 4)
```

Each contract is versioned (`schema_version: "1.0"`). Consumers validate on load.

#### 0.3 — Validation Gate Script
`scripts/validate_stage.py` — runs for each stage:
1. `pytest tests/unit/` — all unit tests pass
2. `pytest tests/integration/test_stage{N}_validation.py` — stage-specific integration tests pass
3. `ruff check .` (or `flake8`) — no lint errors
4. `mypy stlc_platform/` — type checks pass (can be gradual)
5. Contract validation — all artifact schemas are valid JSON Schema
6. Import smoke test — `python -c "from stlc_platform.agents.X import Agent"` succeeds

#### 0.4 — Migrate Existing Code
- Move current `.py` files into the new structure (no logic changes yet)
- Ensure `python -m stlc_platform.orchestrator` still works identically to `python orchestrator.py`
- All existing Behave tests still pass

### Exit Criteria
- [ ] New project structure in place
- [ ] All existing functionality works unchanged via new entry points
- [ ] `validate_stage.py --stage 0` passes (structure, imports, existing tests)
- [ ] Artifact contracts defined and importable
- [ ] Git commit with tag `stage-0-complete`

---

## Stage 1: Domain-Agnostic Test Generation Engine

### Purpose
Remove all hardcoded domain-specific logic. Make the test generator work for any software domain, any tech stack, and any LLM provider.

### Entry Criteria
- Stage 0 exit criteria met

### Tasks

#### 1.1 — LLM Abstraction Layer
- `core/llm/base_client.py`: `BaseLLMClient` ABC with `generate(prompt, schema) -> dict`
- `core/llm/ollama_client.py`: refactored from current `llm_client.py`
- `core/llm/openai_client.py`: OpenAI-compatible client (GPT-4, etc.)
- `core/llm/anthropic_client.py`: Claude API client
- Factory: `create_llm_client(config) -> BaseLLMClient`
- Config-driven selection via `stlc_config.yaml`

#### 1.2 — Dynamic AC Type Classification
- Replace keyword-based `_classify_ac()` with a two-tier approach:
  - **Fast path**: regex/keyword classifier (current logic, generalized)
  - **LLM path**: if fast path confidence is low, use LLM to classify
- Make AC types configurable in `stlc_config.yaml`:
  ```yaml
  ac_types:
    - name: eligibility
      description: "Rules about who/what qualifies"
      keywords: [eligible, qualify, condition, criteria]
    - name: ui_behaviour
      description: "User interface interactions and visual feedback"
      keywords: [display, show, click, navigate, button]
    # ... user can add custom types
  ```
- Domain auto-detection: analyze requirements text to infer domain and inject context

#### 1.3 — Externalized Prompt Templates
- Move all prompt strings from `test_generator.py` into Jinja2 templates under `agents/requirements_agent/prompts/`
- Template files:
  - `system_prompt.j2` — domain-aware system prompt
  - `user_prompt.j2` — main generation prompt
  - `type_hints/{ac_type}.j2` — per-type hint blocks
  - `few_shot_block.j2` — few-shot example formatting
- Users can override any template by placing a file in `config/prompt_overrides/`

#### 1.4 — Tech Stack Awareness
- Config section:
  ```yaml
  tech_stack:
    platform: web          # web | mobile | api | desktop
    frontend: react        # react | angular | vue | flutter | native
    backend: rest          # rest | graphql | grpc | soap
    database: postgres     # postgres | mysql | mongo | dynamodb
    auth: jwt              # jwt | oauth2 | session | saml
  ```
- Tech stack context injected into prompts:
  - `web` → "click", "navigate", "page loads"
  - `mobile` → "tap", "swipe", "screen appears"
  - `api` → "send request", "receive response", "status code"
- Platform-specific test type generation:
  - `web/mobile` → UI + functional tests
  - `api` → contract + integration + security tests

#### 1.5 — Improved Sanitiser
- Make sanitiser rules configurable (not hardcoded)
- Remove `_COMPONENT_SUFFIX_MAP` — use LLM + domain_vocab only
- Add pluggable post-processors: `List[Callable[[TestCase], TestCase]]`

### Validation Gate
```bash
python scripts/validate_stage.py --stage 1
```
Tests:
- Unit: LLM abstraction returns correct types, all providers implement interface
- Unit: AC classifier produces valid types for diverse domain inputs
- Unit: Prompt templates render correctly with all variable combinations
- Unit: Tech stack config changes prompt output appropriately
- Integration: Generate test cases for 3 different domains (e-commerce, healthcare, banking) with same code, no config changes beyond `stlc_config.yaml`
- Integration: Generate test cases using at least 2 different LLM providers
- Regression: Existing sample requirements produce equivalent-quality output

### Exit Criteria
- [ ] No hardcoded domain terms in generator code
- [ ] 3+ domain configs tested, all produce valid output
- [ ] 2+ LLM providers working
- [ ] All prompt text lives in template files, not Python strings
- [ ] `validate_stage.py --stage 1` passes
- [ ] Git commit with tag `stage-1-complete`

---

## Stage 2: BDD Automation Code Generator Agent

### Purpose
Convert generated test cases into executable BDD automation projects with feature files, step definitions, and project scaffolding.

### Entry Criteria
- Stage 1 exit criteria met
- `TestCaseArtifact` contract finalized

### Tasks

#### 2.1 — Feature File Generator
- Input: `List[TestCaseArtifact]` (from Stage 1 output)
- Grouping: one `.feature` file per requirement
- Output Gherkin:
  - `Feature:` from requirement title/description
  - `Background:` extracted from common preconditions across scenarios
  - `Scenario:` with Given/When/Then from test case GWT fields
  - `Scenario Outline:` with `Examples:` table when parameterizable
  - Tags: `@REQ-001`, `@positive`, `@high_priority`, `@ui_behaviour`
- Handle special characters, long lines, multi-line steps

#### 2.2 — Step Definition Generator
- Parse all unique step patterns from generated feature files
- Group similar steps and parameterize: `"user enters {value} in {field}"` → one step def
- Generate skeleton per language/framework:
  | Language | Framework | Output Pattern |
  |----------|-----------|---------------|
  | Python | Behave | `@given('...')` decorator, `def step_impl(context):` |
  | Python | Pytest-BDD | `@scenario`, `@given`, `@when`, `@then` functions |
  | Java | Cucumber | `@Given("...")` annotation, method body |
  | JavaScript | Cucumber.js | `Given('...', async function() {})` |
- Each step body: `raise NotImplementedError("TODO: implement")` or language equivalent
- Import statements for chosen automation library (Selenium/Playwright/etc.)

#### 2.3 — Page Object Model Stubs
- If platform is `web` or `mobile`:
  - Extract page/screen names from test case components
  - Generate POM class stubs with:
    - Locator placeholders: `LOGIN_BUTTON = "css=TODO"`
    - Action methods matching test steps: `def click_login(self):`
    - Base page class with common methods (navigate, wait, screenshot)

#### 2.4 — Project Scaffolder
- Generate complete runnable project:
  - Directory structure per framework conventions
  - Dependency file: `requirements.txt` / `pom.xml` / `package.json`
  - Config file: browser settings, base URL, timeouts
  - Runner config: `behave.ini` / `cucumber.yml` / `jest.config.js`
  - README with setup and run instructions
- Output as directory or downloadable ZIP

### Validation Gate
```bash
python scripts/validate_stage.py --stage 2
```
Tests:
- Unit: Feature file generator produces valid Gherkin (parse with `gherkin-official` library)
- Unit: Step definitions have correct syntax per language
- Unit: No duplicate step definitions generated
- Unit: Scenario Outline examples table is well-formed
- Integration: Generate BDD project from sample test cases, verify:
  - Feature files are parseable
  - Step defs import without errors (Python: `import`, Java: compile check)
  - Project structure matches framework conventions
- Integration: Test with 3 language/framework combinations

### Exit Criteria
- [ ] Feature files generated and Gherkin-valid for all test cases
- [ ] Step definitions compile/import in at least 3 language/framework combos
- [ ] POM stubs generated for web/mobile platforms
- [ ] Project scaffolding produces runnable (with TODOs) project
- [ ] `validate_stage.py --stage 2` passes
- [ ] Git commit with tag `stage-2-complete`

---

## Stage 3: Web Crawler & API Test Generator Agents

### Purpose
Auto-discover application structure via web crawling and generate targeted API tests. This stage also introduces discrepancy detection (comparing live app state against requirements) and test-level classification to maintain test pyramid integrity.

### Entry Criteria
- Stage 1 exit criteria met (Stage 2 can run in parallel with Stage 3)

### Design Principles (from Industry Learnings)
1. **Start from Acceptance Criteria, not exploration** — AC from requirements is the baseline. The crawler validates against AC and avoids duplicating what unit/API tests already cover.
2. **Discrepancy-first reporting** — Before generating any test code, the crawler compares live app findings against requirement artifacts and surfaces mismatches. Show-stoppers get flagged; non-blockers get documented atop the test plan.
3. **Test level tagging** — Every generated test artifact gets a `test_level` field (unit | api | integration | e2e) to preserve the test pyramid. E2E tests target business journeys only; smaller validations stay at API/unit level.
4. **RAG-based context retrieval** — Crawled page structures, API schemas, and locator patterns are embedded into ChromaDB for contextual retrieval rather than dumping everything into agent prompts. This reduces token usage and improves latency.

### Tasks

#### 3.1 — Web Crawler Agent
- **Engine**: Playwright (headless Chromium)
- **Capabilities**:
  - BFS crawl from base URL with configurable max depth
  - Extract per page: URL, title, forms, buttons, links, inputs, images, text content
  - Capture all XHR/Fetch network requests (method, URL, headers, body, response status)
  - Screenshot each page (optional, for visual regression baseline)
  - Handle SPAs: wait for network idle, detect client-side routing
  - Authentication: login flow support (form-based, OAuth redirect)
  - **Discrepancy detection**: compare crawled elements/flows against RequirementArtifacts — flag missing fields, unexpected behavior, features not yet implemented
- **Output**: `SiteModelArtifact` — JSON containing:
  ```json
  {
    "base_url": "https://app.example.com",
    "pages": [
      {
        "url": "/login",
        "title": "Login",
        "elements": [
          {"type": "input", "name": "username", "selector": "#username"},
          {"type": "button", "text": "Sign In", "selector": "[data-testid='login-btn']"}
        ],
        "forms": [...],
        "api_calls": [
          {"method": "POST", "url": "/api/auth/login", "request_body": {...}}
        ]
      }
    ],
    "navigation_graph": {"adjacency": {...}},
    "discrepancies": [
      {
        "type": "missing_element",
        "requirement_id": "REQ-001",
        "expected": "Password reset link on login page",
        "actual": "Not found in crawled DOM",
        "severity": "show_stopper"
      }
    ]
  }
  ```
- **POM Auto-Generator**: use crawled selectors to pre-fill POM locators (feeds into Stage 2 stubs)
- **ChromaDB Embedding**: crawled page structures and element metadata are embedded into ChromaDB so downstream agents can retrieve only relevant context per requirement

#### 3.2 — API Discovery Agent
- **Input sources** (priority order):
  1. OpenAPI/Swagger spec file (if user provides)
  2. Crawled network requests (from 3.1)
  3. HAR file import (if user provides)
- **Output**: `APIModelArtifact`:
  ```json
  {
    "endpoints": [
      {
        "path": "/api/users/{id}",
        "method": "GET",
        "path_params": [{"name": "id", "type": "integer"}],
        "query_params": [],
        "request_body_schema": null,
        "response_schema": {"type": "object", "properties": {...}},
        "auth_required": true,
        "auth_type": "bearer",
        "example_request": {...},
        "example_response": {...}
      }
    ]
  }
  ```
- Handle: REST, GraphQL (introspection query), gRPC (proto file parsing)

#### 3.3 — API Test Generator Agent
- Input: `APIModelArtifact`
- Framework support:
  | Framework | Language | Test Style |
  |-----------|----------|-----------|
  | Pytest + Requests | Python | `def test_get_user():` |
  | REST Assured | Java | `given().when().get().then()` |
  | Karate | Karate DSL | `Scenario: ...` `.feature` files |
  | Supertest | JavaScript | `describe/it` blocks |
- Test types per endpoint:
  - **Happy path**: valid input → expected response + status
  - **Auth tests**: missing token → 401, invalid token → 403
  - **Validation tests**: missing required fields → 400, wrong types → 422
  - **Boundary tests**: max length strings, zero/negative IDs, empty arrays
  - **CRUD sequence**: POST → GET → PUT → DELETE (for resource endpoints)
  - **Schema validation**: response matches defined schema
- Generate test data factories (Faker-based for realistic data)
- Generate environment config (base URL, auth tokens, test user credentials placeholder)
- **Test level classification**: each generated test is tagged with `test_level`:
  - `api` — contract validation, auth checks, field validation (bulk of generated tests)
  - `integration` — multi-endpoint CRUD sequences
  - `e2e` — full business journeys only (login -> action -> verify -> logout)
- **Failure classification metadata**: test templates include structured `failure_type` field:
  - `app_bug` — the application returned unexpected behavior per spec
  - `test_bug` — the test itself has incorrect assertions or data
  - `env_issue` — infrastructure/timeout/connectivity failure
  This prevents masking real product bugs by adjusting tests.

#### 3.4 — Cross-Layer Integration
- Crawler's `api_calls` per page -> link UI actions to API endpoints
- Generate tests that validate both UI state AND API response for same action
- Site model feeds real selectors into Stage 2 POM classes

#### 3.5 — Discrepancy Report Generator
- **Input**: `SiteModelArtifact` + `List[RequirementArtifact]`
- **Purpose**: Before any test code is generated, compare crawled reality against requirements and produce a discrepancy report
- **Output**: `DiscrepancyReportArtifact`:
  ```json
  {
    "summary": {"total": 12, "show_stoppers": 2, "warnings": 7, "info": 3},
    "items": [
      {
        "id": "DISC-001",
        "requirement_id": "REQ-003",
        "severity": "show_stopper",
        "category": "missing_feature",
        "expected": "User can reset password from login page",
        "actual": "No password reset link found in crawled login page",
        "recommendation": "Block test generation for REQ-003 until feature is implemented"
      }
    ],
    "gate_decision": "proceed_with_warnings"
  }
  ```
- **Gate behavior**: if any `show_stopper` discrepancies exist, the pipeline pauses and surfaces them to the user before generating tests for affected requirements. This prevents generating tests for features that don't exist yet.

### Validation Gate
```bash
python scripts/validate_stage.py --stage 3
```
Tests:
- Unit: Crawler extracts elements correctly from known HTML fixtures
- Unit: API model parser handles OpenAPI 3.0 and Swagger 2.0 specs
- Unit: Generated API tests have correct syntax per framework
- Unit: Discrepancy report correctly identifies missing elements vs requirements
- Unit: Test level classification assigns correct levels (api/integration/e2e)
- Unit: Failure classification metadata is present in all generated test templates
- Integration: Crawl a local test app (spin up Flask/Express fixture), verify site model completeness
- Integration: Generate API tests from a public OpenAPI spec, verify tests are syntactically valid
- Integration: REST Assured, Karate, and Pytest+Requests outputs all validate
- Integration: Discrepancy report surfaces known missing features when crawling against requirements
- Integration: ChromaDB stores and retrieves crawled page context for downstream agents
- Integration: Test pyramid distribution check — E2E tests < 20% of total generated tests

### Exit Criteria
- [ ] Crawler produces valid `SiteModelArtifact` for test apps
- [ ] API discovery works from OpenAPI spec and from crawled requests
- [ ] API tests generated for 3+ frameworks, all syntactically valid
- [ ] Cross-layer linking produces POM classes with real selectors
- [ ] Discrepancy report generated before test code, show-stoppers block generation
- [ ] All generated tests have `test_level` tag (test pyramid preserved)
- [ ] Failure classification metadata present in test templates
- [ ] Crawled artifacts embedded in ChromaDB for RAG retrieval
- [ ] `validate_stage.py --stage 3` passes
- [ ] Git commit with tag `stage-3-complete`

---

## Stage 4: Agent Orchestration & Integration Layer

### Purpose
Wire all agents into a unified pipeline with DAG-based execution, shared state, a single configuration file, intelligent model routing, and domain knowledge injection. The orchestrator is the "brain" that decides which agent runs when, with what context, and using which model tier.

### Entry Criteria
- Stages 1, 2, and 3 exit criteria all met

### Design Principles (from Industry Learnings)
1. **Domain knowledge skill files** — Each agent loads domain-specific context files (data catalogs, permission matrices, locator conventions, coding standards) at runtime. Agents get only the context they need rather than everything.
2. **Tiered model routing** — Simple tasks (step definition generation, file scaffolding) use lighter/local models (Ollama). Complex tasks (requirement analysis, discrepancy detection) use more capable models (Claude, GPT-4). A task complexity router selects the appropriate tier.
3. **Execution profiles** — Support scope-based test execution: smoke (critical paths only), targeted (specific requirements), full regression (everything). Scope and risk drive what gets run.
4. **Memory and feedback persistence** — Agent corrections persist across sessions via ChromaDB. When a user corrects an agent (e.g., "don't hardcode IDs"), that feedback is stored and auto-loaded in future runs.
5. **CI/CD integration** — Pipeline can be triggered from CI systems (GitHub Actions, Jenkins, GitLab CI) via CLI or webhook.

### Tasks

#### 4.1 — BaseAgent Interface
```python
class BaseAgent(ABC):
    agent_id: str
    version: str

    @abstractmethod
    async def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult

    @abstractmethod
    async def execute(self, artifacts: Dict[str, Any], config: AgentConfig) -> AgentResult

    @abstractmethod
    async def get_capabilities(self) -> AgentCapabilities
```
- All Stage 1/2/3 agents refactored to implement this interface
- `AgentResult` wraps output artifacts + metadata (duration, tokens used, errors)

#### 4.2 — Pipeline DAG Orchestrator
- Define pipelines in YAML:
  ```yaml
  pipeline: full_stlc
  stages:
    - id: parse_requirements
      agent: requirements_agent
      input: {requirements_file: "$config.requirements_file"}
      output: [parsed_requirements]

    - id: generate_test_cases
      agent: test_case_generator
      depends_on: [parse_requirements]
      input: {requirements: "$parse_requirements.parsed_requirements"}
      output: [test_cases]

    - id: crawl_application
      agent: crawler_agent
      input: {base_url: "$config.app_url"}
      output: [site_model]
      # Runs in parallel with generate_test_cases

    - id: generate_bdd_code
      agent: bdd_agent
      depends_on: [generate_test_cases, crawl_application]
      input:
        test_cases: "$generate_test_cases.test_cases"
        site_model: "$crawl_application.site_model"
      output: [feature_files, step_definitions, project]

    - id: discover_apis
      agent: api_discovery_agent
      depends_on: [crawl_application]
      input: {site_model: "$crawl_application.site_model"}
      output: [api_model]

    - id: generate_api_tests
      agent: api_test_agent
      depends_on: [discover_apis]
      input: {api_model: "$discover_apis.api_model"}
      output: [api_tests]

    - id: assemble_project
      agent: project_assembler
      depends_on: [generate_bdd_code, generate_api_tests]
      input:
        bdd_project: "$generate_bdd_code.project"
        api_tests: "$generate_api_tests.api_tests"
      output: [final_project]
  ```
- DAG resolver: topological sort, parallel execution of independent stages
- Artifact store: persist intermediate results, resume from any stage
- Error handling: retry policy per agent, graceful degradation (skip optional stages)

#### 4.3 — Unified Configuration
- Single `config/stlc_config.yaml` drives everything (all agent configs merged)
- JSON Schema validation on load
- Environment variable overrides: `STLC_LLM_MODEL=gpt-4o` overrides `llm.model`
- Profile system: `stlc_config.web.yaml`, `stlc_config.api.yaml` (merged with base)

#### 4.4 — CLI Entry Point
```bash
# Full pipeline
stlc run --config config/stlc_config.yaml

# Single agent
stlc run --agent bdd_agent --input test_cases.json

# Resume from stage
stlc run --resume-from generate_bdd_code

# Validate only
stlc validate --stage 2

# List agents
stlc agents list
```

#### 4.5 — Domain Knowledge Skill Files
- Each agent can load one or more **skill files** from `config/skills/`:
  ```
  config/skills/
  ├── ecommerce/
  │   ├── data_catalog.yaml      # seed data, test accounts, product IDs
  │   ├── permission_matrix.yaml # which roles see which features
  │   └── locator_conventions.yaml # naming patterns for CSS selectors
  ├── healthcare/
  │   ├── data_catalog.yaml
  │   └── compliance_rules.yaml  # HIPAA constraints for test data
  └── common/
      ├── coding_standards.yaml  # POM patterns, naming conventions
      └── test_design_principles.yaml
  ```
- Skill files are loaded via `config_loader.py` and injected into agent prompts at runtime
- Each agent declares which skill categories it needs via `get_capabilities().required_skills`
- Users can create custom skill files for their domain without modifying agent code

#### 4.6 — Tiered Model Router
- **Purpose**: Route tasks to the appropriate LLM based on complexity
- **Configuration**:
  ```yaml
  model_routing:
    tiers:
      - name: lightweight
        provider: ollama
        model: llama3.2
        use_for: [step_definition_gen, scaffolding, file_formatting]
      - name: standard
        provider: ollama
        model: deepseek-coder-v2
        use_for: [test_case_gen, bdd_generation, api_test_gen]
      - name: advanced
        provider: anthropic
        model: claude-sonnet
        use_for: [requirement_analysis, discrepancy_detection, failure_triage]
    fallback: standard
  ```
- Each agent declares its default tier; the orchestrator can override based on input complexity
- **Complexity heuristic**: input token count, number of requirements, domain novelty score
- Cost tracking: log tokens used per tier per pipeline run

#### 4.7 — Execution Profiles
- Support scope-based test execution to avoid generating/running everything:
  ```yaml
  execution_profiles:
    smoke:
      description: "Critical path only"
      filter: {priority: [critical, high], test_level: [e2e]}
      max_tests: 20
    targeted:
      description: "Specific requirements"
      filter: {requirement_ids: ["REQ-001", "REQ-005"]}
    regression:
      description: "Full suite"
      filter: {}  # no filtering, run everything
    risk_based:
      description: "Risk-weighted selection"
      filter: {risk_score_min: 0.7}
  ```
- Profiles are selected at pipeline invocation: `stlc run --profile smoke`
- Agents respect the profile filter when generating/selecting tests

#### 4.8 — CI/CD Integration Hook
- **CLI trigger**: `stlc run --ci` — machine-readable output (JSON), non-interactive, exit codes for CI
- **Webhook endpoint** (via Stage 5 API): POST `/api/pipeline/trigger` with config payload
- **GitHub Actions example**:
  ```yaml
  - name: Run STLC Pipeline
    run: stlc run --profile smoke --ci --output results/
  - name: Upload Test Artifacts
    uses: actions/upload-artifact@v4
    with:
      name: stlc-results
      path: results/
  ```
- **Pipeline result artifact**: JSON summary with pass/fail counts, discrepancy report, generated file manifest

### Validation Gate
```bash
python scripts/validate_stage.py --stage 4
```
Tests:
- Unit: DAG resolver correctly orders stages, detects cycles
- Unit: Artifact references (`$stage.output`) resolve correctly
- Unit: Config loader merges profiles and env overrides correctly
- Unit: Skill file loader discovers and injects correct files per agent
- Unit: Model router selects correct tier based on task type and complexity
- Unit: Execution profile filters tests correctly (smoke/targeted/regression)
- Integration: Full pipeline runs end-to-end with mock agents (fast)
- Integration: Full pipeline runs with real agents on sample data
- Integration: Resume-from-stage works correctly
- Integration: Parallel stages actually execute concurrently
- Integration: Skill files from different domains produce different agent behavior
- Integration: Model routing falls back correctly when a tier is unavailable
- Integration: CI mode produces machine-readable JSON output with correct exit codes

### Exit Criteria
- [ ] All agents implement `BaseAgent` interface
- [ ] Pipeline DAG runs full STLC flow end-to-end
- [ ] Resume from any stage works
- [ ] Single config file drives all agents
- [ ] CLI entry point functional
- [ ] Domain knowledge skill files loaded per agent
- [ ] Tiered model routing selects correct LLM per task complexity
- [ ] Execution profiles (smoke/targeted/regression) filter correctly
- [ ] CI/CD integration produces machine-readable output
- [ ] Feedback persistence stores and retrieves agent corrections via ChromaDB
- [ ] `validate_stage.py --stage 4` passes
- [ ] Git commit with tag `stage-4-complete`

---

## Stage 5: Frontend UI

### Purpose
Web-based dashboard for controlling the pipeline, browsing results, and managing the feedback loop.

### Entry Criteria
- Stage 4 exit criteria met
- Pipeline API is stable

### Tasks

#### 5.1 — FastAPI Backend
- REST endpoints for all pipeline operations
- WebSocket endpoint for real-time pipeline progress
- Background task queue (Celery or asyncio) for pipeline runs
- File upload for requirements
- ZIP download for generated projects

#### 5.2 — React Frontend
- **Dashboard**: pipeline status cards, recent runs, quality metrics chart
- **Requirements Page**: drag-drop upload, table view, inline edit, re-parse
- **Test Cases Page**: filterable/sortable table, inline edit, approve/reject buttons, regenerate single TC
- **BDD Code Page**: file tree, syntax-highlighted code viewer, download
- **Crawler Page**: interactive site map visualization, element detail panel
- **API Tests Page**: endpoint list, test preview, run individual tests
- **Config Page**: form-based config editor (renders from JSON Schema)
- **History Page**: past runs with logs, diffs, artifact download

#### 5.3 — Real-Time Features
- WebSocket: live agent progress (which stage, % complete, current item)
- Streaming: test cases appear in browser as they're generated
- Inline validation: quality warnings highlighted in test case table
- Notifications: pipeline complete, errors, low quality alerts

### Validation Gate
```bash
python scripts/validate_stage.py --stage 5
```
Tests:
- Unit: API endpoints return correct status codes and schemas
- Unit: React components render without errors (Jest/React Testing Library)
- Integration: Upload requirements → trigger pipeline → see results in UI
- Integration: WebSocket delivers real-time updates
- E2E: Playwright browser test: full user workflow from upload to download

### Exit Criteria
- [ ] All API endpoints functional and documented (OpenAPI auto-generated)
- [ ] UI renders all pages without errors
- [ ] Real-time pipeline progress works
- [ ] Full user workflow: upload → configure → run → browse → download
- [ ] `validate_stage.py --stage 5` passes
- [ ] Git commit with tag `stage-5-complete`

---

## Validation Gate Script Specification

`scripts/validate_stage.py` accepts `--stage N` and runs:

| Check | Stage 0 | Stage 1 | Stage 2 | Stage 3 | Stage 4 | Stage 5 |
|-------|---------|---------|---------|---------|---------|---------|
| Lint (ruff) | Yes | Yes | Yes | Yes | Yes | Yes |
| Type check (mypy) | Yes | Yes | Yes | Yes | Yes | Yes |
| Unit tests | Yes | Yes | Yes | Yes | Yes | Yes |
| Integration tests | Yes | Yes | Yes | Yes | Yes | Yes |
| Import smoke test | Yes | Yes | Yes | Yes | Yes | Yes |
| Contract schema valid | Yes | Yes | Yes | Yes | Yes | Yes |
| Existing tests pass | Yes | Yes | Yes | Yes | Yes | Yes |
| Multi-domain test | -- | Yes | -- | -- | Yes | -- |
| Gherkin parse test | -- | -- | Yes | -- | -- | -- |
| Crawler fixture test | -- | -- | -- | Yes | -- | -- |
| Discrepancy report test | -- | -- | -- | Yes | -- | -- |
| Test pyramid check | -- | -- | -- | Yes | Yes | -- |
| Failure classification | -- | -- | -- | Yes | -- | -- |
| ChromaDB RAG retrieval | -- | -- | -- | Yes | Yes | -- |
| Skill file loading | -- | -- | -- | -- | Yes | -- |
| Model routing test | -- | -- | -- | -- | Yes | -- |
| Execution profile test | -- | -- | -- | -- | Yes | -- |
| CI mode output test | -- | -- | -- | -- | Yes | -- |
| E2E pipeline test | -- | -- | -- | -- | Yes | Yes |
| Frontend render test | -- | -- | -- | -- | -- | Yes |

Exit code `0` = all pass, `1` = failures (with detailed report).

---

## Artifact Contract Versions

All contracts start at `1.0`. Rules for versioning:
- **Patch** (1.0 → 1.1): add optional fields only (backward compatible)
- **Minor** (1.x → 2.0): change required fields (requires migration script)
- Breaking changes require `scripts/migrate.py` to convert old artifacts

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM output inconsistency | Sanitiser + validation + retry with temp bump |
| Crawler blocked by anti-bot | Respect robots.txt, add rate limiting, user-configurable delays |
| Generated code doesn't compile | Syntax validation in gate (parse AST per language) |
| Large requirements files | Batch processing, progress streaming |
| Config complexity | JSON Schema validation, sensible defaults, profile presets |
| Stage regression | Every gate re-runs ALL previous stage tests |
| Test suite bloat / noisy tests | Test pyramid guardrails (E2E < 20%), execution profiles, test level tagging |
| Token cost explosion at scale | Tiered model routing (local models for simple tasks), RAG retrieval (only relevant context) |
| Masking app bugs with test fixes | Failure classification (app_bug vs test_bug vs env_issue), agents refuse to adjust tests for broken behavior |
| Agent lacks domain context | Skill files loaded per agent; institutional knowledge encoded as YAML configs, not hardcoded |
| Stale agent behavior | Feedback persistence via ChromaDB; corrections from previous sessions auto-loaded |

---

## Timeline Estimate (Rough)

| Stage | Estimated Effort |
|-------|-----------------|
| Stage 0 | 1 week |
| Stage 1 | 2 weeks |
| Stage 2 | 2 weeks |
| Stage 3 | 3 weeks |
| Stage 4 | 2 weeks |
| Stage 5 | 3 weeks |
| **Total** | **~13 weeks** |

> Note: Stages 2 and 3 can overlap (parallel development) reducing to ~10-11 weeks.
