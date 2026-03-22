"""
Tests for /api/test-cases/* endpoints.

The test-cases route uses a module-level dict ``_test_cases`` for storage.
We clear it between tests to ensure isolation.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import test_cases as tc_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_test_cases():
    """Clear the in-memory test-case store between tests."""
    tc_module._test_cases.clear()
    yield
    tc_module._test_cases.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_test_case(tc_id="TC-001", **overrides):
    """Insert a test case directly into the in-memory store."""
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
    tc_module._test_cases[tc_id] = data
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

    def test_returns_seeded_test_cases(self, client: TestClient):
        _seed_test_case("TC-001")
        _seed_test_case("TC-002", title="Verify logout")
        data = client.get("/api/test-cases/").json()
        assert len(data) == 2

    def test_filter_by_priority(self, client: TestClient):
        _seed_test_case("TC-001", priority="High")
        _seed_test_case("TC-002", priority="Low")
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

    def test_known_returns_200(self, client: TestClient):
        _seed_test_case("TC-010")
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

    def test_update_title(self, client: TestClient):
        _seed_test_case("TC-020")
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

    def test_approve_sets_status(self, client: TestClient):
        _seed_test_case("TC-030")
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

    def test_reject_sets_status(self, client: TestClient):
        _seed_test_case("TC-040")
        resp = client.post("/api/test-cases/TC-040/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
