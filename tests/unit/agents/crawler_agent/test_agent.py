"""
Unit tests for CrawlerAgent.
"""

from __future__ import annotations

import pytest
from stlc_platform.agents.crawler_agent.agent import CrawlerAgent
from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    RequirementArtifact,
    SiteModelArtifact,
)


@pytest.fixture
def agent() -> CrawlerAgent:
    return CrawlerAgent()


SIMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello</h1>
  <input type="text" name="query" placeholder="Search">
  <button id="search-btn">Search</button>
  <a href="/about">About</a>
  <form action="/search" method="GET">
    <input type="text" name="q">
  </form>
</body>
</html>
"""

LOGIN_HTML = """
<html>
<head><title>Login</title></head>
<body>
  <form action="/api/login" method="POST">
    <input type="text" name="username">
    <input type="password" name="password">
    <button type="submit">Sign In</button>
  </form>
</body>
</html>
"""


class TestValidateInput:
    def test_valid_html_pages_input(self, agent: CrawlerAgent):
        result = agent.validate_input({"html_pages": {"http://localhost/": SIMPLE_HTML}})
        assert result.valid is True

    def test_valid_site_model_input(self, agent: CrawlerAgent):
        model = SiteModelArtifact(base_url="http://localhost")
        result = agent.validate_input({"site_model": model})
        assert result.valid is True

    def test_missing_both_inputs(self, agent: CrawlerAgent):
        result = agent.validate_input({})
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_html_pages_not_dict(self, agent: CrawlerAgent):
        result = agent.validate_input({"html_pages": "not a dict"})
        assert result.valid is False

    def test_empty_html_pages(self, agent: CrawlerAgent):
        result = agent.validate_input({"html_pages": {}})
        assert result.valid is False

    def test_single_page_warning(self, agent: CrawlerAgent):
        result = agent.validate_input({"html_pages": {"http://localhost/": SIMPLE_HTML}})
        assert result.valid is True
        assert len(result.warnings) >= 1  # "minimal coverage" warning


class TestExecute:
    def test_parse_and_build_from_html(self, agent: CrawlerAgent):
        result = agent.execute(
            {"html_pages": {"http://localhost/": SIMPLE_HTML}},
            {},
        )
        assert result.success is True
        site_model = result.artifacts["site_model"]
        assert isinstance(site_model, SiteModelArtifact)
        assert len(site_model.pages) == 1
        assert site_model.pages[0].title == "Test Page"

    def test_multiple_pages(self, agent: CrawlerAgent):
        result = agent.execute(
            {
                "html_pages": {
                    "http://localhost/home": SIMPLE_HTML,
                    "http://localhost/login": LOGIN_HTML,
                }
            },
            {},
        )
        assert result.success is True
        assert result.metadata["total_pages"] == 2

    def test_discrepancy_detection_with_requirements(self, agent: CrawlerAgent):
        reqs = [
            RequirementArtifact(
                req_id="REQ-001",
                title="Login",
                description="User can login with credentials",
                acceptance_criteria=["User enters credentials and clicks Sign In button"],
                priority="High",
            )
        ]
        result = agent.execute(
            {
                "html_pages": {"http://localhost/login": LOGIN_HTML},
                "requirements": reqs,
            },
            {},
        )
        assert result.success is True
        assert "discrepancy_report" in result.artifacts
        assert "gate_decision" in result.metadata

    def test_invalid_input_returns_failure(self, agent: CrawlerAgent):
        result = agent.execute({}, {})
        assert result.success is False
        assert len(result.errors) > 0

    def test_max_pages_config_respected(self, agent: CrawlerAgent):
        pages = {f"http://localhost/page{i}": SIMPLE_HTML for i in range(10)}
        result = agent.execute(
            {"html_pages": pages},
            {"max_pages": 3},
        )
        assert result.success is True
        assert result.metadata["total_pages"] == 3

    def test_site_model_input_discrepancy_only(self, agent: CrawlerAgent):
        """Pre-built site_model + requirements = discrepancy-only mode."""
        model = SiteModelArtifact(
            base_url="http://localhost",
            pages=[
                CrawledPageArtifact(
                    url="http://localhost/login",
                    title="Login",
                    elements=[
                        PageElementArtifact(
                            element_type="button",
                            name="login",
                            selector="#login-btn",
                            text="Login",
                        )
                    ],
                )
            ],
        )
        reqs = [
            RequirementArtifact(
                req_id="REQ-001",
                title="Login",
                description="User can login",
                acceptance_criteria=["User clicks Login button"],
            )
        ]
        result = agent.execute(
            {"site_model": model, "requirements": reqs},
            {},
        )
        assert result.success is True
        assert "site_model" in result.artifacts


class TestGetCapabilities:
    def test_capabilities_agent_id(self, agent: CrawlerAgent):
        caps = agent.get_capabilities()
        assert caps.agent_id == "web_crawler"

    def test_capabilities_output_types(self, agent: CrawlerAgent):
        caps = agent.get_capabilities()
        assert "SiteModelArtifact" in caps.output_types
        assert "DiscrepancyReportArtifact" in caps.output_types
