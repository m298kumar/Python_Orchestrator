"""
Tests for /api/config/* endpoints.

The config route uses a module-level dict ``_config`` for storage.
We reset it between tests to ensure isolation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes import config as config_module

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_config():
    """Reset the in-memory config state and prevent YAML writes."""
    config_module._config.clear()
    config_module._config.update({"project": {}, "llm": {}, "output": {}})
    # Prevent tests from writing to the real YAML config file
    with patch("stlc_platform.core.config_loader.save_config_yaml", return_value=None):
        yield
    config_module._config.clear()
    config_module._config.update({"project": {}, "llm": {}, "output": {}})


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/config/
# ---------------------------------------------------------------------------


class TestGetConfig:
    """GET /api/config/ returns the current configuration."""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/api/config/")
        assert resp.status_code == 200

    def test_response_has_required_keys(self, client: TestClient):
        data = client.get("/api/config/").json()
        assert "project" in data
        assert "llm" in data
        assert "output" in data
        assert "specifications" in data
        assert "review" in data

    def test_values_are_dicts(self, client: TestClient):
        data = client.get("/api/config/").json()
        assert isinstance(data["project"], dict)
        assert isinstance(data["llm"], dict)
        assert isinstance(data["output"], dict)

    def test_sensitive_values_masked(self, client: TestClient):
        config_module._config["llm"]["api_key"] = "secret-123"
        config_module._config["_loaded"] = True
        data = client.get("/api/config/").json()
        assert data["llm"]["api_key"] == "***"


# ---------------------------------------------------------------------------
# PUT /api/config/ — dot-notation updates
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    """PUT /api/config/ updates configuration values."""

    def test_returns_200(self, client: TestClient):
        resp = client.put("/api/config/", json={"updates": {"llm.model": "llama3"}})
        assert resp.status_code == 200

    def test_update_applies_value(self, client: TestClient):
        client.put("/api/config/", json={"updates": {"llm.model": "llama3"}})
        data = client.get("/api/config/").json()
        assert data["llm"]["model"] == "llama3"

    def test_update_dot_notation_creates_nested(self, client: TestClient):
        client.put("/api/config/", json={"updates": {"project.name": "my-project"}})
        data = client.get("/api/config/").json()
        assert data["project"]["name"] == "my-project"

    def test_update_config_ollama_compat(self, client: TestClient):
        """Sending 'ollama.model' via dot-notation is mapped to 'llm.model'."""
        client.put("/api/config/", json={"updates": {"ollama.model": "mistral"}})
        data = client.get("/api/config/").json()
        assert data["llm"]["model"] == "mistral"

    def test_update_config_ollama_base_url_compat(self, client: TestClient):
        """Sending 'ollama.base_url' is mapped to 'llm.base_url'."""
        client.put(
            "/api/config/",
            json={"updates": {"ollama.base_url": "http://remote:11434"}},
        )
        data = client.get("/api/config/").json()
        assert data["llm"]["base_url"] == "http://remote:11434"


# ---------------------------------------------------------------------------
# PUT /api/config/ — structured section updates
# ---------------------------------------------------------------------------


class TestStructuredUpdate:
    """PUT /api/config/ with structured section dicts."""

    def test_structured_llm_update(self, client: TestClient):
        resp = client.put(
            "/api/config/",
            json={"llm": {"model": "gpt-4o", "provider": "openai"}},
        )
        assert resp.status_code == 200
        data = client.get("/api/config/").json()
        assert data["llm"]["model"] == "gpt-4o"
        assert data["llm"]["provider"] == "openai"

    def test_structured_project_update(self, client: TestClient):
        client.put("/api/config/", json={"project": {"name": "StructuredApp"}})
        data = client.get("/api/config/").json()
        assert data["project"]["name"] == "StructuredApp"

    def test_combined_updates_and_structured(self, client: TestClient):
        """Dot-notation and structured can be combined."""
        client.put(
            "/api/config/",
            json={
                "updates": {"output.output_dir": "/tmp/out"},
                "llm": {"model": "combined-model"},
            },
        )
        data = client.get("/api/config/").json()
        assert data["output"]["output_dir"] == "/tmp/out"
        assert data["llm"]["model"] == "combined-model"

    def test_new_sections_and_advanced_values_round_trip(self, client: TestClient):
        response = client.put(
            "/api/config/",
            json={
                "specifications": {"enforce": True, "bdd": "docs/custom-bdd.md"},
                "review": {"sqlite_path": "output/review/custom.sqlite3"},
                "crawler": {"timeout_ms": 45000, "verify_ssl": False},
                "bdd": {"pom_language": "java"},
                "test_generation": {
                    "domain_keywords": {"travel": ["booking"]},
                    "component_suffix_map": {"booking": "Booking Page"},
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["specifications"]["bdd"] == "docs/custom-bdd.md"
        assert data["review"]["sqlite_path"].endswith("custom.sqlite3")
        assert data["crawler"]["timeout_ms"] == 45000
        assert data["crawler"]["verify_ssl"] is False
        assert data["bdd"]["pom_language"] == "java"
        assert data["test_generation"]["domain_keywords"]["travel"] == ["booking"]


# ---------------------------------------------------------------------------
# YAML persistence
# ---------------------------------------------------------------------------


class TestYAMLPersistence:
    """Updates are persisted to YAML via save_config_yaml."""

    def test_persistence_failure_still_returns_success(self, client: TestClient):
        """Even if YAML write fails, in-memory update succeeds."""
        with patch(
            "stlc_platform.core.config_loader.save_config_yaml",
            side_effect=RuntimeError("disk full"),
        ):
            resp = client.put(
                "/api/config/",
                json={"updates": {"llm.model": "fail-persist"}},
            )
            assert resp.status_code == 200
            assert config_module._config["llm"]["model"] == "fail-persist"

    def test_masked_values_not_persisted(self, client: TestClient):
        """Values equal to '***' must NOT be written to YAML."""
        with patch("stlc_platform.core.config_loader.save_config_yaml"):
            client.put(
                "/api/config/",
                json={"updates": {"llm.api_key": "***", "llm.model": "phi3"}},
            )
            assert config_module._config["llm"]["model"] == "phi3"
            assert config_module._config["llm"]["api_key"] == "***"


# ---------------------------------------------------------------------------
# POST /api/config/test-llm — unknown provider
# ---------------------------------------------------------------------------


class TestLLMEndpoint:
    """POST /api/config/test-llm tests provider connectivity."""

    def test_unknown_provider_returns_error(self, client: TestClient):
        resp = client.post(
            "/api/config/test-llm",
            json={"provider": "unknown_provider"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Unknown provider" in data["message"]

    def test_ollama_mock_success(self, client: TestClient):
        """Mock the urllib call for Ollama and verify success response."""
        mock_models = {"models": [{"name": "llama3"}, {"name": "phi3"}]}
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_models).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            resp = client.post(
                "/api/config/test-llm",
                json={
                    "provider": "ollama",
                    "base_url": "http://localhost:11434",
                },
            )
            data = resp.json()
            assert data["success"] is True
            assert "llama3" in data["models"]
            assert "phi3" in data["models"]
            assert "2 model(s)" in data["message"]

    def test_ollama_connection_refused(self, client: TestClient):
        """Ollama unreachable returns a descriptive error."""
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            resp = client.post(
                "/api/config/test-llm",
                json={"provider": "ollama", "base_url": "http://localhost:99999"},
            )
            data = resp.json()
            assert data["success"] is False
            assert "Cannot reach Ollama" in data["message"]

    def test_openai_missing_package(self, client: TestClient):
        """When openai is not installed, return a helpful message."""
        import sys

        # Temporarily hide the openai module if it exists
        saved = sys.modules.get("openai")
        sys.modules["openai"] = None  # type: ignore[assignment]
        try:
            resp = client.post(
                "/api/config/test-llm",
                json={"provider": "openai", "api_key": "sk-test"},
            )
            data = resp.json()
            assert data["success"] is False
            assert "not installed" in data["message"]
        finally:
            if saved is not None:
                sys.modules["openai"] = saved
            else:
                sys.modules.pop("openai", None)

    def test_openai_missing_api_key(self, client: TestClient):
        """OpenAI without api_key returns error (missing key or missing package)."""
        resp = client.post(
            "/api/config/test-llm",
            json={"provider": "openai"},
        )
        data = resp.json()
        assert data["success"] is False
        # Either "api_key is required" or "not installed" — both are valid failures
        assert "api_key" in data["message"].lower() or "not installed" in data["message"].lower()

    def test_anthropic_missing_api_key(self, client: TestClient):
        """Anthropic without api_key returns error (missing key or missing package)."""
        resp = client.post(
            "/api/config/test-llm",
            json={"provider": "anthropic"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "api_key" in data["message"].lower() or "not installed" in data["message"].lower()

    def test_azure_missing_fields(self, client: TestClient):
        """Azure without api_key or base_url returns error."""
        resp = client.post(
            "/api/config/test-llm",
            json={"provider": "azure"},
        )
        data = resp.json()
        assert data["success"] is False

        resp2 = client.post(
            "/api/config/test-llm",
            json={"provider": "azure", "api_key": "key"},
        )
        data2 = resp2.json()
        assert data2["success"] is False
        assert "base_url" in data2["message"].lower() or "not installed" in data2["message"].lower()
