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
            logging.getLogger(__name__).info(
                "Loaded %d historic runs from disk", len(self._runs)
            )
        except (json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).warning(
                "Could not load run history: %s", exc
            )

    def _persist_to_disk(self) -> None:
        """Persist completed/failed runs to disk."""
        import json

        terminal = [
            r for r in self._runs.values()
            if r.get("status") in ("completed", "failed")
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

    def store_artifacts(self, run_id: str, artifacts: Dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["artifacts"].update(artifacts)

    def store_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["metadata"].update(metadata)


class TestCaseStore:
    """Thread-safe in-memory store for generated test cases."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._test_cases: Dict[str, Dict[str, Any]] = {}

    def populate(self, test_cases: List[Dict[str, Any]]) -> int:
        count = 0
        with self._lock:
            for tc in test_cases:
                tc_id = tc.get("tc_id", "")
                if tc_id:
                    tc.setdefault("status", "generated")
                    self._test_cases[tc_id] = tc
                    count += 1
        return count

    def get(self, tc_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._test_cases.get(tc_id)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._test_cases)

    def update(self, tc_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            if tc_id not in self._test_cases:
                return None
            self._test_cases[tc_id].update(changes)
            return dict(self._test_cases[tc_id])

    def clear(self) -> None:
        with self._lock:
            self._test_cases.clear()

    def __bool__(self) -> bool:
        return bool(self._test_cases)


class FeatureFileStore:
    """Thread-safe in-memory store for generated BDD feature files."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._features: Dict[str, Dict[str, Any]] = {}

    def populate(self, features: List[Dict[str, Any]]) -> int:
        count = 0
        with self._lock:
            for f in features:
                filename = f.get("filename", "")
                if filename:
                    self._features[filename] = f
                    count += 1
        return count

    def get(self, filename: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._features.get(filename)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._features)

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
