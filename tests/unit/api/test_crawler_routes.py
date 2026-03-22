"""
Tests for /api/crawler/* endpoints.

The crawler route uses module-level dicts ``_site_model`` and ``_crawled_pages``
for storage. We clear them between tests to ensure isolation.
"""

import pytest

from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import crawler as crawler_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_crawler_data():
    """Clear the in-memory crawler stores between tests."""
    crawler_module._site_model.clear()
    crawler_module._crawled_pages.clear()
    yield
    crawler_module._site_model.clear()
    crawler_module._crawled_pages.clear()


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/crawler/site-model
# ---------------------------------------------------------------------------

class TestGetSiteModel:
    """GET /api/crawler/site-model returns the site model or empty default."""

    def test_returns_200_when_empty(self, client: TestClient):
        resp = client.get("/api/crawler/site-model")
        assert resp.status_code == 200

    def test_empty_model_has_zero_pages(self, client: TestClient):
        data = client.get("/api/crawler/site-model").json()
        assert data["total_pages"] == 0
        assert data["base_url"] == ""


# ---------------------------------------------------------------------------
# GET /api/crawler/pages
# ---------------------------------------------------------------------------

class TestListPages:
    """GET /api/crawler/pages returns crawled pages."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/crawler/pages")
        assert resp.status_code == 200

    def test_returns_list(self, client: TestClient):
        data = client.get("/api/crawler/pages").json()
        assert isinstance(data, list)

    def test_initially_empty(self, client: TestClient):
        data = client.get("/api/crawler/pages").json()
        assert len(data) == 0

    def test_returns_seeded_pages(self, client: TestClient):
        crawler_module._crawled_pages["http://example.com"] = {
            "url": "http://example.com",
            "title": "Example",
            "element_count": 10,
            "form_count": 1,
            "link_count": 5,
        }
        data = client.get("/api/crawler/pages").json()
        assert len(data) == 1
        assert data[0]["url"] == "http://example.com"
