"""Tests for the component resolver."""

from __future__ import annotations

from unittest.mock import MagicMock

from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver


class TestComponentResolver:
    """Test the 4-tier component resolution."""

    def test_tier1_keeps_specific_llm_output(self):
        resolver = ComponentResolver()
        result = resolver.resolve(
            "Patient Registration Form Screen", "Registration", "Patient Registration"
        )
        assert result == "Patient Registration Form Screen"

    def test_tier1_rejects_generic_names(self):
        resolver = ComponentResolver()
        result = resolver.resolve("the application", "Login", "User Login")
        assert result != "the application"

    def test_tier1_rejects_short_names(self):
        resolver = ComponentResolver()
        result = resolver.resolve("Login", "Auth", "User Login")
        # "Login" is only 5 chars, below threshold of 15
        assert "Screen" in result

    def test_tier1_rejects_instruction_text(self):
        resolver = ComponentResolver()
        result = resolver.resolve("Name the specific screen or service", "Auth", "Login")
        assert "specific screen" not in result.lower()

    def test_tier2_chromadb_lookup(self):
        mock_store = MagicMock()
        mock_store.lookup_component.return_value = "OTP Verification Screen"
        resolver = ComponentResolver(vector_store=mock_store)
        result = resolver.resolve("", "Auth", "OTP Setup", "User must verify OTP")
        assert result == "OTP Verification Screen"

    def test_tier2_chromadb_failure_falls_through(self):
        mock_store = MagicMock()
        mock_store.lookup_component.side_effect = RuntimeError("DB error")
        resolver = ComponentResolver(vector_store=mock_store)
        result = resolver.resolve("", "Dashboard", "Main Dashboard")
        assert "Dashboard" in result

    def test_tier3_suffix_map_from_category(self):
        resolver = ComponentResolver()
        result = resolver.resolve("", "Login", "User Login Feature")
        assert "Login" in result

    def test_tier3_suffix_map_from_title(self):
        resolver = ComponentResolver()
        result = resolver.resolve("", "Unknown", "Payment Gateway")
        assert "Payment" in result

    def test_tier3_custom_suffix_map(self):
        resolver = ComponentResolver(suffix_map={"crm": "CRM Module"})
        result = resolver.resolve("", "crm", "CRM Dashboard")
        assert "CRM" in result

    def test_tier4_constructed_from_category(self):
        resolver = ComponentResolver(suffix_map={})  # Empty map = skip tier 3
        result = resolver.resolve("", "inventory management", "")
        assert result == "Inventory Management Screen"

    def test_tier4_constructed_from_title(self):
        resolver = ComponentResolver(suffix_map={})
        result = resolver.resolve("", "", "Compliance Check Workflow")
        assert "Compliance" in result

    def test_tier4_ultimate_fallback(self):
        resolver = ComponentResolver(suffix_map={})
        result = resolver.resolve("", "", "")
        assert result == "Application Screen"

    def test_custom_generic_names(self):
        resolver = ComponentResolver(generic_names={"my custom app"})
        # "my custom app" is in generic names, but the raw is longer and different
        # Actually the check is `any(g in raw_clean.lower() for g in self._generic_names)`
        result2 = resolver.resolve("my custom app", "Auth", "Login")
        assert result2 != "my custom app"
