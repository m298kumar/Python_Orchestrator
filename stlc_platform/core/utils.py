"""
Shared Utilities
================
Common helper functions used across multiple modules in the STLC platform.
These are small, stateless functions that don't belong to any specific agent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def find_project_root() -> Path:
    """
    Walk up from CWD to find the project root directory.
    Looks for markers: config/, stlc_platform/, pyproject.toml, or .git/.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "config" / "stlc_config.yaml").exists():
            return parent
        if (parent / "stlc_platform").is_dir():
            return parent
        if (parent / ".git").is_dir():
            return parent
    return cwd


def slugify(text: str) -> str:
    """
    Convert a string to a URL/file-safe slug.
    'User Login Authentication' -> 'user-login-authentication'
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-")


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep-merge two dicts. Values in override take precedence.
    Nested dicts are merged recursively. Lists are replaced, not appended.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_dir(path: str | Path) -> Path:
    """Create directory (and parents) if it doesn't exist. Returns the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_filename(name: str, extension: str = "") -> str:
    """
    Make a string safe for use as a filename.
    Removes special characters, replaces spaces with underscores.
    """
    safe = re.sub(r'[<>:"/\\|?*]', "", name)
    safe = re.sub(r"\s+", "_", safe.strip())
    safe = safe[:200]  # cap length
    if extension and not safe.endswith(extension):
        safe += extension
    return safe


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Flatten a nested dict using dot notation.
    {'a': {'b': 1, 'c': 2}} -> {'a.b': 1, 'a.c': 2}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size."""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
