# AI Test Case Orchestrator

**Automatically generate test cases from requirements using local Ollama LLM + ChromaDB, 
export to CSV or Zephyr Scale format, and validate with Behave BDD.**

---

## 🏗️ Architecture

```
requirements_file (.txt/.csv/.xlsx/.pdf/.docx/.json)
         │
         ▼
 RequirementsReader          ← Parses requirements into structured objects
         │
         ▼
 RequirementsVectorStore     ← ChromaDB: stores & semantically searches requirements
         │                      (provides context to avoid duplicate test cases)
         ▼
 OllamaClient                ← Local LLM via Ollama (llama3.2, mistral, etc.)
         │
         ▼
 TestCaseGenerator           ← Prompts LLM, parses JSON response into TestCase objects
         │
    ┌────┴─────┐
    ▼          ▼
CSVExporter  ZephyrScaleExporter   ← Export outputs
    └────┬─────┘
         ▼
    JSON Report
```

---

## ⚙️ Setup

### 1. Install dependencies

```bash
chmod +x setup.sh && ./setup.sh
# OR manually:
pip install -r requirements.txt
```

### 2. Install & start Ollama

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.2      # Recommended (fast, 2GB)
ollama pull mistral       # Better structured output (4.1GB)
ollama pull llama3.1:8b   # Best quality (4.7GB)

# Start the server
ollama serve
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env to set your OLLAMA_MODEL and other settings
```

---

## 🚀 Usage

### Basic usage

```bash
# Generate test cases from a CSV requirements file
python orchestrator.py --requirements test_data/sample_requirements.csv

# Use a different model
python orchestrator.py --requirements reqs.txt --model mistral

# Export only Zephyr Scale format
python orchestrator.py --requirements reqs.csv --format zephyr

# Limit to 3 test cases per requirement
python orchestrator.py --requirements reqs.txt --max-tests 3

# Clear ChromaDB and regenerate
python orchestrator.py --requirements reqs.csv --clear-db

# Skip ChromaDB for faster runs
python orchestrator.py --requirements reqs.txt --no-chroma

# Custom output directory
python orchestrator.py --requirements reqs.csv --output-dir ./my_tests
```

### All CLI options

```
Options:
  -r, --requirements PATH   Requirements file path (required)
  -f, --format [csv|zephyr|both]  Output format (default: both)
  -m, --model TEXT          Ollama model name
  --max-tests INTEGER       Max test cases per requirement
  -o, --output-dir PATH     Output directory
  --clear-db                Clear ChromaDB before processing
  --no-chroma               Skip ChromaDB vector store
  --skip-llm-check          Skip Ollama connection check
  --help                    Show help message
```

---

## 📁 Supported Requirements File Formats

| Format | Description | Required Columns (CSV/XLSX) |
|--------|-------------|---------------------------|
| `.txt` | Plain text, one req per block separated by blank line | N/A |
| `.md`  | Markdown with `## REQ-001` headings | N/A |
| `.csv` | Spreadsheet format | `id`, `title`, `description` |
| `.xlsx`| Excel format | `id`, `title`, `description` |
| `.json`| JSON array or `{"requirements": [...]}` | N/A |
| `.pdf` | PDF document (text extracted) | N/A |
| `.docx`| Word document | N/A |

### CSV column names (flexible matching)

| Canonical | Also accepted |
|-----------|--------------|
| `id` | `req_id`, `requirement_id` |
| `title` | `name`, `summary` |
| `description` | `details`, `content`, `requirement` |
| `priority` | `priority` |
| `category` | `type` |
| `acceptance_criteria` | `ac` (semicolon-separated) |

---

## 📤 Output Files

After running, check the `./output/` directory:

| File | Description |
|------|-------------|
| `test_cases.csv` | Standard CSV with all test case details |
| `zephyr_test_cases.csv` | Zephyr Scale import-ready CSV |
| `generation_report.json` | Statistics and metadata |

### Zephyr Scale Import

1. Open Zephyr Scale in Jira
2. Go to **Test Cases** → **Import**
3. Select **CSV** and upload `zephyr_test_cases.csv`
4. Map columns as needed (they match Zephyr's standard format)

---

## 🧪 Running BDD Tests

```bash
# Run all tests (uses mock LLM by default)
behave features/

# Run specific tags
behave features/ --tags=smoke
behave features/ --tags=export
behave features/ --tags=zephyr

# Run with real Ollama (integration tests)
behave features/ --tags=llm_generation

# Verbose output
behave features/ --no-capture --verbose

# Generate HTML report
behave features/ --format html --outfile test_report.html
```

---

## 🔧 Configuration (.env)

```env
# Ollama
OLLAMA_MODEL=llama3.2         # Model name
OLLAMA_TEMPERATURE=0.3        # 0=deterministic, 1=creative
OLLAMA_NUM_CTX=4096           # Context window
OLLAMA_TIMEOUT=120            # Request timeout in seconds

# ChromaDB
CHROMA_PERSIST_DIR=./chroma_db
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Zephyr Scale
ZEPHYR_PROJECT_KEY=MYPROJECT
ZEPHYR_FOLDER_PREFIX=Generated Tests

# Test Generation
MAX_TC_PER_REQ=5
INCLUDE_NEGATIVE=true
INCLUDE_EDGE=true
TC_FORMAT=gherkin             # gherkin or steps
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `ollama` | Ollama Python client |
| `chromadb` | Vector store for requirements |
| `sentence-transformers` | Local text embeddings for ChromaDB |
| `behave` | BDD testing framework |
| `langchain-ollama` | LangChain Ollama integration |
| `pandas` | Excel/CSV processing |
| `python-docx` | Word document reading |
| `PyPDF2` | PDF reading |
| `click` | CLI framework |
| `rich` | Pretty terminal output |

---

## 🐛 Troubleshooting

**Ollama connection error:**
```bash
ollama serve          # Start the server
ollama list           # Check available models
ollama pull llama3.2  # Pull if needed
```

**ChromaDB issues:**
```bash
# Clear the database
python orchestrator.py --requirements reqs.csv --clear-db
# Or skip it entirely
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
