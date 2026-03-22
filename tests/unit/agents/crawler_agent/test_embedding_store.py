"""
Tests for CrawlerEmbeddingStore
================================
Validates the ChromaDB-backed embedding store for crawled page data.
All ChromaDB interactions are mocked to avoid external dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch

from stlc_platform.agents.crawler_agent.embedding_store import CrawlerEmbeddingStore
from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    SiteModelArtifact,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CHROMA_STORE_MODULE = "stlc_platform.core.storage.chroma_store"


def _sample_site_model() -> SiteModelArtifact:
    """Build a minimal site model with two pages."""
    return SiteModelArtifact(
        base_url="https://example.com",
        pages=[
            CrawledPageArtifact(
                url="https://example.com/login",
                title="Login Page",
                elements=[
                    PageElementArtifact(
                        element_type="input", name="username", selector="#username"
                    ),
                    PageElementArtifact(
                        element_type="input", name="password", selector="#password"
                    ),
                    PageElementArtifact(
                        element_type="button", name="submit", text="Sign In"
                    ),
                ],
                forms=[
                    {
                        "action": "/api/login",
                        "method": "post",
                        "fields": [
                            {"name": "username", "type": "text"},
                            {"name": "password", "type": "password"},
                        ],
                    }
                ],
            ),
            CrawledPageArtifact(
                url="https://example.com/dashboard",
                title="Dashboard",
                elements=[
                    PageElementArtifact(
                        element_type="link", name="profile", text="My Profile"
                    ),
                    PageElementArtifact(
                        element_type="link", name="settings", text="Settings"
                    ),
                ],
                forms=[],
            ),
        ],
    )


def _make_mock_store() -> CrawlerEmbeddingStore:
    """Create a CrawlerEmbeddingStore with mock internals pre-initialised."""
    store = CrawlerEmbeddingStore(
        chromadb_config=MagicMock(persist_directory="/tmp/test_chroma")
    )
    mock_collection = MagicMock()
    mock_collection.count.return_value = 0
    store._collection = mock_collection
    store._client = MagicMock()
    store._ready = True
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrawlerEmbeddingStoreInstantiation:
    """Basic construction tests."""

    def test_can_instantiate(self):
        """CrawlerEmbeddingStore can be created without errors."""
        store = CrawlerEmbeddingStore()
        assert store is not None
        assert store._ready is False

    def test_custom_collection_name(self):
        """A custom collection name is accepted."""
        store = CrawlerEmbeddingStore(collection_name="my_pages")
        assert store._collection_name == "my_pages"

    def test_default_collection_name(self):
        """Default collection name is 'crawled_pages'."""
        store = CrawlerEmbeddingStore()
        assert store._collection_name == "crawled_pages"


class TestEmbedSiteModel:
    """Tests for embed_site_model() with mocked ChromaDB."""

    def test_embed_creates_documents(self):
        """embed_site_model stores one document per page."""
        store = _make_mock_store()
        site_model = _sample_site_model()

        count = store.embed_site_model(site_model)

        assert count == 2
        store._collection.add.assert_called_once()

    def test_embed_metadata_contains_url(self):
        """Each embedded document has url, title, element_count, form_count metadata."""
        store = _make_mock_store()
        site_model = _sample_site_model()
        store.embed_site_model(site_model)

        add_call = store._collection.add.call_args
        metadatas = add_call.kwargs.get("metadatas", [])
        assert len(metadatas) == 2
        assert metadatas[0]["url"] == "https://example.com/login"
        assert metadatas[0]["element_count"] == 3
        assert metadatas[0]["form_count"] == 1
        assert metadatas[1]["url"] == "https://example.com/dashboard"
        assert metadatas[1]["element_count"] == 2
        assert metadatas[1]["form_count"] == 0

    def test_embed_document_contains_page_info(self):
        """Embedded documents include URL, title, elements, and forms info."""
        store = _make_mock_store()
        site_model = _sample_site_model()
        store.embed_site_model(site_model)

        add_call = store._collection.add.call_args
        documents = add_call.kwargs.get("documents", [])
        assert len(documents) == 2

        # First doc (login page) should contain URL and form info
        login_doc = documents[0]
        assert "https://example.com/login" in login_doc
        assert "Login Page" in login_doc
        assert "Forms" in login_doc

        # Second doc (dashboard) should have no forms section
        dashboard_doc = documents[1]
        assert "https://example.com/dashboard" in dashboard_doc
        assert "Dashboard" in dashboard_doc

    def test_embed_empty_site_model(self):
        """An empty site model results in zero documents and no add() call."""
        store = _make_mock_store()
        site_model = SiteModelArtifact(base_url="https://example.com", pages=[])

        count = store.embed_site_model(site_model)

        assert count == 0
        store._collection.add.assert_not_called()


class TestRetrieveContext:
    """Tests for retrieve_context() with mocked ChromaDB."""

    def test_retrieve_returns_results(self):
        """retrieve_context returns formatted results from ChromaDB query."""
        store = _make_mock_store()
        store._collection.count.return_value = 2
        store._collection.query.return_value = {
            "documents": [["Login page doc", "Dashboard doc"]],
            "metadatas": [
                [
                    {
                        "url": "https://example.com/login",
                        "title": "Login",
                        "element_count": 3,
                        "form_count": 1,
                    },
                    {
                        "url": "https://example.com/dashboard",
                        "title": "Dashboard",
                        "element_count": 2,
                        "form_count": 0,
                    },
                ]
            ],
            "distances": [[0.2, 0.5]],
        }

        results = store.retrieve_context("login form", n=3)

        assert len(results) == 2
        assert results[0]["document"] == "Login page doc"
        assert results[0]["metadata"]["url"] == "https://example.com/login"
        assert results[0]["similarity_score"] == 0.8  # 1 - 0.2
        assert results[1]["similarity_score"] == 0.5  # 1 - 0.5

    def test_retrieve_empty_collection(self):
        """retrieve_context returns empty list for empty collection."""
        store = _make_mock_store()
        store._collection.count.return_value = 0

        results = store.retrieve_context("anything")
        assert results == []


class TestGracefulFailure:
    """Tests for graceful handling when ChromaDB is unavailable."""

    def test_import_error_on_initialize(self):
        """If chromadb is not importable, initialize() raises ImportError."""
        store = CrawlerEmbeddingStore(
            chromadb_config=MagicMock(persist_directory="/tmp/test_chroma")
        )

        with patch(
            f"{_CHROMA_STORE_MODULE}._make_client",
            side_effect=ImportError("No module named 'chromadb'"),
        ):
            with pytest.raises(ImportError):
                store.initialize()

    def test_runtime_error_on_initialize(self):
        """If ChromaDB client creation fails, RuntimeError propagates."""
        store = CrawlerEmbeddingStore(
            chromadb_config=MagicMock(persist_directory="/tmp/test_chroma")
        )

        with patch(
            f"{_CHROMA_STORE_MODULE}._make_client",
            side_effect=RuntimeError("ChromaDB init failed"),
        ):
            with pytest.raises(RuntimeError):
                store.initialize()
