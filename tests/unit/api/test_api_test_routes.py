"""
Tests for /api/api-tests/* endpoints.

The api-tests route uses a module-level dict ``_api_test_files`` for storage.
We clear it between tests to ensure isolation.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import api_tests as api_tests_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_api_tests():
    """Clear the in-memory API test file store between tests."""
    api_tests_module._api_test_files.clear()
    yield
    api_tests_module._api_test_files.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_api_test(filename="test_pets.py", **overrides):
    """Insert an API test file directly into the in-memory store."""
    data = {
        "filename": filename,
        "framework": "pytest",
        "language": "python",
        "endpoint_path": "/api/pets",
        "test_count": 5,
        "test_level": "api",
        "content": "def test_get_pets(): ...",
    }
    data.update(overrides)
    api_tests_module._api_test_files[filename] = data
    return data


# ---------------------------------------------------------------------------
# GET /api/api-tests/
# ---------------------------------------------------------------------------

class TestListAPITests:
    """GET /api/api-tests/ returns stored API test files."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/api-tests/")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/api-tests/").json()
        assert isinstance(data, list)

    def test_initially_empty(self, client: TestClient):
        data = client.get("/api/api-tests/").json()
        assert len(data) == 0

    def test_returns_seeded_tests(self, client: TestClient):
        _seed_api_test("test_pets.py")
        _seed_api_test("test_users.py", endpoint_path="/api/users")
        data = client.get("/api/api-tests/").json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# GET /api/api-tests/{filename}
# ---------------------------------------------------------------------------

class TestGetAPITest:
    """GET /api/api-tests/{filename} returns a single API test file."""

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.get("/api/api-tests/nonexistent")
        assert resp.status_code == 404

    def test_404_has_detail(self, client: TestClient):
        data = client.get("/api/api-tests/nonexistent").json()
        assert "detail" in data

    def test_known_returns_200(self, client: TestClient):
        _seed_api_test("test_pets.py")
        resp = client.get("/api/api-tests/test_pets.py")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "test_pets.py"
