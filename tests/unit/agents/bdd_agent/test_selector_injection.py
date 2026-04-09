"""Tests for Phase D3: CSS selector injection from crawler site model."""

from stlc_platform.agents.bdd_agent.agent import BDDAgent
from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator
from stlc_platform.agents.bdd_agent.step_parser import ParameterizedStep
from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    SiteModelArtifact,
    TestCaseArtifact,
    TestStepArtifact,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_site_model(elements=None):
    """Build a minimal SiteModelArtifact with a single page."""
    page = CrawledPageArtifact(
        url="http://localhost/login",
        title="Login Page",
        elements=elements or [],
    )
    return SiteModelArtifact(
        base_url="http://localhost",
        pages=[page],
    )


def _make_tc(**overrides) -> TestCaseArtifact:
    defaults = {
        "tc_id": "TC-0001",
        "req_id": "REQ-001",
        "title": "Login test",
        "description": "Verify login",
        "preconditions": "User exists",
        "test_type": "positive",
        "priority": "High",
        "steps": [
            TestStepArtifact(action="Enter credentials", expected_result="Logged in"),
        ],
        "expected_outcome": "User logged in",
        "given": "A user on the login page",
        "when": "The user clicks the login button",
        "then": "The dashboard is displayed",
        "category": "Functional",
        "component": "Login",
    }
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


def _make_steps():
    """Steps whose text overlaps with typical element names."""
    return [
        ParameterizedStep(keyword="given", pattern="a user on the login page", params=[]),
        ParameterizedStep(keyword="when", pattern="the user clicks the login button", params=[]),
        ParameterizedStep(keyword="then", pattern="the dashboard is displayed", params=[]),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSelectorMapBuiltFromSiteModel:
    """Test that BDDAgent.execute() builds a correct selector_map."""

    def test_selector_map_built_from_site_model(self):
        """Selector map is populated from site_model page elements."""
        agent = BDDAgent()
        site_model = _make_site_model(
            elements=[
                PageElementArtifact(
                    element_type="button",
                    name="Login Button",
                    selector="#login-btn",
                    text="Log In",
                ),
                PageElementArtifact(
                    element_type="input",
                    name="Username Field",
                    selector="input#username",
                    text="",
                ),
            ]
        )
        tc = _make_tc()
        result = agent.execute(
            artifacts={"test_cases": [tc], "site_model": site_model},
            config={"framework": "behave"},
        )
        assert result.success
        assert result.metadata["selectors_injected"] == 2

    def test_empty_site_model_no_crash(self):
        """An empty site model (no pages/elements) must not crash."""
        agent = BDDAgent()
        site_model = SiteModelArtifact(base_url="http://localhost", pages=[])
        tc = _make_tc()
        result = agent.execute(
            artifacts={"test_cases": [tc], "site_model": site_model},
            config={"framework": "behave"},
        )
        assert result.success
        assert result.metadata["selectors_injected"] == 0


class TestFuzzyMatchSelector:
    """Unit tests for StepDefinitionGenerator._fuzzy_match_selector."""

    def test_exact_selector_match(self):
        """Exact lowercased key match returns the selector."""
        selector_map = {"login button": "#login-btn"}
        result = StepDefinitionGenerator._fuzzy_match_selector("login button", selector_map)
        assert result == "#login-btn"

    def test_exact_match_case_insensitive(self):
        selector_map = {"login button": "#login-btn"}
        result = StepDefinitionGenerator._fuzzy_match_selector("Login Button", selector_map)
        assert result == "#login-btn"

    def test_fuzzy_selector_match_substring(self):
        """Substring containment matches: key inside element_name."""
        selector_map = {"login": "#login-btn"}
        result = StepDefinitionGenerator._fuzzy_match_selector(
            "the user clicks the login button", selector_map
        )
        assert result == "#login-btn"

    def test_fuzzy_selector_match_word_overlap(self):
        """Word overlap > 50% should match."""
        selector_map = {"submit order button": "button.submit-order"}
        result = StepDefinitionGenerator._fuzzy_match_selector("submit order", selector_map)
        # "submit" and "order" overlap with "submit", "order", "button" -> 2/3 > 50%
        assert result == "button.submit-order"

    def test_no_match_leaves_placeholder(self):
        """When no fuzzy match is found, return None."""
        selector_map = {"username field": "input#user"}
        result = StepDefinitionGenerator._fuzzy_match_selector(
            "completely unrelated step text", selector_map
        )
        assert result is None

    def test_empty_selector_map_returns_none(self):
        result = StepDefinitionGenerator._fuzzy_match_selector("some step", {})
        assert result is None

    def test_empty_element_name_returns_none(self):
        result = StepDefinitionGenerator._fuzzy_match_selector("", {"login": "#btn"})
        assert result is None


class TestSelectorInjectionInStepDefs:
    """Integration test: selectors appear in generated step def code."""

    def test_selector_injection_in_step_defs(self):
        """When selector_map matches step text, a selector comment is injected."""
        gen = StepDefinitionGenerator(framework="behave")
        steps = _make_steps()
        selector_map = {
            "login button": "#login-btn",
            "login page": "[data-page='login']",
        }

        result = gen.generate(steps, selector_map=selector_map)
        assert len(result) == 1

        content = result[0].content
        # The login button step should have a selector comment
        assert '# Selector: "#login-btn"' in content
        # The login page step should have a selector comment
        assert "# Selector: \"[data-page='login']\"" in content

    def test_no_selector_map_leaves_todos(self):
        """Without a selector_map the TODO placeholders remain untouched."""
        gen = StepDefinitionGenerator(framework="behave")
        steps = _make_steps()

        result = gen.generate(steps, selector_map=None)
        content = result[0].content
        assert "TODO: implement this step" in content
        assert "# Selector:" not in content

    def test_partial_match_only_injects_matched(self):
        """Only steps that fuzzy-match get selector comments."""
        gen = StepDefinitionGenerator(framework="behave")
        steps = _make_steps()
        selector_map = {"login button": "#login-btn"}

        result = gen.generate(steps, selector_map=selector_map)
        content = result[0].content

        # The login button step gets a selector
        assert '# Selector: "#login-btn"' in content
        # Count TODO lines still present (unmatched steps keep theirs)
        todo_count = content.count("TODO: implement this step")
        assert todo_count == 3  # All 3 still have the raise line
