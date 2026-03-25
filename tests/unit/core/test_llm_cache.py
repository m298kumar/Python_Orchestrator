"""
Tests for LLMResponseCache — Phase C response caching.
"""

import json
import pytest
from pathlib import Path

from stlc_platform.core.llm.cache import LLMResponseCache


@pytest.fixture
def cache():
    return LLMResponseCache(max_size=5, enabled=True)


@pytest.fixture
def disabled_cache():
    return LLMResponseCache(max_size=5, enabled=False)


# ── Cache Key ──────────────────────────────────────────────────────────────


class TestCacheKey:
    def test_deterministic_key(self):
        k1 = LLMResponseCache.cache_key("sys", "usr", 0.4)
        k2 = LLMResponseCache.cache_key("sys", "usr", 0.4)
        assert k1 == k2

    def test_different_inputs_different_keys(self):
        k1 = LLMResponseCache.cache_key("sys", "usr", 0.4)
        k2 = LLMResponseCache.cache_key("sys", "usr", 0.5)
        k3 = LLMResponseCache.cache_key("sys", "different", 0.4)
        assert k1 != k2
        assert k1 != k3

    def test_key_is_sha256_hex(self):
        key = LLMResponseCache.cache_key("a", "b", 0.1)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


# ── Get / Put ──────────────────────────────────────────────────────────────


class TestGetPut:
    def test_miss_returns_none(self, cache):
        assert cache.get("nonexistent") is None

    def test_put_then_get(self, cache):
        cache.put("k1", "response1")
        assert cache.get("k1") == "response1"

    def test_overwrite_existing(self, cache):
        cache.put("k1", "old")
        cache.put("k1", "new")
        assert cache.get("k1") == "new"
        assert cache.size == 1

    def test_lru_eviction(self, cache):
        # Fill cache to capacity (max_size=5)
        for i in range(5):
            cache.put(f"k{i}", f"v{i}")
        assert cache.size == 5

        # Adding one more should evict k0 (LRU)
        cache.put("k5", "v5")
        assert cache.size == 5
        assert cache.get("k0") is None
        assert cache.get("k5") == "v5"

    def test_access_refreshes_lru(self, cache):
        cache.put("k0", "v0")
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")
        cache.put("k4", "v4")

        # Access k0 to move it to end
        cache.get("k0")

        # Now k1 is the LRU, should be evicted next
        cache.put("k5", "v5")
        assert cache.get("k0") == "v0"  # still there
        assert cache.get("k1") is None  # evicted


# ── Hit/Miss Tracking ─────────────────────────────────────────────────────


class TestHitTracking:
    def test_initial_counters_zero(self, cache):
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.hit_rate == 0.0

    def test_miss_increments(self, cache):
        cache.get("missing")
        assert cache.misses == 1
        assert cache.hits == 0

    def test_hit_increments(self, cache):
        cache.put("k", "v")
        cache.get("k")
        assert cache.hits == 1
        assert cache.misses == 0

    def test_hit_rate_calculation(self, cache):
        cache.put("k", "v")
        cache.get("k")       # hit
        cache.get("missing")  # miss
        assert cache.hit_rate == pytest.approx(0.5)

    def test_clear_resets_counters(self, cache):
        cache.put("k", "v")
        cache.get("k")
        cache.clear()
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.size == 0


# ── Disabled Cache ─────────────────────────────────────────────────────────


class TestDisabledCache:
    def test_put_is_noop(self, disabled_cache):
        disabled_cache.put("k", "v")
        assert disabled_cache.size == 0

    def test_get_returns_none(self, disabled_cache):
        assert disabled_cache.get("k") is None
        assert disabled_cache.misses == 0  # no tracking when disabled


# ── Disk Persistence ───────────────────────────────────────────────────────


class TestDiskPersistence:
    def test_persist_and_reload(self, tmp_path):
        cache1 = LLMResponseCache(max_size=10, persist_path=tmp_path)
        cache1.put("k1", "v1")
        cache1.put("k2", "v2")
        cache1.get("k1")  # hit
        cache1.get("miss")  # miss
        cache1.persist_to_disk()

        # Verify file was created
        assert (tmp_path / "llm_cache.json").exists()

        # Load into a new cache
        cache2 = LLMResponseCache(max_size=10, persist_path=tmp_path)
        assert cache2.get("k1") == "v1"
        assert cache2.get("k2") == "v2"
        # Counters are also restored
        assert cache2.hits >= 1  # at least the hit from loading + get

    def test_load_respects_max_size(self, tmp_path):
        # Write a cache file with more entries than max_size
        data = {"entries": {f"k{i}": f"v{i}" for i in range(20)}, "hits": 0, "misses": 0}
        (tmp_path / "llm_cache.json").write_text(json.dumps(data))

        cache = LLMResponseCache(max_size=5, persist_path=tmp_path)
        assert cache.size <= 5

    def test_missing_file_no_error(self, tmp_path):
        # Should not raise if file doesn't exist
        cache = LLMResponseCache(max_size=5, persist_path=tmp_path)
        assert cache.size == 0

    def test_corrupt_file_handled(self, tmp_path):
        (tmp_path / "llm_cache.json").write_text("not json{{{")
        cache = LLMResponseCache(max_size=5, persist_path=tmp_path)
        assert cache.size == 0
