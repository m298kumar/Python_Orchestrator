# Complete Project Workflow Guide

> **Project:** Python Orchestrator — STLC Automation Platform
> **Version:** 0.5.0
> **Last Updated:** 2026-04-04

This document explains every file in the project, how they connect, and the complete flow from UI interaction to test case generation.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [End-to-End Flow: What Happens When You Click "Run"](#2-end-to-end-flow-what-happens-when-you-click-run)
3. [The Pipeline: DAG-Based Execution](#3-the-pipeline-dag-based-execution)
4. [Core Infrastructure — Every File Explained](#4-core-infrastructure--every-file-explained)
5. [The 5 Agents — How Each Works](#5-the-5-agents--how-each-works)
6. [API Layer — REST + WebSocket](#6-api-layer--rest--websocket)
7. [Frontend Dashboard](#7-frontend-dashboard)
8. [Configuration System](#8-configuration-system)
9. [Root-Level Modules (Legacy)](#9-root-level-modules-legacy)
10. [Exporters](#10-exporters)
11. [Complete Dependency Map](#11-complete-dependency-map)
12. [Data Flow: Artifact Contracts](#12-data-flow-artifact-contracts)
13. [CLI Entry Points](#13-cli-entry-points)

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER INTERACTION                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   CLI       │  │  Web UI      │  │  MCP Server  │  │  REST API    │ │
│  │  (Click)    │  │  (React)     │  │  (Claude)    │  │  (FastAPI)   │ │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                │                  │                  │         │
│         └────────────────┴──────────────────┴──────────────────┘         │
│                                │                                        │
│                         ┌──────▼──────┐                                 │
│                         │  FastAPI    │  ← Entry point for all web/CLI  │
│                         │  Backend    │     requests                     │
│                         └──────┬──────┘                                 │
│                                │                                        │
│                    ┌───────────▼────────────┐                           │
│                    │  Pipeline Orchestrator │  ← DAG-based executor     │
│                    │  (ThreadPoolExecutor)  │     with parallel waves   │
│                    └───────────┬────────────┘                           │
│                                │                                        │
│         ┌──────────────────────┼──────────────────────┐                 │
│         ▼                      ▼                      ▼                 │
│  ┌─────────────┐       ┌─────────────┐        ┌─────────────┐          │
│  │ Stage 1     │       │ Stage 2     │        │ Stage 3     │          │
│  │ Requirements│──────▶│ BDD Gen     │        │ Crawler     │          │
│  │ Agent       │       │ Agent       │        │ Agent       │          │
│  └──────┬──────┘       └──────┬──────┘        └──────┬──────┘          │
│         │                     │                      │                 │
│         │              ┌──────▼──────┐        ┌──────▼──────┐          │
│         │              │ Stage 4     │        │ Stage 3b    │          │
│         │              │ Enrichment  │◀───────│ API Test    │          │
│         │              │ Agent       │        │ Agent       │          │
│         │              └──────┬──────┘        └─────────────┘          │
│         │                     │                                        │
│         │              ┌──────▼──────┐                                 │
│         │              │ Stage 5     │                                 │
│         │              │ Coverage    │                                 │
│         │              │ Tracker     │                                 │
│         │              └──────┬──────┘                                 │
│         │                     │                                        │
│         └─────────────────────┼────────────────────────┐               │
│                               ▼                        ▼               │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │              ChromaDB Vector Store                           │      │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │      │
│  │  │ requirements │ │ tc_examples  │ │  domain_vocab        │ │      │
│  │  │ (semantic    │ │ (approved    │ │ (screen names, UI   │ │      │
│  │  │  search)     │ │  few-shot)   │ │  elements)           │ │      │
│  │  └──────────────┘ └──────────────┘ └──────────────────────┘ │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                               │                                        │
│                    ┌──────────▼──────────┐                             │
│                    │     Exporters       │                             │
│                    │  CSV | Zephyr | JSON│                             │
│                    └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. End-to-End Flow: What Happens When You Click "Run"

### Scenario A: User uploads a requirements file via the Web UI

```
1. User opens browser → http://localhost:8000
   ↓
2. React frontend loads (SPA served by FastAPI)
   ↓
3. User clicks "Upload Requirements" → selects a .csv file
   ↓
4. Frontend POSTs to /api/requirements/upload (FastAPI)
   ↓
5. FastAPI route (api/routes/requirements.py) receives the file
   ↓
6. RequirementsReader reads the file → list of Requirement objects
   ↓
7. Requirements stored in ChromaDB (vector embeddings for semantic search)
   ↓
8. User clicks "Run Pipeline" → selects a pipeline config
   ↓
9. Frontend POSTs to /api/pipeline/run
   ↓
10. FastAPI creates a background task (api/tasks.py)
    ↓
11. PipelineOrchestrator loads the DAG from pipeline YAML
    ↓
12. Stage 1 fires: TestGenerationAgent
    ├── Reads requirements from artifact store
    ├── For each requirement:
    │   ├── ACClassifier classifies each acceptance criterion
    │   ├── PromptRenderer builds the LLM prompt
    │   ├── LLM client (Ollama) generates test case JSON
    │   ├── TestCaseSanitiser cleans the output
    │   └── TestCaseScorer scores it (0.0–1.0)
    ├── Returns list of TestCaseArtifact
    ↓
13. Stage 2 fires: BDDAgent (depends on Stage 1)
    ├── FeatureFileGenerator converts TCs → .feature files
    ├── GherkinValidator checks syntax
    ├── StepParser extracts and parameterizes steps
    ├── StepDefinitionGenerator creates skeleton code
    └── Returns FeatureFileArtifact + StepDefinitionArtifact
    ↓
14. Stage 3 fires in parallel: CrawlerAgent + APITestAgent
    ├── CrawlerAgent crawls the live app → SiteModelArtifact
    │   └── DiscrepancyDetector compares site vs requirements
    └── APITestAgent parses OpenAPI spec → APITestArtifact
    ↓
15. Stage 4 fires: EnrichmentAgent
    ├── Takes discrepancy report from Crawler
    ├── Generates additional TCs for each discrepancy
    └── Returns enriched TestCaseArtifact list
    ↓
16. Stage 5 fires: CoverageTracker
    ├── Maps TCs back to requirements
    ├── Identifies gaps and low-quality TCs
    └── Returns coverage report
    ↓
17. Pipeline completes → Exporters run
    ├── CSVExporter → output/test_cases.csv
    ├── ZephyrScaleExporter → output/zephyr_test_cases.csv
    └── JSONReportExporter → output/generation_report.json
    ↓
18. WebSocket pushes real-time progress to frontend throughout
    ↓
19. Frontend shows completion notification + download links
```

### Scenario B: User runs via CLI

```
1. User runs: python orchestrator.py --requirements reqs.csv
   ↓
2. Click parses arguments → run_orchestrator()
   ↓
3. Steps 1–5 run sequentially (no DAG, no parallelism)
   ↓
4. Rich console shows progress bars and summary table
   ↓
5. Files written to ./output/
```

---

## 3. The Pipeline: DAG-Based Execution

### How the DAG Works

The pipeline is a **Directed Acyclic Graph** — stages are nodes, dependencies are edges. This enables:

- **Parallel execution** — independent stages run simultaneously in "waves"
- **Retry logic** — failed stages retry with circuit breaker pattern
- **Timeout enforcement** — stages killed if they exceed configured timeout
- **Checkpointing** — wave state saved for crash recovery

### Pipeline Loading

**File:** `stlc_platform/pipeline/pipeline_loader.py`

```yaml
# Example: config/pipelines/default.yaml
stages:
  - stage_id: generate_tests
    agent_id: test_generation
    output_keys: [test_cases]

  - stage_id: generate_bdd
    agent_id: bdd_generation
    depends_on: [generate_tests]
    input_map:
      test_cases: generate_tests.test_cases

  - stage_id: crawl_app
    agent_id: web_crawler
    depends_on: [generate_tests]  # runs parallel to BDD

  - stage_id: enrich
    agent_id: enrichment_agent
    depends_on: [generate_bdd, crawl_app]
```

### Wave Execution

**File:** `stlc_platform/pipeline/orchestrator.py`

The orchestrator uses **Kahn's algorithm** for topological wave sort:

```
Wave 1: [generate_tests]          ← no dependencies, runs first
Wave 2: [generate_bdd, crawl_app]  ← both depend only on Wave 1, run in parallel
Wave 3: [enrich]                   ← depends on Wave 2, runs after both complete
Wave 4: [coverage_tracker]         ← depends on Wave 3
```

Each wave runs in a `ThreadPoolExecutor`. The orchestrator:
1. Resolves input artifacts for each stage
2. Injects skill context (coding standards, test design principles)
3. Applies circuit breaker (retry up to N times with backoff)
4. Enforces stage timeout
5. Collects metrics (quality scores, tokens, cost, duration)
6. Saves wave checkpoint
7. Moves to next wave

---

## 4. Core Infrastructure — Every File Explained

### `stlc_platform/core/` — The Foundation

This directory contains the shared infrastructure that ALL agents and pipeline components depend on.

---

#### `core/__init__.py` (1 line)
**Purpose:** Package marker with docstring: "Core infrastructure shared across all agents."
**Role:** Makes `stlc_platform.core` importable as a package.

---

#### `core/config_loader.py` (347 lines)
**Purpose:** The single source of truth for all configuration.

**How it works:**
1. Searches for project root (walks up looking for `pyproject.toml`, `config/stlc_config.yaml`, `.git/`)
2. Loads `config/stlc_config.yaml` as base config
3. Loads `.env` file via `python-dotenv`
4. Applies environment variable overrides (`STLC_` prefix)
5. Returns a singleton `AppConfig` dataclass

**Key dataclasses:**
- `OllamaConfig` — LLM settings (model, temperature, context window, timeout)
- `ChromaDBConfig` — vector store settings (persist dir, embedding model)
- `ZephyrConfig` — Jira export settings (project key, folder prefix)
- `OutputConfig` — file naming and output directory
- `AppConfig` — master config containing all above + test generation settings

**Who uses it:** Almost every module in the project. It's imported at module level by LLM clients, ChromaDB storage, exporters, CLI, API routes, and agents.

---

#### `core/contracts.py` (261 lines)
**Purpose:** Pydantic models that define the data flowing between agents.

**Think of this as the "API contract" between pipeline stages.** Every artifact has a `schema_version` field for backward compatibility.

**Key artifacts:**
| Artifact | Stage | Purpose |
|----------|-------|---------|
| `RequirementArtifact` | Input | Parsed requirement with ID, title, description, AC |
| `TestCaseArtifact` | Stage 1 | Generated test case with steps, GWT, quality score |
| `TestStepArtifact` | Stage 1 | Individual test step (action + expected result) |
| `FeatureFileArtifact` | Stage 2 | Gherkin .feature file content |
| `StepDefinitionArtifact` | Stage 2 | Step definition skeleton code |
| `PageElementArtifact` | Stage 3 | UI element discovered by crawler |
| `CrawledPageArtifact` | Stage 3 | Full page structure from crawler |
| `DiscrepancyArtifact` | Stage 3 | Gap between requirements and actual site |
| `DiscrepancyReportArtifact` | Stage 3 | Aggregated discrepancy findings |
| `SiteModelArtifact` | Stage 3 | Complete site structure |
| `APIEndpointArtifact` | Stage 3b | Single API endpoint definition |
| `APIModelArtifact` | Stage 3b | All API endpoints |
| `APITestArtifact` | Stage 3b | Generated API test code |
| `AgentFeedbackArtifact` | Stage 4 | User feedback for agent improvement |
| `PipelineRunArtifact` | Pipeline | Run metadata (duration, tokens, status) |

**Who uses it:** Every agent, every pipeline component, every API route, every exporter. It's the most imported file in the entire project.

---

#### `core/base_agent.py` (72 lines)
**Purpose:** Abstract base class that ALL agents must implement.

**Three key dataclasses:**
- `AgentCapabilities` — describes what an agent does (used for dynamic discovery)
- `ValidationResult` — input validation result (valid/errors/warnings)
- `AgentResult` — execution result (success/artifacts/metadata/tokens/duration)

**Two abstract methods every agent must implement:**
1. `validate_input(artifacts) -> ValidationResult` — checks if required inputs are present
2. `execute(artifacts, config) -> AgentResult` — does the actual work

**One concrete method:**
- `get_capabilities() -> AgentCapabilities` — returns agent metadata

**Who uses it:** All 5 agents inherit from this. The pipeline orchestrator uses it to discover and invoke agents uniformly.

---

#### `core/utils.py` (108 lines)
**Purpose:** Stateless utility functions used across modules.

**Functions:**
- `find_project_root()` — locates project root directory
- `slugify(text)` — "User Login" → "user-login"
- `truncate(text, max_length)` — truncates with suffix
- `deep_merge(base, override)` — recursive dict merge
- `ensure_dir(path)` — mkdir -p
- `safe_filename(name, extension)` — sanitizes for filesystem
- `flatten_dict(d)` — nested → dot notation
- `chunk_list(items, chunk_size)` — splits list into chunks

---

#### `core/logging_config.py` (56 lines)
**Purpose:** Loads logging from `config/logging.yaml`. Falls back to `basicConfig`.

**Functions:**
- `setup_logging()` — loads YAML config, resolves relative paths, creates `logs/` dir
- `get_logger(name)` — wrapper around `logging.getLogger()`

---

### `core/llm/` — LLM Abstraction Layer

#### `core/llm/__init__.py` (70 lines)
**Purpose:** Factory function `create_llm_client(provider)` that returns the right LLM client.

**Supported providers:** `ollama`, `openai`, `azure`, `anthropic`, `claude`

**How it works:** Reads `config.llm_provider` from config, imports the appropriate client class, and instantiates it. Uses try/except guards so missing optional packages (openai, anthropic) don't crash the app.

---

#### `core/llm/base_client.py` (438 lines)
**Purpose:** Abstract base for all LLM providers. Contains the most important logic in the entire LLM layer.

**Key features:**
- **Token tracking** — counts input/output tokens across all calls
- **Response caching** — SHA-256 keyed cache avoids redundant calls
- **JSON repair** — fixes truncated JSON (tracks bracket/brace state)
- **Hollow detection** — rejects empty/trivial responses
- **Retry with classified adaptation** — on failure, classifies the error type and adapts the prompt

**The retry strategy (Phase C — classified-retry):**
```
Attempt 1: Base temperature, original prompt
    ↓ (failure)
FailureClassifier analyzes the error:
  - TRUNCATION → "Please complete the response"
  - HOLLOW → "Be more specific, avoid generic phrases"
  - OFF_TOPIC → "Focus on the acceptance criterion"
  - REPETITIVE → "Do not repeat steps"
  - SCHEMA_VIOLATION → "Follow the JSON schema exactly"
  - INSTRUCTION_LEAKAGE → "Do not include prompt instructions"
    ↓
Attempt 2: Adapted prompt with slightly higher temperature
    ↓ (still fails)
Returns {"raw_response": ...} → triggers synthesise_tc() fallback
```

**`generate_test_case()` flow:**
1. Check cache (hit → return cached)
2. Call LLM with JSON schema
3. Strip `<think>` blocks (Qwen3 reasoning traces)
4. Repair truncated JSON
5. Parse against schema
6. Check for hollow response
7. On failure → classify → adapt → retry

---

#### `core/llm/ollama_client.py` (157 lines)
**Purpose:** Concrete implementation for local Ollama server.

**How it works:** Uses `requests` to call Ollama's `/api/chat` endpoint. Sends temperature, context window, repeat_penalty (1.15), top_k (40), top_p (0.9), and stop sequences. Extracts token counts from `prompt_eval_count` and `eval_count` in the response.

**Debug mode:** Set `DEBUG_LLM=1` env var to print full request/response.

---

#### `core/llm/openai_client.py` (159 lines)
**Purpose:** Concrete implementation for OpenAI API.

**How it works:** Uses `openai` Python SDK. Sets `response_format: {"type": "json_object"}` for structured output. API key from `STLC_LLM__API_KEY` env var.

---

#### `core/llm/anthropic_client.py` (157 lines)
**Purpose:** Concrete implementation for Anthropic Claude API.

**How it works:** Uses `anthropic` Python SDK. Anthropic uses `system` as a top-level parameter (not in messages). API key from `ANTHROPIC_API_KEY` or `STLC_LLM__API_KEY`.

---

#### `core/llm/cache.py` (169 lines)
**Purpose:** LRU cache for LLM responses.

**Cache key:** SHA-256 hash of `system_prompt + user_prompt + temperature`.

**Features:**
- In-memory LRU with configurable max size (default 500)
- Optional disk persistence to `llm_cache.json`
- Thread-safe (uses OrderedDict with lock)
- Tracks hits, misses, hit rate

---

#### `core/llm/failure_classifier.py` (422 lines)
**Purpose:** Classifies LLM output failures into 6 categories and recommends prompt adaptations.

**6 failure types (checked in priority order):**
1. **TRUNCATION** — unclosed brackets/braces, cut-off strings
2. **SCHEMA_VIOLATION** — missing required fields, wrong types
3. **INSTRUCTION_LEAKAGE** — prompt instructions appearing in response (12 patterns like "chain-of-thought", "think step by step")
4. **HOLLOW** — generic/empty content (14 indicators like "the system responds correctly")
5. **OFF_TOPIC** — response doesn't reference the target AC (term coverage < 20%)
6. **REPETITIVE** — duplicate steps or identical GWT clauses

---

#### `core/llm/pricing.py` (60 lines)
**Purpose:** Token-based cost estimation per provider/model.

**Prices (USD per 1K tokens):**
| Provider | Model | Input | Output |
|----------|-------|-------|--------|
| ollama | all | $0.000 | $0.000 |
| openai | gpt-4o | $0.0025 | $0.010 |
| openai | gpt-4o-mini | $0.00015 | $0.0006 |
| anthropic | claude-sonnet-4 | $0.003 | $0.015 |
| anthropic | claude-opus-4 | $0.015 | $0.075 |

---

### `core/storage/` — ChromaDB Vector Store

#### `core/storage/chroma_store.py` (587 lines)
**Purpose:** Manages 3 ChromaDB collections with Ollama embeddings and SentenceTransformer fallback.

**3 Collections:**

**1. `requirements`** — Stores requirements as vectors for semantic search
- `add_requirements()` — embeds and stores
- `search_similar()` — finds similar requirements (cosine similarity, threshold 0.3)
- `get_context_for_requirement()` — gets context for LLM prompt

**2. `tc_examples`** — Stores approved test cases as few-shot examples
- `store_approved_tc()` — stores a test case with metadata (AC type, test type, domain)
- `retrieve_examples()` — cascading filter: AC type + test type → AC type only → no filter
- `get_example_count()` — counts stored examples

**3. `domain_vocab`** — Stores screen names and UI elements
- `extract_and_store_vocab()` — extracts vocabulary from requirements using regex
- `lookup_component()` — finds the best screen name for a requirement
- `add_vocab()` — adds arbitrary terms (upsert, dedup by ID)

**Embedding fallback chain:**
```
1. Ollama embedding (qwen3-embedding:0.6b) — check if model available
2. Ollama live test — send test embedding request
3. SentenceTransformer (all-MiniLM-L6-v2) — if Ollama unavailable
4. ChromaDB default — if sentence-transformers not installed
5. None — embeddings disabled, vector store unusable
```

**Vocabulary extraction regex:**
- Screen patterns: `"User Login Screen"`, `"navigates to Dashboard"`, `"on the Checkout Page"`
- Element patterns: `"Submit" button`, `"Email" field`, `"password" input`
- Skip words: "the", "this", "user", "system", "app", etc.

---

### `core/quality/` — Quality Scoring & Deduplication

#### `core/quality/scorer.py` (617 lines)
**Purpose:** Deterministic (no LLM calls) quality scorer across 5 dimensions.

**5 Dimensions (weighted):**

| Dimension | Weight | What It Checks |
|-----------|--------|----------------|
| **Coverage** | 25% | Does TC reference target AC? Correct test_type alignment? Expected outcome mentions AC terms? |
| **Clarity** | 20% | Are steps specific (named elements, data values) vs generic? GWT distinctness? Concrete nouns? |
| **Executability** | 20% | Enough non-trivial steps? Verifiable results? Actionable preconditions? No identical steps? |
| **Uniqueness** | 15% | Jaccard similarity against existing TCs. Near-duplicate detection. |
| **Structural** | 20% | All fields present with min length? No truncation? No instruction leakage? No hollow steps? |

**Decision thresholds:**
- `≥ 0.65` → **accept** ✅
- `0.40 – 0.64` → **regenerate** 🔄
- `< 0.40` → **fallback** (use deterministic synthesiser) ❌

**Heuristics loaded from `config/test_generation_heuristics.yaml`:**
- 20 generic phrases to reject
- 11 instruction leak patterns
- Truncation markers

---

#### `core/quality/deduplicator.py` (196 lines)
**Purpose:** Cross-requirement near-duplicate detection using TF-IDF cosine similarity.

**No external dependencies** — TF-IDF implemented from scratch using plain dicts as sparse vectors.

**Algorithm:**
1. Extract text from all TCs (title + description + GWT + all step actions)
2. Build TF-IDF vectors (tokenization: `[a-z0-9]{3,}` regex)
3. Compare all pairs using cosine similarity
4. For each duplicate pair (similarity ≥ 0.85), keep the one with higher quality score
5. Return kept, removed, and duplicate pairs

---

## 5. The 5 Agents — How Each Works

### Agent 1: Requirements Agent (`stlc_platform/agents/requirements_agent/`)

**Purpose:** Parse requirements → generate test cases via LLM.

**This is the most complex agent with 16 files.**

#### Flow:

```
Input: List of RequirementArtifact
    │
    ▼
┌─────────────────────────────────────────────┐
│ TestGenerationAgent.execute()               │
│   ├── TechStackContext (platform verbs)     │
│   ├── ACClassifier (classify AC types)      │
│   ├── ComponentResolver (screen names)      │
│   ├── DomainDetector (auto-detect domain)   │
│   ├── PromptRenderer (build LLM prompt)     │
│   ├── LLMResponseCache (avoid redundant)    │
│   └── TestCaseSanitiser (clean output)      │
│                                             │
│   Calls: TestCaseGenerator.generate_for_all()│
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ For EACH requirement:                       │
│   1. Detect domain (financial, healthcare)  │
│   2. Extract vocab from requirements        │
│   3. Build slot plan (positive/neg/edge)    │
│   4. For EACH slot:                         │
│      a. Classify AC type                    │
│      b. Retrieve few-shot examples          │
│      c. Build prompt (system + user)        │
│      d. Call LLM → parse JSON               │
│      e. Sanitise output (7-step pipeline)   │
│      f. Score quality (5 dimensions)        │
│      g. If score < 0.40 → regenerate (2x)   │
│      h. If still bad → synthesise_tc()      │
│   5. Cross-requirement deduplication        │
│   6. Domain vocab enrichment                │
│   7. Auto-store high-quality TCs (≥0.80)    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
Output: List of TestCaseArtifact
```

#### File-by-file breakdown:

| File | Lines | Purpose |
|------|-------|---------|
| `agent.py` | 221 | Orchestrator — wires all components, calls generator |
| `reader.py` | 300 | Multi-format parser (txt, pdf, docx, csv, xlsx, json, md) |
| `classifier.py` | 288 | AC type classifier (keyword matching + LLM fallback) |
| `generator.py` | 579 | Core engine — generates TCs with quality loop |
| `sanitiser.py` | 429 | 7-step output cleaning pipeline |
| `prompts/__init__.py` | 336 | Jinja2 template renderer for LLM prompts |
| `prompts/_hints.py` | 275 | Type-specific hint text generation |
| `prompts/templates/*.j2` | — | System prompt, user prompt, feedback block, few-shot block |
| `component_resolver.py` | 95 | 4-tier component name resolution |
| `domain_detector.py` | 180 | Auto-detects domain from requirement keywords |
| `tech_stack.py` | 190 | Platform-aware verb substitution (web/mobile/api/desktop) |
| `synthesiser.py` | 326 | Deterministic fallback when LLM fails |
| `constants.py` | 190 | All shared constants (verbs, stopwords, generic phrases) |

**The 7-step sanitisation pipeline:**
1. Strip markdown formatting (bold, italic, backticks)
2. Fix common LLM typos (25+ corrections)
3. Validate description length (min 15 chars)
4. Validate preconditions (not generic, not instruction text)
5. Validate steps (not generic, no loops, no Python leakage)
6. Validate expected outcome (not trivial, references AC)
7. Validate GWT (not garbled, not truncated, not duplicate preconditions)

**The 4-tier component resolution:**
1. LLM returned a specific name (length > 15, not generic) → keep it
2. ChromaDB domain_vocab lookup → find matching screen
3. Config suffix map keyword match → "login" → "Login Screen"
4. Construct from category/title → "Category Screen"

---

### Agent 2: BDD Agent (`stlc_platform/agents/bdd_agent/`)

**Purpose:** Convert test cases → Gherkin feature files → step definitions → POM → project scaffold.

#### Flow:

```
Input: List of TestCaseArtifact
    │
    ▼
1. FeatureFileGenerator → .feature files
   ├── Groups TCs by requirement (one feature per req)
   ├── Detects Scenario Outlines (same steps, different data)
   └── Extracts Background (shared Given steps)
    │
    ▼
2. GherkinValidator → validates syntax
   ├── Checks Feature line, Scenario presence
   ├── Validates When/Then in each scenario
   ├── Checks Examples table for Outlines
   └── Detects duplicate scenario names
    │
    ▼
3. StepParser → extracts and parameterizes steps
   ├── Parses Given/When/Then/And/But
   ├── Deduplicates by normalized text
   └── Replaces quoted strings/numbers with {param}
    │
    ▼
4. StepDefinitionGenerator → skeleton code
   ├── Supports: behave, pytest-bdd, cucumber_java, cucumberjs
   ├── Injects CSS selectors from crawler site model
   └── Fuzzy-matches element names to selectors
    │
    ▼
5. POMGenerator → Page Object Model stubs
   ├── Extracts pages from component fields
   ├── Merges crawled selectors
   └── Generates class stubs with locators and actions
    │
    ▼
6. ProjectScaffolder → complete runnable project
   ├── Creates directory structure per framework
   ├── Generates behave.ini/pytest.ini/pom.xml/package.json
   ├── Generates environment.py/conftest.py
   └── Writes README with setup instructions
    │
    ▼
Output: FeatureFileArtifact[] + StepDefinitionArtifact[] + PageObjectStub[]
```

#### File-by-file breakdown:

| File | Lines | Purpose |
|------|-------|---------|
| `agent.py` | 253 | Orchestrator — 6-step BDD pipeline |
| `feature_generator.py` | 434 | TCs → Gherkin .feature files with Outline detection |
| `gherkin_validator.py` | 216 | Regex-based Gherkin syntax validation |
| `step_parser.py` | 202 | Extracts and parameterizes steps from Gherkin |
| `step_def_generator.py` | 483 | Generates step def code (4 frameworks) |
| `pom_generator.py` | 367 | Generates Page Object Model stubs |
| `scaffolder.py` | 468 | Assembles complete runnable project |
| `templates/*.j2` | — | 7 Jinja2 templates for features, steps, POMs |

---

### Agent 3: Crawler Agent (`stlc_platform/agents/crawler_agent/`)

**Purpose:** Crawl web applications → build site model → detect discrepancies vs requirements.

#### Flow:

```
Input: base_url OR html_pages OR site_model
    │
    ▼
Mode selection:
  ├── base_url → DynamicCrawler (Playwright BFS crawl)
  ├── html_pages → PageParser (BeautifulSoup static parse)
  └── site_model → DiscrepancyDetector only
    │
    ▼
DynamicCrawler (if base_url provided):
  ├── BFS crawl with max_depth=3, max_pages=100
  ├── Waits for network idle (SPA-friendly)
  ├── Captures XHR/Fetch API calls
  ├── Optional screenshots per page
  ├── Form-based authentication support
  └── Same-origin filtering
    │
    ▼
PageParser (for each page):
  ├── Extracts interactive elements (input, button, a, select)
  ├── Builds CSS selectors (#id > [data-testid] > [name] > .class)
  ├── Extracts forms with fields
  └── Truncates visible text to 200 chars
    │
    ▼
SiteModelBuilder:
  ├── Deduplicates pages by URL
  ├── Builds navigation graph (adjacency list)
  └── Infers base URL from first page
    │
    ▼
DiscrepancyDetector (if requirements provided):
  ├── Scans AC text for element patterns ("Submit button", "email input")
  ├── Checks if elements exist in site model
  ├── Checks form fields match requirements
  ├── Classifies severity (show_stopper/warning/info)
  └── Gate decision: block/proceed_with_warnings/proceed
    │
    ▼
CrawlerEmbeddingStore (optional):
  └── Embeds all pages in ChromaDB for semantic search
    │
    ▼
Output: SiteModelArtifact + DiscrepancyReportArtifact
```

#### File-by-file breakdown:

| File | Lines | Purpose |
|------|-------|---------|
| `agent.py` | 267 | Orchestrator — 3 input modes, discrepancy detection |
| `dynamic_crawler.py` | 380 | Playwright BFS crawler with API capture |
| `page_parser.py` | 250 | BeautifulSoup HTML parser |
| `site_model_builder.py` | 109 | Aggregates pages into site model |
| `discrepancy_detector.py` | 348 | Compares site model vs requirements |
| `embedding_store.py` | 221 | ChromaDB wrapper for crawled pages |

---

### Agent 4: API Test Agent (`stlc_platform/agents/api_test_agent/`)

**Purpose:** Parse OpenAPI/HAR/GraphQL specs → generate API test code in 4 frameworks.

#### Flow:

```
Input: openapi_spec OR har_data OR graphql_schema OR api_model
    │
    ▼
Parser selection:
  ├── OpenAPI 3.x → OpenAPIParser
  ├── Swagger 2.0 → OpenAPIParser (legacy mode)
  ├── HAR file → HARParser
  ├── GraphQL introspection → GraphQLParser
  └── GraphQL SDL → GraphQLParser (regex mode)
    │
    ▼
OpenAPIParser:
  ├── Auto-detects format (JSON/YAML, 3.x/2.0)
  ├── Extracts endpoints, params, request/response schemas
  ├── Resolves $ref pointers recursively
  ├── Detects auth (bearer/api_key/oauth2)
  └── Extracts examples from spec
    │
    ▼
APITestGenerator:
  ├── For each endpoint, generates test types:
  │   ├── happy_path → valid request, 200 response
  │   ├── auth → missing auth header, invalid token
  │   ├── validation → missing required fields
  │   ├── boundary → min/max values, empty strings
  │   ├── schema_validation → wrong types, extra fields
  │   └── crud_sequence → POST→GET→PUT→DELETE→GET(404)
  ├── Smart field value generation (heuristic name matching):
  │   ├── "email" → "user@example.com"
  │   ├── "phone" → "+1234567890"
  │   ├── "password" → "SecureP@ss123!"
  │   └── etc. (20+ field patterns)
  ├── Generates conftest.py with shared fixtures
  └── Renders via Jinja2 templates
    │
    ▼
TestClassifier:
  ├── Assigns test_level (api/integration/e2e)
  ├── Assigns failure_type (app_bug/test_bug/env_issue)
  └── Validates E2E pyramid (e2e < 20%)
    │
    ▼
Output: APITestArtifact[]
```

#### File-by-file breakdown:

| File | Lines | Purpose |
|------|-------|---------|
| `agent.py` | 202 | Orchestrator — 4 input modes, pyramid validation |
| `test_generator.py` | 715 | Core engine — 6 test types, 4 frameworks |
| `test_classifier.py` | 103 | Assigns test_level, failure_type, validates pyramid |
| `openapi_parser.py` | 449 | OpenAPI 3.x + Swagger 2.0 parser |
| `har_parser.py` | 322 | HTTP Archive file parser |
| `graphql_parser.py` | 282 | GraphQL introspection + SDL parser |
| `templates/*.j2` | — | 5 templates (pytest, rest_assured, karate, supertest, conftest) |

---

### Agent 5: Enrichment Agent (`stlc_platform/agents/enrichment_agent/`)

**Purpose:** Cross-agent feedback — generates test cases for every crawler discrepancy.

#### Flow:

```
Input: test_cases + discrepancy_report (optional)
    │
    ▼
If no discrepancy_report:
  └── Return original test_cases unchanged (fast path)
    │
    ▼
If discrepancy_report provided:
  └── For each discrepancy item:
      ├── Synthesise TC with ID: TC-DISC-XXXX
      ├── Test level: e2e
      ├── Tags: discrepancy, auto-generated, {discrepancy_type}
      ├── Priority: based on severity (show_stopper→Critical)
      └── Steps: navigate → locate → verify
    │
    ▼
Output: Enriched TestCaseArtifact list
```

#### File-by-file breakdown:

| File | Lines | Purpose |
|------|-------|---------|
| `agent.py` | 212 | Orchestrator — synthesises discrepancy TCs |

---

## 6. API Layer — REST + WebSocket

### `stlc_platform/api/` — FastAPI Backend

#### `api/main.py` (217 lines)
**Purpose:** FastAPI application entry point.

**What it sets up:**
1. CORS middleware (allows frontend requests)
2. Rate limiting via `slowapi`
3. WebSocket endpoint (`/ws/pipeline/{run_id}`)
4. Health check (`/api/health`)
5. Global exception handlers
6. SPA frontend serving in production (serves `frontend/dist/`)
7. API versioning (v0.5.0)

**Startup event:**
- Sets up logging
- Initializes agent registry
- Loads pipeline configurations
- Starts WebSocket manager

---

#### `api/routes/` — Route Modules

| Route File | Endpoints | Purpose |
|------------|-----------|---------|
| `requirements.py` | POST `/upload`, GET `/list` | Upload and list requirements |
| `test_cases.py` | GET `/list`, GET `/{tc_id}`, PATCH `/{tc_id}` | View, filter, edit test cases |
| `pipeline.py` | POST `/run`, GET `/{run_id}`, GET `/list` | Trigger and monitor pipeline runs |
| `agents.py` | GET `/list`, GET `/{id}` | List registered agents and capabilities |
| `feedback.py` | POST `/add`, GET `/list` | Submit and view feedback |
| `metrics.py` | GET `/list`, GET `/trends`, GET `/run/{id}` | Quality metrics and trends |
| `config.py` | GET `/get`, POST `/save` | View and update configuration |
| `bdd.py` | POST `/generate` | Trigger BDD generation |
| `crawler.py` | POST `/start`, GET `/status` | Start and monitor web crawl |
| `api_tests.py` | POST `/generate` | Trigger API test generation |
| `artifacts.py` | GET `/list`, GET `/{id}` | View pipeline artifacts |
| `auth.py` | POST `/login`, POST `/key` | Authentication endpoints |
| `files.py` | POST `/upload`, GET `/download` | File upload/download |

---

#### `api/websocket.py`
**Purpose:** WebSocket connection manager for real-time pipeline progress.

**How it works:**
1. Client connects to `/ws/pipeline/{run_id}`
2. WebSocketManager tracks connections per run_id
3. Pipeline orchestrator broadcasts stage updates
4. Frontend receives JSON messages: `{"stage": "generate_tests", "status": "running", "progress": 0.5}`

---

#### `api/auth.py`
**Purpose:** JWT and API key authentication.

**How it works:**
- API key: `X-API-Key` header checked against `STLC_API_KEY` env var
- JWT: Bearer token with configurable secret
- Disabled by default (`STLC_AUTH_ENABLED=false`)

---

#### `api/deps.py`
**Purpose:** FastAPI dependency injection.

**Provides:**
- Agent registry instance
- WebSocket manager instance
- Config loader instance

---

#### `api/tasks.py`
**Purpose:** Background task handling.

**How it works:**
- Pipeline runs are submitted as background tasks
- Task status tracked in memory
- Results stored in artifact store
- WebSocket broadcasts progress updates

---

#### `api/schemas.py`
**Purpose:** Pydantic request/response schemas for API endpoints.

---

## 7. Frontend Dashboard

### `frontend/` — React SPA

**Tech Stack:** React 18 + TypeScript + Vite + TailwindCSS + Recharts + React Router + Lucide Icons + Axios

#### How it connects to the backend:

```
Browser → http://localhost:8000
    │
    ▼
FastAPI serves frontend/dist/index.html (production)
OR Vite dev server on :5173 (development)
    │
    ▼
React app initializes:
  ├── Axios configured with base URL (API base)
  ├── React Router for navigation
  └── WebSocket connection for pipeline updates
    │
    ▼
Pages:
  ├── Dashboard — overview metrics, recent runs
  ├── Pipeline — run pipeline, monitor progress
  ├── Test Cases — browse, filter, edit TCs
  ├── Agents — view registered agents
  ├── Metrics — quality trends, cost charts
  ├── Feedback — review and approve TCs
  └── Settings — edit configuration
```

#### Key frontend files:

| Path | Purpose |
|------|---------|
| `frontend/src/main.tsx` | React entry point |
| `frontend/src/App.tsx` | Router configuration |
| `frontend/src/api/` | Axios API client functions |
| `frontend/src/components/` | Reusable UI components |
| `frontend/src/pages/` | Page components |
| `frontend/src/hooks/` | Custom React hooks |
| `frontend/src/types/` | TypeScript type definitions |
| `frontend/src/store/` | State management |

---

## 8. Configuration System

### Three-Layer Configuration

```
Layer 1: config/stlc_config.yaml (base defaults)
    │
    ▼
Layer 2: .env file (legacy overrides)
    │
    ▼
Layer 3: Environment variables (STLC_ prefix, highest priority)
```

### Config Files

| File | Purpose |
|------|---------|
| `config/stlc_config.yaml` | Base configuration — LLM, ChromaDB, test generation, quality gates, coverage, circuit breaker, metrics |
| `config/stlc_config.api.yaml` | API-specific profile overlay |
| `config/stlc_config.web.yaml` | Web-specific profile overlay |
| `config/stlc_config.schema.json` | JSON Schema for config validation |
| `config/heuristics.yaml` | Crawler heuristics (page keywords, element patterns) |
| `config/test_generation_heuristics.yaml` | Generic phrases, instruction leak patterns, truncation markers |
| `config/logging.yaml` | Logging configuration |

### Pipeline Definitions

| File | Purpose |
|------|---------|
| `config/pipelines/default.yaml` | Standard 5-stage pipeline |
| `config/pipelines/smoke.yaml` | Quick validation (Stages 1 + export) |
| `config/pipelines/regression.yaml` | Full pipeline with all stages |

### Execution Profiles

| File | Purpose |
|------|---------|
| `config/profiles/smoke.yaml` | Fast run — only essential stages |
| `config/profiles/targeted.yaml` | Medium run — includes BDD |
| `config/profiles/regression.yaml` | Full run — all stages |

### Skill Files

| File | Purpose |
|------|---------|
| `config/skills/common/test_design_principles.yaml` | Test design best practices injected into agent prompts |
| `config/skills/common/coding_standards.yaml` | Coding standards for generated code |
| `config/skills/ecommerce/data_catalog.yaml` | E-commerce specific test data patterns |

---

## 9. Root-Level Modules (Legacy)

These are the original standalone modules that still work independently of the platform.

| File | Lines | Purpose |
|------|-------|---------|
| `orchestrator.py` | 280 | Original CLI entry point — 5-step sequential pipeline with Click |
| `run_pipeline.py` | 438 | Modern pipeline runner — uses `stlc_platform` package, supports `--fixtures` mode |
| `mcp_server.py` | 737 | MCP server — exposes tools for Claude Desktop + standalone CLI mode |
| `config.py` | 83 | Legacy config (dataclass-based, superseded by `core/config_loader.py`) |
| `requirements_reader.py` | 319 | Legacy multi-format parser (superseded by `agents/requirements_agent/reader.py`) |
| `chroma_store.py` | 487 | Legacy ChromaDB store (superseded by `core/storage/chroma_store.py`) |
| `llm_client.py` | 486 | Legacy Ollama client (superseded by `core/llm/ollama_client.py`) |
| `test_generator.py` | ~1300 | Legacy test generator (superseded by `agents/requirements_agent/generator.py`) |
| `environment.py` | 71 | Behave BDD test environment hooks |
| `generate_docs.py` | — | Documentation generation script |
| `chromadb_diagnose.py` | — | ChromaDB diagnostic utility |
| `fix_chromadb.py` | — | ChromaDB fix utility |

**Why both exist:** The root-level modules are standalone scripts that work without the full platform. They're useful for quick one-off runs. The `stlc_platform/` package is the modern architecture with proper abstractions, multi-provider support, and the agent/pipeline system.

---

## 10. Exporters

### `exporters/exporters.py` (253 lines)

Three exporters that convert test cases into output files:

| Exporter | Output | Columns/Format |
|----------|--------|----------------|
| **CSVExporter** | `test_cases.csv` | 17 columns: TC ID, Req ID, Title, Description, Preconditions, Test Type, Priority, Category, Component, Steps, Expected Outcome, Given, When, Then, Tags, Est. Duration, Generated At |
| **ZephyrScaleExporter** | `zephyr_test_cases.csv` | Jira import-ready: Name, Status, Priority, Component, Labels, Description, Precondition, Test Script (Step-by-Step), Test Script (Plain Text), Folder, Requirement, Est. Time, Owner |
| **JSONReportExporter** | `generation_report.json` | Model used, summary stats, breakdown by type/priority, per-req counts, individual TC summaries |

**How they work:**
1. Pipeline completes with test cases
2. Exporters iterate over TestCaseArtifact list
3. Each exporter formats data according to its schema
4. Files written to `config.output.output_dir` (default: `./output/`)

---

## 11. Complete Dependency Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                                 │
│                                                                     │
│  orchestrator.py ──→ Click CLI ──→ sequential pipeline             │
│  run_pipeline.py ──→ Click CLI ──→ modular pipeline                │
│  mcp_server.py ──→ MCP/CLI ──→ ChromaDB tools                       │
│  stlc_platform/cli.py ──→ Click CLI ──→ full platform              │
│  stlc_platform/api/main.py ──→ FastAPI ──→ web + REST              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     CONFIGURATION LAYER                             │
│                                                                     │
│  config_loader.py ←── stlc_config.yaml + .env + env vars           │
│       │                                                           │
│       ├──→ All LLM clients (model, temperature, timeout)           │
│       ├──→ ChromaDB storage (persist dir, embedding model)         │
│       ├──→ Exporters (output dir, filenames)                       │
│       ├──→ Agents (max tests, include negative/edge, format)       │
│       └──→ Pipeline (quality gates, circuit breaker, metrics)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       CORE LAYER                                    │
│                                                                     │
│  contracts.py ──→ Pydantic models (data flowing between agents)    │
│  base_agent.py ──→ ABC (all agents inherit this)                   │
│  utils.py ──→ helpers (slugify, deep_merge, etc.)                  │
│  logging_config.py ──→ logging setup                               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  llm/                                                        │   │
│  │  base_client.py ──→ ABC + retry + cache + JSON repair       │   │
│  │  ollama_client.py ──→ local LLM                             │   │
│  │  openai_client.py ──→ cloud LLM (optional)                 │   │
│  │  anthropic_client.py ──→ cloud LLM (optional)              │   │
│  │  cache.py ──→ LRU response cache                            │   │
│  │  failure_classifier.py ──→ error classification + retry     │   │
│  │  pricing.py ──→ cost estimation                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  storage/                                                    │   │
│  │  chroma_store.py ──→ 3-collection ChromaDB vector store     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  quality/                                                    │   │
│  │  scorer.py ──→ 5-dimension quality scoring                  │   │
│  │  deduplicator.py ──→ TF-IDF near-duplicate detection        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PIPELINE LAYER                                 │
│                                                                     │
│  dag.py ──→ DAG definition + topological wave sort                 │
│  orchestrator.py ──→ ThreadPoolExecutor + circuit breaker          │
│  agent_registry.py ──→ agent discovery + plugin support            │
│  artifact_store.py ──→ in-memory + disk artifact storage           │
│  pipeline_loader.py ──→ loads pipeline YAML into DAG               │
│  profile_loader.py ──→ execution profile loader                    │
│  skill_loader.py ──→ skill context injection                       │
│  circuit_breaker.py ──→ retry management                           │
│  coverage_tracker.py ──→ requirement-to-TC coverage                │
│  feedback_store.py ──→ persistent feedback storage                 │
│  metrics_collector.py ──→ run metrics + degradation detection      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENT LAYER                                  │
│                                                                     │
│  requirements_agent/ ──→ 16 files ──→ parse reqs, generate TCs     │
│  bdd_agent/ ──→ 14 files ──→ Gherkin, step defs, POM, scaffold     │
│  crawler_agent/ ──→ 7 files ──→ crawl, site model, discrepancies   │
│  api_test_agent/ ──→ 12 files ──→ OpenAPI/HAR/GraphQL → test code  │
│  enrichment_agent/ ──→ 2 files ──→ discrepancy-derived TCs         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       API LAYER                                     │
│                                                                     │
│  main.py ──→ FastAPI app + CORS + rate limit + SPA serving         │
│  routes/ ──→ 13 route modules (requirements, TCs, pipeline, etc.)  │
│  websocket.py ──→ real-time progress broadcast                     │
│  auth.py ──→ JWT + API key authentication                          │
│  deps.py ──→ dependency injection                                  │
│  schemas.py ──→ request/response Pydantic models                   │
│  tasks.py ──→ background task handling                             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                                  │
│                                                                     │
│  React 18 + TypeScript + Vite + TailwindCSS                        │
│  Pages: Dashboard, Pipeline, Test Cases, Agents, Metrics,          │
│         Feedback, Settings                                         │
│  WebSocket connection for real-time pipeline monitoring            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXPORT LAYER                                   │
│                                                                     │
│  CSVExporter ──→ output/test_cases.csv                             │
│  ZephyrScaleExporter ──→ output/zephyr_test_cases.csv              │
│  JSONReportExporter ──→ output/generation_report.json              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 12. Data Flow: Artifact Contracts

### How Data Flows Between Agents

```
┌──────────────────────────────────────────────────────────────────┐
│                    ARTIFACT FLOW                                 │
│                                                                  │
│  User uploads:                                                   │
│  requirements.csv ──→ RequirementArtifact[]                     │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 1: Requirements Agent                              │   │
│  │  Input:  RequirementArtifact[]                           │   │
│  │  Output: TestCaseArtifact[]                              │   │
│  │                                                          │   │
│  │  For each requirement:                                   │   │
│  │    RequirementArtifact ──→ ACClassifier                  │   │
│  │                           ──→ PromptRenderer             │   │
│  │                           ──→ LLM (Ollama)               │   │
│  │                           ──→ JSON parse                 │   │
│  │                           ──→ Sanitiser                  │   │
│  │                           ──→ Scorer                     │   │
│  │                           ──→ TestCaseArtifact           │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 2: BDD Agent                                       │   │
│  │  Input:  TestCaseArtifact[]                              │   │
│  │  Output: FeatureFileArtifact[] + StepDefinitionArtifact[]│   │
│  │                                                          │   │
│  │  TestCaseArtifact ──→ FeatureFileGenerator ──→ .feature  │   │
│  │                  ──→ StepParser ──→ StepDefGenerator     │   │
│  │                  ──→ POMGenerator ──→ PageObjectStub[]   │   │
│  │                  ──→ ProjectScaffolder                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 3a: Crawler Agent                                  │   │
│  │  Input:  base_url + RequirementArtifact[]                │   │
│  │  Output: SiteModelArtifact + DiscrepancyReportArtifact   │   │
│  │                                                          │   │
│  │  base_url ──→ DynamicCrawler ──→ pages                  │   │
│  │              ──→ PageParser ──→ CrawledPageArtifact[]    │   │
│  │              ──→ SiteModelBuilder ──→ SiteModelArtifact  │   │
│  │              ──→ DiscrepancyDetector ──→ Report          │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 3b: API Test Agent                                 │   │
│  │  Input:  openapi_spec (JSON/YAML)                        │   │
│  │  Output: APITestArtifact[]                               │   │
│  │                                                          │   │
│  │  OpenAPI ──→ OpenAPIParser ──→ APIModelArtifact          │   │
│  │              ──→ APITestGenerator ──→ APITestArtifact[]  │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 4: Enrichment Agent                                │   │
│  │  Input:  TestCaseArtifact[] + DiscrepancyReportArtifact  │   │
│  │  Output: Enriched TestCaseArtifact[]                     │   │
│  │                                                          │   │
│  │  DiscrepancyArtifact ──→ synthesise TC ──→ TC-DISC-XXXX  │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Stage 5: Coverage Tracker                                │   │
│  │  Input:  TestCaseArtifact[] + RequirementArtifact[]      │   │
│  │  Output: CoverageReport                                  │   │
│  │                                                          │   │
│  │  Maps TCs → Requirements, identifies gaps               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Final: Exporters convert artifacts → CSV/Zephyr/JSON files     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 13. CLI Entry Points

### Three Ways to Run

#### 1. Legacy Orchestrator (`orchestrator.py`)
```bash
python orchestrator.py --requirements reqs.csv [--format csv|zephyr|both]
                       [--model MODEL] [--max-tests N] [--output-dir DIR]
                       [--clear-db] [--no-chroma] [--skip-llm-check]
```
**What happens:** Sequential 5-step pipeline with Rich console output. No DAG, no parallelism.

#### 2. Pipeline Runner (`run_pipeline.py`)
```bash
python run_pipeline.py --requirements reqs.csv [--fixtures]
                       [--profile smoke|targeted|regression]
                       [--provider ollama|openai|anthropic]
```
**What happens:** Uses `stlc_platform` package architecture. Supports execution profiles and fixture mode (built-in ecommerce/healthcare/banking samples).

#### 3. Full Platform CLI (`stlc_platform/cli.py`)
```bash
stlc run --pipeline config/pipelines/default.yaml [--profile smoke]
stlc run --agent test_generation --input requirements.json
stlc validate --stage 0
stlc agents list
stlc feedback add/list
stlc metrics list/trends/run
stlc optimise --input output/test_cases.csv
```
**What happens:** Full platform CLI with agent management, feedback, metrics, and validation commands. Supports `--ci` flag for JSON output.

#### 4. MCP Server (`mcp_server.py`)
```bash
python mcp_server.py              # Start MCP server for Claude Desktop
python mcp_server.py stats        # ChromaDB statistics
python mcp_server.py validate-tc TC-001  # Score a test case
python mcp_server.py repair-tc TC-001    # Repair a test case
python mcp_server.py store-example TC-001  # Store as few-shot
python mcp_server.py list-examples  # List stored examples
python mcp_server.py vocab          # Domain vocabulary summary
```

---

## Appendix A: File Count Summary

| Directory | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| `stlc_platform/core/` | 19 | ~3,692 | Core infrastructure |
| `stlc_platform/agents/requirements_agent/` | 16 | ~3,471 | Test case generation |
| `stlc_platform/agents/bdd_agent/` | 14 | ~2,941 | BDD generation |
| `stlc_platform/agents/crawler_agent/` | 7 | ~1,672 | Web crawling |
| `stlc_platform/agents/api_test_agent/` | 12 | ~2,852 | API test generation |
| `stlc_platform/agents/enrichment_agent/` | 2 | ~214 | Enrichment |
| `stlc_platform/pipeline/` | ~12 | ~2,500 | Pipeline orchestration |
| `stlc_platform/api/` | ~18 | ~2,000 | REST API |
| `stlc_platform/exporters/` | 1 | ~237 | Exporters |
| `exporters/` (legacy) | 1 | ~253 | Legacy exporters |
| Root-level modules | 12 | ~4,000 | Legacy standalone scripts |
| **Total** | **~114** | **~23,830** | |

---

## Appendix B: Key Design Patterns

| Pattern | Where Used | Why |
|---------|------------|-----|
| **Abstract Base Class** | `BaseAgent`, `BaseLLMClient` | Enforce interfaces, fail-fast on missing implementations |
| **Factory Pattern** | `create_llm_client()`, `PipelineDAG` | Dynamic provider/stage creation |
| **Singleton** | `config = load_config()` | Single source of truth, loaded once |
| **Strategy Pattern** | 3 LLM clients, 4 API test frameworks | Swap implementations without changing callers |
| **Chain of Responsibility** | 4-tier component resolution, 5-tier embedding fallback | Try each strategy in priority order |
| **Circuit Breaker** | Pipeline stage retry | Prevent cascading failures |
| **Observer Pattern** | WebSocket progress broadcast | Real-time UI updates |
| **Template Method** | Jinja2 templates for code generation | Framework-specific code from shared logic |
| **Repository Pattern** | `ArtifactStore`, `FeedbackStore` | Abstract data access |
| **Quality Gate** | `TestCaseScorer` + retry loop | Self-correcting generation |
| **Versioned Contracts** | `schema_version` on all artifacts | Backward compatibility |
