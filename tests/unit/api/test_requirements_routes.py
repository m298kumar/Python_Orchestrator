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
    yield
    req_module._requirements.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _upload(client, reqs):
    """Helper: upload a list of requirement dicts as JSON."""
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
        csv_content = b"id,title,description,priority\nREQ-001,Login,User login,High\nREQ-002,Logout,User logout,Medium"
        resp = client.post(
            "/api/requirements/upload",
            files={"file": ("reqs.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] == "Login"

    def test_upload_txt_returns_201(self, client: TestClient):
        txt_content = b"REQ-001 Login feature\nUser must be able to log in with email and password."
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
