"""
Tests for ModelRouter — tiered model selection.
"""


from stlc_platform.core.base_agent import AgentCapabilities
from stlc_platform.pipeline.model_router import (
    ComplexitySignals,
    ModelRouter,
    ModelTier,
)


class TestModelTierDefaults:
    def test_default_router_has_three_tiers(self):
        router = ModelRouter.default()
        assert router.has_tier("lightweight")
        assert router.has_tier("standard")
        assert router.has_tier("advanced")
        assert len(router.available_tiers) == 3


class TestTierSelection:
    def test_selects_agent_default_tier(self):
        router = ModelRouter.default()
        caps = AgentCapabilities(
            agent_id="test", agent_version="1.0",
            default_model_tier="advanced",
        )
        tier = router.select_tier(caps)
        assert tier.name == "advanced"

    def test_selects_lightweight_for_bdd(self):
        router = ModelRouter.default()
        caps = AgentCapabilities(
            agent_id="bdd", agent_version="1.0",
            default_model_tier="lightweight",
        )
        tier = router.select_tier(caps)
        assert tier.name == "lightweight"

    def test_promotes_lightweight_on_high_complexity(self):
        router = ModelRouter.default()
        caps = AgentCapabilities(
            agent_id="bdd", agent_version="1.0",
            default_model_tier="lightweight",
        )
        # Large input context (~10000+ tokens via word-based estimation)
        context = {"data": " ".join(["word"] * 10000), "items": list(range(100))}
        tier = router.select_tier(caps, input_context=context)
        assert tier.name == "standard"

    def test_fallback_when_tier_unavailable(self):
        router = ModelRouter(
            tiers={"standard": ModelTier(name="standard")},
            fallback_tier="standard",
        )
        caps = AgentCapabilities(
            agent_id="test", agent_version="1.0",
            default_model_tier="advanced",  # not available
        )
        tier = router.select_tier(caps)
        assert tier.name == "standard"

    def test_last_resort_when_no_tiers_configured(self):
        router = ModelRouter(tiers={})
        caps = AgentCapabilities(agent_id="test", agent_version="1.0")
        tier = router.select_tier(caps)
        assert tier.name == "standard"  # hardcoded fallback


class TestComplexitySignals:
    def test_low_complexity(self):
        signals = ComplexitySignals(input_token_estimate=100, item_count=5)
        assert signals.complexity_score < 0.5

    def test_high_complexity(self):
        signals = ComplexitySignals(
            input_token_estimate=15000, item_count=100, has_unknown_domain=True
        )
        assert signals.complexity_score > 0.7

    def test_medium_complexity(self):
        signals = ComplexitySignals(input_token_estimate=7000, item_count=30)
        score = signals.complexity_score
        assert 0.4 < score < 0.8

    def test_capped_at_one(self):
        signals = ComplexitySignals(
            input_token_estimate=100000, item_count=1000, has_unknown_domain=True
        )
        assert signals.complexity_score == 1.0


class TestFromConfig:
    def test_parses_config_dict(self):
        config = {
            "model_routing": {
                "fallback": "standard",
                "tiers": {
                    "lightweight": {
                        "provider": "ollama",
                        "model": "phi4-mini",
                        "temperature": 0.4,
                    },
                    "standard": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "temperature": 0.6,
                    },
                },
            }
        }
        router = ModelRouter.from_config(config)
        assert router.has_tier("lightweight")
        assert router.has_tier("standard")
        assert not router.has_tier("advanced")

    def test_empty_config_creates_empty_router(self):
        router = ModelRouter.from_config({})
        assert router.available_tiers == []


class TestGetLLMConfig:
    def test_returns_config_dict(self):
        router = ModelRouter.default()
        tier = ModelTier(name="test", provider="openai", model="gpt-4o", temperature=0.7)
        config = router.get_llm_config(tier)
        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o"
        assert config["tier"] == "test"
        assert "temperature" in config
