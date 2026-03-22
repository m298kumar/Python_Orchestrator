"""
Shared Dependencies
===================
Singleton instances shared across all API routes.
Provides the agent registry, artifact store, run manager, and WebSocket hub.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from stlc_platform.api.websocket import ConnectionManager


class RunManager:
    """
    Manages pipeline run state in memory.

    Each run gets a unique ID and tracks status, artifacts, and metadata.
    Active runs are kept in memory; completed runs persist via ArtifactStore.
    """

    def __init__(self) -> None:
        self._runs: Dict[str, Dict[str, Any]] = {}

    def create_run(self, pipeline_name: str, run_id: Optional[str] = None) -> str:
        """Create a new run entry. Returns the run_id."""
        rid = run_id or str(uuid.uuid4())[:8]
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
        return self._runs.get(run_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        return list(reversed(self._runs.values()))

    def update_run(self, run_id: str, **kwargs: Any) -> None:
        if run_id in self._runs:
            self._runs[run_id].update(kwargs)

    def set_running(self, run_id: str) -> None:
        self.update_run(run_id, status="running")

    def set_completed(self, run_id: str, duration: float) -> None:
        self.update_run(
            run_id,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            total_duration_seconds=round(duration, 3),
        )

    def set_failed(self, run_id: str, error: str, duration: float) -> None:
        self.update_run(
            run_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            total_duration_seconds=round(duration, 3),
            error_message=error,
        )

    def store_artifacts(self, run_id: str, artifacts: Dict[str, Any]) -> None:
        if run_id in self._runs:
            self._runs[run_id]["artifacts"].update(artifacts)

    def store_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        if run_id in self._runs:
            self._runs[run_id]["metadata"].update(metadata)


# ── Singleton instances ──────────────────────────────────────────────────────

_ws_manager: Optional[ConnectionManager] = None
_run_manager: Optional[RunManager] = None
_agent_registry: Optional[Any] = None
_output_dir: Path = Path("./output")


def get_ws_manager() -> ConnectionManager:
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = ConnectionManager()
    return _ws_manager


def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager


def get_agent_registry():
    """Get or create the agent registry (lazy init)."""
    global _agent_registry
    if _agent_registry is None:
        from stlc_platform.pipeline.agent_registry import AgentRegistry
        _agent_registry = AgentRegistry.default()
    return _agent_registry


def get_output_dir() -> Path:
    return _output_dir


def set_output_dir(path: Path) -> None:
    global _output_dir
    _output_dir = path
