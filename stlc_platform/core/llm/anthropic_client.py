"""
Anthropic LLM Client
====================
Concrete implementation of BaseLLMClient for Anthropic Claude API.

Requires: pip install anthropic
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from rich.console import Console

from stlc_platform.core.llm.base_client import BaseLLMClient

console = Console()

# Known Claude models (Anthropic has no list-models endpoint)
_KNOWN_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-haiku-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicClient. "
                "Install it with: pip install anthropic"
            )

        from stlc_platform.core.config_loader import config

        _api_key = api_key or os.getenv("STLC_LLM__API_KEY", "")
        if not _api_key:
            raise ValueError(
                "Anthropic API key is required. Set it via:\n"
                "  - STLC_LLM__API_KEY environment variable\n"
                "  - llm.api_key in stlc_config.yaml\n"
                "  - api_key parameter to AnthropicClient()"
            )

        self.api_key = _api_key
        self.model = model or os.getenv("STLC_LLM__MODEL", "") or "claude-sonnet-4-20250514"
        self.temperature = temperature if temperature is not None else config.ollama.temperature
        self.timeout = timeout or config.ollama.timeout or 120
        self.max_tokens = max_tokens or config.ollama.num_predict or 3200
        self.debug = os.getenv("DEBUG_LLM", "").lower() in ("1", "true", "yes")

        import anthropic as _anthropic

        self._client = _anthropic.Anthropic(
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def check_connection(self) -> bool:
        """Verify Anthropic API is reachable with a minimal request."""
        try:
            self._client.messages.create(
                model=self.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    def list_models(self) -> list:
        """Return known Claude models (Anthropic has no list-models endpoint)."""
        return list(_KNOWN_MODELS)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        """Generate text using Anthropic Messages API."""
        t = temperature if temperature is not None else self.temperature

        messages: list[Dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        # Anthropic uses 'system' as a top-level parameter, not in messages
        system = system_prompt or ""

        # When JSON output is needed, add instruction to system prompt
        if json_schema is not None:
            json_instruction = (
                "\n\nIMPORTANT: You must respond with valid JSON only. "
                "Do not include any text before or after the JSON object."
            )
            system = (system + json_instruction) if system else json_instruction.strip()

        if self.debug:
            console.print(
                f"\n[dim]-- SENDING TO ANTHROPIC "
                f"(model={self.model} | temp={t:.2f} | "
                f"max_tokens={self.max_tokens} | "
                f"json_mode={json_schema is not None}) --[/dim]"
            )
            console.print(f"[dim]{prompt[:500]}...[/dim]\n")

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": t,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system

            response = self._client.messages.create(**kwargs)
            content = response.content[0].text if response.content else ""
            content = content.strip()

            if self.debug:
                console.print(f"[dim]-- RAW RESPONSE ({len(content)} chars) --[/dim]")
                console.print(f"[dim]{content[:600]}[/dim]")
                console.print("[dim]-- END --[/dim]\n")

            return content

        except Exception as e:
            error_type = type(e).__name__
            raise RuntimeError(f"Anthropic API error ({error_type}): {e}")
