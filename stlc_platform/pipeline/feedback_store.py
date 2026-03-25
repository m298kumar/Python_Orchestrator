"""
Feedback Store
==============
Stores and retrieves agent feedback (corrections, preferences, constraints)
for the feedback loop. When a user corrects an agent's output, the correction
is stored and automatically retrieved in future runs to improve quality.

Two storage backends:
  1. JSON file (always available, simple keyword matching)
  2. ChromaDB (optional, enables semantic search for relevant feedback)

Retrieval strategy:
  - If ChromaDB is available and context is provided, semantic search re-ranks
    feedback by relevance to the current requirement/AC context.
  - Otherwise, falls back to keyword filtering + least-applied-first ordering.

Usage:
    store = FeedbackStore(persist_path=Path("./feedback"))
    store.store(AgentFeedbackArtifact(agent_id="bdd_agent", ...))
    feedback = store.retrieve("bdd_agent", context={"query": "login"}, limit=5)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from stlc_platform.core.contracts import AgentFeedbackArtifact

logger = logging.getLogger(__name__)

# ChromaDB collection name for feedback embeddings
_FEEDBACK_COLLECTION = "feedback_embeddings"


class FeedbackStore:
    """
    Stores and retrieves agent feedback for the feedback loop.

    Operates in JSON-only mode by default. When a ChromaDB store is
    provided, feedback is also indexed for semantic search.
    """

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        chroma_store: Any = None,
    ) -> None:
        self._persist_path = persist_path or Path("./feedback")
        self._chroma_store = chroma_store
        self._feedback: List[AgentFeedbackArtifact] = []
        self._chroma_collection: Any = None

        # Load existing feedback from disk
        self._load_from_disk()

        # Initialize ChromaDB collection for semantic search
        if self._chroma_store is not None:
            self._init_chroma_collection()

    def store(self, feedback: AgentFeedbackArtifact) -> None:
        """
        Store a feedback entry.

        Args:
            feedback: The feedback artifact to store.
        """
        # Set created_at if not set
        if not feedback.created_at:
            feedback.created_at = datetime.now(timezone.utc).isoformat()

        self._feedback.append(feedback)
        self._persist_to_disk()

        # Also index in ChromaDB for semantic search
        self._index_in_chroma(feedback)

    def retrieve(
        self,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[AgentFeedbackArtifact]:
        """
        Retrieve relevant feedback for an agent.

        When ChromaDB is available and context contains a 'query' string,
        feedback is semantically ranked by relevance. Otherwise, falls back
        to keyword filtering with least-applied-first ordering.

        Args:
            agent_id: The agent to retrieve feedback for.
            context: Optional context for relevance scoring.
                     Keys: 'query' (str), 'requirement' (object), 'ac_text' (str).
            limit: Maximum number of feedback items to return.

        Returns:
            List of matching AgentFeedbackArtifact items.
        """
        # Try semantic search first if context is available
        if self._chroma_collection is not None and context:
            semantic_results = self._semantic_retrieve(agent_id, context, limit)
            if semantic_results:
                # Increment applied_count for retrieved feedback
                for f in semantic_results:
                    f.applied_count += 1
                self._persist_to_disk()
                return semantic_results

        # Fallback: keyword filter + least-applied ordering
        matching = [f for f in self._feedback if f.agent_id == agent_id]

        # Sort by applied_count (least-applied first) then by created_at (newest first)
        matching.sort(key=lambda f: (f.applied_count, f.created_at or ""), reverse=False)

        # Limit results
        results = matching[:limit]

        # Increment applied_count for retrieved feedback
        for f in results:
            f.applied_count += 1

        if results:
            self._persist_to_disk()

        return results

    def list_all(self, agent_id: Optional[str] = None) -> List[AgentFeedbackArtifact]:
        """
        List all stored feedback, optionally filtered by agent_id.

        Args:
            agent_id: Optional filter — only feedback for this agent.

        Returns:
            List of all matching feedback items.
        """
        if agent_id:
            return [f for f in self._feedback if f.agent_id == agent_id]
        return list(self._feedback)

    def clear(self, agent_id: Optional[str] = None) -> int:
        """
        Clear feedback entries.

        Args:
            agent_id: If specified, only clear feedback for this agent.
                      If None, clear all feedback.

        Returns:
            Number of entries removed.
        """
        if agent_id:
            before = len(self._feedback)
            self._feedback = [f for f in self._feedback if f.agent_id != agent_id]
            removed = before - len(self._feedback)
        else:
            removed = len(self._feedback)
            self._feedback = []

        self._persist_to_disk()
        return removed

    @property
    def count(self) -> int:
        """Total number of stored feedback entries."""
        return len(self._feedback)

    def _persist_to_disk(self) -> None:
        """Save all feedback to a JSON file."""
        self._persist_path.mkdir(parents=True, exist_ok=True)
        feedback_file = self._persist_path / "feedback.json"

        data = [f.model_dump() for f in self._feedback]
        feedback_file.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )

    def _load_from_disk(self) -> None:
        """Load feedback from JSON file on disk."""
        feedback_file = self._persist_path / "feedback.json"
        if not feedback_file.exists():
            return

        try:
            data = json.loads(feedback_file.read_text(encoding="utf-8"))
            self._feedback = [AgentFeedbackArtifact(**item) for item in data]
        except (json.JSONDecodeError, TypeError, Exception):
            # Corrupted file — start fresh
            self._feedback = []

    # ── ChromaDB Semantic Search ──────────────────────────────────────────

    def _init_chroma_collection(self) -> None:
        """Initialize the ChromaDB collection for feedback embeddings."""
        try:
            if hasattr(self._chroma_store, "_client"):
                client = self._chroma_store._client
                self._chroma_collection = client.get_or_create_collection(
                    name=_FEEDBACK_COLLECTION,
                    metadata={"hnsw:space": "cosine"},
                )
                # Re-index existing feedback that may not be in ChromaDB yet
                self._reindex_existing()
            elif hasattr(self._chroma_store, "initialize"):
                # Store with lazy init — defer collection creation
                self._chroma_store.initialize()
                if hasattr(self._chroma_store, "_client"):
                    self._chroma_collection = self._chroma_store._client.get_or_create_collection(
                        name=_FEEDBACK_COLLECTION,
                        metadata={"hnsw:space": "cosine"},
                    )
                    self._reindex_existing()
        except Exception as e:
            logger.warning("Failed to init ChromaDB feedback collection: %s", e)
            self._chroma_collection = None

    def _reindex_existing(self) -> None:
        """Index any existing feedback entries that are not yet in ChromaDB."""
        if self._chroma_collection is None or not self._feedback:
            return
        try:
            existing_ids = set(self._chroma_collection.get(include=[])["ids"])
            for i, fb in enumerate(self._feedback):
                doc_id = f"fb_{fb.agent_id}_{i}"
                if doc_id not in existing_ids:
                    self._index_in_chroma(fb, doc_id=doc_id)
        except Exception as e:
            logger.debug("Reindex skipped: %s", e)

    def _index_in_chroma(
        self, feedback: AgentFeedbackArtifact, doc_id: Optional[str] = None
    ) -> None:
        """Index a single feedback entry in the ChromaDB collection."""
        if self._chroma_collection is None:
            return
        try:
            idx = len(self._feedback) - 1
            fid = doc_id or f"fb_{feedback.agent_id}_{idx}"
            document = (
                f"{feedback.feedback_type}: {feedback.message}"
            )
            metadata = {
                "agent_id": feedback.agent_id,
                "feedback_type": feedback.feedback_type,
                "created_at": feedback.created_at or "",
                "message": feedback.message[:500],
            }
            self._chroma_collection.upsert(
                documents=[document],
                metadatas=[metadata],
                ids=[fid],
            )
        except Exception as e:
            logger.debug("Failed to index feedback in ChromaDB: %s", e)

    def _semantic_retrieve(
        self,
        agent_id: str,
        context: Dict[str, Any],
        limit: int,
    ) -> List[AgentFeedbackArtifact]:
        """
        Retrieve feedback using ChromaDB semantic search.

        Builds a query from the context (query string, requirement, AC text)
        and finds the most relevant feedback entries for this agent.
        """
        if self._chroma_collection is None:
            return []

        # Build query text from context
        query_parts: List[str] = []
        if "query" in context:
            query_parts.append(str(context["query"]))
        if "ac_text" in context:
            query_parts.append(str(context["ac_text"])[:200])
        if "requirement" in context:
            req = context["requirement"]
            if hasattr(req, "title"):
                query_parts.append(req.title)
            if hasattr(req, "description"):
                query_parts.append(req.description[:200])

        if not query_parts:
            return []

        query_text = " ".join(query_parts)

        try:
            count = self._chroma_collection.count()
            if count == 0:
                return []

            results = self._chroma_collection.query(
                query_texts=[query_text],
                n_results=min(limit * 2, count),  # over-fetch, then filter by agent
                where={"agent_id": agent_id},
                include=["metadatas", "distances"],
            )

            if not results["metadatas"] or not results["metadatas"][0]:
                return []

            # Map ChromaDB results back to in-memory feedback objects
            matched: List[AgentFeedbackArtifact] = []
            for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
                similarity = 1 - dist
                if similarity < 0.3:  # minimum relevance threshold
                    continue
                msg = meta.get("message", "")
                # Find matching feedback in memory
                for fb in self._feedback:
                    if (
                        fb.agent_id == agent_id
                        and fb.message[:500] == msg
                        and fb not in matched
                    ):
                        matched.append(fb)
                        break

            return matched[:limit]

        except Exception as e:
            logger.debug("Semantic feedback retrieval failed: %s", e)
            return []
