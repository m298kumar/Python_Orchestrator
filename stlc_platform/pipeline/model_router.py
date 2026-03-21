"""
Tiered Model Router
===================
Selects the appropriate LLM provider/model based on task complexity.

The router supports three tiers:
  - lightweight: Fast, cheap models for template-driven tasks (BDD, crawler)
  - standard: General-purpose models for most generation tasks
  - advanced: Most capable models for complex reasoning (requirements analysis)

The router returns config dicts, not LLM instances — the agent or LLM factory
handles actual instantiation.

Usage:
    router = ModelRouter.from_config(yaml_config)
    tier = router.select_tier(agent_caps, input_context)
    llm_config = router.get_llm_config(tier)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from stlc_platform.core.base_agent import AgentCapabilities


@dataclass
class ModelTier:
    """
    A named LLM tier with provider/model configuration.

    Attributes:
        name: Tier identifier ("lightweight", "standard", "advanced").
        provider: LLM provider ("ollama", "openai", "anthropic").
        model: Model name/identifier.
        temperature: Default temperature for this tier.
        max_tokens: Max generation tokens.
    """

    name: str
    provider: str = "ollama"
    model: str = ""
    temperature: float = 0.6
    max_tokens: int = 3200


@dataclass
class ComplexitySignals:
    """Heuristic signals derived from input context."""

    input_token_estimate: int = 0
    item_count: int = 0
    has_unknown_domain: bool = False

    @property
    def complexity_score(self) -> float:
        """
        Compute a 0-1 complexity score.

        Scoring rules:
        - input_token_estimate > 10000 → +0.3
        - item_count > 50 → +0.2
        - has_unknown_domain → +0.2
        - Baseline: 0.3
        """
        score = 0.3
        if self.input_token_estimate > 10000:
            score += 0.3
        elif self.input_token_estimate > 5000:
            score += 0.15
        if self.item_count > 50:
            score += 0.2
        elif self.item_count > 20:
            score += 0.1
        if self.has_unknown_domain:
            score += 0.2
        return min(score, 1.0)


class ModelRouter:
    """
    Routes agents to the appropriate LLM tier based on capabilities and context.

    The router:
    1. Checks the agent's default_model_tier
    2. Applies complexity heuristics to potentially upgrade the tier
    3. Falls back gracefully if a tier is unavailable
    """

    # Tier priority for fallback (prefer cheaper tiers when target unavailable)
    TIER_ORDER = ["lightweight", "standard", "advanced"]

    def __init__(
        self,
        tiers: Optional[Dict[str, ModelTier]] = None,
        fallback_tier: str = "standard",
    ) -> None:
        self._tiers = tiers or {}
        self._fallback = fallback_tier

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ModelRouter":
        """
        Create a router from config dict.

        Expected format:
            model_routing:
              fallback: standard
              tiers:
                lightweight:
                  provider: ollama
                  model: phi4-mini:3.8b
                  temperature: 0.4
                standard:
                  provider: ollama
                  model: phi4-mini:3.8b
                  temperature: 0.6
                advanced:
                  provider: openai
                  model: gpt-4o
                  temperature: 0.7
        """
        routing = config.get("model_routing", {})
        fallback = routing.get("fallback", "standard")
        tiers_raw = routing.get("tiers", {})

        tiers: Dict[str, ModelTier] = {}
        for name, tier_cfg in tiers_raw.items():
            tiers[name] = ModelTier(
                name=name,
                provider=tier_cfg.get("provider", "ollama"),
                model=tier_cfg.get("model", ""),
                temperature=tier_cfg.get("temperature", 0.6),
                max_tokens=tier_cfg.get("max_tokens", 3200),
            )

        return cls(tiers=tiers, fallback_tier=fallback)

    @classmethod
    def default(cls) -> "ModelRouter":
        """Create a router with sensible defaults for local development."""
        return cls(
            tiers={
                "lightweight": ModelTier(
                    name="lightweight",
                    provider="ollama",
                    model="phi4-mini:3.8b",
                    temperature=0.4,
                    max_tokens=2000,
                ),
                "standard": ModelTier(
                    name="standard",
                    provider="ollama",
                    model="phi4-mini:3.8b",
                    temperature=0.6,
                    max_tokens=3200,
                ),
                "advanced": ModelTier(
                    name="advanced",
                    provider="ollama",
                    model="phi4-mini:3.8b",
                    temperature=0.7,
                    max_tokens=4096,
                ),
            },
            fallback_tier="standard",
        )

    def select_tier(
        self,
        agent_caps: AgentCapabilities,
        input_context: Optional[Dict[str, Any]] = None,
    ) -> ModelTier:
        """
        Select the best tier for an agent given its capabilities and input context.

        Logic:
        1. Start with agent's default_model_tier
        2. Compute complexity signals from input_context
        3. If complexity is high, promote to next tier
        4. Fall back if selected tier is unavailable
        """
        # Start with agent's preferred tier
        preferred = getattr(agent_caps, "default_model_tier", "standard")

        # Compute complexity signals
        signals = self._analyze_context(input_context or {})

        # Potentially promote tier based on complexity
        selected = self._apply_complexity_promotion(preferred, signals)

        # Resolve to actual tier (with fallback)
        return self._resolve_tier(selected)

    def get_llm_config(self, tier: ModelTier) -> Dict[str, Any]:
        """
        Convert a tier to an LLM config dict suitable for create_llm_client().

        Returns:
            Dict with provider, model, temperature, max_tokens keys.
        """
        return {
            "provider": tier.provider,
            "model": tier.model,
            "temperature": tier.temperature,
            "max_tokens": tier.max_tokens,
            "tier": tier.name,
        }

    @property
    def available_tiers(self) -> List[str]:
        """Return names of configured tiers."""
        return sorted(self._tiers.keys())

    def has_tier(self, name: str) -> bool:
        """Check if a named tier is configured."""
        return name in self._tiers

    def _analyze_context(self, context: Dict[str, Any]) -> ComplexitySignals:
        """Extract complexity signals from input context."""
        signals = ComplexitySignals()

        # Estimate token count from string values
        for value in context.values():
            if isinstance(value, str):
                signals.input_token_estimate += len(value) // 4
            elif isinstance(value, list):
                signals.item_count += len(value)
                for item in value:
                    if isinstance(item, str):
                        signals.input_token_estimate += len(item) // 4

        return signals

    def _apply_complexity_promotion(
        self, preferred: str, signals: ComplexitySignals
    ) -> str:
        """Promote to a higher tier if complexity warrants it."""
        score = signals.complexity_score

        if preferred == "lightweight" and score > 0.6:
            return "standard"
        elif preferred == "standard" and score > 0.7:
            return "advanced"

        return preferred

    def _resolve_tier(self, name: str) -> ModelTier:
        """Resolve tier name to ModelTier, with fallback."""
        if name in self._tiers:
            return self._tiers[name]

        # Try fallback
        if self._fallback in self._tiers:
            return self._tiers[self._fallback]

        # Last resort: return any available tier
        if self._tiers:
            return next(iter(self._tiers.values()))

        # No tiers configured at all — return a default
        return ModelTier(name="standard", provider="ollama", model="phi4-mini:3.8b")
