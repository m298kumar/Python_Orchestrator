"""Unit tests for the Artifact Store."""

from __future__ import annotations

from pathlib import Path

import pytest
from stlc_platform.pipeline.artifact_store import ArtifactStore


class TestStoreAndRetrieve:
    def test_store_and_get(self):
        store = ArtifactStore()
        store.store("stage_a", {"model": {"key": "value"}})
        assert store.get("stage_a", "model") == {"key": "value"}

    def test_has_stage(self):
        store = ArtifactStore()
        assert store.has_stage("x") is False
        store.store("x", {"out": 1})
        assert store.has_stage("x") is True

    def test_get_all(self):
        store = ArtifactStore()
        store.store("s1", {"a": 1, "b": 2})
        assert store.get_all("s1") == {"a": 1, "b": 2}

    def test_missing_stage_raises(self):
        store = ArtifactStore()
        with pytest.raises(KeyError, match="stage_a"):
            store.get("stage_a", "key")

    def test_missing_key_raises(self):
        store = ArtifactStore()
        store.store("s1", {"a": 1})
        with pytest.raises(KeyError, match="b"):
            store.get("s1", "b")

    def test_overwrite_replaces(self):
        store = ArtifactStore()
        store.store("s1", {"a": 1})
        store.store("s1", {"a": 2})
        assert store.get("s1", "a") == 2


class TestDiskPersistence:
    def test_persist_and_load(self, tmp_path: Path):
        store = ArtifactStore(run_dir=tmp_path / "run1")
        store.store("s1", {"result": [1, 2, 3]})
        store.store("s2", {"data": "hello"})
        store.persist_to_disk()

        # Verify files exist
        assert (tmp_path / "run1" / "manifest.json").exists()
        assert (tmp_path / "run1" / "s1.json").exists()

        # Load into a fresh store
        store2 = ArtifactStore(run_dir=tmp_path / "run1")
        loaded = store2.load_from_disk()
        assert loaded == ["s1", "s2"]
        assert store2.get("s1", "result") == [1, 2, 3]
        assert store2.get("s2", "data") == "hello"

    def test_partial_load(self, tmp_path: Path):
        store = ArtifactStore(run_dir=tmp_path / "run2")
        store.store("s1", {"a": 1})
        store.store("s2", {"b": 2})
        store.store("s3", {"c": 3})
        store.persist_to_disk()

        store2 = ArtifactStore(run_dir=tmp_path / "run2")
        loaded = store2.load_from_disk(up_to_stage="s2")
        assert loaded == ["s1", "s2"]
        assert store2.has_stage("s1")
        assert store2.has_stage("s2")
        assert not store2.has_stage("s3")
