"""
OpenAI LLM Client
=================
Concrete implementation of BaseLLMClient for OpenAI-compatible APIs
(GPT-4, GPT-3.5, Azure OpenAI, etc.).

Requires: pip install openai
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from rich.console import Console

from stlc_platform.core.llm.base_client import BaseLLMClient

console = Console()


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI and OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        super().__init__()
        try:
            import openai  # noqa: F401
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAIClient. "
                "Install it with: pip install openai"
            )

        from stlc_platform.core.config_loader import config

        self.api_key = api_key or os.getenv("STLC_LLM__API_KEY", "") or config.ollama.base_url
        # Use dedicated config if available, fall back to env or empty
        _api_key = api_key or os.getenv("STLC_LLM__API_KEY", "")
        if not _api_key:
            raise ValueError(
                "OpenAI API key is required. Set it via:\n"
                "  - STLC_LLM__API_KEY environment variable\n"
                "  - llm.api_key in stlc_config.yaml\n"
                "  - api_key parameter to OpenAIClient()"
            )

        self.api_key = _api_key
        self.model = model or os.getenv("STLC_LLM__MODEL", "") or "gpt-4o"
        self.base_url = base_url or os.getenv("STLC_LLM__BASE_URL", "") or None
        self.temperature = temperature if temperature is not None else config.ollama.temperature
        self.timeout = timeout or config.ollama.timeout or 120
        self.max_tokens = max_tokens or config.ollama.num_predict or 3200
        self.debug = os.getenv("DEBUG_LLM", "").lower() in ("1", "true", "yes")

        import openai as _openai

        client_kwargs: Dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout,
        }
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = _openai.OpenAI(**client_kwargs)

    def check_connection(self) -> bool:
        """Verify OpenAI API is reachable by listing models."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list:
        """List available models from OpenAI."""
        try:
            response = self._client.models.list()
            return [m.id for m in response.data]
        except Exception:
            return []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Generate text using OpenAI Chat Completions API."""
        messages: list[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t = temperature if temperature is not None else self.temperature

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": t,
            "max_tokens": self.max_tokens,
        }

        # Use JSON mode when schema is provided
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
            # Prepend JSON instruction to system prompt if not already there
            if messages and messages[0]["role"] == "system":
                if "json" not in messages[0]["content"].lower():
                    messages[0]["content"] += (
                        "\n\nIMPORTANT: You must respond with valid JSON only."
                    )
            else:
                messages.insert(0, {
                    "role": "system",
                    "content": "You must respond with valid JSON only.",
                })

        if self.debug:
            console.print(
                f"\n[dim]-- SENDING TO OPENAI "
                f"(model={self.model} | temp={t:.2f} | "
                f"max_tokens={self.max_tokens} | "
                f"json_mode={json_schema is not None}) --[/dim]"
            )
            console.print(f"[dim]{prompt[:500]}...[/dim]\n")

        try:
            response = self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            content = content.strip()

            # Extract token counts from OpenAI response
            usage = getattr(response, "usage", None)
            if usage:
                self._record_tokens(
                    getattr(usage, "prompt_tokens", 0),
                    getattr(usage, "completion_tokens", 0),
                )

            if self.debug:
                console.print(f"[dim]-- RAW RESPONSE ({len(content)} chars) --[/dim]")
                console.print(f"[dim]{content[:600]}[/dim]")
                console.print("[dim]-- END --[/dim]\n")

            return content

        except Exception as e:
            error_type = type(e).__name__
            raise RuntimeError(f"OpenAI API error ({error_type}): {e}")
