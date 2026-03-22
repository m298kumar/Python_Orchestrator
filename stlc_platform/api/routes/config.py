"""
Config Routes
=============
View and update the current STLC platform configuration.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from stlc_platform.api.schemas import ConfigResponse, ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["config"])

# In-memory config state
_config: Dict[str, Any] = {
    "project": {},
    "ollama": {},
    "output": {},
}

# Fields that should be masked in responses
_SENSITIVE_KEYS = {"api_key", "secret", "password", "token"}


def _sanitize(d: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive values in a config dict."""
    result: Dict[str, Any] = {}
    for k, v in d.items():
        if any(sk in k.lower() for sk in _SENSITIVE_KEYS):
            result[k] = "***"
        elif isinstance(v, dict):
            result[k] = _sanitize(v)
        else:
            result[k] = v
    return result


def _load_initial_config() -> None:
    """Load config from the config loader on first access."""
    global _config
    if _config.get("_loaded"):
        return
    try:
        from stlc_platform.core.config_loader import load_config
        cfg = load_config()
        _config["project"] = getattr(cfg, "project", {}).__dict__ if hasattr(getattr(cfg, "project", None), "__dict__") else {}
        _config["ollama"] = getattr(cfg, "ollama", {}).__dict__ if hasattr(getattr(cfg, "ollama", None), "__dict__") else {}
        _config["output"] = getattr(cfg, "output", {}).__dict__ if hasattr(getattr(cfg, "output", None), "__dict__") else {}
    except Exception:
        pass
    _config["_loaded"] = True


@router.get("/", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    """Return the current configuration with sensitive fields masked."""
    _load_initial_config()
    return ConfigResponse(
        project=_sanitize(_config.get("project", {})),
        ollama=_sanitize(_config.get("ollama", {})),
        output=_sanitize(_config.get("output", {})),
    )


@router.put("/", response_model=ConfigResponse)
def update_config(update: ConfigUpdate) -> ConfigResponse:
    """Update configuration values. Keys use dot notation (e.g. 'ollama.model')."""
    _load_initial_config()

    for key, value in update.updates.items():
        parts = key.split(".")
        target = _config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    return ConfigResponse(
        project=_sanitize(_config.get("project", {})),
        ollama=_sanitize(_config.get("ollama", {})),
        output=_sanitize(_config.get("output", {})),
    )
