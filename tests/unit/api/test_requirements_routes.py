"""
Tests for /api/requirements/* endpoints.

Note: The requirements route uses a module-level dict `_requirements` for
storage. We clear it between tests to ensure isolation.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import requirements as req_module


@pytest.fixture(autouse=True)
def _clear_requirements():
    """Clear the in-memory requirements store between tests."""
    req_module._requirements.clear()
    req_module._requirement_history.clear()
    yield
    req_module._requirements.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _upload(client, reqs):
    """Helper: upload a list of requirement dicts as JSON."""
    reqs = [
        {**req, "acceptance_criteria": req.get("acceptance_criteria", ["Outcome is verifiable"])}
        for req in reqs
    ]
    payload = json.dumps(reqs).encode()
    return client.post(
        "/api/requirements/upload",
        files={"file": ("requirements.json", io.BytesIO(payload), "application/json")},
    )


class TestListRequirements:
    """GET /api/requirements/ returns stored requirements."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/requirements/")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/requirements/").json()
        assert isinstance(data, list)

    def test_initially_empty(self, client: TestClient):
        data = client.get("/api/requirements/").json()
        assert len(data) == 0


class TestUploadRequirements:
    """POST /api/requirements/upload accepts a JSON file."""

    def test_upload_json_returns_201(self, client: TestClient):
        resp = _upload(
            client,
            [
                {"id": "REQ-001", "title": "Login", "description": "User login"},
            ],
        )
        assert resp.status_code == 201

    def test_upload_returns_list(self, client: TestClient):
        resp = _upload(
            client,
            [
                {"id": "REQ-001", "title": "Login", "description": "User login"},
            ],
        )
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["req_id"] == "REQ-001"

    def test_upload_populates_requirements_list(self, client: TestClient):
        _upload(
            client,
            [
                {"id": "REQ-001", "title": "Login", "description": "User login"},
                {"id": "REQ-002", "title": "Logout", "description": "User logout"},
            ],
        )
        data = client.get("/api/requirements/").json()
        assert len(data) == 2

    def test_uploaded_requirement_has_correct_ids(self, client: TestClient):
        _upload(
            client,
            [
                {"id": "REQ-001", "title": "Login", "description": "User login"},
                {"id": "REQ-002", "title": "Logout", "description": "User logout"},
            ],
        )
        data = client.get("/api/requirements/").json()
        ids = {r["req_id"] for r in data}
        assert "REQ-001" in ids
        assert "REQ-002" in ids

    def test_upload_unsupported_extension_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("reqs.exe", io.BytesIO(b"hello"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_upload_csv_returns_201(self, client: TestClient):
        csv_content = b"id,title,description,priority,acceptance_criteria\nREQ-001,Login,User login,High,Login succeeds\nREQ-002,Logout,User logout,Medium,Logout succeeds"
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("reqs.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Login"

    def test_upload_txt_returns_201(self, client: TestClient):
        txt_content = b"REQ-001 Login feature\nUser must be able to log in. Acceptance criteria: login succeeds."
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("reqs.txt", io.BytesIO(txt_content), "text/plain")},
        )
        assert resp.status_code == 201
        assert len(resp.json()) >= 1

    def test_upload_invalid_json_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("reqs.json", io.BytesIO(b"not-json{{{"), "application/json")},
        )
        assert resp.status_code == 400

    def test_upload_without_acceptance_criteria_violates_specification(self, client):
        payload = json.dumps(
            [{"id": "REQ-001", "title": "Login", "description": "User login"}]
        ).encode()
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("requirements.json", io.BytesIO(payload), "application/json")},
        )
        assert resp.status_code == 422
        assert "acceptance criterion" in str(resp.json())


class TestGetRequirement:
    """GET /api/requirements/{req_id} returns a single requirement."""

    def test_unknown_returns_404(self, client: TestClient):
        resp = client.get("/api/requirements/REQ-999")
        assert resp.status_code == 404

    def test_known_returns_200_after_upload(self, client: TestClient):
        _upload(
            client,
            [
                {"id": "REQ-010", "title": "Search", "description": "User can search."},
            ],
        )
        resp = client.get("/api/requirements/REQ-010")
        assert resp.status_code == 200
        data = resp.json()
        assert data["req_id"] == "REQ-010"
        assert data["title"] == "Search"

    def test_404_has_detail(self, client: TestClient):
        data = client.get("/api/requirements/REQ-999").json()
        assert "detail" in data

    def test_update_retains_revision_history(self, client: TestClient):
        _upload(
            client,
            [{"id": "REQ-010", "title": "Search", "description": "Original"}],
        )
        update = client.put(
            "/api/requirements/REQ-010",
            json={"description": "Revised"},
        )
        assert update.status_code == 200

        history = client.get("/api/requirements/REQ-010/history").json()["revisions"]
        assert [revision["description"] for revision in history] == ["Original", "Revised"]
        assert [revision["revision_number"] for revision in history] == [1, 2]
