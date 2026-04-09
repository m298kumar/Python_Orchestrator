"""
Tests for /api/bdd/* endpoints.

Uses the shared FeatureFileStore via deps; we inject a fresh store per test.
"""

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.deps import FeatureFileStore
from stlc_platform.api.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Inject a fresh FeatureFileStore and redirect output_dir per test."""
    store = FeatureFileStore()
    monkeypatch.setattr("stlc_platform.api.routes.bdd.get_output_dir", lambda: tmp_path)
    monkeypatch.setattr("stlc_platform.api.routes.bdd.get_ff_store", lambda: store)
    monkeypatch.setattr("stlc_platform.api.deps._ff_store", store)
    yield store


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_feature(store_fixture, filename="login.feature", **overrides):
    """Insert a feature file into the injected store."""
    data = {
        "filename": filename,
        "req_id": "REQ-001",
        "scenario_count": 3,
        "tags": ["@smoke"],
        "content": "Feature: Login\n  Scenario: Valid login\n    Given a user\n",
    }
    data.update(overrides)
    store_fixture.populate([data])
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

    def test_returns_seeded_features(self, client: TestClient, _isolated_store):
        _seed_feature(_isolated_store, "login.feature")
        _seed_feature(_isolated_store, "checkout.feature", req_id="REQ-002")
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

    def test_known_returns_200(self, client: TestClient, _isolated_store):
        _seed_feature(_isolated_store, "login.feature")
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
