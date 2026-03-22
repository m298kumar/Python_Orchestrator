"""
Tests for /api/bdd/* endpoints.

The BDD route uses a module-level dict ``_feature_files`` for storage.
We clear it between tests to ensure isolation.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import bdd as bdd_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_features():
    """Clear the in-memory feature file store between tests."""
    bdd_module._feature_files.clear()
    yield
    bdd_module._feature_files.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_feature(filename="login.feature", **overrides):
    """Insert a feature file directly into the in-memory store."""
    data = {
        "filename": filename,
        "req_id": "REQ-001",
        "scenario_count": 3,
        "tags": ["@smoke"],
        "content": "Feature: Login\n  Scenario: Valid login\n    Given a user\n",
    }
    data.update(overrides)
    bdd_module._feature_files[filename] = data
    return data


# ---------------------------------------------------------------------------
# GET /api/bdd/features
# ---------------------------------------------------------------------------

class TestListFeatures:
    """GET /api/bdd/features returns stored feature files."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/bdd/features")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/bdd/features").json()
        assert isinstance(data, list)

    def test_initially_empty(self, client: TestClient):
        data = client.get("/api/bdd/features").json()
        assert len(data) == 0

    def test_returns_seeded_features(self, client: TestClient):
        _seed_feature("login.feature")
        _seed_feature("checkout.feature", req_id="REQ-002")
        data = client.get("/api/bdd/features").json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# GET /api/bdd/features/{filename}
# ---------------------------------------------------------------------------

class TestGetFeature:
    """GET /api/bdd/features/{filename} returns a single feature file."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/bdd/features/nonexistent")
        assert resp.status_code == 404

    def test_known_returns_200(self, client: TestClient):
        _seed_feature("login.feature")
        resp = client.get("/api/bdd/features/login.feature")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "login.feature"


# ---------------------------------------------------------------------------
# GET /api/bdd/project/download
# ---------------------------------------------------------------------------

class TestDownloadProject:
    """GET /api/bdd/project/download returns a ZIP archive."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/bdd/project/download")
        assert resp.status_code == 200

    def test_returns_zip_content_type(self, client: TestClient):
        resp = client.get("/api/bdd/project/download")
        assert "application/zip" in resp.headers.get("content-type", "")
