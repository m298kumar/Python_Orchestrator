# AI Test Case Orchestrator — STLC Automation Platform

**Automatically generate, validate, and manage test cases from requirements using local or cloud LLMs, ChromaDB semantic search, and a multi-agent pipeline — with BDD generation, API testing, web crawling, and a full web dashboard.**

---

## 📋 Project Overview

The **Python Orchestrator** is an AI-powered Software Testing Life Cycle (STLC) automation platform. It reads requirements in virtually any format, uses LLMs (Ollama, OpenAI, Anthropic) to intelligently generate test cases, validates them with quality scoring, and exports them to CSV, Zephyr Scale, or JSON. Beyond test generation, it includes a web crawler for UI discrepancy detection, an API test generator, a BDD feature file generator, and a real-time web dashboard — all orchestrated through a DAG-based pipeline.

### 💡 Why This Project?

Manual test case creation is tedious, error-prone, and often inconsistent across team members. This platform solves that by:

- **Reducing test design time** from hours to minutes per requirement
- **Ensuring consistency** through AI-driven standardisation and quality scoring
- **Catching edge cases** that humans often miss (negative tests, boundary values, security scenarios)
- **Building institutional knowledge** via the ChromaDB feedback loop — the system gets smarter with every approved test case
- **Supporting the full STLC** — not just test case generation, but BDD features, API tests, and UI validation in one pipeline

---

## ✨ Features

### 🧠 AI-Powered Test Generation
- **Multi-format requirement parsing** — `.txt`, `.md`, `.csv`, `.xlsx`, `.json`, `.pdf`, `.docx`
- **Acceptance Criteria Type Classification** — 6 AC types: eligibility, UI behaviour, timing, data validation, security, general
- **Type-specific prompt engineering** — tailored hints for positive, negative, and edge case scenarios
- **Few-shot learning** — retrieves approved test examples from ChromaDB for consistent quality
- **Dynamic component resolution** — maps screen/UI elements via ChromaDB vocabulary + static suffix maps
- **Output sanitisation** — loop detection, generic step filtering, hallucination prevention, Python dict leakage detection

### 🔬 ChromaDB Vector Store
- **Semantic search** — prevents duplicate test cases by understanding requirement context
- **Approved example feedback loop** — store high-quality test cases to improve future generations
- **Domain vocabulary extraction** — automatically extracts screen names and UI elements for component resolution
- **Ollama embeddings** with SentenceTransformer fallback

### 🤖 Multi-Agent Architecture
| Agent | Capability |
|-------|-----------|
| **Requirements Agent** | Parses requirements, classifies AC types, generates test cases |
| **BDD Agent** | Generates Gherkin feature files and step definition skeletons |
| **Crawler Agent** | Crawls web apps (Playwright/BeautifulSoup), builds site models, detects discrepancies vs requirements |
| **API Test Agent** | Generates API tests from OpenAPI specs in 4 frameworks: pytest, Rest Assured, Karate, Supertest |
| **Enrichment Agent** | Improves existing test cases with feedback and quality enhancements |

### 📊 Quality & Coverage
- **Quality scoring** (0.0–1.0) across 5 dimensions: coverage, clarity, executability, uniqueness, structure
- **Test case deduplication** — removes redundant generated tests
- **Coverage tracking** — maps test cases to requirements, identifies gaps, auto-fills missing coverage
- **Degradation detection** — monitors quality trends across pipeline runs

### 🔌 Multi-Provider LLM Support
- **Ollama** (local, default) — llama3.2, mistral, qwen, and more
- **OpenAI** (cloud, optional)
- **Anthropic** (cloud, optional)
- **LLM caching** — reduces token costs on repeated prompts

### 🌐 Web Dashboard
- **React 18 + TypeScript + Vite + TailwindCSS** frontend
- **Real-time pipeline monitoring** via WebSocket
- **Test case viewing, metrics visualization, agent management**
- **Feedback management and configuration UI**

### 📤 Export Formats
- **Standard CSV** — 17-column test case export
- **Zephyr Scale CSV** — Jira import-ready format
- **JSON Report** — generation metadata, statistics, quality scores

### 🛠️ MCP Server (Model Context Protocol)
- Expose orchestrator as tools for Claude Desktop and other MCP clients
- Tools: validate test cases (scored 0–100), repair test cases, store approved examples, retrieve few-shot examples, domain vocabulary summary

### 🐳 Docker & CI/CD
- **Multi-stage Docker build** — Node.js frontend + Python backend, non-root user, health checks
- **Docker Compose** — app + Ollama services with GPU support
- **GitHub Actions CI/CD** — linting, type checking, security scans, unit/integration tests, Docker Trivy scanning

### 🌍 Domain Awareness
The platform automatically detects your application domain and tailors test generation accordingly:

| Domain | Keywords Detected |
|--------|------------------|
| **Financial Services** | cheque, banking, deposit, transaction, account, ledger, transfer, payment |
| **Healthcare** | patient, clinical, ehr, prescription, pharmacy, diagnosis, medical |
| **Retail / E-Commerce** | product, cart, checkout, inventory, catalogue, order, shipping |
| **Insurance** | policy, claim, premium, underwriting |
| **Education** | student, course, enrol, grade, curriculum, lms |
| **IT Service Management** | ticket, incident, asset, sla, helpdesk, itil |

---

## 🔍 How It Works — Step by Step

### Step 1: Ingest Requirements
Drop in any requirements file — CSV, Excel, PDF, Word doc, or plain text. The `RequirementsReader` parses it into structured objects with ID, title, description, priority, category, and acceptance criteria. Flexible column name matching means your existing spreadsheets work out of the box.

### Step 2: Store in ChromaDB
Each requirement is embedded and stored in ChromaDB's vector store. This enables:
- **Semantic deduplication** — the LLM sees what tests already exist and avoids repeating them
- **Few-shot retrieval** — approved test examples are fetched as context for the LLM
- **Domain vocabulary** — screen names and UI elements are extracted and indexed

### Step 3: Classify Acceptance Criteria
Every acceptance criterion is classified into one of 6 types:

| AC Type | Example | Generated Test Focus |
|---------|---------|---------------------|
| **Eligibility** | "User must be 18+ to register" | Boundary values, threshold tests |
| **UI Behaviour** | "Submit button is disabled until form is valid" | State transitions, visual validation |
| **Timing** | "Session expires after 30 minutes" | Timeout, scheduling, real-time tests |
| **Data Validation** | "Email must be valid format" | Format checks, length limits, pattern matching |
| **Security** | "Password must be encrypted" | Auth flows, injection, access control |
| **General** | "User can view their profile" | Standard CRUD, navigation |

### Step 4: Generate Test Cases
The LLM receives a type-specific prompt with:
- The requirement details
- Classified AC type with tailored hints
- Few-shot examples from ChromaDB (if available)
- Domain context and component resolution
- Chain-of-thought instructions for thorough reasoning

Output is strict JSON with Gherkin-style steps (Given/When/Then).

### Step 5: Sanitise & Score
Every generated test case passes through a multi-layer sanitiser:
1. **Loop detection** — catches repetitive/generic step patterns
2. **Instruction text filtering** — removes LLM meta-commentary
3. **Generic step detection** — flags vague steps like "verify the result"
4. **Python dict leakage detection** — catches raw JSON/dict output
5. **Hollow response detection** — rejects empty or near-empty outputs

Then a quality scorer rates each test case 0.0–1.0 across 5 dimensions:
- **Coverage** (25%) — how well the test covers the requirement
- **Clarity** (20%) — readability and understandability
- **Executability** (20%) — can a human or automation run it?
- **Uniqueness** (15%) — is it distinct from other generated tests?
- **Structural** (20%) — proper format, complete steps, expected outcomes

Tests scoring below 0.4 are flagged for regeneration. Tests above 0.65 are accepted.

### Step 6: Export & Feedback
Test cases are exported to your chosen format. After review, you can store approved examples back into ChromaDB via the MCP server, creating a continuous improvement loop where each generation cycle produces better quality output.

---

## 📝 Example Input & Output

### Sample Requirements CSV

```csv
id,title,description,priority,category,acceptance_criteria
REQ-001,User Login Authentication,"Users authenticate with email and password. System validates credentials and creates a session.",High,Security,"Valid login redirects to dashboard; Invalid shows error; Account locks after 5 fails"
REQ-002,Password Reset via Email,"Forgotten password reset via email link. Link expires after 24 hours.",High,Security,"Email delivered in 60s; Link valid 24h; Link one-time use"
REQ-003,Product Search,"Users can search products by keyword, category, price range, and rating.",High,E-Commerce,"Search returns relevant results; Filters work correctly; Results paginated"
```

### Generated Test Case (CSV Output)

| TC ID | Req ID | Title | Type | Priority | Steps |
|-------|--------|-------|------|----------|-------|
| TC-001 | REQ-001 | Verify successful login with valid credentials | Positive | High | 4 |
| TC-002 | REQ-001 | Verify login with invalid password | Negative | High | 3 |
| TC-003 | REQ-001 | Verify account lockout after 5 failed attempts | Edge | Critical | 5 |
| TC-004 | REQ-001 | Verify login with SQL injection attempt | Security | Critical | 3 |
| TC-005 | REQ-001 | Verify login with empty email field | Negative | Medium | 3 |
| TC-006 | REQ-001 | Verify session creation after successful login | Positive | High | 4 |

### Generated Test Case (Gherkin Format)

```gherkin
Feature: User Login Authentication

  Scenario: Verify successful login with valid credentials
    Given the user is on the Login Screen
    When the user enters a valid email address in the email field
    And the user enters the correct password in the password field
    And the user clicks the Login button
    Then the user is redirected to the Dashboard
    And a session is created for the user
```

### JSON Generation Report

```json
{
  "model": "llama3.2",
  "total_requirements": 5,
  "total_test_cases": 28,
  "avg_quality_score": 0.78,
  "breakdown_by_type": {
    "positive": 10,
    "negative": 11,
    "edge": 5,
    "security": 2
  },
  "breakdown_by_priority": {
    "Critical": 4,
    "High": 14,
    "Medium": 8,
    "Low": 2
  }
}
```

---

## 🌐 API Reference

The FastAPI backend exposes a comprehensive REST API. Full docs available at `http://localhost:8000/docs` (Swagger UI) when the server is running.

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/requirements/upload` | Upload requirements file |
| `POST` | `/api/pipeline/run` | Trigger pipeline execution |
| `GET` | `/api/pipeline/{run_id}` | Get pipeline run status |
| `GET` | `/api/test-cases` | List generated test cases |
| `GET` | `/api/test-cases/{tc_id}` | Get specific test case |
| `POST` | `/api/feedback/add` | Submit feedback on a test case |
| `GET` | `/api/metrics/trends` | Quality score trends |
| `GET` | `/api/agents` | List registered agents |
| `POST` | `/api/crawler/start` | Start web crawl |
| `POST` | `/api/api-tests/generate` | Generate API tests from OpenAPI spec |
| `WS` | `/ws/pipeline/{run_id}` | Real-time pipeline progress via WebSocket |

### Authentication

The API supports JWT and API key authentication (disabled by default via `STLC_AUTH_ENABLED=false`). Enable it in production:

```env
STLC_AUTH_ENABLED=true
STLC_API_KEY=your-secret-key
STLC_JWT_SECRET=your-jwt-secret
```

---

## 🏗️ Architecture

```
requirements_file (.txt/.csv/.xlsx/.pdf/.docx/.json)
         │
         ▼
 ┌─────────────────────────────────────────────┐
 │           Config Layer                      │
 │  stlc_config.yaml + env vars + profiles     │
 └──────────────────┬──────────────────────────┘
                    ▼
 ┌─────────────────────────────────────────────┐
 │         Pipeline Orchestrator (DAG)         │
 │  Parallel wave execution with circuit       │
 │  breaker, retry, timeout, checkpointing     │
 └────┬────┬────┬────┬────┬────────────────────┘
      │    │    │    │    │
      ▼    ▼    ▼    ▼    ▼
  Stage 1  Stage 2  Stage 3   Stage 4  Stage 5
  Req/TC   BDD      Crawler   Enrich   Coverage
  Gen      Gen      + API     Agent    Tracker
                    Test Gen
      │
      ▼
 ┌─────────────────────────────────────────────┐
 │         ChromaDB Vector Store               │
 │  requirements | tc_examples | domain_vocab  │
 └─────────────────────────────────────────────┘
      │
      ▼
 ┌─────────────────────────────────────────────┐
 │         Export Layer                        │
 │  CSV | Zephyr Scale | JSON Report          │
 └─────────────────────────────────────────────┘
      │
      ▼
 ┌─────────────────────────────────────────────┐
 │         Feedback Loop                       │
 │  Approved TCs → ChromaDB → Better next run  │
 └─────────────────────────────────────────────┘
```

---

## 🔄 Pipeline Stages in Detail

The DAG-based pipeline executes stages in waves, allowing independent stages to run in parallel.

### Stage 1: Requirements & Test Case Generation
- Parse requirements from uploaded file
- Store in ChromaDB with semantic embeddings
- Classify each acceptance criterion by type
- Generate test cases via LLM with type-specific prompts
- Sanitise and quality-score each test case
- **Output:** `RequirementArtifact` → `TestCaseArtifact[]`

### Stage 2: BDD Feature Generation
- Convert test cases into Gherkin feature files
- Generate step definition skeletons in Python
- Map Given/When/Then to automation framework (Playwright)
- **Output:** `FeatureFileArtifact[]` → `StepDefinitionArtifact[]`

### Stage 3a: Web Crawler & Discrepancy Detection
- Crawl the live application (Playwright for dynamic, BeautifulSoup for static)
- Build a structured site model with pages, elements, and flows
- Compare actual UI against requirements to find discrepancies
- Embed crawled pages in ChromaDB for semantic search
- **Output:** `SiteModelArtifact` → `DiscrepancyReportArtifact`

### Stage 3b: API Test Generation
- Parse OpenAPI/Swagger spec or discover endpoints
- Classify endpoints by CRUD operations
- Generate test code in the chosen framework
- Smart payload generation via heuristic field-name matching
- **Output:** `APIModelArtifact` → `APITestArtifact[]`

### Stage 4: Enrichment
- Review existing test cases for quality improvements
- Apply feedback from previous runs
- Add missing preconditions, edge cases, or data variations
- **Output:** Enhanced `TestCaseArtifact[]`

### Stage 5: Coverage Analysis
- Map test cases back to requirements
- Identify requirements with insufficient coverage
- Flag low-quality test cases for regeneration
- Auto-fill coverage gaps if enabled
- **Output:** Coverage report with gap analysis

---

## 🎯 Benefits

### For QA Engineers
- **10x faster test design** — generate comprehensive test suites in minutes instead of hours
- **Consistent quality** — every test case is scored and validated against 5 quality dimensions
- **No missed scenarios** — AI catches negative, edge, and security cases humans often overlook
- **Reusable knowledge** — approved examples are stored and reused, building a living test library

### For Development Teams
- **BDD ready** — Gherkin feature files and step definitions generated automatically
- **API tests included** — pytest, Rest Assured, Karate, or Supertest code from OpenAPI specs
- **UI validation** — crawler detects discrepancies between requirements and the live application
- **Local-first** — Ollama runs entirely on your machine, no data leaves your network

### For Engineering Managers
- **Metrics & trends** — track quality scores, costs, and coverage across pipeline runs
- **Degradation alerts** — get notified when test quality drops
- **Audit trail** — JSON reports with full generation metadata for compliance
- **Jira integration** — one-click Zephyr Scale import for test management

### For Organizations
- **Zero cloud dependency** — runs 100% locally with Ollama + ChromaDB
- **Cost control** — LLM caching and local models eliminate per-token charges
- **Scalable** — Docker Compose with GPU support for enterprise workloads
- **Extensible** — plugin architecture for custom agents, exporters, and LLM providers

### Prerequisites

- **Python 3.10+**
- **Ollama** (for local LLM) — [install](https://ollama.ai)
- **Node.js 20+** (for frontend development)
- **Docker** (optional, for containerized deployment)

### Option 1: Quick CLI Run (Standalone)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install & start Ollama
ollama serve
ollama pull llama3.2        # or qwen:latest (default)
ollama pull qwen3-embedding:0.6b  # for ChromaDB embeddings

# 3. Configure
cp .env.example .env
# Edit .env to set your model and preferences

# 4. Run
python orchestrator.py --requirements test_data/sample_requirements.csv
```

### Option 2: Full Platform (API + Dashboard)

```bash
# 1. Install dependencies
pip install -e .

# 2. Start Ollama
ollama serve
ollama pull llama3.2

# 3. Run the FastAPI server
python -m uvicorn stlc_platform.api.main:app --host 0.0.0.0 --port 8000

# 4. Open http://localhost:8000 in your browser
```

### Option 3: Docker Compose (Recommended for Production)

```bash
# Build and start everything (app + Ollama)
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

---

## 📄 Supported Requirements Formats

The platform accepts requirements in virtually any format. Here's what each looks like:

### CSV / Excel

```csv
id,title,description,priority,category,acceptance_criteria
REQ-001,User Login,"Users log in with email and password",High,Security,"Valid login redirects; Invalid shows error"
```

Flexible column matching: `id` also accepts `req_id`, `requirement_id`. `title` accepts `name`, `summary`. `description` accepts `details`, `content`, `requirement`.

### Plain Text (`.txt`)

```
REQ-001: User Login
Users authenticate with email and password.
Priority: High
Category: Security
Acceptance Criteria:
- Valid login redirects to dashboard
- Invalid credentials show error message

REQ-002: Password Reset
Forgotten password reset via email link.
```

Requirements are separated by blank lines. ID is detected from patterns like `REQ-001`, `R1`, `#1`.

### Markdown (`.md`)

```markdown
## REQ-001: User Login
Users authenticate with email and password.

**Priority:** High
**Category:** Security

### Acceptance Criteria
- Valid login redirects to dashboard
- Invalid shows error

## REQ-002: Password Reset
Forgotten password reset via email link.
```

### JSON

```json
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "User Login",
      "description": "Users authenticate with email and password.",
      "priority": "High",
      "category": "Security",
      "acceptance_criteria": ["Valid login redirects", "Invalid shows error"]
    }
  ]
}
```

### PDF & Word (`.pdf`, `.docx`)

Documents are parsed by extracting text and detecting requirement blocks using regex patterns for IDs and headings. Works best when requirements follow a consistent numbering scheme.

---

## 🖥️ Frontend Dashboard

The React dashboard provides a visual interface for the entire platform.

### Features
- **Pipeline Monitor** — watch pipeline stages execute in real-time via WebSocket with live progress bars and stage status indicators
- **Test Case Browser** — view, filter, and search generated test cases with quality scores
- **Metrics Dashboard** — charts for quality score trends, test type distribution, priority breakdown, and cost tracking (Recharts)
- **Agent Management** — view registered agents, their capabilities, and execution history
- **Feedback Panel** — review and approve test cases, store examples for few-shot learning
- **Configuration UI** — edit pipeline settings, LLM parameters, and quality gate thresholds without touching YAML files

### Tech Stack
- **React 18** with TypeScript
- **Vite** for fast builds and HMR
- **TailwindCSS** for styling
- **React Router** for navigation
- **Recharts** for data visualization
- **Lucide Icons** for consistent iconography
- **Axios** for API communication
- **Vitest + React Testing Library** for testing

### Development

```bash
cd frontend
npm install
npm run dev        # Start dev server on http://localhost:5173
npm run build      # Production build (output to frontend/dist/)
npm run lint       # ESLint check
npm run preview    # Preview production build
```

The built frontend is served by FastAPI in production mode when `STLC_SERVE_FRONTEND=true`.

---

## 📖 CLI Usage

### Orchestrator (Legacy Standalone)

```bash
# Generate test cases from requirements
python orchestrator.py --requirements reqs.csv

# Use a different model
python orchestrator.py --requirements reqs.txt --model mistral

# Export only Zephyr Scale format
python orchestrator.py --requirements reqs.csv --format zephyr

# Limit test cases per requirement
python orchestrator.py --requirements reqs.txt --max-tests 3

# Clear ChromaDB and regenerate
python orchestrator.py --requirements reqs.csv --clear-db

# Skip ChromaDB for faster runs
python orchestrator.py --requirements reqs.txt --no-chroma
```

### Pipeline Runner (Modern Platform)

```bash
# Run full pipeline
stlc run --pipeline config/pipelines/default.yaml

# Run single agent
stlc run --agent test_generation --input requirements.json

# List registered agents
stlc agents list

# View metrics
stlc metrics list
stlc metrics trends

# CI mode (JSON output)
stlc run --pipeline default.yaml --ci
```

### MCP Server

```bash
# Start MCP server for Claude Desktop
python mcp_server.py

# CLI mode
python mcp_server.py stats
python mcp_server.py validate-tc TC-001
python mcp_server.py store-example TC-001
python mcp_server.py list-examples
```

---

## ⚙️ Configuration

### Quality Scoring Deep Dive

Every generated test case is scored 0.0–1.0. Understanding the scoring helps you tune the system:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| **Coverage** | 25% | Does the test address the requirement's acceptance criteria? Are all conditions tested? |
| **Clarity** | 20% | Is the test readable? Are steps specific and unambiguous? Can any QA engineer understand it? |
| **Executability** | 20% | Can the test be executed by a human or automation? Are preconditions clear? Are expected outcomes specific? |
| **Uniqueness** | 15% | Is this test distinct from others? Does it test a different scenario or angle? |
| **Structural** | 20% | Does it have proper format? Complete Given/When/Then? Valid priority and type? |

**Thresholds:**
- **≥ 0.65** — Accepted ✅
- **0.40 – 0.64** — Flagged for regeneration 🔄
- **< 0.40** — Rejected, regenerated (up to 2 attempts) ❌

### Execution Profiles

Profiles let you run the pipeline with different scopes:

| Profile | Use Case | Stages Executed |
|---------|----------|----------------|
| **Smoke** | Quick validation | Requirements → Test Generation → Export |
| **Targeted** | Specific feature testing | Requirements → Test Generation → BDD → Export |
| **Regression** | Full suite | All 5 stages including Crawler, API Tests, Enrichment |

```bash
# Run smoke profile (fastest)
stlc run --pipeline default.yaml --profile smoke

# Run full regression
stlc run --pipeline default.yaml --profile regression
```

### Environment Variables (.env)

```env
# Ollama LLM
OLLAMA_MODEL=qwen:latest
OLLAMA_TEMPERATURE=0.6
OLLAMA_NUM_CTX=8192
OLLAMA_TIMEOUT=450

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_db
EMBEDDING_BACKEND=ollama
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b

# Test Generation
MAX_TC_PER_REQ=6
INCLUDE_NEGATIVE=true
INCLUDE_EDGE=true
TC_FORMAT=gherkin

# Export
ZEPHYR_PROJECT_KEY=PROJ
OUTPUT_DIR=./output
```

### Pipeline Config (config/stlc_config.yaml)

The platform uses a YAML-based config with profile overlays:
- `stlc_config.yaml` — base configuration
- `stlc_config.api.yaml` — API-specific overrides
- `stlc_config.web.yaml` — web-specific overrides

---

## 🧪 Running Tests

```bash
# Unit tests
pytest tests/unit/ --cov=stlc_platform --cov-report=html

# Integration tests
pytest tests/integration/

# BDD tests (behave)
behave features/
behave features/ --tags=smoke
behave features/ --tags=llm_generation

# Full test suite with coverage
pytest tests/ --cov=stlc_platform --cov-report=term-missing --cov-fail-under=75
```

---

## 📁 Project Structure

```
Python_Orchestrator/
├── orchestrator.py              # Legacy CLI entry point
├── run_pipeline.py              # Modern pipeline runner
├── mcp_server.py                # MCP server for AI tool exposure
├── config.py                    # Legacy config (dataclass-based)
├── requirements_reader.py       # Multi-format requirement parser
├── chroma_store.py              # ChromaDB vector store
├── llm_client.py                # Ollama LLM client
├── test_generator.py            # Core test case generator
├── environment.py               # Behave BDD test hooks
│
├── stlc_platform/               # Modern platform package
│   ├── core/                    # Core utilities
│   │   ├── llm/                 # Pluggable LLM providers
│   │   ├── storage/             # ChromaDB storage
│   │   └── quality/             # Scoring & deduplication
│   ├── agents/                  # Specialized AI agents
│   │   ├── requirements_agent/  # Test generation
│   │   ├── bdd_agent/           # BDD feature generation
│   │   ├── crawler_agent/       # Web crawling & discrepancy detection
│   │   ├── api_test_agent/      # API test generation
│   │   └── enrichment_agent/    # Test case enrichment
│   ├── pipeline/                # DAG-based pipeline orchestration
│   ├── api/                     # FastAPI REST + WebSocket API
│   ├── exporters/               # CSV, Zephyr, JSON exporters
│   └── cli.py                   # Full CLI interface
│
├── frontend/                    # React dashboard
├── config/                      # YAML configs, pipelines, profiles, skills
├── exporters/                   # Legacy exporters
├── tests/                       # Unit + integration tests
├── test_data/                   # Sample requirement files
├── output/                      # Generated test case outputs
└── docker-compose.yml           # Docker orchestration
```

---

## 📦 Dependencies

| Category | Packages |
|----------|----------|
| **LLM & AI** | ollama, langchain, langchain-ollama, chromadb, sentence-transformers |
| **Web API** | fastapi, uvicorn, python-multipart |
| **File Processing** | python-docx, PyPDF2, openpyxl, pandas |
| **Testing** | behave, pytest |
| **Utilities** | python-dotenv, pydantic, pydantic-settings, rich, click, requests, PyYAML, Jinja2, beautifulsoup4 |
| **MCP** | mcp, slowapi |
| **Auth** | PyJWT |

---

## 🤖 Recommended Models

### For Ollama (Local)

| Model | Size | Best For | RAM Required |
|-------|------|----------|-------------|
| **qwen:latest** | ~4.7GB | Default, balanced quality | 8GB |
| **llama3.2** | ~2GB | Fast generation, lower-end machines | 4GB |
| **mistral** | ~4.1GB | Better structured JSON output | 8GB |
| **llama3.1:8b** | ~4.7GB | Highest quality output | 8GB |
| **qwen2.5:32b** | ~18GB | Enterprise-grade quality (GPU recommended) | 32GB+ |

### Embedding Models

| Model | Size | Notes |
|-------|------|-------|
| **qwen3-embedding:0.6b** | ~0.6GB | Recommended, fast and accurate | 2GB |
| **nomic-embed-text** | ~0.3GB | Excellent alternative | 1GB |
| **all-MiniLM-L6-v2** | ~80MB | SentenceTransformer fallback, no Ollama needed | 512MB |

### For Cloud Providers

| Provider | Model | Notes |
|----------|-------|-------|
| **OpenAI** | gpt-4o, gpt-4o-mini | Best structured output, paid |
| **Anthropic** | claude-sonnet-4-20250514 | Excellent reasoning, paid |

Switch providers in `config/stlc_config.yaml`:

```yaml
llm:
  provider: openai  # or anthropic
  model: gpt-4o-mini
  api_key: sk-...
```

---

## 🔌 Plugin Architecture

The platform supports custom plugins via Python entry points. You can extend it without modifying core code:

### Custom Agents

Create a new agent by extending `BaseAgent`:

```python
from stlc_platform.core.base_agent import BaseAgent, AgentResult

class MyCustomAgent(BaseAgent):
    def get_capabilities(self):
        return {"agent_id": "my_agent", "description": "Does something special"}

    def execute(self, input_artifacts, config):
        # Your logic here
        return AgentResult(artifacts={"output": my_artifacts}, status="success")
```

Register in `pyproject.toml`:

```toml
[project.entry-points."stlc_platform.agents"]
my_agent = "my_package.my_agent:MyCustomAgent"
```

### Custom Exporters

Add new export formats by creating an exporter class and registering it. The existing `CSVExporter`, `ZephyrScaleExporter`, and `JSONReportExporter` serve as templates.

### Custom Skill Files

Add domain-specific knowledge to `config/skills/`:

```yaml
# config/skills/my_domain/data_catalog.yaml
domain: My Domain
common_fields:
  - field: customer_id
    type: string
    format: "CUST-XXXX"
    test_values: ["CUST-0001", "CUST-9999", "INVALID"]
```

The skill loader automatically injects these into the agent context during pipeline execution.

---

## 🐛 Troubleshooting

**Ollama connection error:**
```bash
ollama serve
ollama list
ollama pull llama3.2
```

**ChromaDB issues:**
```bash
python orchestrator.py --requirements reqs.csv --clear-db
# Or skip entirely
python orchestrator.py --requirements reqs.csv --no-chroma
```

**LLM returns bad JSON:**
- Lower `OLLAMA_TEMPERATURE` (try `0.1`)
- Try `mistral` model (better structured output)
- Increase `OLLAMA_NUM_CTX` for long requirements

**Slow generation:**
- Use `--no-chroma` to skip embedding
- Use a smaller model (`llama3.2` instead of `llama3.1:8b`)
- Reduce `MAX_TC_PER_REQ`

---

## 📄 License

MIT
