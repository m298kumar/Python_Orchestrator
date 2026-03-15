"""
Configuration for the Test Case Orchestrator
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class OllamaConfig:
    """Ollama LLM configuration"""
    base_url: str    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str       = os.getenv("OLLAMA_MODEL", "qwen:latest")
    temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.6"))  # Qwen3 recommended
    num_ctx: int     = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    timeout: int     = int(os.getenv("OLLAMA_TIMEOUT", "450"))          # thinking mode needs time
    num_predict: int = int(os.getenv("OLLAMA_NUM_PREDICT", "3200"))     # tokens to generate


@dataclass
class ChromaDBConfig:
    """ChromaDB vector store configuration"""
    persist_directory: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    collection_name: str   = os.getenv("CHROMA_COLLECTION", "requirements")

    # Embedding backend: "ollama" (recommended) or "sentence_transformer"
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "ollama")

    # Ollama embedding model — pulled separately from the LLM
    # Recommended: qwen3-embedding:0.6b  (fast, accurate, no HF dependencies)
    # Fallback:    nomic-embed-text       (also excellent)
    ollama_embedding_model: str = os.getenv(
        "OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:0.6b"
    )
    ollama_embedding_url: str = os.getenv(
        "OLLAMA_EMBEDDING_URL", "http://localhost:11434/api/embeddings"
    )

    # Sentence-transformer fallback (only used if embedding_backend=sentence_transformer)
    sentence_transformer_model: str = os.getenv(
        "ST_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
    )


@dataclass
class ZephyrConfig:
    """Zephyr Scale CSV export configuration"""
    project_key: str     = os.getenv("ZEPHYR_PROJECT_KEY", "PROJ")
    default_priority: str = "Normal"
    default_status: str   = "Draft"
    default_component: str = ""
    default_labels: str   = "automated,generated"
    folder_prefix: str    = "Generated Tests"


@dataclass
class OutputConfig:
    """Output configuration"""
    output_dir: str      = os.getenv("OUTPUT_DIR", "./output")
    csv_filename: str    = "test_cases.csv"
    zephyr_filename: str = "zephyr_test_cases.csv"
    report_filename: str = "generation_report.json"


@dataclass
class AppConfig:
    """Main application configuration"""
    ollama:   OllamaConfig   = field(default_factory=OllamaConfig)
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    zephyr:   ZephyrConfig   = field(default_factory=ZephyrConfig)
    output:   OutputConfig   = field(default_factory=OutputConfig)

    # Test generation settings
    max_test_cases_per_requirement: int = int(os.getenv("MAX_TC_PER_REQ", "6"))
    include_negative_tests: bool = os.getenv("INCLUDE_NEGATIVE", "true").lower() == "true"
    include_edge_cases: bool     = os.getenv("INCLUDE_EDGE", "true").lower() == "true"
    test_case_format: str        = os.getenv("TC_FORMAT", "gherkin")


# Singleton config instance
config = AppConfig()