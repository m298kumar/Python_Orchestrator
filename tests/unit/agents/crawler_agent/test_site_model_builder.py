"""
Unit tests for SiteModelBuilder.
"""

from __future__ import annotations

import pytest
from stlc_platform.agents.crawler_agent.site_model_builder import SiteModelBuilder
from stlc_platform.core.contracts import CrawledPageArtifact, PageElementArtifact


@pytest.fixture
def builder() -> SiteModelBuilder:
    return SiteModelBuilder()


def _make_page(
    url: str,
    title: str = "",
    link_hrefs: list | None = None,
) -> CrawledPageArtifact:
    """Helper to build a CrawledPageArtifact with link elements."""
    elements = []
    for href in link_hrefs or []:
        elements.append(
            PageElementArtifact(
                element_type="link",
                name=href,
                selector=f"a[href='{href}']",
                text=href,
                attributes={"href": href},
            )
        )
    return CrawledPageArtifact(url=url, title=title, elements=elements)


class TestBuildModel:
    def test_builds_model_from_pages(self, builder: SiteModelBuilder):
        pages = [
            _make_page("http://localhost/login", "Login"),
            _make_page("http://localhost/dashboard", "Dashboard"),
        ]
        model = builder.build(pages, base_url="http://localhost")
        assert model.base_url == "http://localhost"
        assert len(model.pages) == 2

    def test_deduplicates_by_url(self, builder: SiteModelBuilder):
        pages = [
            _make_page("http://localhost/login", "Login V1"),
            _make_page("http://localhost/login", "Login V2"),  # duplicate
            _make_page("http://localhost/dashboard", "Dashboard"),
        ]
        model = builder.build(pages)
        assert len(model.pages) == 2
        # Keeps first occurrence
        assert model.pages[0].title == "Login V1"

    def test_crawl_timestamp_set(self, builder: SiteModelBuilder):
        pages = [_make_page("http://localhost/home")]
        model = builder.build(pages)
        assert model.crawl_timestamp != ""
        # Should be a valid ISO format string
        assert "T" in model.crawl_timestamp

    def test_base_url_from_parameter(self, builder: SiteModelBuilder):
        pages = [_make_page("http://localhost/home")]
        model = builder.build(pages, base_url="https://myapp.com")
        assert model.base_url == "https://myapp.com"

    def test_base_url_inferred(self, builder: SiteModelBuilder):
        pages = [_make_page("http://example.com/products")]
        model = builder.build(pages)
        assert model.base_url == "http://example.com"

    def test_empty_pages_returns_empty_model(self, builder: SiteModelBuilder):
        model = builder.build([], base_url="http://localhost")
        assert len(model.pages) == 0
        assert model.navigation_graph == {}


class TestNavigationGraph:
    def test_navigation_graph_built(self, builder: SiteModelBuilder):
        pages = [
            _make_page(
                "http://localhost/login",
                link_hrefs=["http://localhost/dashboard"],
            ),
            _make_page(
                "http://localhost/dashboard",
                link_hrefs=["http://localhost/login"],
            ),
        ]
        model = builder.build(pages)
        graph = model.navigation_graph
        assert "http://localhost/dashboard" in graph.get("http://localhost/login", [])
        assert "http://localhost/login" in graph.get("http://localhost/dashboard", [])

    def test_navigation_graph_excludes_external(self, builder: SiteModelBuilder):
        pages = [
            _make_page(
                "http://localhost/home",
                link_hrefs=[
                    "http://localhost/about",
                    "https://external-site.com/help",
                ],
            ),
            _make_page("http://localhost/about"),
        ]
        model = builder.build(pages)
        graph = model.navigation_graph
        home_links = graph.get("http://localhost/home", [])
        assert "http://localhost/about" in home_links
        assert "https://external-site.com/help" not in home_links
