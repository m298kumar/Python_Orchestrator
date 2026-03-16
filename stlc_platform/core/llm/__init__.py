"""LLM abstraction layer — pluggable providers."""

from stlc_platform.core.llm.base_client import BaseLLMClient
from stlc_platform.core.llm.ollama_client import OllamaClient

__all__ = ["BaseLLMClient", "OllamaClient"]
