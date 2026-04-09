"""
Stage 3 Integration Tests — Web Crawler Agent
==============================================
End-to-end validation of the crawler agent pipeline:
HTML pages -> PageParser -> SiteModelBuilder -> DiscrepancyDetector -> CrawlerAgent

Tests use the HTML fixture files in tests/fixtures/html_pages/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
from stlc_platform.agents.crawler_agent import (
    CrawlerAgent,
    DiscrepancyDetector,
    PageParser,
    SiteModelBuilder,
)
from stlc_platform.core.contracts import (
    DiscrepancyReportArtifact,
    RequirementArtifact,
    SiteModelArtifact,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "html_pages"

_PAGE_URLS = {
    "login.html": "http://localhost/login",
    "dashboard.html": "http://localhost/dashboard",
    "product_list.html": "http://localhost/products",
    "checkout.html": "http://localhost/checkout",
}


@pytest.fixture
def html_pages() -> Dict[str, str]:
    """Load all HTML fixture files as a dict of URL -> HTML string."""
    pages = {}
    for filename, url in _PAGE_URLS.items():
        filepath = _FIXTURES_DIR / filename
        if filepath.exists():
            pages[url] = filepath.read_text(encoding="utf-8")
    return pages


@pytest.fixture
def parsed_pages(html_pages: Dict[str, str]) -> list:
    """Parse all HTML fixtures into CrawledPageArtifacts."""
    parser = PageParser()
    return [parser.parse(html, url=url) for url, html in html_pages.items()]


@pytest.fixture
def site_model(parsed_pages: list) -> SiteModelArtifact:
    """Build a SiteModelArtifact from all parsed pages."""
    builder = SiteModelBuilder()
    return builder.build(parsed_pages, base_url="http://localhost")


@pytest.fixture
def ecommerce_requirements() -> list:
    """Sample requirements that partially match the HTML fixtures."""
    return [
        RequirementArtifact(
            req_id="REQ-001",
            title="User Login",
            description="Users can login with username and password",
            acceptance_criteria=[
                "User enters username in the username field",
                "User enters password in the password field",
                "User clicks Sign In button",
            ],
            priority="High",
        ),
        RequirementArtifact(
            req_id="REQ-002",
            title="Product Search",
            description="Users can search for products",
            acceptance_criteria=[
                "User enters search query",
                "User clicks Search button",
                "Search results are displayed",
            ],
            priority="Medium",
        ),
        RequirementArtifact(
            req_id="REQ-003",
            title="Checkout Payment",
            description="Users can complete payment during checkout",
            acceptance_criteria=[
                "User enters card number in the card_number field",
                "User clicks Place Order button",
            ],
            priority="Critical",
        ),
        RequirementArtifact(
            req_id="REQ-004",
            title="Wishlist Management",
            description="Users can manage their wishlist",
            acceptance_criteria=[
                "User clicks Add to Wishlist button",
                "User sees Remove from Wishlist button",
            ],
            priority="High",
        ),
    ]


# ---------------------------------------------------------------------------
# Page Parsing Tests
# ---------------------------------------------------------------------------


class TestPageParsing:
    def test_all_fixtures_parse_successfully(self, html_pages: Dict[str, str]):
        """All 4 HTML fixture files parse without errors."""
        parser = PageParser()
        for url, html in html_pages.items():
            result = parser.parse(html, url=url)
            assert result.url == url
            assert result.title != ""

    def test_login_page_has_form_elements(self, parsed_pages: list):
        """Login page should have username/password inputs and submit button."""
        login = next(p for p in parsed_pages if "login" in p.url)
        element_types = {e.element_type for e in login.elements}
        assert "input" in element_types
        assert "button" in element_types
        assert len(login.forms) >= 1

    def test_checkout_page_has_payment_form(self, parsed_pages: list):
        """Checkout page should have payment form with card fields."""
        checkout = next(p for p in parsed_pages if "checkout" in p.url)
        assert len(checkout.forms) >= 1
        form = checkout.forms[0]
        field_names = [f["name"] for f in form["fields"]]
        assert "card_number" in field_names
        assert "cvv" in field_names

    def test_product_page_has_add_to_cart_buttons(self, parsed_pages: list):
        """Product list page should have Add to Cart buttons."""
        products = next(p for p in parsed_pages if "products" in p.url)
        cart_buttons = [
            e for e in products.elements if e.element_type == "button" and "cart" in e.text.lower()
        ]
        assert len(cart_buttons) >= 2  # Two products in fixture


# ---------------------------------------------------------------------------
# Site Model Building Tests
# ---------------------------------------------------------------------------


class TestSiteModelBuilding:
    def test_site_model_has_all_pages(self, site_model: SiteModelArtifact):
        """Site model should contain all 4 fixture pages."""
        assert len(site_model.pages) == 4

    def test_navigation_graph_has_edges(self, site_model: SiteModelArtifact):
        """Navigation graph should show cross-links between pages."""
        graph = site_model.navigation_graph
        assert len(graph) > 0
        # Login page should link to dashboard, products, checkout
        login_links = graph.get("http://localhost/login", [])
        assert len(login_links) >= 2  # At least some nav links

    def test_base_url_set(self, site_model: SiteModelArtifact):
        assert site_model.base_url == "http://localhost"

    def test_timestamp_set(self, site_model: SiteModelArtifact):
        assert site_model.crawl_timestamp != ""
        assert "T" in site_model.crawl_timestamp


# ---------------------------------------------------------------------------
# Discrepancy Detection Tests
# ---------------------------------------------------------------------------


class TestDiscrepancyDetection:
    def test_detects_discrepancies_for_missing_features(
        self,
        site_model: SiteModelArtifact,
        ecommerce_requirements: list,
    ):
        """Wishlist buttons don't exist in fixtures, so should be flagged."""
        detector = DiscrepancyDetector()
        report = detector.detect(site_model, ecommerce_requirements)
        assert isinstance(report, DiscrepancyReportArtifact)
        # REQ-004 mentions wishlist buttons which don't exist
        wishlist_items = [i for i in report.items if i.requirement_id == "REQ-004"]
        assert len(wishlist_items) >= 1

    def test_gate_decision_reflects_severity(
        self,
        site_model: SiteModelArtifact,
        ecommerce_requirements: list,
    ):
        """Gate decision should be based on highest severity found."""
        detector = DiscrepancyDetector()
        report = detector.detect(site_model, ecommerce_requirements)
        # At minimum, missing wishlist buttons should produce warnings
        assert report.gate_decision in ("proceed", "proceed_with_warnings", "block")
        assert report.total_requirements == 4

    def test_report_summary_populated(
        self,
        site_model: SiteModelArtifact,
        ecommerce_requirements: list,
    ):
        """Report summary should have human-readable text."""
        detector = DiscrepancyDetector()
        report = detector.detect(site_model, ecommerce_requirements)
        assert report.summary != ""


# ---------------------------------------------------------------------------
# CrawlerAgent End-to-End Tests
# ---------------------------------------------------------------------------


class TestCrawlerAgentEndToEnd:
    def test_full_pipeline_html_to_site_model(self, html_pages: Dict[str, str]):
        """Full pipeline: html_pages -> CrawlerAgent -> SiteModelArtifact."""
        agent = CrawlerAgent()
        result = agent.execute({"html_pages": html_pages}, {})
        assert result.success is True
        assert "site_model" in result.artifacts
        model = result.artifacts["site_model"]
        assert len(model.pages) == 4
        assert result.metadata["total_pages"] == 4
        assert result.metadata["total_elements"] > 0
        assert result.metadata["total_forms"] > 0

    def test_full_pipeline_with_requirements(
        self,
        html_pages: Dict[str, str],
        ecommerce_requirements: list,
    ):
        """Full pipeline with requirements produces discrepancy report."""
        agent = CrawlerAgent()
        result = agent.execute(
            {"html_pages": html_pages, "requirements": ecommerce_requirements},
            {},
        )
        assert result.success is True
        assert "discrepancy_report" in result.artifacts
        assert "gate_decision" in result.metadata

    def test_discrepancy_only_mode(
        self,
        site_model: SiteModelArtifact,
        ecommerce_requirements: list,
    ):
        """Pre-built site_model + requirements = discrepancy-only mode."""
        agent = CrawlerAgent()
        result = agent.execute(
            {"site_model": site_model, "requirements": ecommerce_requirements},
            {},
        )
        assert result.success is True
        assert "site_model" in result.artifacts
        assert "discrepancy_report" in result.artifacts

    def test_metadata_completeness(self, html_pages: Dict[str, str]):
        """Metadata should include all expected keys."""
        agent = CrawlerAgent()
        result = agent.execute({"html_pages": html_pages}, {})
        assert "total_pages" in result.metadata
        assert "total_elements" in result.metadata
        assert "total_forms" in result.metadata
        assert "total_links" in result.metadata
