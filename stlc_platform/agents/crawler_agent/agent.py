"""
Crawler Agent
=============
BaseAgent implementation that wires up the PageParser, SiteModelBuilder,
and DiscrepancyDetector to produce site model artifacts from raw HTML pages.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.agents.crawler_agent.page_parser import PageParser
from stlc_platform.agents.crawler_agent.site_model_builder import SiteModelBuilder
from stlc_platform.agents.crawler_agent.discrepancy_detector import DiscrepancyDetector
from stlc_platform.agents.crawler_agent.dynamic_crawler import (
    DynamicCrawler,
    is_playwright_available,
)
from stlc_platform.core.contracts import SiteModelArtifact


class CrawlerAgent(BaseAgent):
    """
    Agent that parses HTML pages into a structured site model and optionally
    detects discrepancies against requirements.

    Lifecycle:
      1. validate_input() -- check for html_pages or site_model
      2. execute() -- parse pages, build model, detect discrepancies
      3. get_capabilities() -- describe input/output types

    Input modes:
      - base_url: str (dynamic Playwright crawl — requires Playwright installed)
      - html_pages: Dict[str, str] mapping URL -> HTML string (static parsing)
      - site_model: SiteModelArtifact (discrepancy-only mode)

    Optional input:
      - requirements: List[RequirementArtifact] (triggers discrepancy detection)

    Config keys:
      - max_pages: int (default: 100) -- limit how many pages to parse
      - max_depth: int (default: 3) -- max link depth for dynamic crawl
      - headless: bool (default: True) -- browser visibility
      - capture_screenshots: bool (default: False) -- save screenshots
      - auth_config: dict -- authentication configuration for dynamic crawl
    """

    agent_id: str = "web_crawler"
    agent_version: str = "1.0.0"

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """Validate that input contains html_pages or site_model."""
        errors: List[str] = []
        warnings: List[str] = []

        base_url = artifacts.get("base_url")
        html_pages = artifacts.get("html_pages")
        site_model = artifacts.get("site_model")

        if base_url is None and html_pages is None and site_model is None:
            errors.append(
                "'base_url' (str), 'html_pages' (Dict[str, str]), or "
                "'site_model' (SiteModelArtifact) is required."
            )
        elif base_url is not None:
            if not isinstance(base_url, str) or not base_url.startswith("http"):
                errors.append("'base_url' must be a valid HTTP/HTTPS URL.")
            elif not is_playwright_available():
                warnings.append(
                    "Playwright not installed. Dynamic crawling unavailable. "
                    "Install with: pip install playwright && playwright install chromium"
                )
        elif html_pages is not None:
            if not isinstance(html_pages, dict):
                errors.append("'html_pages' must be a dict mapping URL to HTML string.")
            elif len(html_pages) == 0:
                errors.append("'html_pages' must not be empty.")
            else:
                if len(html_pages) == 1:
                    warnings.append(
                        "Only 1 page provided. Site model will have minimal coverage."
                    )
        elif site_model is not None:
            if not isinstance(site_model, SiteModelArtifact):
                errors.append("'site_model' must be a SiteModelArtifact instance.")

        # Check requirements (optional)
        requirements = artifacts.get("requirements")
        if requirements is not None and not isinstance(requirements, list):
            errors.append("'requirements' must be a list of RequirementArtifact.")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        """
        Parse HTML pages into a site model and optionally detect discrepancies.

        Args:
            artifacts: Must contain "html_pages" or "site_model".
                       Optionally contains "requirements".
            config: Optional overrides (max_pages).

        Returns:
            AgentResult with site_model and optionally discrepancy_report.
        """
        # Validate
        validation = self.validate_input(artifacts)
        if not validation.valid:
            return AgentResult(
                success=False,
                errors=validation.errors,
            )

        max_pages = config.get("max_pages", 100)

        try:
            site_model = artifacts.get("site_model")

            if site_model is None:
                base_url_input = artifacts.get("base_url")

                if base_url_input and is_playwright_available():
                    # Dynamic crawl mode (Playwright)
                    max_depth = config.get("max_depth", 3)
                    crawler = DynamicCrawler(
                        base_url=base_url_input,
                        max_depth=max_depth,
                        max_pages=max_pages,
                        headless=config.get("headless", True),
                        capture_screenshots=config.get("capture_screenshots", False),
                        auth_config=config.get("auth_config"),
                    )
                    crawl_result = crawler.crawl()

                    # Build site model from crawled pages
                    builder = SiteModelBuilder()
                    site_model = builder.build(
                        crawl_result.pages, base_url=base_url_input
                    )

                    # Store captured API requests in metadata for cross-layer use
                    if crawl_result.captured_requests:
                        config["_captured_requests"] = crawl_result.captured_requests
                else:
                    # Static parsing mode (BeautifulSoup)
                    html_pages = artifacts.get("html_pages", {})
                    if not html_pages:
                        return AgentResult(
                            success=False,
                            errors=["No html_pages provided and dynamic crawl unavailable."],
                        )
                    parser = PageParser()
                    builder = SiteModelBuilder()

                    parsed_pages = []
                    for url, html in list(html_pages.items())[:max_pages]:
                        page = parser.parse(html, url=url)
                        parsed_pages.append(page)

                    base_url = config.get("base_url", "")
                    site_model = builder.build(parsed_pages, base_url=base_url)

            # Optionally run discrepancy detection
            requirements = artifacts.get("requirements")
            discrepancy_report = None
            if requirements:
                detector = DiscrepancyDetector()
                discrepancy_report = detector.detect(site_model, requirements)
                site_model.discrepancies = discrepancy_report

            # Compute metadata
            total_elements = sum(len(p.elements) for p in site_model.pages)
            total_forms = sum(len(p.forms) for p in site_model.pages)
            total_links = sum(
                len([e for e in p.elements if e.element_type == "link"])
                for p in site_model.pages
            )

            result_artifacts: Dict[str, Any] = {
                "site_model": site_model,
            }
            if discrepancy_report:
                result_artifacts["discrepancy_report"] = discrepancy_report

            metadata: Dict[str, Any] = {
                "total_pages": len(site_model.pages),
                "total_elements": total_elements,
                "total_forms": total_forms,
                "total_links": total_links,
            }
            if discrepancy_report:
                metadata["total_discrepancies"] = discrepancy_report.total_discrepancies
                metadata["gate_decision"] = discrepancy_report.gate_decision

            if validation.warnings:
                metadata["validation_warnings"] = validation.warnings

            return AgentResult(
                success=True,
                artifacts=result_artifacts,
                metadata=metadata,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                errors=[f"Crawler agent failed: {e}"],
            )

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["base_url", "html_pages", "SiteModelArtifact", "RequirementArtifact"],
            output_types=[
                "SiteModelArtifact",
                "CrawledPageArtifact",
                "DiscrepancyReportArtifact",
            ],
            description=(
                "Crawls web applications (dynamic via Playwright or static via "
                "BeautifulSoup) into a structured site model with elements, "
                "forms, API calls, and navigation graph. Optionally detects "
                "discrepancies between the site model and requirements."
            ),
            required_skills=["coding_standards"],
            default_model_tier="lightweight",
        )
