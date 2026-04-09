"""Tests for Dynamic Crawler module.

Since Playwright may not be installed in the test environment, these tests
focus on the non-browser components: module imports, graceful fallback,
data structures, and URL normalization.
"""

import pytest
from stlc_platform.agents.crawler_agent.dynamic_crawler import (
    CapturedRequest,
    CrawlResult,
    is_playwright_available,
)


class TestGracefulFallback:
    def test_is_playwright_available_returns_bool(self):
        result = is_playwright_available()
        assert isinstance(result, bool)

    def test_import_without_playwright_does_not_crash(self):
        """Module should import cleanly even without Playwright."""
        from stlc_platform.agents.crawler_agent import dynamic_crawler

        assert hasattr(dynamic_crawler, "DynamicCrawler")
        assert hasattr(dynamic_crawler, "is_playwright_available")

    def test_dynamic_crawler_raises_without_playwright(self):
        """Instantiation should raise ImportError if Playwright is not installed."""
        if is_playwright_available():
            pytest.skip("Playwright is installed; cannot test fallback")

        from stlc_platform.agents.crawler_agent.dynamic_crawler import DynamicCrawler

        with pytest.raises(ImportError, match="Playwright is required"):
            DynamicCrawler(base_url="https://example.com")


class TestDataStructures:
    def test_captured_request_defaults(self):
        req = CapturedRequest(method="GET", url="https://example.com/api/test")
        assert req.method == "GET"
        assert req.status == 0
        assert req.content_type == ""
        assert req.is_api_call is False

    def test_captured_request_api_call(self):
        req = CapturedRequest(
            method="POST",
            url="https://example.com/api/users",
            status=201,
            content_type="application/json",
            is_api_call=True,
        )
        assert req.is_api_call is True
        assert req.status == 201

    def test_crawl_result_defaults(self):
        result = CrawlResult()
        assert result.pages == []
        assert result.captured_requests == []
        assert result.screenshots == {}
        assert result.errors == []
        assert result.pages_visited == 0
        assert result.pages_skipped == 0

    def test_crawl_result_accumulation(self):
        result = CrawlResult()
        result.pages_visited = 5
        result.pages_skipped = 2
        result.errors.append("timeout on page X")
        assert result.pages_visited == 5
        assert len(result.errors) == 1


class TestCrawlerAgentIntegration:
    def test_crawler_agent_accepts_base_url(self):
        """CrawlerAgent.validate_input should accept base_url when Playwright is available."""
        if not is_playwright_available():
            pytest.skip("Playwright is not installed")

        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent

        agent = CrawlerAgent()
        result = agent.validate_input({"base_url": "https://example.com"})
        assert result.valid is True

    def test_crawler_agent_errors_without_playwright(self):
        """CrawlerAgent should error (not warn) when base_url given but Playwright absent."""
        if is_playwright_available():
            pytest.skip("Playwright is installed")

        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent

        agent = CrawlerAgent()
        result = agent.validate_input({"base_url": "https://example.com"})
        assert result.valid is False
        assert len(result.errors) > 0
        assert "Playwright" in result.errors[0]

    def test_crawler_agent_rejects_invalid_url(self):
        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent

        agent = CrawlerAgent()
        result = agent.validate_input({"base_url": "not-a-url"})
        assert result.valid is False

    def test_crawler_agent_still_supports_html_pages(self):
        from stlc_platform.agents.crawler_agent.agent import CrawlerAgent

        agent = CrawlerAgent()
        result = agent.validate_input({"html_pages": {"/login": "<html><body>Login</body></html>"}})
        assert result.valid is True
