"""
Tests for the WebSocket ConnectionManager.

These are pure unit tests of the ConnectionManager class. They use
a per-test event loop and mock WebSocket objects -- no real HTTP
connections or pytest-asyncio needed.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from stlc_platform.api.websocket import ConnectionManager


@pytest.fixture()
def loop():
    """Provide a fresh event loop for each test."""
    _loop = asyncio.new_event_loop()
    yield _loop
    _loop.close()


@pytest.fixture()
def manager():
    return ConnectionManager()


def _make_ws() -> AsyncMock:
    """Create a mock WebSocket that tracks sent messages."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestConnectionManagerConnect:
    """connect() accepts and registers a WebSocket."""

    def test_connect_accepts_websocket(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        ws.accept.assert_awaited_once()

    def test_connect_increments_active_connections(self, loop, manager):
        assert manager.active_connections == 0
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        assert manager.active_connections == 1

    def test_connect_multiple_runs(self, loop, manager):
        ws1 = _make_ws()
        ws2 = _make_ws()
        loop.run_until_complete(manager.connect(ws1, "run1"))
        loop.run_until_complete(manager.connect(ws2, "run2"))
        assert manager.active_connections == 2


class TestConnectionManagerDisconnect:
    """disconnect() removes a WebSocket."""

    def test_disconnect_decrements_active_connections(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        manager.disconnect(ws, "run1")
        assert manager.active_connections == 0

    def test_disconnect_unknown_is_safe(self, manager):
        ws = _make_ws()
        manager.disconnect(ws, "nonexistent")
        assert manager.active_connections == 0

    def test_disconnect_one_of_many(self, loop, manager):
        ws1 = _make_ws()
        ws2 = _make_ws()
        loop.run_until_complete(manager.connect(ws1, "run1"))
        loop.run_until_complete(manager.connect(ws2, "run1"))
        manager.disconnect(ws1, "run1")
        assert manager.active_connections == 1


class TestConnectionManagerBroadcast:
    """broadcast() sends messages to all connections for a run_id."""

    def test_broadcast_sends_to_connected(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast("run1", "test_event", {"key": "value"}))
        ws.send_text.assert_awaited_once()

    def test_broadcast_message_is_json(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast("run1", "test_event", {"x": 1}))
        sent = ws.send_text.call_args[0][0]
        parsed = json.loads(sent)
        assert parsed["event"] == "test_event"
        assert parsed["run_id"] == "run1"
        assert parsed["data"]["x"] == 1
        assert "timestamp" in parsed

    def test_broadcast_to_multiple_clients(self, loop, manager):
        ws1 = _make_ws()
        ws2 = _make_ws()
        loop.run_until_complete(manager.connect(ws1, "run1"))
        loop.run_until_complete(manager.connect(ws2, "run1"))
        loop.run_until_complete(manager.broadcast("run1", "evt", {}))
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    def test_broadcast_does_not_send_to_other_runs(self, loop, manager):
        ws1 = _make_ws()
        ws2 = _make_ws()
        loop.run_until_complete(manager.connect(ws1, "run1"))
        loop.run_until_complete(manager.connect(ws2, "run2"))
        loop.run_until_complete(manager.broadcast("run1", "evt", {}))
        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_not_awaited()

    def test_broadcast_no_connections_is_safe(self, loop, manager):
        loop.run_until_complete(manager.broadcast("nobody", "evt", {}))

    def test_broadcast_removes_dead_connections(self, loop, manager):
        ws = _make_ws()
        ws.send_text.side_effect = Exception("connection closed")
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast("run1", "evt", {}))
        assert manager.active_connections == 0


class TestBroadcastStageStart:
    """broadcast_stage_start() sends stage_start event."""

    def test_stage_start_event(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast_stage_start("run1", "requirements"))
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["event"] == "stage_start"
        assert sent["data"]["stage_id"] == "requirements"


class TestBroadcastStageComplete:
    """broadcast_stage_complete() sends stage_complete event."""

    def test_stage_complete_event(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast_stage_complete("run1", "bdd", True, 2.5))
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["event"] == "stage_complete"
        assert sent["data"]["stage_id"] == "bdd"
        assert sent["data"]["success"] is True
        assert sent["data"]["duration_seconds"] == 2.5


class TestBroadcastPipelineComplete:
    """broadcast_pipeline_complete() sends pipeline_complete event."""

    def test_pipeline_complete_event(self, loop, manager):
        ws = _make_ws()
        loop.run_until_complete(manager.connect(ws, "run1"))
        loop.run_until_complete(manager.broadcast_pipeline_complete("run1", "completed", 10.0))
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["event"] == "pipeline_complete"
        assert sent["data"]["status"] == "completed"
        assert sent["data"]["total_duration_seconds"] == 10.0


class TestActiveConnections:
    """active_connections property reports total count."""

    def test_starts_at_zero(self, manager):
        assert manager.active_connections == 0

    def test_counts_across_runs(self, loop, manager):
        for i in range(3):
            ws = _make_ws()
            loop.run_until_complete(manager.connect(ws, f"run{i}"))
        assert manager.active_connections == 3
