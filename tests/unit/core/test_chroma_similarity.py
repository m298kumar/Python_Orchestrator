"""Unit tests for ChromaDB similarity threshold filtering.

Tests that retrieve_examples and search_similar correctly filter
results based on the min_similarity parameter.
"""

import json
from unittest.mock import MagicMock

import pytest
from stlc_platform.core.storage.chroma_store import RequirementsVectorStore  # noqa: I001

# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_collection():
    """Create a mock ChromaDB collection."""
    coll = MagicMock()
    coll.count.return_value = 0
    coll.add.return_value = None
    return coll


def _make_store():
    """Create a store with mocked internals, ready to use."""
    s = RequirementsVectorStore()
    s._client = MagicMock()
    s._embed_fn = None
    s._coll_reqs = _mock_collection()
    s._coll_tcs = _mock_collection()
    s._coll_vocab = _mock_collection()
    s._ready = True
    return s


def _tc_meta(title="Test TC", ac_type="functional", test_type="positive"):
    """Build a tc_examples metadata dict with embedded tc_json."""
    tc = {"title": title, "test_type": test_type, "ac_type": ac_type, "steps": []}
    return {
        "ac_type": ac_type,
        "test_type": test_type,
        "domain": "",
        "title": title,
        "component": "",
        "tc_json": json.dumps(tc),
    }


# ── retrieve_examples threshold tests ───────────────────────────────────────


class TestRetrieveExamplesSimilarityThreshold:
    @pytest.fixture
    def store(self):
        return _make_store()

    def test_filters_low_similarity_results(self, store):
        """Results with similarity below threshold are excluded."""
        store._coll_tcs.count.return_value = 2
        store._coll_tcs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[_tc_meta("Good TC"), _tc_meta("Bad TC")]],
            "distances": [[0.3, 0.9]],  # similarities: 0.7, 0.1
        }
        results = store.retrieve_examples("login", "functional", "positive", min_similarity=0.4)
        assert len(results) == 1
        assert results[0]["title"] == "Good TC"
        assert results[0]["_similarity"] == 0.7

    def test_returns_results_above_threshold(self, store):
        """Results with similarity at or above threshold are included."""
        store._coll_tcs.count.return_value = 3
        store._coll_tcs.query.return_value = {
            "documents": [["doc1", "doc2", "doc3"]],
            "metadatas": [
                [
                    _tc_meta("TC High"),
                    _tc_meta("TC Medium"),
                    _tc_meta("TC Exact"),
                ]
            ],
            "distances": [[0.1, 0.3, 0.5]],  # similarities: 0.9, 0.7, 0.5
        }
        results = store.retrieve_examples("login", "functional", "positive", min_similarity=0.5)
        assert len(results) == 3
        assert results[0]["_similarity"] == 0.9
        assert results[1]["_similarity"] == 0.7
        assert results[2]["_similarity"] == 0.5

    def test_min_similarity_zero_returns_everything(self, store):
        """With min_similarity=0.0, all results are returned regardless of distance."""
        store._coll_tcs.count.return_value = 3
        store._coll_tcs.query.return_value = {
            "documents": [["doc1", "doc2", "doc3"]],
            "metadatas": [
                [
                    _tc_meta("TC1"),
                    _tc_meta("TC2"),
                    _tc_meta("TC3"),
                ]
            ],
            "distances": [[0.1, 0.7, 0.99]],  # similarities: 0.9, 0.3, 0.01
        }
        results = store.retrieve_examples(
            "login",
            "functional",
            "positive",
            min_similarity=0.0,
        )
        assert len(results) == 3

    def test_min_similarity_one_returns_nothing(self, store):
        """With min_similarity=1.0, practically no results pass the filter."""
        store._coll_tcs.count.return_value = 2
        store._coll_tcs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[_tc_meta("TC1"), _tc_meta("TC2")]],
            "distances": [[0.01, 0.2]],  # similarities: 0.99, 0.8
        }
        results = store.retrieve_examples(
            "login",
            "functional",
            "positive",
            min_similarity=1.0,
        )
        assert len(results) == 0

    def test_default_threshold_is_0_4(self, store):
        """The default min_similarity for retrieve_examples is 0.4."""
        store._coll_tcs.count.return_value = 2
        # distance 0.5 -> similarity 0.5 (passes 0.4 default)
        # distance 0.7 -> similarity 0.3 (fails 0.4 default)
        store._coll_tcs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[_tc_meta("Above"), _tc_meta("Below")]],
            "distances": [[0.5, 0.7]],
        }
        results = store.retrieve_examples("login", "functional", "positive")
        assert len(results) == 1
        assert results[0]["title"] == "Above"


# ── search_similar threshold tests ──────────────────────────────────────────


class TestSearchSimilarThreshold:
    @pytest.fixture
    def store(self):
        return _make_store()

    def test_filters_below_custom_threshold(self, store):
        """search_similar with a custom min_similarity filters low scores."""
        store._coll_reqs.count.return_value = 3
        store._coll_reqs.query.return_value = {
            "documents": [["doc1", "doc2", "doc3"]],
            "metadatas": [
                [
                    {"req_id": "REQ-001"},
                    {"req_id": "REQ-002"},
                    {"req_id": "REQ-003"},
                ]
            ],
            "distances": [[0.1, 0.5, 0.85]],  # similarities: 0.9, 0.5, 0.15
        }
        results = store.search_similar("login", min_similarity=0.4)
        assert len(results) == 2
        assert results[0]["similarity_score"] == 0.9
        assert results[1]["similarity_score"] == 0.5

    def test_default_threshold_is_0_3(self, store):
        """The default min_similarity for search_similar is 0.3."""
        store._coll_reqs.count.return_value = 2
        # distance 0.6 -> similarity 0.4 (passes 0.3 default)
        # distance 0.8 -> similarity 0.2 (fails 0.3 default)
        store._coll_reqs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"req_id": "REQ-001"}, {"req_id": "REQ-002"}]],
            "distances": [[0.6, 0.8]],
        }
        results = store.search_similar("login")
        assert len(results) == 1
        assert results[0]["similarity_score"] == 0.4

    def test_min_similarity_zero_returns_all(self, store):
        """search_similar with min_similarity=0.0 returns everything."""
        store._coll_reqs.count.return_value = 2
        store._coll_reqs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"req_id": "REQ-001"}, {"req_id": "REQ-002"}]],
            "distances": [[0.1, 0.95]],  # similarities: 0.9, 0.05
        }
        results = store.search_similar("login", min_similarity=0.0)
        assert len(results) == 2

    def test_high_threshold_filters_all(self, store):
        """search_similar with min_similarity=1.0 filters everything."""
        store._coll_reqs.count.return_value = 2
        store._coll_reqs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"req_id": "REQ-001"}, {"req_id": "REQ-002"}]],
            "distances": [[0.05, 0.2]],  # similarities: 0.95, 0.8
        }
        results = store.search_similar("login", min_similarity=1.0)
        assert len(results) == 0
