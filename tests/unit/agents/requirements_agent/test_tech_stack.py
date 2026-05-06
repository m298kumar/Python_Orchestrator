"""Tests for the TechStackContext class."""

from __future__ import annotations

from stlc_platform.agents.requirements_agent.tech_stack import TechStackContext


class TestDefaultVerbs:
    """Test default platform verb mappings."""

    def test_web_click(self):
        ctx = TechStackContext(platform="web")
        assert ctx.get_verb("click") == "click"

    def test_mobile_click_is_tap(self):
        ctx = TechStackContext(platform="mobile")
        assert ctx.get_verb("click") == "tap"

    def test_api_click_is_send_request(self):
        ctx = TechStackContext(platform="api")
        assert ctx.get_verb("click") == "send request"

    def test_desktop_click(self):
        ctx = TechStackContext(platform="desktop")
        assert ctx.get_verb("click") == "click"

    def test_web_page_loads(self):
        ctx = TechStackContext(platform="web")
        assert ctx.get_verb("page_loads") == "page loads"

    def test_mobile_page_loads_is_screen_appears(self):
        ctx = TechStackContext(platform="mobile")
        assert ctx.get_verb("page_loads") == "screen appears"

    def test_api_navigate_is_call_endpoint(self):
        ctx = TechStackContext(platform="api")
        assert ctx.get_verb("navigate") == "call endpoint"

    def test_unknown_action_returns_itself(self):
        ctx = TechStackContext(platform="web")
        assert ctx.get_verb("fly_to_moon") == "fly_to_moon"

    def test_unknown_platform_returns_action(self):
        ctx = TechStackContext(platform="mainframe")
        assert ctx.get_verb("click") == "click"  # fallback


class TestGetAllVerbs:
    """Test retrieving all verbs for a platform."""

    def test_web_has_all_keys(self):
        ctx = TechStackContext(platform="web")
        verbs = ctx.get_all_verbs()
        assert "click" in verbs
        assert "navigate" in verbs
        assert "page_loads" in verbs
        assert "screen" in verbs

    def test_api_screen_is_endpoint(self):
        ctx = TechStackContext(platform="api")
        verbs = ctx.get_all_verbs()
        assert verbs["screen"] == "endpoint"


class TestTestModifiers:
    """Test platform-specific test modifiers."""

    def test_web_positive(self):
        ctx = TechStackContext(platform="web")
        mod = ctx.get_test_modifier("positive")
        assert "browser" in mod.lower()

    def test_mobile_edge_case(self):
        ctx = TechStackContext(platform="mobile")
        mod = ctx.get_test_modifier("edge_case")
        assert "offline" in mod.lower() or "orientation" in mod.lower()

    def test_api_negative(self):
        ctx = TechStackContext(platform="api")
        mod = ctx.get_test_modifier("negative")
        assert "invalid" in mod.lower() or "authentication" in mod.lower()

    def test_unknown_test_type_returns_empty(self):
        ctx = TechStackContext(platform="web")
        assert ctx.get_test_modifier("chaos") == ""


class TestPlatformSummary:
    """Test get_platform_summary() output."""

    def test_minimal_summary(self):
        ctx = TechStackContext(platform="web", backend="")
        assert ctx.get_platform_summary() == "web application"

    def test_full_summary(self):
        ctx = TechStackContext(
            platform="web",
            frontend="react",
            backend="rest",
            database="postgres",
            auth="jwt",
        )
        summary = ctx.get_platform_summary()
        assert "web application" in summary
        assert "react frontend" in summary
        assert "REST backend" in summary
        assert "postgres database" in summary
        assert "JWT auth" in summary

    def test_partial_summary(self):
        ctx = TechStackContext(platform="mobile", frontend="flutter")
        summary = ctx.get_platform_summary()
        assert "mobile application" in summary
        assert "flutter frontend" in summary
        assert "database" not in summary  # no database set


class TestFromConfig:
    """Test factory method from_config()."""

    def test_empty_config(self):
        ctx = TechStackContext.from_config()
        assert ctx.platform == "web"

    def test_with_platform(self):
        ctx = TechStackContext.from_config({"platform": "api"})
        assert ctx.platform == "api"
        assert ctx.get_verb("click") == "send request"

    def test_with_full_tech_stack(self):
        ctx = TechStackContext.from_config(
            {
                "platform": "web",
                "frontend": "vue",
                "backend": "graphql",
                "database": "mongo",
                "auth": "oauth2",
            }
        )
        assert ctx.frontend == "vue"
        assert ctx.backend == "graphql"
        assert ctx.database == "mongo"
        assert ctx.auth == "oauth2"

    def test_custom_verbs_override(self):
        custom_verbs = {
            "web": {"click": "press", "navigate": "go to"},
        }
        ctx = TechStackContext.from_config(
            tech_stack={"platform": "web"},
            platform_verbs=custom_verbs,
        )
        assert ctx.get_verb("click") == "press"
        assert ctx.get_verb("navigate") == "go to"

    def test_custom_modifiers_override(self):
        custom_mods = {
            "api": {"positive": "Verify endpoint returns 200 OK."},
        }
        ctx = TechStackContext.from_config(
            tech_stack={"platform": "api"},
            platform_modifiers=custom_mods,
        )
        assert "200 OK" in ctx.get_test_modifier("positive")
