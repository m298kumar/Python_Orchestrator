"""
WebSocket Connection Manager
=============================
Manages WebSocket connections for real-time pipeline progress updates.
Broadcasts stage events to all connected clients for a given run_id.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by pipeline run_id."""

    def __init__(self) -> None:
        # run_id -> set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept a WebSocket connection and register it for a run."""
        await websocket.accept()
        if run_id not in self._connections:
            self._connections[run_id] = set()
        self._connections[run_id].add(websocket)
        logger.info(
            "WebSocket connected for run %s (total: %d)", run_id, len(self._connections[run_id])
        )

    def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket connection."""
        if run_id in self._connections:
            self._connections[run_id].discard(websocket)
            if not self._connections[run_id]:
                del self._connections[run_id]
            logger.info("WebSocket disconnected for run %s", run_id)

    async def broadcast(self, run_id: str, event: str, data: Dict[str, Any]) -> None:
        """Broadcast a message to all connections for a run_id."""
        message = json.dumps(
            {
                "event": event,
                "run_id": run_id,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if run_id not in self._connections:
            return

        dead: List[WebSocket] = []
        for ws in self._connections[run_id]:
            try:
                await ws.send_text(message)
            except Exception:
                logger.debug("WebSocket send failed for run %s", run_id, exc_info=True)
                dead.append(ws)

        for ws in dead:
            self._connections[run_id].discard(ws)

    async def broadcast_stage_start(self, run_id: str, stage_id: str) -> None:
        """Notify that a stage has started."""
        await self.broadcast(run_id, "stage_start", {"stage_id": stage_id})

    async def broadcast_stage_complete(
        self, run_id: str, stage_id: str, success: bool, duration: float
    ) -> None:
        """Notify that a stage has completed."""
        await self.broadcast(
            run_id,
            "stage_complete",
            {
                "stage_id": stage_id,
                "success": success,
                "duration_seconds": round(duration, 3),
            },
        )

    async def broadcast_pipeline_complete(self, run_id: str, status: str, duration: float) -> None:
        """Notify that the entire pipeline has finished."""
        await self.broadcast(
            run_id,
            "pipeline_complete",
            {
                "status": status,
                "total_duration_seconds": round(duration, 3),
            },
        )

    @property
    def active_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(conns) for conns in self._connections.values())
