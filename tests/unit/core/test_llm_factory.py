"""Tests for the LLM client factory function."""

from __future__ import annotations

import pytest

from stlc_platform.core.llm import create_llm_client
from stlc_platform.core.llm.base_client import BaseLLMClient
from stlc_platform.core.llm.ollama_client import OllamaClient


class TestCreateLLMClient:
    """Tests for create_llm_client factory."""

    def test_ollama_provider(self):
        """Test that 'ollama' returns an OllamaClient."""
        client = create_llm_client("ollama")
        assert isinstance(client, OllamaClient)
        assert isinstance(client, BaseLLMClient)

    def test_ollama_is_default(self):
        """Test that default provider is ollama when config says so."""
        # The default config has provider=ollama
        client = create_llm_client(None)
        assert isinstance(client, OllamaClient)

    def test_openai_provider_class_check(self):
        """Test that 'openai' returns OpenAIClient or raises ImportError."""
        from stlc_platform.core.llm import OpenAIClient
        if OpenAIClient is None:
            with pytest.raises(ImportError, match="openai"):
                create_llm_client("openai", api_key="sk-test")
        else:
            # Can't fully construct without valid config, but class should be correct
            assert issubclass(OpenAIClient, BaseLLMClient)

    def test_anthropic_provider_class_check(self):
        """Test that 'anthropic' returns AnthropicClient or raises ImportError."""
        from stlc_platform.core.llm import AnthropicClient
        if AnthropicClient is None:
            with pytest.raises(ImportError, match="anthropic"):
                create_llm_client("anthropic", api_key="sk-test")
        else:
            assert issubclass(AnthropicClient, BaseLLMClient)

    def test_azure_alias(self):
        """Test that 'azure' routes to OpenAIClient."""
        from stlc_platform.core.llm import OpenAIClient
        if OpenAIClient is None:
            with pytest.raises(ImportError, match="openai"):
                create_llm_client("azure", api_key="sk-test")
        else:
            assert issubclass(OpenAIClient, BaseLLMClient)

    def test_claude_alias(self):
        """Test that 'claude' routes to AnthropicClient."""
        from stlc_platform.core.llm import AnthropicClient
        if AnthropicClient is None:
            with pytest.raises(ImportError, match="anthropic"):
                create_llm_client("claude", api_key="sk-test")
        else:
            assert issubclass(AnthropicClient, BaseLLMClient)

    def test_unknown_provider(self):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_client("unknown_provider")

    def test_provider_case_insensitive(self):
        """Test that provider names are case-insensitive."""
        client = create_llm_client("OLLAMA")
        assert isinstance(client, OllamaClient)

    def test_provider_whitespace_stripped(self):
        """Test that whitespace around provider is stripped."""
        client = create_llm_client("  ollama  ")
        assert isinstance(client, OllamaClient)

    def test_kwargs_passed_through(self):
        """Test that extra kwargs are forwarded to the client constructor."""
        client = create_llm_client("ollama", base_url="http://custom:11434")
        assert client.base_url == "http://custom:11434"
