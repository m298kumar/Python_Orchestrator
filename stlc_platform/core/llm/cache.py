"""
LLM Response Cache
==================
Caches LLM responses keyed by (system_prompt + user_prompt + temperature).
Avoids redundant LLM calls when the same requirement is processed again.

Features:
  - In-memory LRU cache with configurable max size
  - Optional disk persistence (JSON) between runs
  - SHA-256 cache keys for deterministic lookups
  - Hit/miss counting for observability
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LLMResponseCache:
    """
    LRU cache for LLM responses with optional disk persistence.

    Usage:
        cache = LLMResponseCache(max_size=500, persist_path=Path("./cache"))
        key = cache.cache_key(system_prompt, user_prompt, 0.4)
        cached = cache.get(key)
        if cached is None:
            response = llm.generate(...)
            cache.put(key, response)
    """

    def __init__(
        self,
        max_size: int = 500,
        persist_path: Optional[Path] = None,
        enabled: bool = True,
    ) -> None:
        self._max_size = max_size
        self._persist_path = persist_path
        self._enabled = enabled
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._hits = 0
        self._misses = 0

        if self._persist_path and self._enabled:
            self._load_from_disk()

    @staticmethod
    def cache_key(
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        """
        Generate a deterministic cache key from prompt + temperature.

        Uses SHA-256 hash of the concatenated inputs.
        """
        raw = f"sys:{system_prompt}|usr:{user_prompt}|t:{temperature:.4f}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[str]:
        """
        Look up a cached response.

        Returns the cached response string, or None if not found.
        Moves accessed items to the end (LRU).
        """
        if not self._enabled:
            return None

        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]

        self._misses += 1
        return None

    def put(self, key: str, response: str) -> None:
        """
        Store a response in the cache.

        Evicts the least-recently-used entry if at capacity.
        """
        if not self._enabled:
            return

        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = response
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # evict LRU
            self._cache[key] = response

    @property
    def hits(self) -> int:
        """Number of cache hits."""
        return self._hits

    @property
    def misses(self) -> int:
        """Number of cache misses."""
        return self._misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a float (0.0-1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """Current number of cached entries."""
        return len(self._cache)

    def clear(self) -> None:
        """Clear all cached entries and reset counters."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def persist_to_disk(self) -> None:
        """Save cache to disk as JSON."""
        if self._persist_path is None:
            return
        try:
            self._persist_path.mkdir(parents=True, exist_ok=True)
            cache_file = self._persist_path / "llm_cache.json"
            data = {
                "entries": dict(self._cache),
                "hits": self._hits,
                "misses": self._misses,
            }
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Failed to persist LLM cache: %s", e)

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if self._persist_path is None:
            return
        cache_file = self._persist_path / "llm_cache.json"
        if not cache_file.exists():
            return
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            entries = data.get("entries", {})
            # Only load up to max_size entries (most recent)
            items = list(entries.items())
            if len(items) > self._max_size:
                items = items[-self._max_size:]
            self._cache = OrderedDict(items)
            self._hits = data.get("hits", 0)
            self._misses = data.get("misses", 0)
            logger.debug("Loaded %d cache entries from disk", len(self._cache))
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to load LLM cache from disk: %s", e)
            self._cache = OrderedDict()
