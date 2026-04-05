# Future Enhancement Plan

> **Project:** Python Orchestrator — STLC Automation Platform
> **Created:** 2026-04-03
> **Status:** Proposed
> **Review Cycle:** Quarterly

This document outlines planned enhancements for the STLC Automation Platform, prioritised by effort, impact, and dependency order. Each phase builds on the previous one to ensure incremental delivery without breaking existing functionality.

---

## Phase 0: Quick Wins (Weeks 1–2)

Low-effort, high-impact improvements that can be shipped immediately.

### 0.1 Auto-Feedback Loop
**Effort:** Low | **Impact:** High | **Dependencies:** None

Currently, storing approved examples requires manual `mcp_server.py store-example TC-XXXX`. Automate this:

- **Auto-store** any test case scoring **≥ 0.80** directly into ChromaDB `tc_examples` collection
- **Flag for review** test cases scoring 0.40–0.64 — surface them in the dashboard's review queue
- **Log rejections** with failure reasons (loop detected, hollow response, generic steps) for analysis
- **Configurable threshold** via `AUTO_STORE_THRESHOLD` env var (default: 0.80)

**Acceptance Criteria:**
- [ ] High-scoring TCs are automatically stored as few-shot examples without human action
- [ ] Flagged TCs appear in a "Pending Review" section in the dashboard
- [ ] Rejection reasons are persisted in `feedback/` for trend analysis
- [ ] Threshold is configurable via `.env` and `stlc_config.yaml`

**Files to modify:**
- `stlc_platform/core/quality/scorer.py` — hook for auto-store trigger
- `stlc_platform/agents/requirements_agent/generator.py` — post-scoring logic
- `mcp_server.py` — expose auto-store API
- `config/stlc_config.yaml` — add `auto_store_threshold` setting

---

### 0.2 Test Suite Optimisation & Deduplication
**Effort:** Low | **Impact:** Medium | **Dependencies:** None

Over time, test suites grow bloated with overlapping scenarios.

- Run cross-run deduplication to identify redundant test cases
- Suggest consolidation ("TC-042 and TC-087 test the same scenario with different data")
- Add a `stlc optimise --input output/test_cases.csv` CLI command
- Surface dedup suggestions in the dashboard

**Acceptance Criteria:**
- [ ] Deduplication command identifies overlapping test cases with similarity scores
- [ ] Consolidation report generated in JSON format
- [ ] Dashboard shows "Potential Duplicates" section with merge suggestions

**Files to modify:**
- `stlc_platform/core/quality/deduplicator.py` — enhance with cross-run comparison
- `stlc_platform/cli.py` — add `optimise` command
- `frontend/` — add deduplication UI panel

---

### 0.3 Smart Prompt Caching & Cost Tracking
**Effort:** Low | **Impact:** Medium | **Dependencies:** None

- Cache LLM responses by requirement hash (partially implemented in `core/llm/cache.py`)
- Track token cost per requirement, per run, and per agent
- Add cost summary to the JSON generation report
- Add cost trend chart to the dashboard

**Acceptance Criteria:**
- [ ] Cache hit rate displayed in pipeline run summary
- [ ] Token cost breakdown per requirement in `generation_report.json`
- [ ] Cost trend chart in dashboard metrics page

**Files to modify:**
- `stlc_platform/core/llm/cache.py` — complete implementation
- `stlc_platform/pipeline/metrics_collector.py` — add cost tracking
- `stlc_platform/exporters/exporters.py` — add cost to JSON report
- `frontend/` — add cost chart component

---

## Phase 1: Core Platform (Weeks 3–6)

Medium-effort features that significantly improve the user experience and platform capabilities.

### 1.1 Jira / Azure DevOps Integration
**Effort:** Medium | **Impact:** High | **Dependencies:** Phase 0.1

Eliminate manual file uploads by pulling requirements directly from issue trackers and pushing generated test cases back.

- **Jira:** Fetch Epics → Stories → Acceptance Criteria via REST API
- **Azure DevOps:** Fetch work items with AC fields
- **Push back:** Create Jira Test issues or ADO Test Cases from generated output
- **Sync status:** Update test execution results (pass/fail/blocked) from runs

**Acceptance Criteria:**
- [ ] `stlc fetch --source jira --project KEY` pulls requirements into the pipeline
- [ ] Generated test cases can be pushed as Jira Test issues
- [ ] Execution results sync back to Jira/ADO
- [ ] Credentials managed securely (env vars or keyring, never hardcoded)

**Files to create:**
- `stlc_platform/integrations/jira_client.py`
- `stlc_platform/integrations/ado_client.py`
- `stlc_platform/integrations/__init__.py`

**Files to modify:**
- `stlc_platform/cli.py` — add `fetch` and `push` commands
- `config/stlc_config.yaml` — add integration settings section
- `stlc_platform/api/routes/` — add integration endpoints

---

### 1.2 Visual Test Case Editor
**Effort:** Medium | **Impact:** High | **Dependencies:** None

Replace the read-only test case viewer with a full editor in the dashboard.

- Inline editing of steps, preconditions, expected outcomes
- Drag-and-drop reordering of test steps
- Side-by-side diff when regenerating a test case (before vs. after)
- One-click "Approve & Store" button that triggers the feedback loop
- Export edited test cases back to CSV/Zephyr

**Acceptance Criteria:**
- [ ] All test case fields are editable in the dashboard
- [ ] Changes are saved to a local draft before submission
- [ ] Diff view shows what changed between generations
- [ ] "Approve & Store" button stores the edited version in ChromaDB
- [ ] Edited test cases can be re-exported

**Files to modify:**
- `frontend/src/components/` — add TestCaseEditor component
- `frontend/src/components/` — add DiffViewer component
- `stlc_platform/api/routes/test_cases.py` — add update/patch endpoints
- `stlc_platform/api/routes/feedback.py` — add approve endpoint

---

### 1.3 Requirement Change Detection
**Effort:** Medium | **Impact:** High | **Dependencies:** Phase 0.1, 1.1

When requirements evolve, the system should detect what changed and act accordingly.

- Diff new requirements against ChromaDB-stored previous versions
- Classify changes as: **new**, **modified**, **removed**, **unchanged**
- Identify which test cases need regeneration vs. which are still valid
- Generate a "Test Impact Report" showing what changed and why
- Auto-regenerate tests for modified requirements only

**Acceptance Criteria:**
- [ ] Change detection runs automatically when new requirements are uploaded
- [ ] Impact report lists affected test cases with recommended action
- [ ] Pipeline can run in "delta mode" — only process changed requirements
- [ ] Report exported as JSON and visible in dashboard

**Files to create:**
- `stlc_platform/core/change_detector.py`

**Files to modify:**
- `stlc_platform/pipeline/orchestrator.py` — add delta mode support
- `stlc_platform/cli.py` — add `--delta` flag
- `stlc_platform/api/routes/requirements.py` — add change detection endpoint

---

## Phase 2: Execution & Intelligence (Weeks 7–12)

High-effort features that transform the platform from a generator into a full testing lifecycle tool.

### 2.1 Test Execution Engine
**Effort:** High | **Impact:** Very High | **Dependencies:** Phase 1.1, 1.2

Currently the platform *generates* tests but doesn't *run* them. Close the loop.

- **BDD execution:** Run generated Behave tests against the live app via Playwright
- **API execution:** Run generated API tests against target endpoints
- **Result capture:** Parse pass/fail/skipped results and store them
- **Feedback loop:** Failed tests trigger auto-enrichment ("this scenario wasn't covered well enough")
- **Execution scheduling:** Run tests on a schedule or on-demand via API
- **HTML reports:** Generate Allure or ExtentReports-style execution reports

**Acceptance Criteria:**
- [ ] `stlc run-tests --suite output/test_cases.csv --target http://app:3000` executes tests
- [ ] Execution results are stored and visible in the dashboard
- [ ] Failed tests are flagged for regeneration with failure context
- [ ] Execution reports generated in HTML format
- [ ] Scheduled execution via cron-like configuration

**Files to create:**
- `stlc_platform/execution/bdd_runner.py`
- `stlc_platform/execution/api_runner.py`
- `stlc_platform/execution/result_parser.py`
- `stlc_platform/execution/scheduler.py`
- `stlc_platform/execution/__init__.py`

**Files to modify:**
- `stlc_platform/cli.py` — add `run-tests` command
- `stlc_platform/pipeline/` — add execution stage (Stage 6)
- `stlc_platform/api/routes/` — add execution endpoints
- `frontend/` — add execution results dashboard

---

### 2.2 Test Data Generation
**Effort:** Medium | **Impact:** Medium | **Dependencies:** None

Generate realistic test data to accompany test steps.

- **Domain-aware data:** Financial data for banking, patient data for healthcare, etc.
- **Parameterised tests:** One test case, multiple data rows (data-driven testing)
- **Data types:** Names, emails, phone numbers, addresses, credit card numbers, dates
- **Edge case data:** Empty strings, max-length strings, special characters, SQL injection payloads
- **Data catalog integration:** Extend `config/skills/*/data_catalog.yaml` with field-specific generators

**Acceptance Criteria:**
- [ ] Test cases include a `test_data` field with generated values
- [ ] Data respects domain-specific formats (e.g., `CUST-0001` for customer IDs)
- [ ] Edge case data variants are generated for each field
- [ ] Data can be exported as CSV/JSON for external test runners

**Files to create:**
- `stlc_platform/core/data_generator.py`
- `stlc_platform/core/data_faker.py`

**Files to modify:**
- `stlc_platform/core/contracts.py` — add `test_data` field to `TestCaseArtifact`
- `stlc_platform/agents/requirements_agent/generator.py` — inject data generation
- `config/skills/` — expand data catalogs per domain

---

### 2.3 Compliance & Audit Trail
**Effort:** Medium | **Impact:** High (regulated industries) | **Dependencies:** Phase 0.1, 2.1

For regulated industries (healthcare, finance, insurance), provide immutable audit trails.

- **Immutable run log:** Every generation run recorded with model, prompt, output, score, timestamp
- **Traceability matrix:** Requirement → Test Case → Execution Result (full chain)
- **Compliance reports:** Export reports showing coverage per requirement with quality scores
- **Role-based access control:** Who approved what, when, and from which IP
- **Data retention policy:** Configurable retention period for audit logs

**Acceptance Criteria:**
- [ ] Every pipeline run produces an immutable audit log
- [ ] Traceability matrix exportable as PDF/CSV
- [ ] Compliance report shows "REQ-001 has 5 test cases, all scored > 0.70"
- [ ] RBAC enforced on approval actions
- [ ] Audit logs retained per configurable policy

**Files to create:**
- `stlc_platform/core/audit_logger.py`
- `stlc_platform/core/traceability.py`
- `stlc_platform/api/auth/rbac.py`

**Files to modify:**
- `stlc_platform/pipeline/orchestrator.py` — inject audit logging at each stage
- `stlc_platform/api/auth.py` — add RBAC layer
- `stlc_platform/exporters/exporters.py` — add compliance report export
- `config/stlc_config.yaml` — add audit/retention settings

---

## Phase 3: Scale & Extend (Weeks 13–20)

Advanced features for enterprise adoption and platform extensibility.

### 3.1 Multi-Project / Workspace Support
**Effort:** High | **Impact:** Medium | **Dependencies:** Phase 1.3, 2.3

Currently single-project. Add workspace isolation and cross-project reuse.

- **Workspace isolation:** Separate ChromaDB collections, configs, and outputs per project
- **Cross-project reuse:** Share test cases between projects (e.g., "login" tests from Project A apply to Project B)
- **Shared skill files:** Common coding standards and test design principles across workspaces
- **Workspace admin:** Manage projects, members, and shared resources

**Acceptance Criteria:**
- [ ] `stlc workspace create <name>` creates an isolated project environment
- [ ] Cross-project test case search and import
- [ ] Shared skill files applied across workspaces
- [ ] Workspace-level metrics and dashboards

**Files to create:**
- `stlc_platform/core/workspace_manager.py`
- `stlc_platform/api/routes/workspaces.py`

**Files to modify:**
- `stlc_platform/core/storage/chroma_store.py` — add workspace-scoped collections
- `stlc_platform/pipeline/orchestrator.py` — workspace context injection
- `frontend/` — add workspace selector and management UI

---

### 3.2 Natural Language Requirement Input
**Effort:** Medium | **Impact:** Medium | **Dependencies:** Phase 1.1

Accept free-form, conversational requirements instead of structured files.

- **Conversational input:** "As a user, I want to reset my password via email so I can regain access"
- **LLM extraction:** Parse into structured requirement (ID, title, description, AC)
- **Voice-to-text:** Support audio input for stakeholder interviews
- **Interactive clarification:** LLM asks follow-up questions when requirements are ambiguous

**Acceptance Criteria:**
- [ ] `stlc input --text "As a user..."` produces a structured requirement
- [ ] Ambiguous requirements trigger clarification questions
- [ ] Voice input supported via API endpoint
- [ ] Extracted requirements feed directly into the pipeline

**Files to create:**
- `stlc_platform/agents/nl_parser_agent.py`
- `stlc_platform/api/routes/nl_input.py`

**Files to modify:**
- `stlc_platform/cli.py` — add `input` command
- `frontend/` — add conversational requirement input UI

---

### 3.3 Performance & Load Test Generation
**Effort:** High | **Impact:** Medium | **Dependencies:** Phase 2.1

Extend beyond functional testing into performance testing.

- **Script generation:** Generate JMeter / k6 / Locust scripts from requirements
- **Performance-sensitive detection:** Identify requirements with timing constraints ("response within 2s")
- **Load profile generation:** Auto-generate load profiles based on expected user volumes
- **Performance thresholds:** Define and validate SLA targets

**Acceptance Criteria:**
- [ ] Performance test scripts generated for timing-related requirements
- [ ] Scripts are executable against target endpoints
- [ ] Load profiles configurable per test
- [ ] Results compared against defined SLA thresholds

**Files to create:**
- `stlc_platform/agents/performance_agent.py`
- `stlc_platform/execution/performance_runner.py`
- `stlc_platform/exporters/jmeter_exporter.py`
- `stlc_platform/exporters/k6_exporter.py`

**Files to modify:**
- `stlc_platform/pipeline/` — add performance generation stage
- `config/stlc_config.yaml` — add performance testing settings

---

### 3.4 Multi-Language & Multi-Framework Code Generation
**Effort:** High | **Impact:** Low-Medium | **Dependencies:** Phase 2.1

Generate test code in multiple languages and frameworks.

- **BDD step definitions:** Python (behave), Java (Cucumber), JavaScript (Cucumber.js), C# (SpecFlow)
- **API tests:** Python (pytest), Java (Rest Assured), JavaScript (Supertest), Karate DSL
- **UI tests:** Python (Playwright), Java (Selenium), JavaScript (Playwright/WDIO)
- **Test case localisation:** Generate test descriptions in Spanish, French, etc.

**Acceptance Criteria:**
- [ ] Output language/framework configurable per project
- [ ] Generated code compiles/passes lint in target language
- [ ] Localisation support for test descriptions
- [ ] Template-based generation for easy addition of new frameworks

**Files to create:**
- `stlc_platform/exporters/codegen/java_generator.py`
- `stlc_platform/exporters/codegen/js_generator.py`
- `stlc_platform/exporters/codegen/csharp_generator.py`
- `config/templates/` — language-specific code templates

**Files to modify:**
- `stlc_platform/agents/bdd_agent/` — add multi-language support
- `stlc_platform/agents/api_test_agent/test_generator.py` — add framework templates
- `config/stlc_config.yaml` — add code generation settings

---

### 3.5 Collaborative Review Workflow
**Effort:** High | **Impact:** Medium | **Dependencies:** Phase 1.2, 2.3

Replace single-person review with team workflows.

- **Assignment:** Assign test cases for review to specific team members
- **Comments:** Annotate individual test steps with feedback
- **Approval workflow:** Draft → In Review → Approved → Published
- **Notifications:** Slack/Teams/Discord integration for pending reviews
- **Review analytics:** Track reviewer throughput, approval rates, bottlenecks

**Acceptance Criteria:**
- [ ] Test cases can be assigned to reviewers
- [ ] Comments and annotations visible per test step
- [ ] Status transitions enforced (cannot publish without approval)
- [ ] Slack/Teams notifications sent on assignment and approval
- [ ] Review analytics dashboard shows team metrics

**Files to create:**
- `stlc_platform/core/review_workflow.py`
- `stlc_platform/integrations/slack_notifier.py`
- `stlc_platform/integrations/teams_notifier.py`
- `stlc_platform/api/routes/reviews.py`

**Files to modify:**
- `stlc_platform/core/contracts.py` — add review state fields
- `frontend/` — add review workflow UI
- `config/stlc_config.yaml` — add notification settings

---

## Phase 4: Future Exploration (Beyond Week 20)

Long-term ideas that require significant research or depend on external ecosystem maturity.

### 4.1 AI-Powered Bug Prediction
- Analyze historical test failures to predict which areas of the application are most likely to break
- Prioritise test generation for high-risk areas
- Integrate with code change analysis (git diff) to focus tests on modified code paths

### 4.2 Self-Healing Tests
- When a test fails due to a UI change (e.g., button renamed), the crawler re-scans the page
- The system auto-updates the test step with the new element locator
- Failed tests are repaired without human intervention

### 4.3 Generative Test Orchestration
- LLM decides which pipeline stages to run based on requirement type (e.g., API-only req skips crawler)
- Dynamic agent selection based on domain detection
- Self-optimising prompt templates based on quality score feedback

### 4.4 Visual Regression Testing
- Integrate with Percy, Chromatic, or custom screenshot comparison
- Generate visual regression tests from UI requirements
- Detect layout shifts, color changes, missing elements

### 4.5 Security Test Generation (DAST)
- Generate OWASP ZAP / Burp Suite scan configurations from security requirements
- Auto-generate injection payloads, XSS vectors, CSRF tests
- Integrate with SAST tools for code-level security analysis

---

## Priority Summary

| Phase | Enhancement | Effort | Impact | Priority |
|-------|------------|--------|--------|----------|
| **0** | Auto-Feedback Loop | Low | High | P0 |
| **0** | Test Suite Optimisation | Low | Medium | P0 |
| **0** | Smart Prompt Caching & Cost Tracking | Low | Medium | P0 |
| **1** | Jira / ADO Integration | Medium | High | P1 |
| **1** | Visual Test Case Editor | Medium | High | P1 |
| **1** | Requirement Change Detection | Medium | High | P1 |
| **2** | Test Execution Engine | High | Very High | P2 |
| **2** | Test Data Generation | Medium | Medium | P2 |
| **2** | Compliance & Audit Trail | Medium | High | P2 |
| **3** | Multi-Project Workspaces | High | Medium | P3 |
| **3** | Natural Language Input | Medium | Medium | P3 |
| **3** | Performance Test Generation | High | Medium | P3 |
| **3** | Multi-Language Code Generation | High | Low-Medium | P3 |
| **3** | Collaborative Review Workflow | High | Medium | P3 |
| **4** | AI Bug Prediction | Research | High | Future |
| **4** | Self-Healing Tests | Research | High | Future |
| **4** | Generative Test Orchestration | Research | Medium | Future |
| **4** | Visual Regression Testing | Research | Medium | Future |
| **4** | Security Test Generation (DAST) | Research | High | Future |

---

## Implementation Guidelines

### For Each Enhancement
1. Create a feature branch from `master`
2. Write unit and integration tests (minimum 75% coverage)
3. Update `CHANGELOG.md` with the change
4. Update relevant documentation (README, API docs, config schema)
5. Run full CI pipeline before merging
6. Tag release with semantic versioning

### Dependency Management
- Phases are sequential — do not start Phase N until Phase N-1 is complete
- Within a phase, enhancements can be developed in parallel if they have no cross-dependencies
- Each enhancement should be independently deployable (feature flags where needed)

### Quality Gates
- All new code must pass `ruff`, `mypy`, `bandit`, and `pip-audit` checks
- Integration tests must pass for all 5 pipeline stages
- Docker build must succeed with Trivy scan showing no critical vulnerabilities
- Frontend must pass ESLint, Prettier, and Vitest checks

---

## Review & Update Schedule

This document should be reviewed and updated:
- **Quarterly** — reassess priorities based on user feedback and market changes
- **After each major release** — mark completed items, add new ideas
- **When new technology emerges** — evaluate if new LLMs, tools, or frameworks change the roadmap

**Last reviewed:** 2026-04-03
**Next review:** 2026-07-01
