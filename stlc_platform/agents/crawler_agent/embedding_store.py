"""
Crawler Embedding Store
=======================
ChromaDB-backed vector store for crawled page data.  Stores page content
as embeddings so that downstream agents (e.g., test generators) can retrieve
relevant page context via semantic search.

This is an *optional* enhancement — if ChromaDB is not installed the caller
gets a clear ``ImportError`` on construction, and the CrawlerAgent wraps
usage in try/except so it degrades gracefully.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from stlc_platform.core.contracts import SiteModelArtifact

logger = logging.getLogger(__name__)


class CrawlerEmbeddingStore:
    """Lightweight ChromaDB wrapper for crawled page embeddings.

    Uses the same client factory as
    ``stlc_platform.core.storage.chroma_store`` so that a single
    ChromaDB instance is shared across the platform.

    Parameters
    ----------
    collection_name:
        ChromaDB collection to use (default ``"crawled_pages"``).
    chromadb_config:
        Optional config object.  When *None* the global
        ``stlc_config.yaml`` config is loaded via ``config_loader``.
    """

    COLLECTION_NAME = "crawled_pages"

    def __init__(
        self,
        collection_name: Optional[str] = None,
        chromadb_config: Optional[Any] = None,
    ) -> None:
        self._collection_name = collection_name or self.COLLECTION_NAME
        self._config = chromadb_config
        self._client: Any = None
        self._collection: Any = None
        self._ready = False

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _get_config(self) -> Any:
        # If config is a raw dict it cannot be used directly (attribute access will fail).
        # Fall back to the global config_loader which always returns a proper config object.
        if self._config is not None and not isinstance(self._config, dict):
            return self._config
        from stlc_platform.core.config_loader import config

        return config.chromadb

    def initialize(self) -> None:
        """Create the ChromaDB client and collection (lazy, idempotent)."""
        if self._ready:
            return

        from stlc_platform.core.storage.chroma_store import _make_client

        cfg = self._get_config()
        self._client = _make_client(cfg.persist_directory)

        # Do NOT inject a custom embedding function for the crawled_pages collection.
        # Using ChromaDB's stable built-in default means the collection opens cleanly
        # on every restart regardless of whether Ollama or sentence_transformers is
        # available — eliminating the embedding-function conflict that occurred when
        # the runtime environment changed between sessions.
        kw: Dict[str, Any] = {
            "name": self._collection_name,
            "metadata": {"hnsw:space": "cosine"},
        }
        try:
            self._collection = self._client.get_or_create_collection(**kw)
        except Exception as exc:
            err = str(exc).lower()
            if "embedding function" in err or "conflict" in err:
                # One-time cleanup: collection was created with a custom embedding
                # function in a previous session. Delete it so it is recreated with
                # the default function going forward. Crawled-page data is ephemeral
                # and will be repopulated on the next crawl run.
                logger.info(
                    "Recreating collection '%s' with default embedding function "
                    "(stale custom-function configuration detected).",
                    self._collection_name,
                )
                try:
                    self._client.delete_collection(self._collection_name)
                except Exception as del_exc:
                    logger.debug(
                        "Could not delete stale collection '%s': %s",
                        self._collection_name, del_exc,
                    )
                self._collection = self._client.get_or_create_collection(**kw)
            else:
                raise

        self._ready = True
        logger.info(
            "CrawlerEmbeddingStore ready — collection '%s' (%d docs)",
            self._collection_name,
            self._collection.count(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_site_model(self, site_model: SiteModelArtifact) -> int:
        """Embed all pages from a ``SiteModelArtifact`` into ChromaDB.

        Returns the number of documents stored.
        """
        self.initialize()

        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        for page in site_model.pages:
            doc_parts = [f"URL: {page.url}"]
            if page.title:
                doc_parts.append(f"Title: {page.title}")

            # Elements summary
            element_count = len(page.elements)
            if page.elements:
                element_types: Dict[str, int] = {}
                for el in page.elements:
                    element_types[el.element_type] = element_types.get(el.element_type, 0) + 1
                el_summary = ", ".join(f"{k}: {v}" for k, v in sorted(element_types.items()))
                doc_parts.append(f"Elements ({element_count}): {el_summary}")

                # Include element names/text for richer embeddings
                element_names = [el.name or el.text for el in page.elements if el.name or el.text][
                    :20
                ]  # Cap at 20 to keep document size reasonable
                if element_names:
                    doc_parts.append("Element details: " + "; ".join(element_names))

            # Forms summary
            form_count = len(page.forms)
            if page.forms:
                form_summaries = []
                for form in page.forms:
                    action = form.get("action", "")
                    method = form.get("method", "")
                    fields = form.get("fields", [])
                    field_names = [f.get("name", "") for f in fields if isinstance(f, dict)]
                    form_summaries.append(
                        f"{method.upper()} {action} (fields: {', '.join(field_names[:10])})"
                    )
                doc_parts.append(f"Forms ({form_count}): " + "; ".join(form_summaries))

            document = "\n".join(doc_parts)
            doc_id = f"page_{uuid.uuid4().hex[:12]}"

            documents.append(document)
            metadatas.append(
                {
                    "url": page.url,
                    "title": page.title or "",
                    "element_count": element_count,
                    "form_count": form_count,
                }
            )
            ids.append(doc_id)

        if documents:
            self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info("Embedded %d page(s) into '%s'", len(documents), self._collection_name)

        return len(documents)

    def retrieve_context(self, query: str, n: int = 3) -> List[Dict[str, Any]]:
        """Query the collection for relevant page context.

        Returns a list of dicts with keys: ``document``, ``metadata``,
        ``similarity_score``.
        """
        self.initialize()

        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(n, count),
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        return [
            {
                "document": doc,
                "metadata": meta,
                "similarity_score": round(1 - dist, 4),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    @property
    def count(self) -> int:
        """Return the number of documents in the collection."""
        self.initialize()
        return int(self._collection.count())
