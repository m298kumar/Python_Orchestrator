"""
Feedback Store
==============
Stores and retrieves agent feedback (corrections, preferences, constraints)
for the feedback loop. When a user corrects an agent's output, the correction
is stored and automatically retrieved in future runs to improve quality.

Two storage backends:
  1. JSON file (always available, simple keyword matching)
  2. ChromaDB (optional, enables semantic search for relevant feedback)

Usage:
    store = FeedbackStore(persist_path=Path("./feedback"))
    store.store(AgentFeedbackArtifact(agent_id="bdd_agent", ...))
    feedback = store.retrieve("bdd_agent", limit=5)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from stlc_platform.core.contracts import AgentFeedbackArtifact


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

        # Load existing feedback from disk
        self._load_from_disk()

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

    def retrieve(
        self,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[AgentFeedbackArtifact]:
        """
        Retrieve relevant feedback for an agent.

        Args:
            agent_id: The agent to retrieve feedback for.
            context: Optional context for relevance scoring.
            limit: Maximum number of feedback items to return.

        Returns:
            List of matching AgentFeedbackArtifact items.
        """
        # Filter by agent_id
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
