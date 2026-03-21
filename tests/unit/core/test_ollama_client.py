"""Unit tests for OllamaClient.

All HTTP calls are mocked — no real Ollama server needed.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from stlc_platform.core.llm.ollama_client import OllamaClient


@pytest.fixture
def client():
    """Create an OllamaClient with explicit params (avoids config dependency)."""
    return OllamaClient(
        base_url="http://localhost:11434",
        model="test-model",
        temperature=0.7,
        num_ctx=4096,
        timeout=60,
        num_predict=2048,
    )


class TestConstructor:
    def test_explicit_params(self, client):
        assert client.base_url == "http://localhost:11434"
        assert client.model == "test-model"
        assert client.temperature == 0.7
        assert client.num_ctx == 4096
        assert client.timeout == 60
        assert client.num_predict == 2048

    def test_defaults_from_config(self):
        """When no params given, should read from config (lazy import)."""
        mock_cfg = MagicMock()
        mock_cfg.ollama.base_url = "http://custom:1234"
        mock_cfg.ollama.model = "custom-model"
        mock_cfg.ollama.temperature = 0.5
        mock_cfg.ollama.num_ctx = 8192
        mock_cfg.ollama.timeout = 120
        mock_cfg.ollama.num_predict = 4096
        with patch("stlc_platform.core.config_loader.config", mock_cfg):
            c = OllamaClient()
            assert c.base_url == "http://custom:1234"
            assert c.model == "custom-model"


class TestCheckConnection:
    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_connection_success(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=200)
        assert client.check_connection() is True

    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_connection_failure(self, mock_get, client):
        mock_get.side_effect = requests.ConnectionError()
        assert client.check_connection() is False

    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_connection_bad_status(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=500)
        assert client.check_connection() is False


class TestListModels:
    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_list_models_success(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"models": [{"name": "llama3"}, {"name": "mistral"}]},
        )
        models = client.list_models()
        assert models == ["llama3", "mistral"]

    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_list_models_empty(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: {"models": []},
        )
        assert client.list_models() == []

    @patch("stlc_platform.core.llm.ollama_client.requests.get")
    def test_list_models_connection_error(self, mock_get, client):
        mock_get.side_effect = requests.ConnectionError()
        assert client.list_models() == []


class TestGenerate:
    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_success(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "Hello world"}},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = client.generate("Say hello")
        assert result == "Hello world"

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_with_system_prompt(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "response"}},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        client.generate("prompt", system_prompt="You are a tester")
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "You are a tester"

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_with_json_schema(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": '{"key": "value"}'}},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        schema = {"type": "object", "properties": {"key": {"type": "string"}}}
        client.generate("prompt", json_schema=schema)
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["format"] == schema

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_timeout(self, mock_post, client):
        mock_post.side_effect = requests.Timeout()
        with pytest.raises(TimeoutError, match="timed out"):
            client.generate("prompt")

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_connection_error(self, mock_post, client):
        mock_post.side_effect = requests.ConnectionError()
        with pytest.raises(ConnectionError, match="Cannot connect"):
            client.generate("prompt")

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_http_error(self, mock_post, client):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError(response=MagicMock(text="bad"))
        mock_post.return_value = resp
        with pytest.raises(RuntimeError, match="Ollama API error"):
            client.generate("prompt")

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_generate_custom_temperature(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "ok"}},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        client.generate("prompt", temperature=0.1)
        payload = mock_post.call_args[1]["json"]
        assert payload["options"]["temperature"] == 0.1


class TestPullModel:
    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_pull_model_success(self, mock_post, client):
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [
            b'{"status": "downloading"}',
            b'{"status": "success"}',
        ]
        mock_post.return_value = mock_resp
        assert client.pull_model("llama3") is True

    @patch("stlc_platform.core.llm.ollama_client.requests.post")
    def test_pull_model_failure(self, mock_post, client):
        mock_post.side_effect = requests.ConnectionError()
        assert client.pull_model("llama3") is False
