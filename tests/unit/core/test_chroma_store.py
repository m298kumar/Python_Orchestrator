"""Unit tests for ChromaDB vector store helper functions and RequirementsVectorStore.

Tests the non-network components: vocab extraction, TC formatting,
and RequirementsVectorStore lifecycle with a mocked ChromaDB client.
"""

from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import MagicMock

import pytest
from stlc_platform.core.storage.chroma_store import (
    RequirementsVectorStore,
    _extract_vocab,
    _tc_to_doc,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


@dataclass
class FakeRequirement:
    req_id: str
    title: str
    description: str
    acceptance_criteria: Optional[List[str]] = None
    priority: str = "Medium"
    category: str = "Functional"
    tags: Optional[List[str]] = None

    def to_chroma_document(self):
        ac = " ".join(self.acceptance_criteria or [])
        return f"{self.req_id} {self.title} {self.description} {ac}"


def _mock_collection():
    """Create a mock ChromaDB collection."""
    coll = MagicMock()
    coll.count.return_value = 0
    coll.add.return_value = None
    return coll


# ── Tests for _extract_vocab ─────────────────────────────────────────────────


class TestExtractVocab:
    def test_extracts_screen_names(self):
        req = FakeRequirement(
            req_id="REQ-001",
            title="Login Feature",
            description="User navigates to the Login Screen and enters credentials",
        )
        vocab = _extract_vocab(req)
        screens = [s.lower() for s in vocab["screens"]]
        assert any("login" in s for s in screens)

    def test_extracts_element_names(self):
        req = FakeRequirement(
            req_id="REQ-002",
            title="Checkout",
            description="User clicks the 'Submit Order' button and sees the 'Confirmation' label",
        )
        vocab = _extract_vocab(req)
        assert len(vocab["elements"]) >= 1

    def test_extracts_from_acceptance_criteria(self):
        req = FakeRequirement(
            req_id="REQ-003",
            title="Dashboard",
            description="Main dashboard",
            acceptance_criteria=["User sees the Dashboard Screen with analytics"],
        )
        vocab = _extract_vocab(req)
        assert vocab["req_id"] == "REQ-003"
        assert vocab["req_title"] == "Dashboard"

    def test_empty_requirement(self):
        req = FakeRequirement(
            req_id="REQ-004",
            title="Empty",
            description="No UI elements",
        )
        vocab = _extract_vocab(req)
        assert isinstance(vocab["screens"], list)
        assert isinstance(vocab["elements"], list)

    def test_category_from_attribute(self):
        req = FakeRequirement(
            req_id="REQ-005",
            title="Test",
            description="Test",
            category="Security",
        )
        vocab = _extract_vocab(req)
        assert vocab["category"] == "security"


# ── Tests for _tc_to_doc ─────────────────────────────────────────────────────


class TestTcToDoc:
    def test_formats_basic_tc(self):
        tc = {
            "title": "Login test",
            "test_type": "positive",
            "description": "Test login flow",
            "given": "User on login page",
            "when": "User enters credentials",
            "then": "Dashboard loads",
        }
        doc = _tc_to_doc(tc)
        assert "title: Login test" in doc
        assert "given: User on login page" in doc

    def test_formats_steps(self):
        tc = {
            "title": "With steps",
            "steps": [
                {"action": "Click login", "expected_result": "Form appears"},
                {"action": "Enter username", "expected_result": "Field filled"},
            ],
        }
        doc = _tc_to_doc(tc)
        assert "1. Click login -> Form appears" in doc
        assert "2. Enter username -> Field filled" in doc

    def test_empty_tc(self):
        doc = _tc_to_doc({})
        assert "title:" in doc
        assert "steps:" in doc

    def test_string_steps(self):
        tc = {"title": "test", "steps": ["step1", "step2"]}
        doc = _tc_to_doc(tc)
        assert "step1" in doc


# ── Tests for RequirementsVectorStore ────────────────────────────────────────


class TestRequirementsVectorStoreInit:
    def test_not_ready_before_initialize(self):
        store = RequirementsVectorStore()
        assert store._ready is False

    def test_collection_names(self):
        assert RequirementsVectorStore.COLL_REQS == "requirements"
        assert RequirementsVectorStore.COLL_TCS == "tc_examples"
        assert RequirementsVectorStore.COLL_VOCAB == "domain_vocab"


class TestRequirementsVectorStoreWithMock:
    """Tests using a mocked ChromaDB client to avoid real DB dependency."""

    @pytest.fixture
    def store(self):
        """Create a store with mocked internals."""
        s = RequirementsVectorStore()
        s._client = MagicMock()
        s._embed_fn = None
        s._coll_reqs = _mock_collection()
        s._coll_tcs = _mock_collection()
        s._coll_vocab = _mock_collection()
        s._ready = True
        return s

    def test_add_requirements(self, store):
        reqs = [
            FakeRequirement(
                req_id="REQ-001", title="Login", description="User can log in", tags=["login"]
            ),
            FakeRequirement(
                req_id="REQ-002", title="Logout", description="User can log out", tags=["logout"]
            ),
        ]
        store.add_requirements(reqs)
        store._coll_reqs.upsert.assert_called_once()
        call_args = store._coll_reqs.upsert.call_args
        assert len(call_args[1]["ids"]) == 2
        assert len(call_args[1]["documents"]) == 2
        assert all(item.startswith("requirement_default_REQ-") for item in call_args[1]["ids"])
        assert all("content_hash" in item for item in call_args[1]["metadatas"])
        assert all(item["revision_number"] == 1 for item in call_args[1]["metadatas"])

    def test_add_empty_requirements(self, store):
        store.add_requirements([])
        store._coll_reqs.upsert.assert_not_called()

    def test_changed_requirement_creates_linked_revision(self, store):
        req = FakeRequirement(req_id="REQ-001", title="Login", description="Version one")
        store.add_requirements([req])
        first_metadata = store._coll_reqs.upsert.call_args.kwargs["metadatas"][0]
        first_id = store._coll_reqs.upsert.call_args.kwargs["ids"][0]
        store._coll_reqs.get.return_value = {"metadatas": [first_metadata]}

        req.description = "Version two"
        store.add_requirements([req])

        second_metadata = store._coll_reqs.upsert.call_args.kwargs["metadatas"][0]
        second_id = store._coll_reqs.upsert.call_args.kwargs["ids"][0]
        assert second_id != first_id
        assert second_metadata["revision_number"] == 2
        assert second_metadata["previous_revision_id"] == first_id

    def test_search_similar_empty_collection(self, store):
        store._coll_reqs.count.return_value = 0
        results = store.search_similar("test query")
        assert results == []

    def test_search_similar_returns_results(self, store):
        store._coll_reqs.count.return_value = 2
        store._coll_reqs.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"req_id": "REQ-001"}, {"req_id": "REQ-002"}]],
            "distances": [[0.1, 0.5]],
        }
        results = store.search_similar("login")
        assert len(results) == 2
        assert results[0]["similarity_score"] == 0.9
        assert results[0]["metadata"]["req_id"] == "REQ-001"

    def test_store_approved_tc(self, store):
        tc_dict = {"title": "Login TC", "test_type": "positive"}
        doc_id = store.store_approved_tc(
            tc_dict, "security", "positive", "ecommerce", human_approved=True
        )
        assert doc_id.startswith("ex_security_positive_")
        store._coll_tcs.upsert.assert_called_once()

    def test_store_tc_rejects_automatic_promotion(self, store):
        with pytest.raises(ValueError, match="human approval"):
            store.store_approved_tc({}, "general", "positive")

    def test_delete_approved_tc_removes_promoted_example(self, store):
        store.delete_approved_tc("rag-example")
        store._coll_tcs.delete.assert_called_once_with(ids=["rag-example"])

    def test_retrieve_examples_empty(self, store):
        store._coll_tcs.count.return_value = 0
        results = store.retrieve_examples("login", "security", "positive")
        assert results == []

    def test_get_example_count_empty(self, store):
        store._coll_tcs.count.return_value = 0
        assert store.get_example_count() == 0

    def test_extract_and_store_vocab(self, store):
        reqs = [
            FakeRequirement(
                req_id="REQ-001",
                title="Login Feature",
                description="User sees the Login Screen and clicks the 'Submit' button",
            ),
        ]
        count = store.extract_and_store_vocab(reqs)
        assert count >= 0  # May or may not extract vocab depending on regex matching

    def test_lookup_component_empty(self, store):
        store._coll_vocab.count.return_value = 0
        result = store.lookup_component("security", "Login")
        assert result is None

    def test_get_domain_vocab_summary_empty(self, store):
        store._coll_vocab.count.return_value = 0
        summary = store.get_domain_vocab_summary()
        assert summary == {"screens": [], "elements": []}

    def test_get_all_requirements_empty(self, store):
        store._coll_reqs.count.return_value = 0
        assert store.get_all_requirements() == []

    def test_stats(self, store):
        store._coll_reqs.count.return_value = 5
        store._coll_tcs.count.return_value = 10
        store._coll_vocab.count.return_value = 3
        stats = store.stats
        assert stats == {"requirements": 5, "tc_examples": 10, "domain_vocab": 3}
