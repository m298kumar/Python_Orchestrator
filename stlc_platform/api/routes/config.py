"""
Config Routes
=============
View and update the current STLC platform configuration.
Supports both dot-notation and structured updates, persists to YAML,
and provides an LLM connection test endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter

from stlc_platform.api.schemas import (
    ConfigResponse,
    ConfigUpdate,
    LLMTestRequest,
    LLMTestResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

# In-memory config state
_config: Dict[str, Any] = {
    "project": {},
    "llm": {},
    "output": {},
}

# Fields that should be masked in responses
_SENSITIVE_KEYS = {"api_key", "secret", "password", "token"}

# Masked sentinel — values equal to this are never persisted to YAML
_MASK = "***"


def _sanitize(d: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive values in a config dict."""
    result: Dict[str, Any] = {}
    for k, v in d.items():
        if any(sk in k.lower() for sk in _SENSITIVE_KEYS):
            result[k] = _MASK
        elif isinstance(v, dict):
            result[k] = _sanitize(v)
        else:
            result[k] = v
    return result


def _deep_merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *overlay* into *base* (returns a new dict)."""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _load_initial_config() -> None:
    """Load config from the YAML file on first access.

    Reads directly from the YAML dict (not the OllamaConfig dataclass)
    so that all fields — including ``api_key`` and ``provider`` — are preserved.
    """
    global _config
    if _config.get("_loaded"):
        return
    try:
        from stlc_platform.core.config_loader import _find_project_root, _load_yaml
        yaml_cfg = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
        _config["project"] = yaml_cfg.get("project", {})
        _config["llm"] = yaml_cfg.get("llm", {})
        _config["output"] = yaml_cfg.get("output", yaml_cfg.get("export", {}))
    except Exception:
        pass
    _config["_loaded"] = True


def _dot_to_nested(flat: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dot-notation keys to a nested dict.

    Example: {"llm.model": "gpt-4o"} -> {"llm": {"model": "gpt-4o"}}
    """
    nested: Dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        d = nested
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = value
    return nested


def _strip_masked(d: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any value that is the masked sentinel (recursively)."""
    result: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            cleaned = _strip_masked(v)
            if cleaned:
                result[k] = cleaned
        elif v != _MASK:
            result[k] = v
    return result


def _apply_updates(updates_flat: Dict[str, Any]) -> None:
    """Apply dot-notation updates to the in-memory config dict."""
    for key, value in updates_flat.items():
        parts = key.split(".")
        target = _config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value


def _persist_to_yaml(nested_updates: Dict[str, Any]) -> None:
    """Persist updates to the YAML config file (best-effort)."""
    try:
        from stlc_platform.core.config_loader import save_config_yaml
        clean = _strip_masked(nested_updates)
        if clean:
            save_config_yaml(clean)
    except Exception as exc:
        logger.warning("Config YAML persistence failed: %s", exc)


# ---------------------------------------------------------------------------
# GET /api/config/
# ---------------------------------------------------------------------------

@router.get("/", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    """Return the current configuration with sensitive fields masked."""
    _load_initial_config()
    return ConfigResponse(
        project=_sanitize(_config.get("project", {})),
        llm=_sanitize(_config.get("llm", {})),
        output=_sanitize(_config.get("output", {})),
    )


# ---------------------------------------------------------------------------
# PUT /api/config/
# ---------------------------------------------------------------------------

@router.put("/", response_model=ConfigResponse)
def update_config(update: ConfigUpdate) -> ConfigResponse:
    """Update configuration values.

    Accepts two formats (can be combined):
    1. Dot-notation via ``updates``: ``{"updates": {"llm.model": "gpt-4o"}}``
    2. Structured sections: ``{"llm": {"model": "gpt-4o"}}``

    Backward-compatible: ``ollama.*`` keys in dot-notation are mapped to ``llm.*``.
    """
    _load_initial_config()

    all_flat: Dict[str, Any] = {}

    # 1. Dot-notation updates
    if update.updates:
        for key, value in update.updates.items():
            # Map ollama.* -> llm.* for backward compatibility
            if key.startswith("ollama."):
                key = "llm." + key[len("ollama."):]
            all_flat[key] = value

    # 2. Structured section updates -> flatten to dot-notation
    for section_name in ("project", "llm", "output"):
        section_data = getattr(update, section_name, None)
        if section_data:
            for k, v in section_data.items():
                all_flat[f"{section_name}.{k}"] = v

    # Apply in-memory
    _apply_updates(all_flat)

    # Persist to YAML (best-effort, skip masked values)
    nested = _dot_to_nested(all_flat)
    _persist_to_yaml(nested)

    return ConfigResponse(
        project=_sanitize(_config.get("project", {})),
        llm=_sanitize(_config.get("llm", {})),
        output=_sanitize(_config.get("output", {})),
    )


# ---------------------------------------------------------------------------
# POST /api/config/test-llm
# ---------------------------------------------------------------------------

@router.post("/test-llm", response_model=LLMTestResponse)
def test_llm_connection(req: LLMTestRequest) -> LLMTestResponse:
    """Test connectivity to an LLM provider and list available models."""

    provider = req.provider.lower().strip()

    if provider == "ollama":
        return _test_ollama(req)
    elif provider == "openai":
        return _test_openai(req)
    elif provider == "anthropic":
        return _test_anthropic(req)
    elif provider == "azure":
        return _test_azure(req)
    else:
        return LLMTestResponse(
            success=False,
            message=f"Unknown provider: '{req.provider}'. Supported: ollama, openai, anthropic, azure.",
        )


def _test_ollama(req: LLMTestRequest) -> LLMTestResponse:
    """Test Ollama connectivity via its /api/tags endpoint."""
    import urllib.request
    import urllib.error
    import json

    base_url = (req.base_url or "http://localhost:11434").rstrip("/")
    url = f"{base_url}/api/tags"

    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return LLMTestResponse(
                success=True,
                message=f"Connected to Ollama at {base_url}. Found {len(models)} model(s).",
                models=models,
            )
    except urllib.error.URLError as exc:
        return LLMTestResponse(
            success=False,
            message=f"Cannot reach Ollama at {base_url}: {exc.reason}",
        )
    except Exception as exc:
        return LLMTestResponse(
            success=False,
            message=f"Ollama connection error: {exc}",
        )


def _test_openai(req: LLMTestRequest) -> LLMTestResponse:
    """Test OpenAI connectivity by listing models."""
    try:
        import openai  # type: ignore[import-untyped]
    except ImportError:
        return LLMTestResponse(
            success=False,
            message="Package 'openai' not installed. Run: pip install openai",
        )

    if not req.api_key:
        return LLMTestResponse(success=False, message="api_key is required for OpenAI.")

    try:
        client = openai.OpenAI(api_key=req.api_key)
        model_list = client.models.list()
        models = sorted([m.id for m in model_list.data])[:50]
        return LLMTestResponse(
            success=True,
            message=f"Connected to OpenAI. Found {len(models)} model(s).",
            models=models,
        )
    except openai.AuthenticationError:
        return LLMTestResponse(success=False, message="Invalid OpenAI API key.")
    except Exception as exc:
        return LLMTestResponse(success=False, message=f"OpenAI error: {exc}")


def _test_anthropic(req: LLMTestRequest) -> LLMTestResponse:
    """Test Anthropic connectivity with a minimal API call."""
    try:
        import anthropic  # type: ignore[import-untyped]
    except ImportError:
        return LLMTestResponse(
            success=False,
            message="Package 'anthropic' not installed. Run: pip install anthropic",
        )

    if not req.api_key:
        return LLMTestResponse(success=False, message="api_key is required for Anthropic.")

    try:
        client = anthropic.Anthropic(api_key=req.api_key)
        client.messages.create(
            model=req.model or "claude-sonnet-4-20250514",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return LLMTestResponse(
            success=True,
            message="Connected to Anthropic successfully.",
            models=[req.model or "claude-sonnet-4-20250514"],
        )
    except anthropic.AuthenticationError:
        return LLMTestResponse(success=False, message="Invalid Anthropic API key.")
    except Exception as exc:
        return LLMTestResponse(success=False, message=f"Anthropic error: {exc}")


def _test_azure(req: LLMTestRequest) -> LLMTestResponse:
    """Test Azure OpenAI connectivity."""
    try:
        import openai  # type: ignore[import-untyped]
    except ImportError:
        return LLMTestResponse(
            success=False,
            message="Package 'openai' not installed. Run: pip install openai",
        )

    if not req.api_key:
        return LLMTestResponse(success=False, message="api_key is required for Azure OpenAI.")
    if not req.base_url:
        return LLMTestResponse(success=False, message="base_url is required for Azure OpenAI.")

    try:
        client = openai.AzureOpenAI(
            api_key=req.api_key,
            azure_endpoint=req.base_url,
            api_version="2024-02-15-preview",
        )
        model_list = client.models.list()
        models = sorted([m.id for m in model_list.data])[:50]
        return LLMTestResponse(
            success=True,
            message=f"Connected to Azure OpenAI. Found {len(models)} model(s).",
            models=models,
        )
    except openai.AuthenticationError:
        return LLMTestResponse(success=False, message="Invalid Azure OpenAI credentials.")
    except Exception as exc:
        return LLMTestResponse(success=False, message=f"Azure OpenAI error: {exc}")
