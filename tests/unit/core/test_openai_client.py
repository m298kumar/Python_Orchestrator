"""Tests for OpenAI LLM client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestOpenAIClient:
    """Tests for OpenAIClient using mocked openai SDK."""

    def _make_client(self, **kwargs):
        """Create an OpenAIClient with mocked SDK and config."""
        with patch.dict("os.environ", {"STLC_LLM__API_KEY": "sk-test-key-123"}, clear=False):
            with patch(
                "stlc_platform.core.llm.openai_client.OpenAIClient.__init__", return_value=None
            ):
                from stlc_platform.core.llm.base_client import TokenUsage
                from stlc_platform.core.llm.openai_client import OpenAIClient

                client = OpenAIClient.__new__(OpenAIClient)
                # Base class attributes (normally set by BaseLLMClient.__init__)
                client._last_token_usage = TokenUsage()
                client._accumulated_tokens = TokenUsage()
                client._cache = None
                # OpenAIClient attributes
                client.api_key = "sk-test-key-123"
                client.model = kwargs.get("model", "gpt-4o")
                client.base_url = kwargs.get("base_url", None)
                client.temperature = kwargs.get("temperature", 0.6)
                client.timeout = kwargs.get("timeout", 120)
                client.max_tokens = kwargs.get("max_tokens", 3200)
                client.debug = False
                client._client = MagicMock()
                return client

    def test_generate_basic(self):
        """Test basic text generation."""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"title": "test"}'
        client._client.chat.completions.create.return_value = mock_response

        result = client.generate("test prompt")
        assert result == '{"title": "test"}'
        client._client.chat.completions.create.assert_called_once()

    def test_generate_with_system_prompt(self):
        """Test generation with system prompt."""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        client._client.chat.completions.create.return_value = mock_response

        result = client.generate("user prompt", system_prompt="system instructions")
        assert result == "response"

        call_kwargs = client._client.chat.completions.create.call_args
        messages = call_kwargs[1]["messages"] if "messages" in call_kwargs[1] else call_kwargs[0][0]
        # Should have system + user messages
        assert any(m["role"] == "system" for m in messages)
        assert any(m["role"] == "user" for m in messages)

    def test_generate_with_json_schema(self):
        """Test JSON mode is enabled when schema provided."""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"result": true}'
        client._client.chat.completions.create.return_value = mock_response

        result = client.generate("prompt", json_schema={"type": "object"})
        assert result == '{"result": true}'

        call_kwargs = client._client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_generate_with_custom_temperature(self):
        """Test temperature override."""
        client = self._make_client(temperature=0.5)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "output"
        client._client.chat.completions.create.return_value = mock_response

        client.generate("prompt", temperature=0.9)
        call_kwargs = client._client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.9

    def test_check_connection_success(self):
        """Test successful connection check."""
        client = self._make_client()
        client._client.models.list.return_value = MagicMock()
        assert client.check_connection() is True

    def test_check_connection_failure(self):
        """Test failed connection check."""
        client = self._make_client()
        client._client.models.list.side_effect = Exception("connection failed")
        assert client.check_connection() is False

    def test_list_models(self):
        """Test listing available models."""
        client = self._make_client()
        mock_model1 = MagicMock()
        mock_model1.id = "gpt-4o"
        mock_model2 = MagicMock()
        mock_model2.id = "gpt-3.5-turbo"
        mock_response = MagicMock()
        mock_response.data = [mock_model1, mock_model2]
        client._client.models.list.return_value = mock_response

        models = client.list_models()
        assert "gpt-4o" in models
        assert "gpt-3.5-turbo" in models

    def test_list_models_failure(self):
        """Test list_models returns empty on error."""
        client = self._make_client()
        client._client.models.list.side_effect = Exception("error")
        assert client.list_models() == []

    def test_generate_api_error(self):
        """Test API error handling."""
        client = self._make_client()
        client._client.chat.completions.create.side_effect = RuntimeError("API overloaded")

        with pytest.raises(RuntimeError, match="OpenAI API error"):
            client.generate("prompt")

    def test_is_base_llm_client_subclass(self):
        """Test OpenAIClient inherits from BaseLLMClient."""
        from stlc_platform.core.llm.base_client import BaseLLMClient
        from stlc_platform.core.llm.openai_client import OpenAIClient

        assert issubclass(OpenAIClient, BaseLLMClient)
