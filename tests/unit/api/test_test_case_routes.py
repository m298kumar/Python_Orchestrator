"""
Tests for /api/test-cases/* endpoints.

Uses the shared TestCaseStore via deps; we inject a fresh store per test.
"""

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.deps import TestCaseStore
from stlc_platform.api.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Inject a fresh TestCaseStore and redirect output_dir per test."""
    store = TestCaseStore()
    monkeypatch.setattr("stlc_platform.api.routes.test_cases.get_output_dir", lambda: tmp_path)
    monkeypatch.setattr("stlc_platform.api.routes.test_cases.get_tc_store", lambda: store)
    # Also patch the deps-level singleton so endpoints pick it up
    monkeypatch.setattr("stlc_platform.api.deps._tc_store", store)
    yield store


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_test_case(store_fixture, tc_id="TC-001", **overrides):
    """Insert a test case into the injected store."""
    data = {
        "tc_id": tc_id,
        "req_id": "REQ-001",
        "title": "Verify login",
        "description": "Ensure user can log in",
        "test_type": "functional",
        "priority": "High",
        "category": "Auth",
        "component": "Login",
        "given": "a registered user",
        "when": "user submits valid credentials",
        "then": "user is redirected to dashboard",
        "expected_outcome": "Successful login",
        "tags": ["smoke"],
        "status": "generated",
    }
    data.update(overrides)
    store_fixture.populate([data])
    return data


# ---------------------------------------------------------------------------
# GET /api/test-cases/
# ---------------------------------------------------------------------------


class TestListTestCases:
    """GET /api/test-cases/ returns stored test cases."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/test-cases/")
        assert resp.status_code == 200

    def test_returns_empty_list_when_no_data(self, client: TestClient):
        data = client.get("/api/test-cases/").json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_returns_seeded_test_cases(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-001")
        _seed_test_case(_isolated_store, "TC-002", title="Verify logout")
        data = client.get("/api/test-cases/").json()
        assert len(data) == 2

    def test_filter_by_priority(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-001", priority="High")
        _seed_test_case(_isolated_store, "TC-002", priority="Low")
        data = client.get("/api/test-cases/", params={"priority": "High"}).json()
        assert len(data) == 1
        assert data[0]["tc_id"] == "TC-001"


# ---------------------------------------------------------------------------
# GET /api/test-cases/{tc_id}
# ---------------------------------------------------------------------------


class TestGetTestCase:
    """GET /api/test-cases/{tc_id} returns a single test case."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/test-cases/nonexistent")
        assert resp.status_code == 404

    def test_404_has_detail(self, client: TestClient):
        data = client.get("/api/test-cases/nonexistent").json()
        assert "detail" in data

    def test_known_returns_200(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-010")
        resp = client.get("/api/test-cases/TC-010")
        assert resp.status_code == 200
        assert resp.json()["tc_id"] == "TC-010"


# ---------------------------------------------------------------------------
# PUT /api/test-cases/{tc_id}
# ---------------------------------------------------------------------------


class TestUpdateTestCase:
    """PUT /api/test-cases/{tc_id} edits a test case."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.put("/api/test-cases/nonexistent", json={"title": "New"})
        assert resp.status_code == 404

    def test_update_title(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-020")
        resp = client.put("/api/test-cases/TC-020", json={"title": "Updated title"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated title"


# ---------------------------------------------------------------------------
# POST /api/test-cases/{tc_id}/approve
# ---------------------------------------------------------------------------


class TestApproveTestCase:
    """POST /api/test-cases/{tc_id}/approve marks a test case approved."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/test-cases/nonexistent/approve")
        assert resp.status_code == 404

    def test_approve_sets_status(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-030")
        resp = client.post("/api/test-cases/TC-030/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# POST /api/test-cases/{tc_id}/reject
# ---------------------------------------------------------------------------


class TestRejectTestCase:
    """POST /api/test-cases/{tc_id}/reject marks a test case rejected."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.post("/api/test-cases/nonexistent/reject")
        assert resp.status_code == 404

    def test_reject_sets_status(self, client: TestClient, _isolated_store):
        _seed_test_case(_isolated_store, "TC-040")
        resp = client.post("/api/test-cases/TC-040/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
