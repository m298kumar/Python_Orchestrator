"""
Tests for /api/feedback endpoints.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import feedback as feedback_module
from stlc_platform.pipeline.feedback_store import FeedbackStore


@pytest.fixture()
def feedback_store(tmp_path):
    """A FeedbackStore backed by a temp directory."""
    return FeedbackStore(persist_path=tmp_path / "feedback")


@pytest.fixture()
def client(feedback_store):
    """TestClient with a patched FeedbackStore at the route-module level."""
    # The feedback route uses its own _get_feedback_store() which caches
    # in _feedback_store. We patch that module-level variable directly.
    old = feedback_module._feedback_store
    feedback_module._feedback_store = feedback_store
    yield TestClient(app)
    feedback_module._feedback_store = old


class TestPostFeedback:
    """POST /api/feedback/ creates a feedback entry."""

    def test_returns_201(self, client: TestClient):
        resp = client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "correction",
            "message": "Use Given/When/Then consistently.",
        })
        assert resp.status_code == 201

    def test_response_contains_agent_id(self, client: TestClient):
        resp = client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "correction",
            "message": "Prefer short scenario titles.",
        })
        data = resp.json()
        assert data["agent_id"] == "bdd_agent"

    def test_response_contains_message(self, client: TestClient):
        resp = client.post("/api/feedback/", json={
            "agent_id": "api_test_agent",
            "feedback_type": "preference",
            "message": "Always include 401 test.",
        })
        data = resp.json()
        assert data["message"] == "Always include 401 test."

    def test_response_contains_feedback_type(self, client: TestClient):
        resp = client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "constraint",
            "message": "Max 10 scenarios per feature.",
        })
        data = resp.json()
        assert data["feedback_type"] == "constraint"

    def test_response_has_created_at(self, client: TestClient):
        resp = client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "correction",
            "message": "test",
        })
        data = resp.json()
        assert "created_at" in data
        assert len(data["created_at"]) > 0


class TestListFeedback:
    """GET /api/feedback/ returns stored feedback."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/feedback/")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/feedback/").json()
        assert isinstance(data, list)

    def test_initially_empty(self, client: TestClient):
        data = client.get("/api/feedback/").json()
        assert len(data) == 0

    def test_contains_posted_entry(self, client: TestClient):
        client.post("/api/feedback/", json={
            "agent_id": "crawler_agent",
            "feedback_type": "constraint",
            "message": "Max depth 3.",
        })
        data = client.get("/api/feedback/").json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "crawler_agent"

    def test_filter_by_agent_id(self, client: TestClient):
        """GET /api/feedback/?agent_id=X filters results."""
        client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "correction",
            "message": "fb1",
        })
        client.post("/api/feedback/", json={
            "agent_id": "api_test_agent",
            "feedback_type": "correction",
            "message": "fb2",
        })
        resp = client.get("/api/feedback/", params={"agent_id": "bdd_agent"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "bdd_agent"

    def test_no_filter_returns_all(self, client: TestClient):
        client.post("/api/feedback/", json={
            "agent_id": "bdd_agent",
            "feedback_type": "correction",
            "message": "fb1",
        })
        client.post("/api/feedback/", json={
            "agent_id": "api_test_agent",
            "feedback_type": "correction",
            "message": "fb2",
        })
        data = client.get("/api/feedback/").json()
        assert len(data) == 2
