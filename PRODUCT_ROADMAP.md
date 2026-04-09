# Product Roadmap — STLC Automation Platform

> **Project:** Python Orchestrator — STLC Automation Platform
> **Consolidated:** 2026-04-09
> **Sources:** FUTURE_ENHANCEMENTS.md (2026-04-03) + Production Readiness Audit (2026-04-09)
> **Status:** Active
> **Review Cycle:** Quarterly

This document consolidates the original feature enhancement plan with the findings from the April 2026 production readiness audit. Items marked **[AUDIT]** are new requirements surfaced during that audit. Items without a tag are carried over from the original plan unchanged.

---

## Production Readiness Score: ~65%

The platform has solid architecture (FastAPI, React, Docker, DAG orchestration) but has gaps that must close before end-user deployment. The pre-production phase below addresses every ship-blocker identified in the audit.

---

## Pre-Production Phase: Ship Blockers (Weeks 1–4)

These items **must be completed before shipping to any end user**. They address security, operational visibility, and the minimum user experience bar for a production system.

---

### P0.1 Live Pipeline Log Streaming **[AUDIT]**
**Effort:** Medium | **Impact:** Critical | **Dependencies:** None

Users currently see nothing while a pipeline executes. The WebSocket at `/ws/pipeline/{run_id}` broadcasts lifecycle events (`stage_start`, `stage_complete`) but no actual log lines. The frontend never connects to it during a run.

- Add a per-run structured log sink: capture each stage's log output tagged with `run_id` + `stage_id`, written to `.stlc_runs/{run_id}/logs/{stage_id}.jsonl`
- Add `GET /api/pipeline/{run_id}/logs?stage_id=&level=INFO|WARNING|ERROR&offset=` for paginated retrieval
- Extend WebSocket to broadcast real-time log lines: `{"event": "log", "stage_id": "...", "level": "INFO", "message": "...", "ts": "..."}`
- Add a `LogViewer` React component: scrollable, filterable by level and stage, colour-coded, with a download-as-text button
- Show per-run logs in the pipeline history detail view

**Acceptance Criteria:**
- [ ] Every pipeline stage's log output is persisted per run_id and stage_id
- [ ] `GET /api/pipeline/{run_id}/logs` returns paginated, filterable log entries
- [ ] WebSocket stream includes log lines in real time
- [ ] LogViewer component shows live logs during a run and historical logs afterward
- [ ] Logs can be downloaded as `.txt` or `.jsonl` from the UI

**Files to create/modify:**
- `stlc_platform/api/routes/pipeline.py` — add `/logs` endpoint
- `stlc_platform/api/websocket.py` — add log broadcast event
- `stlc_platform/api/tasks.py` — wire log sink into pipeline execution
- `frontend/src/components/LogViewer.tsx` — new component
- `frontend/src/pages/History.tsx` — integrate LogViewer in run detail view

---

### P0.2 Real-Time Pipeline Progress UI **[AUDIT]**
**Effort:** Medium | **Impact:** Critical | **Dependencies:** P0.1

`Dashboard.tsx` triggers pipeline runs but never connects to the WebSocket. Users have no live feedback — no stage timeline, no active-stage indicator, no ETA.

- Add a `RunMonitor` React component that connects to `/ws/pipeline/{run_id}` on mount
- Render a stage-by-stage timeline: each stage shows status (pending / running / completed / failed / skipped), elapsed time, and artifact count on completion
- Show a "Currently Running" card on the Dashboard for any active run
- Extend WebSocket server to broadcast stage duration when a stage completes
- Add estimated time remaining based on historical stage durations from `MetricsCollector`

**Acceptance Criteria:**
- [ ] Dashboard shows a live stage timeline for any active pipeline run
- [ ] Each stage node updates in real time (pending → running → completed/failed)
- [ ] Elapsed time and artifact count shown per stage on completion
- [ ] "Currently Running" section visible on Dashboard homepage
- [ ] Stage timeline visible in History detail view for completed runs

**Files to create/modify:**
- `frontend/src/components/RunMonitor.tsx` — new stage-timeline component
- `frontend/src/pages/Dashboard.tsx` — integrate RunMonitor for active runs
- `frontend/src/pages/History.tsx` — show RunMonitor in historical detail view
- `stlc_platform/api/websocket.py` — add stage duration to complete broadcast

---

### P0.3 Auth Enabled by Default + Security Headers **[AUDIT]**
**Effort:** Small | **Impact:** Critical | **Dependencies:** None

`STLC_AUTH_ENABLED=false` is the default in both `.env.example` and `docker-compose.yml`. Anyone on the network can trigger pipeline runs, view all artifacts, and modify configuration without credentials.

- Change `docker-compose.yml` production profile to set `STLC_AUTH_ENABLED=true`
- Add startup validation: if `STLC_AUTH_ENABLED=true` and `STLC_ADMIN_PASSWORD` is missing or equals "admin", abort with a clear error message
- Add password strength check (minimum 12 characters, mixed case + digit + special char)
- Add security headers middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin`
- Rate-limit the `/api/pipeline/run` endpoint (max 10 runs/hour per IP) using the already-installed `slowapi`
- Rate-limit the `/api/auth/login` endpoint (max 10 attempts/minute per IP)

**Acceptance Criteria:**
- [ ] Production docker-compose defaults auth to enabled
- [ ] Startup fails with a readable error if password is weak or default
- [ ] Security headers present on all API responses
- [ ] Pipeline run endpoint returns 429 after rate limit exceeded
- [ ] Login endpoint rate-limited and returns meaningful error on lockout

**Files to modify:**
- `docker-compose.yml` — enable auth by default
- `.env.example` — update defaults and add comments
- `stlc_platform/api/main.py` — add security headers middleware, startup validation
- `stlc_platform/api/routes/pipeline.py` — add rate limit decorator
- `stlc_platform/api/routes/auth.py` — add rate limit decorator

---

### P0.4 Dependency Health Check + Status UI **[AUDIT]**
**Effort:** Small | **Impact:** High | **Dependencies:** None

`/api/health` only checks whether the agent registry loaded — it does not verify if Ollama is reachable or ChromaDB is connected. A pipeline will fail at runtime even though health shows "ok". Users have no way to know the system is ready before triggering a run.

- Extend `/api/health` to perform live checks with 3-second timeouts:
  - Ollama: POST a minimal prompt to the configured model, record latency
  - ChromaDB: call `client.heartbeat()`, record latency
  - Agents: count registered agents
- Return structured degraded/critical statuses alongside latency metrics
- Add a **Status** page in the frontend showing each service with its status badge and last-checked timestamp
- Show a warning banner on the Dashboard if any service is degraded before the user triggers a run

**Acceptance Criteria:**
- [ ] `/api/health` returns `{status, services: {ollama, chromadb, agents}, uptime_seconds}`
- [ ] Each service check has a hard 3-second timeout and returns a latency in ms
- [ ] Status page in frontend shows service health with live refresh (every 30s)
- [ ] Dashboard shows a warning banner if health is degraded or critical

**Files to modify:**
- `stlc_platform/api/main.py` — extend health endpoint
- `frontend/src/pages/` — add `Status.tsx` page
- `frontend/src/App.tsx` — add `/status` route
- `frontend/src/components/Layout.tsx` — add Status link to sidebar
- `frontend/src/pages/Dashboard.tsx` — add degraded health warning banner

---

### P0.5 Config Persistence to Disk **[AUDIT]**
**Effort:** Small | **Impact:** High | **Dependencies:** None

The config API stores updates in an in-memory `_config` dict. On every container restart or server reload, all configuration changes (LLM model, crawler URL, thresholds) revert to YAML defaults. Users lose every setting they configured through the UI.

- After a successful `PUT /api/config/`, write the merged config back to `config/stlc_config.yaml`
- Keep an atomic write (write to a temp file, then rename) to avoid corrupting the YAML on partial writes
- Add `GET /api/config/diff` that compares the current in-memory config against the YAML defaults and returns changed fields only
- Add a "Reset to defaults" button in the Config UI that calls a new `POST /api/config/reset` endpoint

**Acceptance Criteria:**
- [ ] Config changes survive a server restart
- [ ] YAML is written atomically (no partial-write corruption on crash)
- [ ] `GET /api/config/diff` returns only the fields that differ from defaults
- [ ] "Reset to defaults" restores the original YAML and refreshes the UI

**Files to modify:**
- `stlc_platform/api/routes/config.py` — add disk write, diff, and reset endpoints
- `frontend/src/pages/Config.tsx` — add "Reset to defaults" button and diff indicator

---

### P0.6 Standardised Error Codes + Actionable UI Messages **[AUDIT]**
**Effort:** Small | **Impact:** High | **Dependencies:** None

All 500 errors look identical to the frontend — an Ollama timeout, a ChromaDB failure, and a bad requirement format all produce "Internal server error". Users cannot diagnose problems without reading server logs.

- Define an `ErrorCode` enum: `LLM_TIMEOUT`, `LLM_UNAVAILABLE`, `CHROMADB_UNAVAILABLE`, `REQUIREMENTS_MISSING`, `PIPELINE_ALREADY_RUNNING`, `STAGE_FAILED`, etc.
- Extend all API error responses to include `error_code`, `suggested_action`, and `timestamp`
- Map each `error_code` to a user-facing message and a "How to fix" tooltip in the frontend
- Surface stage-level failure details in the run history view (which stage failed, what error code)

**Acceptance Criteria:**
- [ ] All API errors include `error_code`, `detail`, `suggested_action`, and `timestamp`
- [ ] Frontend maps error codes to readable messages with fix guidance
- [ ] History page shows per-stage error codes for failed stages
- [ ] No user-facing "Internal server error" without an actionable message alongside it

**Files to create/modify:**
- `stlc_platform/api/error_codes.py` — new enum + message map
- `stlc_platform/api/main.py` — update exception handler
- `stlc_platform/api/routes/*.py` — add error codes to all raises
- `frontend/src/api/client.ts` — map error codes to UI messages

---

### P0.7 Empty States + First-Run Onboarding **[AUDIT]**
**Effort:** Small | **Impact:** Medium | **Dependencies:** None

Every page (History, TestCases, BDD, API Tests, Requirements) shows a blank table or a spinner when no data exists. New users see an empty screen with no guidance on what to do next.

- Create a reusable `EmptyState` component: icon + heading + description + CTA button
- Add `EmptyState` to all data pages with page-specific copy and calls to action
- Add a first-run onboarding banner on Dashboard (shown only when zero pipeline runs exist) with a step-by-step checklist: Upload Requirements → Configure LLM → Run Pipeline

**Acceptance Criteria:**
- [ ] All data pages show an `EmptyState` with relevant CTA when no data exists
- [ ] Dashboard shows onboarding checklist for first-time users
- [ ] Onboarding banner dismisses permanently once the first pipeline run completes

**Files to create/modify:**
- `frontend/src/components/EmptyState.tsx` — new reusable component
- `frontend/src/pages/History.tsx`, `TestCases.tsx`, `BddCode.tsx`, `ApiTests.tsx`, `Crawler.tsx`, `Requirements.tsx` — integrate EmptyState

---

### P0.8 Per-Stage Artifact Download + Export Filters **[AUDIT]**
**Effort:** Small | **Impact:** Medium | **Dependencies:** None

`/api/artifacts/{run_id}/download` packages everything into one ZIP. Users cannot download only the test cases CSV, or only the BDD feature files. There are no export buttons on the TestCases, BDD, or API Tests pages.

- Extend the artifacts endpoint: `GET /api/artifacts/{run_id}/download?stage=generate_bdd_code&format=zip|json|csv`
- Add per-stage export buttons to TestCases (CSV, JSON, XLSX), BDD (zip of feature files), and API Tests (zip of test scripts) pages
- Add a "Download All" button to the History detail view that downloads the full run ZIP

**Acceptance Criteria:**
- [ ] Artifact download supports optional `stage` and `format` query params
- [ ] TestCases page has Export dropdown (CSV / JSON / XLSX)
- [ ] BDD page has "Download feature files (.zip)" button
- [ ] API Tests page has "Download test scripts (.zip)" button

**Files to modify:**
- `stlc_platform/api/routes/artifacts.py` — add stage + format filters
- `frontend/src/pages/TestCases.tsx`, `BddCode.tsx`, `ApiTests.tsx` — add export buttons

---

## Phase 0: Quick Wins (Weeks 5–6)

Low-effort, high-impact improvements that can ship quickly once the pre-production blockers are complete.

---

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

### 0.4 Config UX — Validation, Tooltips & Help Text **[AUDIT]**
**Effort:** Low | **Impact:** Medium | **Dependencies:** P0.5

Users don't know what `num_ctx`, `rate_limit_ms`, or `accept_threshold` mean. There's no validation feedback until a pipeline run fails.

- Add a help tooltip (`?` icon) next to every form field in Config.tsx explaining what it controls, recommended values, and the impact of changing it
- Add real-time client-side validation: URL format check for base URLs, range checks for numeric fields, non-empty checks for required fields
- Extend the "Test LLM Connection" button to also validate the currently entered URL before saving
- Add a `GET /api/config/validate` endpoint that validates the full config and returns a list of warnings

**Acceptance Criteria:**
- [ ] Every Config field has a tooltip with description, recommended value, and impact
- [ ] Invalid URLs and out-of-range values are flagged before the user saves
- [ ] Config validation endpoint returns structured warnings
- [ ] "Test Connection" also validates the URL field format before making the request

**Files to modify:**
- `frontend/src/pages/Config.tsx` — add Tooltip component and validation logic
- `frontend/src/components/Tooltip.tsx` — new reusable tooltip component
- `stlc_platform/api/routes/config.py` — add `/validate` endpoint

---

### 0.5 Mobile-Responsive Layout **[AUDIT]**
**Effort:** Low–Medium | **Impact:** Medium | **Dependencies:** None

The sidebar is `w-64` fixed-width. On phones it consumes the full viewport. Wide tables overflow without scrolling. The layout is unusable below 768px.

- Convert sidebar to collapsible with a hamburger menu on mobile (`md:block hidden`)
- Stack sidebar above content on mobile; slide-in drawer on small screens
- Replace wide table layouts with card-based responsive views on screens below 768px
- Increase touch targets on buttons and inputs to ≥44px height on mobile

**Acceptance Criteria:**
- [ ] Layout is usable on 375px (iPhone SE), 768px (tablet), and 1280px (desktop)
- [ ] Sidebar collapses to hamburger menu on mobile
- [ ] Data tables reflow to card layout on small screens
- [ ] All interactive elements meet 44px minimum touch target

**Files to modify:**
- `frontend/src/components/Layout.tsx` — add responsive sidebar and hamburger
- `frontend/src/pages/*.tsx` — add responsive card variants for table views

---

### 0.6 Per-Page Error Boundaries + Error Tracking **[AUDIT]**
**Effort:** Low | **Impact:** Medium | **Dependencies:** None

A single root-level `ErrorBoundary` wraps the whole app. A crash in one component breaks everything. Crashes in production are invisible — nothing reports them.

- Wrap each page's content section in its own `ErrorBoundary` so crashes are isolated
- Add a section-level error UI: "This section failed to load" with a "Retry" button
- Integrate Sentry for automatic error capture: `npm install @sentry/react` + initialise with DSN
- Add "Go back" and "Return to Dashboard" links to the root-level error screen in addition to "Reload"

**Acceptance Criteria:**
- [ ] A crash in History page does not crash the Dashboard or Config pages
- [ ] Each page section shows a scoped error UI on crash
- [ ] Sentry receives crash reports with user context (run_id, current page)
- [ ] Root ErrorBoundary offers "Go back" and "Return to Dashboard" options

**Files to modify:**
- `frontend/src/components/ErrorBoundary.tsx` — extend with section-level and recovery options
- `frontend/src/pages/*.tsx` — wrap each page in scoped ErrorBoundary
- `frontend/src/main.tsx` — initialise Sentry

---

### 0.7 Loading Skeletons **[AUDIT]**
**Effort:** Low | **Impact:** Low | **Dependencies:** None

Pages show a spinner then a content pop-in. There is no layout stability while data loads.

- Create a `Skeleton` component (animated grey bar, same Tailwind pattern used elsewhere)
- Replace full-page spinners with skeleton placeholders matching the page layout:
  - History: skeleton rows matching the run list card dimensions
  - TestCases / BDD / ApiTests: skeleton rows for the table view
  - Dashboard stats cards: skeleton rectangles during initial load

**Acceptance Criteria:**
- [ ] No full-page blank spinners on initial load of any page
- [ ] Skeleton layout matches the real content dimensions so there is no layout shift on load

**Files to create/modify:**
- `frontend/src/components/Skeleton.tsx` — new component
- `frontend/src/pages/History.tsx`, `TestCases.tsx`, `BddCode.tsx`, `ApiTests.tsx`, `Dashboard.tsx` — replace spinners

---

## Phase 1: Core Platform (Weeks 7–12)

Medium-effort features that significantly improve the user experience and platform capabilities.

---

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
- `frontend/src/components/` — add TestCaseEditor, DiffViewer components
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

### 1.4 User Management UI + RBAC **[AUDIT]**
**Effort:** Medium | **Impact:** High | **Dependencies:** P0.3

Currently there is no way to manage users through the UI. RBAC has only two undifferentiated roles. There is no per-user API key management or audit trail of who did what.

- Add an Admin page at `/admin/users` to create, edit, and deactivate users
- Add role definitions: `admin` (full access), `operator` (trigger runs, view results), `viewer` (read-only)
- Add API key generation and revocation UI per user
- Add `GET /api/auth/users`, `POST /api/auth/users`, `DELETE /api/auth/users/{id}` endpoints (admin only)
- Add `GET /api/auth/me` to return current user profile and role
- Add an audit log: every login, config change, pipeline run trigger, and approval action recorded with timestamp and user

**Acceptance Criteria:**
- [ ] Admin can create, edit roles, and deactivate users through the UI
- [ ] Viewer role cannot trigger pipeline runs or modify config
- [ ] API keys can be generated per user and revoked on demand
- [ ] All auth events (login, config change, run trigger) appear in a queryable audit log
- [ ] `GET /api/auth/me` returns role and permissions

**Files to create:**
- `stlc_platform/core/audit_logger.py`
- `stlc_platform/api/auth/rbac.py`
- `stlc_platform/api/routes/users.py`
- `frontend/src/pages/Admin.tsx`

**Files to modify:**
- `stlc_platform/api/auth.py` — add RBAC layer and audit hooks
- `config/stlc_config.yaml` — add audit retention settings

---

### 1.5 Stage-Level Run History Detail **[AUDIT]**
**Effort:** Medium | **Impact:** Medium | **Dependencies:** P0.1, P0.2

The History page shows run-level totals (stages completed / failed / skipped) but no per-stage detail — no duration per stage, no artifact count, no error messages per stage, no generated file list.

- Extend `PipelineRunStatus` schema to include a `stages` array: `[{stage_id, status, duration_seconds, artifact_count, error_message, error_code, generated_files: []}]`
- Add `GET /api/pipeline/{run_id}/stages` returning per-stage detail
- Expand the History run detail view to show the stage breakdown table with status badges, durations, and artifact counts
- Show error message and `suggested_action` inline for failed stages

**Acceptance Criteria:**
- [ ] History detail view shows a per-stage breakdown with status, duration, artifact count
- [ ] Failed stages show error code and suggested fix inline
- [ ] `GET /api/pipeline/{run_id}/stages` returns structured per-stage detail
- [ ] Stage durations match the values recorded in `MetricsCollector`

**Files to modify:**
- `stlc_platform/api/schemas.py` — add `StageDetail` model and extend `PipelineRunStatus`
- `stlc_platform/api/routes/pipeline.py` — add `/stages` endpoint
- `frontend/src/pages/History.tsx` — add stage breakdown table in run detail

---

## Phase 2: Execution & Intelligence (Weeks 13–20)

High-effort features that transform the platform from a generator into a full testing lifecycle tool.

---

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
**Effort:** Medium | **Impact:** High (regulated industries) | **Dependencies:** Phase 0.1, 2.1, 1.4

For regulated industries (healthcare, finance, insurance), provide immutable audit trails.

- **Immutable run log:** Every generation run recorded with model, prompt, output, score, timestamp
- **Traceability matrix:** Requirement → Test Case → Execution Result (full chain)
- **Compliance reports:** Export reports showing coverage per requirement with quality scores
- **Role-based access control:** Who approved what, when, and from which IP — extends Phase 1.4 RBAC
- **Data retention policy:** Configurable retention period for audit logs

**Acceptance Criteria:**
- [ ] Every pipeline run produces an immutable audit log
- [ ] Traceability matrix exportable as PDF/CSV
- [ ] Compliance report shows "REQ-001 has 5 test cases, all scored > 0.70"
- [ ] RBAC enforced on approval actions
- [ ] Audit logs retained per configurable policy

**Files to create:**
- `stlc_platform/core/traceability.py`
- `stlc_platform/exporters/compliance_exporter.py`

**Files to modify:**
- `stlc_platform/pipeline/orchestrator.py` — inject audit logging at each stage
- `stlc_platform/api/auth.py` — extend RBAC from Phase 1.4
- `stlc_platform/exporters/exporters.py` — add compliance report export
- `config/stlc_config.yaml` — add audit/retention settings

---

## Phase 3: Scale & Extend (Weeks 21–30)

Advanced features for enterprise adoption and platform extensibility.

---

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
**Effort:** High | **Impact:** Low–Medium | **Dependencies:** Phase 2.1

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

## Phase 4: Future Exploration (Beyond Week 30)

Long-term ideas that require significant research or depend on external ecosystem maturity.

### 4.1 AI-Powered Bug Prediction
Analyze historical test failures to predict which areas of the application are most likely to break. Prioritise test generation for high-risk areas. Integrate with code change analysis (git diff) to focus tests on modified code paths.

### 4.2 Self-Healing Tests
When a test fails due to a UI change (e.g., button renamed), the crawler re-scans the page. The system auto-updates the test step with the new element locator. Failed tests are repaired without human intervention.

### 4.3 Generative Test Orchestration
LLM decides which pipeline stages to run based on requirement type (e.g., API-only requirement skips crawler). Dynamic agent selection based on domain detection. Self-optimising prompt templates based on quality score feedback.

### 4.4 Visual Regression Testing
Integrate with Percy, Chromatic, or custom screenshot comparison. Generate visual regression tests from UI requirements. Detect layout shifts, colour changes, and missing elements.

### 4.5 Security Test Generation (DAST)
Generate OWASP ZAP / Burp Suite scan configurations from security requirements. Auto-generate injection payloads, XSS vectors, and CSRF tests. Integrate with SAST tools for code-level security analysis.

---

## Complete Priority Table

| Phase | ID | Enhancement | Source | Effort | Impact | Priority |
|---|---|---|---|---|---|---|
| **Pre-Prod** | P0.1 | Live Pipeline Log Streaming | Audit | Medium | **Critical** | **P0** |
| **Pre-Prod** | P0.2 | Real-Time Pipeline Progress UI | Audit | Medium | **Critical** | **P0** |
| **Pre-Prod** | P0.3 | Auth Enabled by Default + Security Headers | Audit | Small | **Critical** | **P0** |
| **Pre-Prod** | P0.4 | Dependency Health Check + Status UI | Audit | Small | High | **P0** |
| **Pre-Prod** | P0.5 | Config Persistence to Disk | Audit | Small | High | **P0** |
| **Pre-Prod** | P0.6 | Standardised Error Codes + Actionable Messages | Audit | Small | High | **P0** |
| **Pre-Prod** | P0.7 | Empty States + First-Run Onboarding | Audit | Small | Medium | **P0** |
| **Pre-Prod** | P0.8 | Per-Stage Artifact Download + Export Filters | Audit | Small | Medium | **P0** |
| **0** | 0.1 | Auto-Feedback Loop | Original | Low | High | P1 |
| **0** | 0.2 | Test Suite Optimisation & Deduplication | Original | Low | Medium | P1 |
| **0** | 0.3 | Smart Prompt Caching & Cost Tracking | Original | Low | Medium | P1 |
| **0** | 0.4 | Config UX — Validation, Tooltips, Help Text | Audit | Low | Medium | P1 |
| **0** | 0.5 | Mobile-Responsive Layout | Audit | Low–Med | Medium | P1 |
| **0** | 0.6 | Per-Page Error Boundaries + Error Tracking | Audit | Low | Medium | P1 |
| **0** | 0.7 | Loading Skeletons | Audit | Low | Low | P1 |
| **1** | 1.1 | Jira / Azure DevOps Integration | Original | Medium | High | P2 |
| **1** | 1.2 | Visual Test Case Editor | Original | Medium | High | P2 |
| **1** | 1.3 | Requirement Change Detection | Original | Medium | High | P2 |
| **1** | 1.4 | User Management UI + RBAC | Audit | Medium | High | P2 |
| **1** | 1.5 | Stage-Level Run History Detail | Audit | Medium | Medium | P2 |
| **2** | 2.1 | Test Execution Engine | Original | High | Very High | P3 |
| **2** | 2.2 | Test Data Generation | Original | Medium | Medium | P3 |
| **2** | 2.3 | Compliance & Audit Trail | Original + Audit | Medium | High | P3 |
| **3** | 3.1 | Multi-Project Workspaces | Original | High | Medium | P4 |
| **3** | 3.2 | Natural Language Requirement Input | Original | Medium | Medium | P4 |
| **3** | 3.3 | Performance Test Generation | Original | High | Medium | P4 |
| **3** | 3.4 | Multi-Language Code Generation | Original | High | Low–Med | P4 |
| **3** | 3.5 | Collaborative Review Workflow | Original | High | Medium | P4 |
| **4** | 4.1 | AI Bug Prediction | Original | Research | High | Future |
| **4** | 4.2 | Self-Healing Tests | Original | Research | High | Future |
| **4** | 4.3 | Generative Test Orchestration | Original | Research | Medium | Future |
| **4** | 4.4 | Visual Regression Testing | Original | Research | Medium | Future |
| **4** | 4.5 | Security Test Generation (DAST) | Original | Research | High | Future |

---

## Implementation Guidelines

### For Each Enhancement
1. Create a feature branch from `master`
2. Write unit and integration tests (minimum 75% coverage for new code)
3. Update `CHANGELOG.md` with the change
4. Update relevant documentation (README, API docs, config schema)
5. Run full CI pipeline before merging
6. Tag release with semantic versioning

### Dependency Management
- Pre-Production phase must be fully complete before any Phase 0 items are started
- Phases 0–3 are sequential — do not start Phase N until Phase N-1 is complete
- Within a phase, enhancements with no cross-dependencies can be developed in parallel
- Each enhancement must be independently deployable (use feature flags where integration risk is high)

### Quality Gates
- All new code must pass `ruff`, `mypy`, `bandit`, and `pip-audit` checks
- Integration tests must pass for all 6 pipeline stages
- Docker build must succeed with Trivy scan showing no critical vulnerabilities
- Frontend must pass ESLint, Prettier, and Vitest checks
- No new endpoint without an OpenAPI docstring and at least one integration test

---

## Review & Update Schedule

- **After Pre-Production phase completes** — re-score all Phase 0 items based on user feedback
- **Quarterly** — reassess priorities based on user feedback and market changes
- **After each major release** — mark completed items, add new ideas from production observations
- **When new technology emerges** — evaluate if new LLMs, tools, or frameworks change the roadmap

**Document created:** 2026-04-09
**Consolidates:** `FUTURE_ENHANCEMENTS.md` (2026-04-03) + Production Readiness Audit (2026-04-09)
**Next review:** 2026-07-01
