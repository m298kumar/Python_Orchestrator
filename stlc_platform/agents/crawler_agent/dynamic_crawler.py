"""
Dynamic Crawler
===============
Headless browser-based web crawler using Playwright for crawling dynamic
(SPA) and static web applications.

Features:
  - BFS crawl from base URL with configurable max_depth
  - Captures XHR/Fetch network requests (method, URL, status, content-type)
  - Waits for network idle (SPA-friendly)
  - Optional screenshot per page
  - Authentication support (form-based login flow)
  - Graceful fallback: if Playwright is not installed, raises ImportError
    with instructions

Dependencies:
  - playwright (optional): ``pip install playwright && playwright install chromium``

Usage:
    crawler = DynamicCrawler(base_url="https://example.com", max_depth=3)
    result = await crawler.crawl()  # returns CrawlResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from stlc_platform.core.contracts import CrawledPageArtifact, PageElementArtifact

# Check Playwright availability at import time
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def is_playwright_available() -> bool:
    """Check if Playwright is installed and available."""
    return _PLAYWRIGHT_AVAILABLE


@dataclass
class CapturedRequest:
    """A network request captured during page load."""

    method: str
    url: str
    status: int = 0
    content_type: str = ""
    request_body: Optional[str] = None
    is_api_call: bool = False


@dataclass
class CrawlResult:
    """Result of a dynamic crawl session."""

    pages: List[CrawledPageArtifact] = field(default_factory=list)
    captured_requests: List[CapturedRequest] = field(default_factory=list)
    screenshots: Dict[str, bytes] = field(default_factory=dict)  # url -> png bytes
    errors: List[str] = field(default_factory=list)
    pages_visited: int = 0
    pages_skipped: int = 0


class DynamicCrawler:
    """
    Headless Chromium crawler using Playwright.

    Performs BFS crawl from base_url, extracting page elements,
    capturing API calls, and building CrawledPageArtifacts.

    Args:
        base_url: Starting URL for the crawl.
        max_depth: Maximum link depth from base URL (default: 3).
        max_pages: Maximum total pages to crawl (default: 50).
        headless: Run browser in headless mode (default: True).
        wait_for_idle: Wait for network idle after navigation (default: True).
        capture_screenshots: Take a screenshot of each page (default: False).
        timeout_ms: Navigation timeout in milliseconds (default: 30000).
        auth_config: Optional auth configuration dict with keys:
            - login_url: URL of the login page
            - username_selector: CSS selector for username field
            - password_selector: CSS selector for password field
            - submit_selector: CSS selector for submit button
            - username: Username value
            - password: Password value
    """

    def __init__(
        self,
        base_url: str,
        max_depth: int = 3,
        max_pages: int = 50,
        headless: bool = True,
        wait_for_idle: bool = True,
        capture_screenshots: bool = False,
        timeout_ms: int = 30000,
        auth_config: Optional[Dict[str, str]] = None,
    ):
        if not _PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is required for dynamic crawling. Install it with:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self.base_url = base_url.rstrip("/")
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.headless = headless
        self.wait_for_idle = wait_for_idle
        self.capture_screenshots = capture_screenshots
        self.timeout_ms = timeout_ms
        self.auth_config = auth_config

        # Parse base URL for same-origin filtering
        parsed = urlparse(self.base_url)
        self._base_origin = f"{parsed.scheme}://{parsed.netloc}"

    def crawl(self) -> CrawlResult:
        """
        Execute the BFS crawl synchronously.

        Returns a CrawlResult with all discovered pages and captured requests.
        """
        result = CrawlResult()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            # Perform authentication if configured
            if self.auth_config:
                self._authenticate(page)

            # BFS crawl
            visited: Set[str] = set()
            queue: List[tuple] = [(self.base_url, 0)]  # (url, depth)

            while queue and len(visited) < self.max_pages:
                url, depth = queue.pop(0)

                # Normalize URL
                url = self._normalize_url(url)

                # Skip if already visited or exceeds depth
                if url in visited or depth > self.max_depth:
                    result.pages_skipped += 1
                    continue

                # Skip non-same-origin URLs
                if not url.startswith(self._base_origin):
                    result.pages_skipped += 1
                    continue

                visited.add(url)

                try:
                    # Set up request interception with a named handler
                    # so we can properly remove it later (lambdas can't be removed by identity)
                    captured: List[CapturedRequest] = []

                    def _response_handler(resp: Any) -> None:
                        self._on_response(resp, captured)

                    page.on("response", _response_handler)

                    try:
                        # Navigate
                        if self.wait_for_idle:
                            page.goto(url, wait_until="networkidle")
                        else:
                            page.goto(url, wait_until="domcontentloaded")

                        # Wait a bit for any remaining async ops
                        page.wait_for_timeout(500)

                        # Extract page content
                        title = page.title()

                        # Extract elements via page evaluation
                        elements = self._extract_elements(page)

                        # Extract forms
                        forms = self._extract_forms(page)

                        # Build API calls from captured requests
                        api_calls = [
                            {
                                "method": r.method,
                                "url": r.url,
                                "status": r.status,
                                "content_type": r.content_type,
                            }
                            for r in captured
                            if r.is_api_call
                        ]

                        # Create artifact
                        page_artifact = CrawledPageArtifact(
                            url=url,
                            title=title,
                            elements=elements,
                            forms=forms,
                            api_calls=api_calls,
                        )
                        result.pages.append(page_artifact)
                        result.captured_requests.extend(captured)
                        result.pages_visited += 1

                        # Screenshot
                        if self.capture_screenshots:
                            result.screenshots[url] = page.screenshot()

                        # Discover links for BFS
                        links = self._extract_links(page, url)
                        for link in links:
                            if link not in visited:
                                queue.append((link, depth + 1))
                    finally:
                        # Remove the exact handler reference to avoid listener leak
                        page.remove_listener("response", _response_handler)

                except Exception as e:
                    result.errors.append(f"Error crawling {url}: {e}")

            browser.close()

        return result

    def _authenticate(self, page: Any) -> None:
        """Perform form-based login."""
        cfg = self.auth_config
        if not cfg:
            return

        login_url = cfg.get("login_url", f"{self.base_url}/login")
        page.goto(login_url)

        username_sel = cfg.get("username_selector", "#username")
        password_sel = cfg.get("password_selector", "#password")
        submit_sel = cfg.get("submit_selector", 'button[type="submit"]')

        page.fill(username_sel, cfg.get("username", ""))
        page.fill(password_sel, cfg.get("password", ""))
        page.click(submit_sel)

        # Wait for navigation after login
        page.wait_for_load_state("networkidle")

    def _on_response(self, response: Any, captured: List[CapturedRequest]) -> None:
        """Capture network responses, identifying API calls."""
        try:
            url = response.url
            method = response.request.method
            status = response.status
            content_type = response.headers.get("content-type", "")

            # Identify API calls (JSON responses, not static assets)
            is_api = (
                "application/json" in content_type
                or "application/xml" in content_type
                or "/api/" in url
                or "/graphql" in url
            )

            captured.append(CapturedRequest(
                method=method,
                url=url,
                status=status,
                content_type=content_type,
                is_api_call=is_api,
            ))
        except (AttributeError, TypeError, OSError):
            pass  # Ignore capture errors for non-critical network tracking

    def _extract_elements(self, page: Any) -> List[PageElementArtifact]:
        """Extract interactive elements from the live page via JS evaluation."""
        raw_elements = page.evaluate("""() => {
            const elements = [];
            const selectors = 'input, button, a, select, textarea, [role="button"]';

            document.querySelectorAll(selectors).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;  // Skip hidden

                let type = el.tagName.toLowerCase();
                if (type === 'a') type = 'link';
                if (el.getAttribute('role') === 'button') type = 'button';

                // Build best selector
                let selector = el.tagName.toLowerCase();
                if (el.id) selector = '#' + el.id;
                else if (el.dataset.testid) selector = `[data-testid="${el.dataset.testid}"]`;
                else if (el.name) selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                else if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/)[0];
                    if (cls) selector = '.' + cls;
                }

                elements.push({
                    element_type: type,
                    name: el.name || el.id || el.getAttribute('aria-label') || el.textContent?.trim().substring(0, 50) || '',
                    selector: selector,
                    text: el.textContent?.trim().substring(0, 200) || el.placeholder || el.value || '',
                    attributes: {
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        href: el.href || '',
                        role: el.getAttribute('role') || '',
                    }
                });
            });
            return elements;
        }""")

        return [
            PageElementArtifact(
                element_type=e["element_type"],
                name=e["name"],
                selector=e["selector"],
                text=e["text"],
                attributes={k: v for k, v in e.get("attributes", {}).items() if v},
            )
            for e in raw_elements
        ]

    def _extract_forms(self, page: Any) -> List[Dict[str, Any]]:
        """Extract forms from the live page."""
        return list(page.evaluate("""() => {
            const forms = [];
            document.querySelectorAll('form').forEach(form => {
                const fields = [];
                form.querySelectorAll('input, select, textarea').forEach(field => {
                    const ftype = field.type || (field.tagName === 'SELECT' ? 'select' : 'text');
                    if (ftype === 'hidden' || ftype === 'submit') return;
                    fields.push({
                        name: field.name || '',
                        type: ftype,
                        required: field.required ? 'true' : 'false',
                    });
                });
                forms.push({
                    action: form.action || '',
                    method: (form.method || 'GET').toUpperCase(),
                    fields: fields,
                });
            });
            return forms;
        }"""))

    def _extract_links(self, page: Any, current_url: str) -> List[str]:
        """Extract same-origin links from the page."""
        raw_links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href)
                .filter(href => href && !href.startsWith('javascript:')
                        && !href.startsWith('mailto:') && !href.startsWith('#'));
        }""")

        links = []
        for link in raw_links:
            normalized = self._normalize_url(link)
            if normalized.startswith(self._base_origin):
                links.append(normalized)
        return list(set(links))

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes."""
        parsed = urlparse(url)
        # Remove fragment
        normalized = parsed._replace(fragment="").geturl()
        return normalized.rstrip("/") if normalized != self.base_url else normalized
