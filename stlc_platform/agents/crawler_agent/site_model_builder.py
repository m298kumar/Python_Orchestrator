"""
Site Model Builder
==================
Aggregates multiple CrawledPageArtifacts into a single SiteModelArtifact
with navigation graph, deduplication, and timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urljoin, urlparse

from stlc_platform.core.contracts import CrawledPageArtifact, SiteModelArtifact


class SiteModelBuilder:
    """Build a SiteModelArtifact from a list of parsed pages."""

    def build(
        self,
        pages: List[CrawledPageArtifact],
        base_url: str = "",
    ) -> SiteModelArtifact:
        """
        Aggregate pages into a site model.

        Args:
            pages: List of CrawledPageArtifacts (one per page).
            base_url: Explicit base URL. Inferred from first page if empty.

        Returns:
            A SiteModelArtifact with navigation graph and timestamp.
        """
        deduped = self._deduplicate_pages(pages)

        if not base_url and deduped:
            base_url = self._infer_base_url(deduped)

        nav_graph = self._build_navigation_graph(deduped)
        timestamp = datetime.now(timezone.utc).isoformat()

        return SiteModelArtifact(
            base_url=base_url,
            pages=deduped,
            navigation_graph=nav_graph,
            crawl_timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deduplicate_pages(
        self, pages: List[CrawledPageArtifact]
    ) -> List[CrawledPageArtifact]:
        """Remove duplicate pages by URL (keeps first occurrence)."""
        seen: set = set()
        result: List[CrawledPageArtifact] = []
        for page in pages:
            key = page.url.rstrip("/")
            if key not in seen:
                seen.add(key)
                result.append(page)
        return result

    def _build_navigation_graph(
        self, pages: List[CrawledPageArtifact]
    ) -> Dict[str, List[str]]:
        """
        Build an adjacency list of internal page links.

        Only includes links that point to URLs present in the site model.
        """
        # Collect all known page URLs (normalized)
        known_urls: set = set()
        for page in pages:
            known_urls.add(page.url.rstrip("/"))

        graph: Dict[str, List[str]] = {}
        for page in pages:
            page_key = page.url.rstrip("/")
            targets: List[str] = []

            for element in page.elements:
                if element.element_type == "link":
                    href = element.attributes.get("href", "")
                    if not href:
                        continue
                    # Resolve relative hrefs against the page URL
                    resolved = urljoin(page.url, href)
                    href_normalized = resolved.rstrip("/")
                    # Only include internal links (present in site model)
                    if href_normalized in known_urls:
                        if href_normalized not in targets:
                            targets.append(href_normalized)

            graph[page_key] = targets

        return graph

    def _infer_base_url(self, pages: List[CrawledPageArtifact]) -> str:
        """Infer base URL from the first page's URL (scheme + netloc)."""
        if not pages:
            return ""
        parsed = urlparse(pages[0].url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return pages[0].url
