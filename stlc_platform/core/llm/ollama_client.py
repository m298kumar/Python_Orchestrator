"""
Ollama LLM Client
=================
Concrete implementation of BaseLLMClient for local Ollama server.
Migrated from the original llm_client.py with no logic changes.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests
from rich.console import Console

from stlc_platform.core.llm.base_client import BaseLLMClient

console = Console()


class OllamaClient(BaseLLMClient):
    """Client for interacting with local Ollama LLM."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
        timeout: Optional[int] = None,
        num_predict: Optional[int] = None,
    ):
        super().__init__()
        # Import config lazily to avoid circular imports during early init
        from stlc_platform.core.config_loader import config

        self.base_url = base_url or config.ollama.base_url
        self.model = model or config.ollama.model
        self.temperature = temperature if temperature is not None else config.ollama.temperature
        self.num_ctx = num_ctx or config.ollama.num_ctx
        self.timeout = timeout or config.ollama.timeout
        self.num_predict = num_predict or config.ollama.num_predict
        self.debug = os.getenv("DEBUG_LLM", "").lower() in ("1", "true", "yes")

    def check_connection(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def list_models(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except (OSError, ValueError, KeyError):
            pass
        return []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t = temperature if temperature is not None else self.temperature

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": t,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
                "repeat_penalty": 1.15,
                "top_k": 40,
                "top_p": 0.9,
                "stop": ["}\n\n", "}\n```", "} ```"],
            },
        }

        if json_schema is not None:
            payload["format"] = json_schema

        if self.debug:
            console.print(
                f"\n[dim]-- SENDING TO OLLAMA "
                f"(temp={t:.2f} | repeat_penalty=1.15 | num_predict={self.num_predict} | "
                f"format={'schema' if json_schema else 'text'}) --[/dim]"
            )
            console.print(f"[dim]{prompt[:500]}...[/dim]\n")

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            resp_json = resp.json()
            content: str = resp_json["message"]["content"].strip()

            # Extract token counts from Ollama response
            prompt_tokens = resp_json.get("prompt_eval_count", 0)
            completion_tokens = resp_json.get("eval_count", 0)
            self._record_tokens(prompt_tokens, completion_tokens)

            if self.debug:
                console.print(f"[dim]-- RAW RESPONSE ({len(content)} chars) --[/dim]")
                console.print(
                    f"[dim]  tokens: prompt={prompt_tokens} completion={completion_tokens}[/dim]"
                )
                console.print(f"[dim]{content[:600]}[/dim]")
                console.print("[dim]-- END --[/dim]\n")

            return content

        except requests.Timeout:
            raise TimeoutError(
                f"Ollama timed out after {self.timeout}s. "
                "Increase OLLAMA_TIMEOUT or use a smaller model."
            )
        except requests.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}. Run: ollama serve")
        except requests.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e.response.text}")

    def pull_model(self, model_name: str) -> bool:
        console.print(f"[cyan]Pulling model: {model_name}...[/cyan]")
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=300,
            )
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("status") == "success":
                        console.print(f"[green]Model {model_name} pulled[/green]")
                        return True
            return True
        except Exception as e:
            console.print(f"[red]Failed to pull model: {e}[/red]")
            return False
