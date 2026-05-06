"""
Crawler Agent
=============
BaseAgent implementation that wires up the PageParser, SiteModelBuilder,
and DiscrepancyDetector to produce site model artifacts from raw HTML pages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from stlc_platform.agents.crawler_agent.discrepancy_detector import DiscrepancyDetector
from stlc_platform.agents.crawler_agent.dynamic_crawler import (
    DynamicCrawler,
    is_playwright_available,
)
from stlc_platform.agents.crawler_agent.page_parser import PageParser
from stlc_platform.agents.crawler_agent.site_model_builder import SiteModelBuilder
from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.contracts import SiteModelArtifact

logger = logging.getLogger(__name__)


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

        self._validate_input_source(artifacts, errors, warnings)

        requirements = artifacts.get("requirements")
        if requirements is not None and not isinstance(requirements, list):
            errors.append("'requirements' must be a list of RequirementArtifact.")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_input_source(
        self, artifacts: Dict[str, Any], errors: List[str], warnings: List[str]
    ) -> None:
        """Validate that exactly one usable input source is present."""
        base_url = artifacts.get("base_url")
        html_pages = artifacts.get("html_pages")
        site_model = artifacts.get("site_model")

        if site_model is not None:
            if not isinstance(site_model, SiteModelArtifact):
                errors.append("'site_model' must be a SiteModelArtifact instance.")
        elif base_url is not None:
            # base_url is valid with or without Playwright:
            # DynamicCrawler (Playwright) when available, SimpleHTTPCrawler otherwise.
            self._validate_base_url(base_url, errors, warnings)
            if not is_playwright_available():
                warnings.append(
                    "Playwright is not installed — using SimpleHTTPCrawler (static HTML only, "
                    "no JavaScript rendering). Install Playwright for full dynamic crawling: "
                    "pip install playwright && playwright install chromium"
                )
        elif html_pages is not None:
            self._validate_html_pages(html_pages, errors, warnings)
        else:
            errors.append(
                "'base_url' (str), 'html_pages' (Dict[str, str]), or "
                "'site_model' (SiteModelArtifact) is required."
            )

    def _validate_base_url(self, base_url: Any, errors: List[str], warnings: List[str]) -> None:
        """Validate the base_url input."""
        if not isinstance(base_url, str) or not base_url.startswith("http"):
            errors.append("'base_url' must be a valid HTTP/HTTPS URL.")

    def _validate_html_pages(self, html_pages: Any, errors: List[str], warnings: List[str]) -> None:
        """Validate the html_pages input."""
        if not isinstance(html_pages, dict):
            errors.append("'html_pages' must be a dict mapping URL to HTML string.")
        elif len(html_pages) == 0:
            errors.append("'html_pages' must not be empty.")
        elif len(html_pages) == 1:
            warnings.append("Only 1 page provided. Site model will have minimal coverage.")

    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
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

        # Crawler settings live under the nested "crawler" key in stlc_config.yaml;
        # fall back to top-level for backwards-compat with direct config dicts.
        crawler_cfg = config.get("crawler", config)
        max_pages = int(crawler_cfg.get("max_pages", 100))

        try:
            site_model = artifacts.get("site_model")

            if site_model is None:
                site_model = self._build_site_model(artifacts, config, max_pages)
                if site_model is None:
                    return AgentResult(
                        success=False,
                        errors=["No base_url or html_pages provided — cannot build site model."],
                    )

            # Fail fast when no pages were crawled so the optional stage is cleanly
            # skipped rather than completing with an empty (and misleading) site model.
            if len(site_model.pages) == 0:
                base_url = getattr(site_model, "base_url", None) or artifacts.get("base_url", "")
                return AgentResult(
                    success=False,
                    errors=[
                        f"Crawler found no pages at '{base_url}'. "
                        "The application may be unavailable, require authentication, "
                        "or have blocked the crawler via robots.txt. "
                        "Stage is unavailable — configure base_url or provide html_pages."
                    ],
                )

            # Optionally run discrepancy detection
            discrepancy_report = self._run_discrepancy_detection(
                site_model, artifacts.get("requirements")
            )

            result_artifacts, metadata = self._compile_results(
                site_model, discrepancy_report, validation
            )

            return AgentResult(
                success=True,
                artifacts=result_artifacts,
                metadata=metadata,
            )

        except (ValueError, TypeError, KeyError, OSError) as e:
            return AgentResult(
                success=False,
                errors=[f"Crawler agent failed: {type(e).__name__}: {e}"],
            )

    def _build_site_model(
        self, artifacts: Dict[str, Any], config: Dict[str, Any], max_pages: int
    ) -> Any:
        """Build a SiteModelArtifact from base_url or html_pages.

        Crawl mode priority:
          1. DynamicCrawler (Playwright)  — base_url + Playwright installed
          2. SimpleHTTPCrawler (requests) — base_url + Playwright absent
          3. Static PageParser            — html_pages dict provided
        """
        base_url_input = artifacts.get("base_url")
        crawler_cfg = config.get("crawler", config)

        if base_url_input:
            if is_playwright_available():
                try:
                    return self._dynamic_crawl(base_url_input, config, max_pages)
                except Exception as exc:
                    # Chromium binary missing or launch failed — fall back to HTTP crawler
                    logger.warning(
                        "DynamicCrawler failed (%s) — falling back to SimpleHTTPCrawler for %s",
                        exc,
                        base_url_input,
                    )
            else:
                logger.warning(
                    "Playwright unavailable — falling back to SimpleHTTPCrawler for %s",
                    base_url_input,
                )
            return self._simple_http_crawl(base_url_input, crawler_cfg, max_pages)

        # Static parsing from pre-fetched html_pages dict
        html_pages = artifacts.get("html_pages", {})
        if not html_pages:
            return None

        parser = PageParser()
        builder = SiteModelBuilder()
        parsed_pages = [
            parser.parse(html, url=url) for url, html in list(html_pages.items())[:max_pages]
        ]
        base_url = crawler_cfg.get("base_url", config.get("base_url", ""))
        return builder.build(parsed_pages, base_url=base_url)

    def _simple_http_crawl(
        self, base_url: str, crawler_cfg: Dict[str, Any], max_pages: int
    ) -> Any:
        """Perform a requests-based HTTP crawl and return a SiteModelArtifact."""
        from stlc_platform.agents.crawler_agent.simple_http_crawler import SimpleHTTPCrawler

        auth_raw = crawler_cfg.get("auth", {}) or {}
        auth = auth_raw if isinstance(auth_raw, dict) and any(auth_raw.values()) else None

        # verify_ssl=False bypasses Windows CRL revocation checks
        # (CRYPT_E_NO_REVOCATION_CHECK) — configure via crawler.verify_ssl in stlc_config.yaml
        verify_ssl = bool(crawler_cfg.get("verify_ssl", True))

        crawler = SimpleHTTPCrawler(
            base_url=base_url,
            max_depth=int(crawler_cfg.get("max_depth", 3)),
            max_pages=max_pages,
            rate_limit_ms=int(crawler_cfg.get("rate_limit_ms", 1000)),
            respect_robots_txt=bool(crawler_cfg.get("respect_robots_txt", True)),
            auth=auth,
            verify_ssl=verify_ssl,
        )
        crawl_result = crawler.crawl()
        builder = SiteModelBuilder()
        return builder.build(crawl_result.pages, base_url=base_url)

    def _dynamic_crawl(self, base_url_input: str, config: Dict[str, Any], max_pages: int) -> Any:
        """Perform a dynamic Playwright crawl and return a SiteModelArtifact."""
        crawler_cfg = config.get("crawler", config)
        auth_raw = crawler_cfg.get("auth", config.get("auth_config")) or {}
        auth_config = auth_raw if isinstance(auth_raw, dict) and any(auth_raw.values()) else None
        crawler = DynamicCrawler(
            base_url=base_url_input,
            max_depth=int(crawler_cfg.get("max_depth", 3)),
            max_pages=max_pages,
            headless=bool(crawler_cfg.get("headless", True)),
            wait_for_idle=bool(crawler_cfg.get("wait_for_network_idle", True)),
            capture_screenshots=bool(crawler_cfg.get("capture_screenshots", False)),
            timeout_ms=int(crawler_cfg.get("rate_limit_ms", 30000)),
            auth_config=auth_config,
        )
        crawl_result = crawler.crawl()

        builder = SiteModelBuilder()
        site_model = builder.build(crawl_result.pages, base_url=base_url_input)

        if crawl_result.captured_requests:
            config["_captured_requests"] = crawl_result.captured_requests
        return site_model

    def _run_discrepancy_detection(self, site_model: Any, requirements: Any) -> Any:
        """Run discrepancy detection if requirements are provided."""
        if not requirements:
            return None
        detector = DiscrepancyDetector()
        report = detector.detect(site_model, requirements)
        site_model.discrepancies = report
        return report

    def _compile_results(self, site_model: Any, discrepancy_report: Any, validation: Any) -> tuple:
        """Compile result artifacts and metadata."""
        total_elements = sum(len(p.elements) for p in site_model.pages)
        total_forms = sum(len(p.forms) for p in site_model.pages)
        total_links = sum(
            len([e for e in p.elements if e.element_type == "link"]) for p in site_model.pages
        )

        result_artifacts: Dict[str, Any] = {"site_model": site_model}
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

        metadata["chromadb_embedded"] = self._try_embed_chromadb(site_model)
        return result_artifacts, metadata

    def _try_embed_chromadb(self, site_model: Any) -> bool:
        """Attempt to embed site model into ChromaDB (non-fatal)."""
        try:
            from stlc_platform.agents.crawler_agent.embedding_store import (
                CrawlerEmbeddingStore,
            )

            store = CrawlerEmbeddingStore()
            doc_count = store.embed_site_model(site_model)
            logger.info("Embedded %d pages into ChromaDB", doc_count)
            return doc_count > 0
        except ImportError:
            logger.debug("ChromaDB not available — skipping page embedding")
        except Exception as exc:
            logger.warning("ChromaDB embedding failed (non-fatal): %s", exc)
        return False

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
