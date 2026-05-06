"""
LLM Pricing
============
Token-based cost estimation for supported LLM providers.
Prices are per 1K tokens (input and output separately).
"""

from __future__ import annotations

from typing import Dict

# Prices in USD per 1,000 tokens
# Updated 2026-03. Local models (Ollama) have zero cost.
PRICING: Dict[str, Dict[str, Dict[str, float]]] = {
    "ollama": {
        "_default": {"in": 0.0, "out": 0.0},
    },
    "openai": {
        "gpt-4o": {"in": 0.0025, "out": 0.01},
        "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
        "gpt-4.1": {"in": 0.002, "out": 0.008},
        "gpt-4.1-mini": {"in": 0.0004, "out": 0.0016},
        "gpt-4.1-nano": {"in": 0.0001, "out": 0.0004},
        "o3-mini": {"in": 0.00115, "out": 0.0044},
        "_default": {"in": 0.0025, "out": 0.01},
    },
    "anthropic": {
        "claude-sonnet-4-20250514": {"in": 0.003, "out": 0.015},
        "claude-opus-4-20250514": {"in": 0.015, "out": 0.075},
        "claude-haiku-4-20250514": {"in": 0.0008, "out": 0.004},
        "_default": {"in": 0.003, "out": 0.015},
    },
    "azure": {
        "_default": {"in": 0.0025, "out": 0.01},
    },
}


def estimate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate the cost in USD for a given LLM call.

    Falls back to provider default if the specific model isn't listed.
    Returns 0.0 for unknown providers.
    """
    provider_prices = PRICING.get(provider.lower(), {})
    model_prices = provider_prices.get(model, provider_prices.get("_default"))

    if model_prices is None:
        return 0.0

    cost = (input_tokens / 1000) * model_prices["in"] + (output_tokens / 1000) * model_prices["out"]
    return round(cost, 6)
