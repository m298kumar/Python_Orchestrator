"""Tests for Anthropic LLM client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAnthropicClient:
    """Tests for AnthropicClient using mocked anthropic SDK."""

    def _make_client(self, **kwargs):
        """Create an AnthropicClient with mocked SDK and config."""
        from stlc_platform.core.llm.anthropic_client import AnthropicClient
        from stlc_platform.core.llm.base_client import TokenUsage

        client = AnthropicClient.__new__(AnthropicClient)
        # Base class attributes (normally set by BaseLLMClient.__init__)
        client._last_token_usage = TokenUsage()
        client._accumulated_tokens = TokenUsage()
        client._cache = None
        # AnthropicClient attributes
        client.api_key = "sk-ant-test-key"
        client.model = kwargs.get("model", "claude-sonnet-4-20250514")
        client.temperature = kwargs.get("temperature", 0.6)
        client.timeout = kwargs.get("timeout", 120)
        client.max_tokens = kwargs.get("max_tokens", 3200)
        client.debug = False
        client._client = MagicMock()
        return client

    def test_generate_basic(self):
        """Test basic text generation."""
        client = self._make_client()
        mock_block = MagicMock()
        mock_block.text = '{"title": "test"}'
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        client._client.messages.create.return_value = mock_response

        result = client.generate("test prompt")
        assert result == '{"title": "test"}'
        client._client.messages.create.assert_called_once()

    def test_generate_with_system_prompt(self):
        """Test system prompt is passed as top-level param."""
        client = self._make_client()
        mock_block = MagicMock()
        mock_block.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        client._client.messages.create.return_value = mock_response

        result = client.generate("user prompt", system_prompt="be helpful")
        assert result == "response"

        call_kwargs = client._client.messages.create.call_args[1]
        assert "system" in call_kwargs
        assert "be helpful" in call_kwargs["system"]

    def test_generate_with_json_schema(self):
        """Test JSON instruction is appended when schema provided."""
        client = self._make_client()
        mock_block = MagicMock()
        mock_block.text = '{"result": true}'
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        client._client.messages.create.return_value = mock_response

        client.generate("prompt", system_prompt="system", json_schema={"type": "object"})
        call_kwargs = client._client.messages.create.call_args[1]
        assert "valid JSON" in call_kwargs["system"]

    def test_generate_with_custom_temperature(self):
        """Test temperature override."""
        client = self._make_client(temperature=0.5)
        mock_block = MagicMock()
        mock_block.text = "output"
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        client._client.messages.create.return_value = mock_response

        client.generate("prompt", temperature=0.9)
        call_kwargs = client._client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.9

    def test_check_connection_success(self):
        """Test successful connection check."""
        client = self._make_client()
        mock_block = MagicMock()
        mock_block.text = ""
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        client._client.messages.create.return_value = mock_response
        assert client.check_connection() is True

    def test_check_connection_failure(self):
        """Test failed connection check."""
        client = self._make_client()
        client._client.messages.create.side_effect = Exception("auth failed")
        assert client.check_connection() is False

    def test_list_models(self):
        """Test listing known models."""
        client = self._make_client()
        models = client.list_models()
        assert len(models) > 0
        assert "claude-sonnet-4-20250514" in models

    def test_generate_api_error(self):
        """Test API error handling."""
        client = self._make_client()
        client._client.messages.create.side_effect = RuntimeError("rate limited")

        with pytest.raises(RuntimeError, match="Anthropic API error"):
            client.generate("prompt")

    def test_generate_empty_response(self):
        """Test handling of empty response content."""
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.content = []
        client._client.messages.create.return_value = mock_response

        result = client.generate("prompt")
        assert result == ""

    def test_is_base_llm_client_subclass(self):
        """Test AnthropicClient inherits from BaseLLMClient."""
        from stlc_platform.core.llm.anthropic_client import AnthropicClient
        from stlc_platform.core.llm.base_client import BaseLLMClient

        assert issubclass(AnthropicClient, BaseLLMClient)
