# STLC Automation Platform — Specification Workflow Model

> Version: 1.0
> Created: 2026-03-15
> Status: DRAFT

---

## Workflow Principles

1. **Sequential Gating** — Each stage has entry criteria, deliverables, and exit criteria. A stage cannot begin until the previous stage's exit criteria are met.
2. **Backward Compatibility** — Improving an earlier stage must not break downstream stages. Agents communicate through versioned artifact contracts.
3. **Validation at Every Gate** — After each stage: run unit tests, integration tests, linting, and type checks. All must pass before proceeding.
4. **Incremental Deployment** — Each completed stage produces a usable, standalone capability.
5. **Contract-Driven** — Agents exchange data via defined schemas (JSON/YAML). Changing a schema requires a version bump and backward-compatible migration.

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
│   └── stlc_config.schema.json       # JSON Schema for validation
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
RequirementArtifact    — output of requirements parsing
TestCaseArtifact       — output of test case generation
FeatureFileArtifact    — output of BDD agent
StepDefinitionArtifact — output of BDD agent
SiteModelArtifact      — output of web crawler
APIModelArtifact       — output of API discovery
APITestArtifact        — output of API test generator
PipelineRunArtifact    — metadata about a pipeline execution
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
Auto-discover application structure via web crawling and generate targeted API tests.

### Entry Criteria
- Stage 1 exit criteria met (Stage 2 can run in parallel with Stage 3)

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
    "navigation_graph": {"adjacency": {...}}
  }
  ```
- **POM Auto-Generator**: use crawled selectors to pre-fill POM locators (feeds into Stage 2 stubs)

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

#### 3.4 — Cross-Layer Integration
- Crawler's `api_calls` per page → link UI actions to API endpoints
- Generate tests that validate both UI state AND API response for same action
- Site model feeds real selectors into Stage 2 POM classes

### Validation Gate
```bash
python scripts/validate_stage.py --stage 3
```
Tests:
- Unit: Crawler extracts elements correctly from known HTML fixtures
- Unit: API model parser handles OpenAPI 3.0 and Swagger 2.0 specs
- Unit: Generated API tests have correct syntax per framework
- Integration: Crawl a local test app (spin up Flask/Express fixture), verify site model completeness
- Integration: Generate API tests from a public OpenAPI spec, verify tests are syntactically valid
- Integration: REST Assured, Karate, and Pytest+Requests outputs all validate

### Exit Criteria
- [ ] Crawler produces valid `SiteModelArtifact` for test apps
- [ ] API discovery works from OpenAPI spec and from crawled requests
- [ ] API tests generated for 3+ frameworks, all syntactically valid
- [ ] Cross-layer linking produces POM classes with real selectors
- [ ] `validate_stage.py --stage 3` passes
- [ ] Git commit with tag `stage-3-complete`

---

## Stage 4: Agent Orchestration & Integration Layer

### Purpose
Wire all agents into a unified pipeline with DAG-based execution, shared state, and a single configuration file.

### Entry Criteria
- Stages 1, 2, and 3 exit criteria all met

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

### Validation Gate
```bash
python scripts/validate_stage.py --stage 4
```
Tests:
- Unit: DAG resolver correctly orders stages, detects cycles
- Unit: Artifact references (`$stage.output`) resolve correctly
- Unit: Config loader merges profiles and env overrides correctly
- Integration: Full pipeline runs end-to-end with mock agents (fast)
- Integration: Full pipeline runs with real agents on sample data
- Integration: Resume-from-stage works correctly
- Integration: Parallel stages actually execute concurrently

### Exit Criteria
- [ ] All agents implement `BaseAgent` interface
- [ ] Pipeline DAG runs full STLC flow end-to-end
- [ ] Resume from any stage works
- [ ] Single config file drives all agents
- [ ] CLI entry point functional
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
| Multi-domain test | — | Yes | — | — | Yes | — |
| Gherkin parse test | — | — | Yes | — | — | — |
| Crawler fixture test | — | — | — | Yes | — | — |
| E2E pipeline test | — | — | — | — | Yes | Yes |
| Frontend render test | — | — | — | — | — | Yes |

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
