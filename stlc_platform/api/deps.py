"""
Shared Dependencies
===================
Singleton instances shared across all API routes.
Provides the agent registry, artifact store, run manager, and WebSocket hub.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from stlc_platform.api.websocket import ConnectionManager


class RunManager:
    """
    Manages pipeline run state with in-memory cache and disk persistence.

    Each run gets a unique ID and tracks status, artifacts, and metadata.
    Completed/failed runs are persisted to ``{persist_dir}/runs.json``
    so they survive server restarts.
    """

    AUTO_ARCHIVE_DAYS = 30  # Runs older than this are auto-archived on load

    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._persist_dir = persist_dir or Path("./output")
        self._persist_file = self._persist_dir / "runs.json"
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load previously persisted runs from disk on startup."""
        import json
        import logging

        if not self._persist_file.exists():
            return
        try:
            data = json.loads(self._persist_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for run in data:
                    rid = run.get("run_id", "")
                    if rid:
                        self._runs[rid] = run
                        # Auto-archive runs older than AUTO_ARCHIVE_DAYS
                        if not run.get("archived") and run.get("started_at"):
                            try:
                                started = datetime.fromisoformat(
                                    run["started_at"].replace("Z", "+00:00")
                                )
                                if (
                                    datetime.now(timezone.utc) - started
                                ).days >= self.AUTO_ARCHIVE_DAYS:
                                    self._runs[rid]["archived"] = True
                                    self._runs[rid]["archived_at"] = datetime.now(
                                        timezone.utc
                                    ).isoformat()
                            except (ValueError, TypeError):
                                pass
            logging.getLogger(__name__).info("Loaded %d historic runs from disk", len(self._runs))
        except (json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).warning("Could not load run history: %s", exc)

    def _persist_to_disk(self) -> None:
        """Persist completed/failed/cancelled runs to disk."""
        import json

        terminal = [
            r
            for r in self._runs.values()
            if r.get("status") in ("completed", "failed", "cancelled")
        ]
        if not terminal:
            return
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._persist_file.write_text(
                json.dumps(terminal, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    def create_run(self, pipeline_name: str, run_id: Optional[str] = None) -> str:
        """Create a new run entry. Returns the run_id."""
        rid = run_id or str(uuid.uuid4())
        with self._lock:
            self._runs[rid] = {
                "run_id": rid,
                "pipeline_name": pipeline_name,
                "status": "pending",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "current_stage": None,
                "stages_completed": [],
                "stages_failed": [],
                "stages_skipped": [],
                "total_duration_seconds": None,
                "error_message": None,
                "artifacts": {},
                "metadata": {},
            }
        return rid

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            # Return a shallow copy to prevent external mutation without lock
            return dict(run)

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self._runs.values()))

    def update_run(self, run_id: str, **kwargs: Any) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(kwargs)

    def set_running(self, run_id: str) -> None:
        self.update_run(run_id, status="running")

    def set_completed(self, run_id: str, duration: float) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(
                    status="completed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    total_duration_seconds=round(duration, 3),
                )
        self._persist_to_disk()

    def set_failed(self, run_id: str, error: str, duration: float) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(
                    status="failed",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    total_duration_seconds=round(duration, 3),
                    error_message=error,
                )
        self._persist_to_disk()

    def set_cancelled(self, run_id: str) -> None:
        """Mark a run as cancelled."""
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(
                    status="cancelled",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    error_message="Cancelled by user",
                )
        self._persist_to_disk()

    def is_cancelled(self, run_id: str) -> bool:
        """Check if a run has been cancelled."""
        with self._lock:
            run = self._runs.get(run_id)
            return run is not None and run["status"] == "cancelled"

    # ── Archive / Delete helpers ─────────────────────────────────────────────

    def archive_run(self, run_id: str) -> bool:
        """Soft-archive a run so it is hidden from active views. Returns True if found."""
        with self._lock:
            if run_id not in self._runs:
                return False
            self._runs[run_id]["archived"] = True
            self._runs[run_id]["archived_at"] = datetime.now(timezone.utc).isoformat()
        self._persist_to_disk()
        return True

    def restore_run(self, run_id: str) -> bool:
        """Un-archive a run. Returns True if found."""
        with self._lock:
            if run_id not in self._runs:
                return False
            self._runs[run_id]["archived"] = False
            self._runs[run_id].pop("archived_at", None)
        self._persist_to_disk()
        return True

    def delete_run(self, run_id: str) -> bool:
        """Hard-delete a single run from memory and disk. Returns True if found."""
        import shutil

        with self._lock:
            if run_id not in self._runs:
                return False
            del self._runs[run_id]
        run_dir = self._persist_dir / ".stlc_runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        self._persist_to_disk()
        return True

    def clear_all_runs(self) -> int:
        """Hard-delete ALL terminal runs (completed/failed/cancelled/archived).
        Active (pending/running) runs are preserved. Returns count deleted."""
        import shutil

        with self._lock:
            to_delete = [
                rid
                for rid, r in self._runs.items()
                if r.get("status") not in ("pending", "running")
            ]
            for rid in to_delete:
                del self._runs[rid]

        runs_dir = self._persist_dir / ".stlc_runs"
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir() and run_dir.name in to_delete:
                    shutil.rmtree(run_dir, ignore_errors=True)

        self._persist_to_disk()
        return len(to_delete)

    def store_artifacts(self, run_id: str, artifacts: Dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["artifacts"].update(artifacts)

    def store_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["metadata"].update(metadata)


class TestCaseStore:
    """Thread-safe in-memory store for generated test cases.

    Each test case is tagged with the run_id that produced it.
    Composite keys (tc_id::run_id) prevent cross-run overwrites.
    The consolidated view (get_all) returns every unique entry across all runs.
    Use get_by_run(run_id) to retrieve only test cases from a specific run.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._test_cases: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _key(tc_id: str, run_id: str = "") -> str:
        return f"{tc_id}::{run_id}" if run_id else tc_id

    def populate(self, test_cases: List[Dict[str, Any]], run_id: str = "") -> int:
        """Merge test cases into the store, tagging each with run_id.

        Uses composite keys so the same tc_id from different runs coexist.
        """
        count = 0
        with self._lock:
            for tc in test_cases:
                tc_id = tc.get("tc_id", "")
                if tc_id:
                    entry = dict(tc)
                    entry.setdefault("status", "generated")
                    entry.setdefault("quality_validated", True)
                    if run_id:
                        entry["run_id"] = run_id
                    self._test_cases[self._key(tc_id, run_id)] = entry
                    count += 1
        return count

    def clear_run(self, run_id: str) -> int:
        """Remove all test cases belonging to a specific run. Returns count removed."""
        with self._lock:
            to_remove = [k for k, v in self._test_cases.items() if v.get("run_id") == run_id]
            for k in to_remove:
                del self._test_cases[k]
            return len(to_remove)

    def get(self, tc_id: str, run_id: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            if run_id:
                return self._test_cases.get(self._key(tc_id, run_id))
            # Try bare key first (backward compat), then scan for composite match
            if tc_id in self._test_cases:
                return self._test_cases[tc_id]
            for k, v in self._test_cases.items():
                if k.startswith(tc_id + "::"):
                    return v
            return None

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Return all test cases across all runs (consolidated view)."""
        with self._lock:
            return dict(self._test_cases)

    def get_by_run(self, run_id: str) -> Dict[str, Dict[str, Any]]:
        """Return only test cases tagged with the given run_id."""
        with self._lock:
            return {k: v for k, v in self._test_cases.items() if v.get("run_id") == run_id}

    def update(
        self, tc_id: str, changes: Dict[str, Any], run_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            if run_id:
                key = self._key(tc_id, run_id)
                if key not in self._test_cases:
                    return None
                self._test_cases[key].update(changes)
                return dict(self._test_cases[key])
            # Support both bare and composite keys
            if tc_id in self._test_cases:
                self._test_cases[tc_id].update(changes)
                return dict(self._test_cases[tc_id])
            for k in self._test_cases:
                if k.startswith(tc_id + "::"):
                    self._test_cases[k].update(changes)
                    return dict(self._test_cases[k])
            return None

    def clear(self) -> None:
        with self._lock:
            self._test_cases.clear()

    def __bool__(self) -> bool:
        return bool(self._test_cases)


class FeatureFileStore:
    """Thread-safe in-memory store for generated BDD feature files.

    Each feature file is tagged with the run_id that produced it.
    Composite keys (filename::run_id) prevent cross-run overwrites.
    The consolidated view (get_all) returns every entry across all runs.
    Use get_by_run(run_id) for a specific run's files.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._features: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _key(filename: str, run_id: str = "") -> str:
        return f"{filename}::{run_id}" if run_id else filename

    def populate(self, features: List[Dict[str, Any]], run_id: str = "") -> int:
        """Merge feature files into the store, tagging each with run_id.

        Uses composite keys so the same filename from different runs coexist.
        """
        count = 0
        with self._lock:
            for f in features:
                filename = f.get("filename", "")
                if filename:
                    entry = dict(f)
                    if run_id:
                        entry["run_id"] = run_id
                    self._features[self._key(filename, run_id)] = entry
                    count += 1
        return count

    def clear_run(self, run_id: str) -> int:
        """Remove all feature files belonging to a specific run. Returns count removed."""
        with self._lock:
            to_remove = [k for k, v in self._features.items() if v.get("run_id") == run_id]
            for k in to_remove:
                del self._features[k]
            return len(to_remove)

    def get(self, filename: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            # Try bare key first (backward compat), then scan for composite match
            if filename in self._features:
                return self._features[filename]
            for k, v in self._features.items():
                if k.startswith(filename + "::"):
                    return v
            return None

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Return all feature files across all runs (consolidated view)."""
        with self._lock:
            return dict(self._features)

    def get_by_run(self, run_id: str) -> Dict[str, Dict[str, Any]]:
        """Return only feature files tagged with the given run_id."""
        with self._lock:
            return {k: v for k, v in self._features.items() if v.get("run_id") == run_id}

    def clear(self) -> None:
        with self._lock:
            self._features.clear()

    def __bool__(self) -> bool:
        return bool(self._features)


# ── Singleton instances ──────────────────────────────────────────────────────

_ws_manager: Optional[ConnectionManager] = None
_run_manager: Optional[RunManager] = None
_agent_registry: Optional[Any] = None
_tc_store: Optional[TestCaseStore] = None
_ff_store: Optional[FeatureFileStore] = None
_metrics_collector: Optional[Any] = None
_output_dir: Path = Path("./output")
_init_lock = threading.Lock()


def get_ws_manager() -> ConnectionManager:
    global _ws_manager
    if _ws_manager is None:
        with _init_lock:
            if _ws_manager is None:
                _ws_manager = ConnectionManager()
    return _ws_manager


def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        with _init_lock:
            if _run_manager is None:
                _run_manager = RunManager()
    return _run_manager


def get_agent_registry():
    """Get or create the agent registry (lazy init)."""
    global _agent_registry
    if _agent_registry is None:
        with _init_lock:
            if _agent_registry is None:
                from stlc_platform.pipeline.agent_registry import AgentRegistry

                _agent_registry = AgentRegistry.default()
    return _agent_registry


def get_tc_store() -> TestCaseStore:
    global _tc_store
    if _tc_store is None:
        with _init_lock:
            if _tc_store is None:
                _tc_store = TestCaseStore()
    return _tc_store


def get_ff_store() -> FeatureFileStore:
    global _ff_store
    if _ff_store is None:
        with _init_lock:
            if _ff_store is None:
                _ff_store = FeatureFileStore()
    return _ff_store


def get_metrics_collector():
    """Get or create the metrics collector singleton (lazy init)."""
    global _metrics_collector
    if _metrics_collector is None:
        with _init_lock:
            if _metrics_collector is None:
                from stlc_platform.pipeline.metrics_collector import MetricsCollector

                _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_output_dir() -> Path:
    return _output_dir


def set_output_dir(path: Path) -> None:
    global _output_dir
    _output_dir = path
