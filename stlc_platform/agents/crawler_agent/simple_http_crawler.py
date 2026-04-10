"""
Simple HTTP Crawler
===================
A lightweight, requests-based fallback crawler for when Playwright is unavailable.

Performs BFS crawl using ``requests`` + ``BeautifulSoup`` to fetch and parse HTML
pages. Produces the same ``CrawlResult`` dataclass as ``DynamicCrawler`` so it
is a drop-in fallback for the crawler agent.

Limitations vs DynamicCrawler:
  - No JavaScript execution (static HTML only)
  - No network request capture (XHR/Fetch)
  - No screenshots

Features:
  - BFS link traversal up to max_depth / max_pages
  - Rate limiting (rate_limit_ms)
  - robots.txt respect (urllib.robotparser)
  - Per-page error handling (logs warning, continues crawl)
  - Same-origin link filtering
  - Basic HTTP auth support
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from stlc_platform.agents.crawler_agent.dynamic_crawler import CrawlResult
from stlc_platform.agents.crawler_agent.page_parser import PageParser

logger = logging.getLogger(__name__)

_CRAWL_USER_AGENT = "STLC-Crawler/1.0 (SimpleHTTPCrawler; +https://github.com/stlc)"


class SimpleHTTPCrawler:
    """
    Requests-based BFS web crawler.

    Mirrors the ``DynamicCrawler`` interface and returns the same
    ``CrawlResult`` dataclass, allowing the crawler agent to use it as a
    transparent fallback when Playwright is not installed.

    Args:
        base_url: Starting URL for the crawl.
        max_depth: Maximum link depth from base URL (default: 3).
        max_pages: Maximum total pages to crawl (default: 100).
        rate_limit_ms: Milliseconds to wait between requests (default: 1000).
        respect_robots_txt: Honour the site's robots.txt (default: True).
        auth: Optional dict with keys ``username`` and ``password`` for HTTP
              Basic auth, or ``type``/``login_url`` for session cookie auth
              (form-based login not supported in this crawler — ignored).
        timeout_s: Per-request timeout in seconds (default: 30).
    """

    def __init__(
        self,
        base_url: str,
        max_depth: int = 3,
        max_pages: int = 100,
        rate_limit_ms: int = 1000,
        respect_robots_txt: bool = True,
        auth: Optional[Dict[str, Any]] = None,
        timeout_s: int = 30,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit_s = rate_limit_ms / 1000.0
        self.respect_robots_txt = respect_robots_txt
        self.auth = auth or {}
        self.timeout_s = timeout_s
        self.verify_ssl = verify_ssl

        parsed = urlparse(self.base_url)
        self._origin = f"{parsed.scheme}://{parsed.netloc}"

        self._robot_parser: Optional[RobotFileParser] = None
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self) -> CrawlResult:
        """
        BFS crawl from base_url up to max_depth / max_pages.

        Returns:
            CrawlResult with pages list populated.
        """
        result = CrawlResult()
        parser = PageParser()

        if self.respect_robots_txt:
            self._load_robots_txt()

        visited: Set[str] = set()
        # Queue entries: (url, depth)
        queue: deque[tuple[str, int]] = deque([(self.base_url, 0)])

        while queue and result.pages_visited < self.max_pages:
            url, depth = queue.popleft()
            norm_url = self._normalise(url)

            if norm_url in visited:
                result.pages_skipped += 1
                continue
            if not self._is_same_origin(norm_url):
                result.pages_skipped += 1
                continue
            if self.respect_robots_txt and not self._robots_allows(norm_url):
                logger.debug("robots.txt disallows %s — skipping", norm_url)
                result.pages_skipped += 1
                continue

            visited.add(norm_url)

            html = self._fetch(norm_url, result)
            if html is None:
                continue  # error already recorded

            page = parser.parse(html, url=norm_url)
            result.pages.append(page)
            result.pages_visited += 1

            logger.debug(
                "SimpleHTTPCrawler: fetched %s (depth=%d, pages=%d/%d)",
                norm_url, depth, result.pages_visited, self.max_pages,
            )

            # Enqueue outgoing links if within depth limit
            if depth < self.max_depth:
                for link_url in self._extract_links(html, norm_url):
                    norm_link = self._normalise(link_url)
                    if norm_link not in visited and self._is_same_origin(norm_link):
                        queue.append((norm_link, depth + 1))

            # Rate limiting
            if self.rate_limit_s > 0:
                time.sleep(self.rate_limit_s)

        logger.info(
            "SimpleHTTPCrawler finished: %d pages visited, %d skipped",
            result.pages_visited, result.pages_skipped,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_session(self):
        """Build a requests.Session with auth and headers."""
        try:
            import requests
        except ImportError as exc:
            raise ImportError(
                "The 'requests' package is required for SimpleHTTPCrawler. "
                "Install it with: pip install requests"
            ) from exc

        session = requests.Session()
        session.headers.update({"User-Agent": _CRAWL_USER_AGENT})
        session.verify = self.verify_ssl

        if not self.verify_ssl:
            # Suppress the InsecureRequestWarning that urllib3 emits when
            # verify=False — users have explicitly opted in via config.
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

        # HTTP Basic auth
        username = self.auth.get("username", "")
        password = self.auth.get("password", "")
        if username and password:
            session.auth = (username, password)

        return session

    def _load_robots_txt(self) -> None:
        """Fetch and parse robots.txt for the target origin."""
        robots_url = f"{self._origin}/robots.txt"
        try:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            self._robot_parser = rp
            logger.debug("Loaded robots.txt from %s", robots_url)
        except Exception as exc:
            logger.debug("Could not load robots.txt (%s): %s", robots_url, exc)
            self._robot_parser = None

    def _robots_allows(self, url: str) -> bool:
        """Return True if robots.txt allows crawling this URL."""
        if self._robot_parser is None:
            return True
        return self._robot_parser.can_fetch(_CRAWL_USER_AGENT, url)

    def _fetch(self, url: str, result: CrawlResult) -> Optional[str]:
        """
        GET a URL and return the response HTML.

        Records error in result.errors on failure and returns None.
        """
        try:
            response = self._session.get(url, timeout=self.timeout_s, allow_redirects=True)
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                logger.debug("Skipping non-HTML response at %s (%s)", url, content_type)
                result.pages_skipped += 1
                return None
            response.raise_for_status()
            return response.text
        except Exception as exc:
            msg = f"Failed to fetch {url}: {exc}"
            logger.warning(msg)
            result.errors.append(msg)
            return None

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all <a href> links from HTML and resolve relative URLs."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        soup = BeautifulSoup(html, "html.parser")
        links: List[str] = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            # Strip fragment
            absolute = absolute.split("#")[0]
            if absolute:
                links.append(absolute)
        return links

    def _normalise(self, url: str) -> str:
        """Strip trailing slash and fragment for dedup."""
        return url.rstrip("/").split("#")[0]

    def _is_same_origin(self, url: str) -> bool:
        """Return True if url belongs to the same origin as base_url."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}" == self._origin
