"""
Unified Config Loader
=====================
Loads configuration from:
  1. config/stlc_config.yaml (base)
  2. Environment variables (override, prefixed with STLC_)
  3. .env file (legacy compatibility)

Also provides backward-compatible access patterns so existing code
(config.ollama.model, config.output.output_dir, etc.) still works.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv


def _find_project_root() -> Path:
    """Walk up from CWD to find the directory containing config/ or stlc_platform/."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "config" / "stlc_config.yaml").exists():
            return parent
        if (parent / "stlc_platform").is_dir():
            return parent
    return cwd


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML config file. Returns empty dict if file not found."""
    if not path.exists():
        return {}
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # PyYAML not installed — fall back to empty config
        return {}


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge overlay into base.

    - Dict values are merged recursively
    - All other values in overlay overwrite base
    - Keys in base not present in overlay are preserved
    """
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _deep_get(d: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    """Nested dict access: _deep_get(d, ['llm', 'model']) -> d['llm']['model']."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d


def _env_override(yaml_val: Any, env_key: str, cast_type: type = str) -> Any:
    """Return env var value if set, otherwise yaml value."""
    env_val = os.getenv(env_key)
    if env_val is not None:
        if cast_type is bool:
            return env_val.lower() in ("true", "1", "yes")
        return cast_type(env_val)
    return yaml_val


# ── Legacy-compatible dataclass config ───────────────────────────────────────
# These mirror the original config.py exactly so existing code doesn't break.


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b-instruct"
    temperature: float = 0.6
    num_ctx: int = 8192
    timeout: int = 450
    num_predict: int = 3200


@dataclass
class ChromaDBConfig:
    persist_directory: str = "./chroma_db"
    collection_name: str = "requirements"
    embedding_backend: str = "ollama"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_url: str = "http://localhost:11434/api/embeddings"
    sentence_transformer_model: str = "all-MiniLM-L6-v2"


@dataclass
class ZephyrConfig:
    project_key: str = "PROJ"
    default_priority: str = "Normal"
    default_status: str = "Draft"
    default_component: str = ""
    default_labels: str = "automated,generated"
    folder_prefix: str = "Generated Tests"


@dataclass
class OutputConfig:
    output_dir: str = "./output"
    csv_filename: str = "test_cases.csv"
    zephyr_filename: str = "zephyr_test_cases.csv"
    report_filename: str = "generation_report.json"


@dataclass
class AppConfig:
    """Main application configuration — backward compatible with original config.py."""

    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    zephyr: ZephyrConfig = field(default_factory=ZephyrConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    max_test_cases_per_requirement: int = 6
    include_negative_tests: bool = True
    include_edge_cases: bool = True
    test_case_format: str = "gherkin"

    # New fields for multi-stage platform
    project_name: str = "My Application"
    project_domain: str = ""
    llm_provider: str = "ollama"


_KNOWN_TOP_LEVEL_KEYS = {
    "project",
    "specifications",
    "review",
    "llm",
    "chromadb",
    "test_generation",
    "bdd",
    "crawler",
    "api_testing",
    "export",
    "quality_gate",
    "coverage",
    "circuit_breaker",
    "metrics",
    "output",
    "stage_timeout_seconds",
}


def _validate_yaml_keys(yaml_cfg: Dict[str, Any]) -> None:
    """Warn about unknown top-level keys in stlc_config.yaml."""
    unknown = set(yaml_cfg.keys()) - _KNOWN_TOP_LEVEL_KEYS
    if unknown:
        _logger = logging.getLogger(__name__)
        _logger.warning(
            "Unknown keys in stlc_config.yaml (possible typos): %s. Known keys: %s",
            ", ".join(sorted(unknown)),
            ", ".join(sorted(_KNOWN_TOP_LEVEL_KEYS)),
        )


def load_config() -> AppConfig:
    """
    Load config from YAML + .env + environment variables.
    Returns an AppConfig that is backward-compatible with the original config.py.
    """
    # Load .env for legacy compatibility
    load_dotenv()

    # Load YAML
    root = _find_project_root()
    yaml_cfg = _load_yaml(root / "config" / "stlc_config.yaml")

    # Validate top-level keys to catch typos early
    _validate_yaml_keys(yaml_cfg)

    # Build config with YAML as base, env vars as overrides
    cfg = AppConfig()

    # -- LLM --
    llm = yaml_cfg.get("llm", {})
    cfg.ollama.base_url = _env_override(llm.get("base_url", cfg.ollama.base_url), "OLLAMA_BASE_URL")
    cfg.ollama.model = _env_override(llm.get("model", cfg.ollama.model), "OLLAMA_MODEL")
    cfg.ollama.temperature = _env_override(
        llm.get("temperature", cfg.ollama.temperature), "OLLAMA_TEMPERATURE", float
    )
    cfg.ollama.num_ctx = _env_override(
        llm.get("num_ctx", cfg.ollama.num_ctx), "OLLAMA_NUM_CTX", int
    )
    cfg.ollama.timeout = _env_override(
        llm.get("timeout", cfg.ollama.timeout), "OLLAMA_TIMEOUT", int
    )
    cfg.ollama.num_predict = _env_override(
        llm.get("num_predict", cfg.ollama.num_predict), "OLLAMA_NUM_PREDICT", int
    )
    cfg.llm_provider = _env_override(llm.get("provider", cfg.llm_provider), "STLC_LLM_PROVIDER")

    # -- ChromaDB --
    chroma = yaml_cfg.get("chromadb", {})
    cfg.chromadb.persist_directory = _env_override(
        chroma.get("persist_directory", cfg.chromadb.persist_directory),
        "CHROMA_PERSIST_DIR",
    )
    cfg.chromadb.collection_name = _env_override(
        chroma.get("collection_name", cfg.chromadb.collection_name),
        "CHROMA_COLLECTION",
    )
    cfg.chromadb.embedding_backend = _env_override(
        chroma.get("embedding_backend", cfg.chromadb.embedding_backend),
        "EMBEDDING_BACKEND",
    )
    cfg.chromadb.ollama_embedding_model = _env_override(
        chroma.get("ollama_embedding_model", cfg.chromadb.ollama_embedding_model),
        "OLLAMA_EMBEDDING_MODEL",
    )
    cfg.chromadb.ollama_embedding_url = _env_override(
        chroma.get("ollama_embedding_url", cfg.chromadb.ollama_embedding_url),
        "OLLAMA_EMBEDDING_URL",
    )
    cfg.chromadb.sentence_transformer_model = _env_override(
        chroma.get("sentence_transformer_model", cfg.chromadb.sentence_transformer_model),
        "ST_EMBEDDING_MODEL",
    )

    # -- Test Generation --
    tg = yaml_cfg.get("test_generation", {})
    cfg.max_test_cases_per_requirement = _env_override(
        tg.get("max_per_requirement", cfg.max_test_cases_per_requirement),
        "MAX_TC_PER_REQ",
        int,
    )
    cfg.include_negative_tests = _env_override(
        tg.get("include_negative", cfg.include_negative_tests),
        "INCLUDE_NEGATIVE",
        bool,
    )
    cfg.include_edge_cases = _env_override(
        tg.get("include_edge_cases", cfg.include_edge_cases),
        "INCLUDE_EDGE",
        bool,
    )
    cfg.test_case_format = _env_override(tg.get("format", cfg.test_case_format), "TC_FORMAT")

    # -- Output --
    export = yaml_cfg.get("export", {})
    cfg.output.output_dir = _env_override(
        export.get("output_dir", cfg.output.output_dir), "OUTPUT_DIR"
    )

    # -- Zephyr --
    zephyr = export.get("zephyr", {})
    if zephyr:
        cfg.zephyr.project_key = _env_override(
            zephyr.get("project_key", cfg.zephyr.project_key),
            "ZEPHYR_PROJECT_KEY",
        )
        cfg.zephyr.folder_prefix = zephyr.get("folder_prefix", cfg.zephyr.folder_prefix)
        cfg.zephyr.default_status = zephyr.get("default_status", cfg.zephyr.default_status)
        cfg.zephyr.default_labels = zephyr.get("default_labels", cfg.zephyr.default_labels)

    # -- Project --
    project = yaml_cfg.get("project", {})
    cfg.project_name = project.get("name", cfg.project_name)
    cfg.project_domain = project.get("domain", cfg.project_domain)

    return cfg


def save_config_yaml(updates: dict) -> Path:
    """Deep-merge *updates* into ``config/stlc_config.yaml`` and write back.

    Args:
        updates: Nested dict of config keys/values to merge.

    Returns:
        The Path to the written YAML file.
    """
    import yaml

    root = _find_project_root()
    yaml_path = root / "config" / "stlc_config.yaml"

    # Read existing YAML (or start fresh)
    current: Dict[str, Any] = {}
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}

    merged = deep_merge(current, updates)

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(merged, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return yaml_path


def load_config_yaml(profile: str = "") -> Dict[str, Any]:
    """
    Load raw YAML config dict with optional profile overlay.

    Args:
        profile: Optional profile name (e.g., "web", "api").
                 Loads config/stlc_config.{profile}.yaml and deep-merges
                 onto the base config/stlc_config.yaml.

    Returns:
        Merged config dict.

    Raises:
        FileNotFoundError: If the profile overlay file doesn't exist.
    """
    root = _find_project_root()
    base = _load_yaml(root / "config" / "stlc_config.yaml")

    if profile:
        overlay_path = root / "config" / f"stlc_config.{profile}.yaml"
        if not overlay_path.exists():
            raise FileNotFoundError(f"Config profile '{profile}' not found at {overlay_path}")
        overlay = _load_yaml(overlay_path)
        base = deep_merge(base, overlay)

    return base


# Singleton — loaded once, importable everywhere
config = load_config()
