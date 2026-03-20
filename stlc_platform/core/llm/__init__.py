"""LLM abstraction layer — pluggable providers."""

from stlc_platform.core.llm.base_client import BaseLLMClient
from stlc_platform.core.llm.ollama_client import OllamaClient

# Optional providers — import-guarded so missing packages don't break core
try:
    from stlc_platform.core.llm.openai_client import OpenAIClient
except ImportError:
    OpenAIClient = None  # type: ignore[assignment,misc]

try:
    from stlc_platform.core.llm.anthropic_client import AnthropicClient
except ImportError:
    AnthropicClient = None  # type: ignore[assignment,misc]


def create_llm_client(provider: str | None = None, **kwargs) -> BaseLLMClient:
    """
    Factory function to create an LLM client based on the provider string.

    Args:
        provider: One of "ollama", "openai", "anthropic". If None, reads from config.
        **kwargs: Passed through to the client constructor.

    Returns:
        A concrete BaseLLMClient instance.

    Raises:
        ImportError: If the required package for a provider is not installed.
        ValueError: If the provider string is unrecognised.
    """
    if provider is None:
        from stlc_platform.core.config_loader import config
        provider = getattr(config, "llm_provider", "ollama") or "ollama"

    provider = provider.lower().strip()

    if provider == "ollama":
        return OllamaClient(**kwargs)

    if provider in ("openai", "azure"):
        if OpenAIClient is None:
            raise ImportError(
                f"Provider '{provider}' requires the 'openai' package. "
                "Install it with: pip install openai"
            )
        return OpenAIClient(**kwargs)

    if provider in ("anthropic", "claude"):
        if AnthropicClient is None:
            raise ImportError(
                f"Provider '{provider}' requires the 'anthropic' package. "
                "Install it with: pip install anthropic"
            )
        return AnthropicClient(**kwargs)

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. "
        "Supported providers: ollama, openai, anthropic"
    )


__all__ = [
    "BaseLLMClient",
    "OllamaClient",
    "OpenAIClient",
    "AnthropicClient",
    "create_llm_client",
]
