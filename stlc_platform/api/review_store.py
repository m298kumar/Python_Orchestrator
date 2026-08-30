"""Persistent human-review decisions for generated test cases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class TestCaseReviewStore:
    """SQLite-backed audit trail keyed by pipeline run and test-case ID."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS test_case_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    tc_id TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
                    reason TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL DEFAULT '',
                    quality_score REAL NOT NULL,
                    quality_issues_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    rag_example_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_reviews_identity "
                "ON test_case_reviews(run_id, tc_id, id DESC)"
            )

    @staticmethod
    def content_hash(test_case: Dict[str, Any]) -> str:
        excluded = {
            "status",
            "approval_reason",
            "rejection_reason",
            "rag_example_id",
            "reviewer",
            "reviewed_at",
            "review_id",
            "review_reason",
            "review_content_hash",
        }
        canonical = json.dumps(
            {key: value for key, value in test_case.items() if key not in excluded},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def record(
        self,
        test_case: Dict[str, Any],
        decision: str,
        reason: str = "",
        reviewer: str = "",
        rag_example_id: str = "",
    ) -> Dict[str, Any]:
        run_id = str(test_case.get("run_id") or "legacy")
        tc_id = str(test_case.get("tc_id") or "")
        created_at = datetime.now(timezone.utc).isoformat()
        values = (
            run_id,
            tc_id,
            decision,
            reason,
            reviewer,
            float(test_case.get("quality_score", 0.0) or 0.0),
            json.dumps(test_case.get("quality_issues", []) or [], ensure_ascii=False),
            self.content_hash(test_case),
            rag_example_id,
            created_at,
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO test_case_reviews (
                    run_id, tc_id, decision, reason, reviewer, quality_score,
                    quality_issues_json, content_hash, rag_example_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            review_id = cursor.lastrowid
        return {
            "review_id": review_id,
            "status": decision,
            "reason": reason,
            "reviewer": reviewer,
            "rag_example_id": rag_example_id or None,
            "reviewed_at": created_at,
            "review_content_hash": values[7],
        }

    def latest(self, run_id: str, tc_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM test_case_reviews WHERE run_id = ? AND tc_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (run_id or "legacy", tc_id),
            ).fetchone()
        return self._row(row) if row else None

    def latest_for(self, identities: Iterable[tuple[str, str]]) -> Dict[tuple[str, str], Dict[str, Any]]:
        return {
            identity: review
            for identity in identities
            if (review := self.latest(identity[0], identity[1])) is not None
        }

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "review_id": row["id"],
            "status": row["decision"],
            "reason": row["reason"],
            "reviewer": row["reviewer"],
            "quality_score_at_review": row["quality_score"],
            "quality_issues_at_review": json.loads(row["quality_issues_json"]),
            "review_content_hash": row["content_hash"],
            "rag_example_id": row["rag_example_id"] or None,
            "reviewed_at": row["created_at"],
        }
