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

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from stlc_platform.core.contracts import CrawledPageArtifact, PageElementArtifact

logger = logging.getLogger(__name__)

# Check Playwright availability at import time (pip package only)
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def is_playwright_available() -> bool:
    """Return True if the playwright pip package is importable."""
    return _PLAYWRIGHT_AVAILABLE


def is_playwright_ready() -> bool:
    """
    Return True if playwright is installed AND the Chromium binary file exists on disk.

    This is a stricter check than ``is_playwright_available()``:
    the pip package might be installed without the browser binary
    (which requires a separate ``playwright install chromium`` step).

    Note: ``p.chromium.executable_path`` only returns the *expected* path string
    without verifying the file exists — we must check ``os.path.isfile()`` explicitly.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe_path = p.chromium.executable_path
        return os.path.isfile(exe_path)
    except Exception:
        return False


def _ensure_chromium() -> None:
    """
    Auto-install the Chromium browser binary if the playwright package is
    installed but the binary has not been downloaded yet.

    Runs ``playwright install chromium`` as a subprocess.  One-time cost
    (~200 MB download); subsequent calls return immediately once the binary
    is present.

    Raises:
        ImportError: If playwright package is not installed, or if the
            auto-install subprocess fails.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        raise ImportError(
            "Playwright is not installed — dynamic crawling unavailable. "
            "pip install playwright && playwright install chromium"
        )
    if is_playwright_ready():
        return  # Binary already present — nothing to do

    logger.info(
        "Chromium binary not found. Running 'playwright install chromium' "
        "(one-time download ~200 MB)…"
    )
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise ImportError(
            "Playwright chromium browser is not installed — dynamic crawling unavailable. "
            f"Auto-install failed: {result.stderr.strip()}"
        )
    logger.info("Chromium installed successfully.")


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
        # Ensure pip package is installed and Chromium binary is present.
        # Auto-installs Chromium if the package is there but the binary isn't.
        _ensure_chromium()

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

    # Realistic Chrome user-agent — Cloudflare checks this against Sec-CH-UA headers
    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def crawl(self) -> CrawlResult:
        """
        Execute the BFS crawl synchronously.

        Returns a CrawlResult with all discovered pages and captured requests.
        """
        result = CrawlResult()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.headless,
                args=[
                    # Disable the AutomationControlled flag that Cloudflare detects
                    "--disable-blink-features=AutomationControlled",
                    # Suppress the 'Chrome is being controlled by automation' banner
                    "--disable-infobars",
                    # Avoid sandbox issues in some environments
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )
            context = browser.new_context(
                user_agent=self._USER_AGENT,
                viewport={"width": 1280, "height": 800},
                # Mimic real browser locale / timezone
                locale="en-US",
                timezone_id="America/New_York",
                # Disable the webdriver flag via permissions
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )

            # Override navigator.webdriver BEFORE any page navigation.
            # Cloudflare's JS challenge reads this property — setting it to
            # undefined makes the browser indistinguishable from a real user.
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                    configurable: true,
                });
                // Remove Playwright-specific chrome runtime markers
                window.chrome = { runtime: {} };
                // Spoof plugins array (headless has 0, real browsers have some)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)

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
                    new_links = self._visit_page(page, url, result)
                    for link in new_links:
                        if link not in visited:
                            queue.append((link, depth + 1))
                except Exception as e:
                    result.errors.append(f"Error crawling {url}: {e}")

            browser.close()

        return result

    def _visit_page(self, page: Any, url: str, result: CrawlResult) -> List[str]:
        """Visit a single page, extract content, and return discovered links."""
        captured: List[CapturedRequest] = []

        def _response_handler(resp: Any) -> None:
            self._on_response(resp, captured)

        page.on("response", _response_handler)
        try:
            wait_strategy = "networkidle" if self.wait_for_idle else "domcontentloaded"
            page.goto(url, wait_until=wait_strategy)

            # If Cloudflare served a JS challenge (cf-mitigated header / challenge page),
            # wait for it to resolve and the real page to load.
            if self._is_cloudflare_challenge(page):
                logger.info("Cloudflare challenge detected at %s — waiting for resolution…", url)
                page.wait_for_timeout(6000)   # CF challenges typically resolve in 3–5 s
                # Wait again for network to settle after the redirect
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            page.wait_for_timeout(500)

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
            page_artifact = CrawledPageArtifact(
                url=url,
                title=page.title(),
                elements=self._extract_elements(page),
                forms=self._extract_forms(page),
                api_calls=api_calls,
            )
            result.pages.append(page_artifact)
            result.captured_requests.extend(captured)
            result.pages_visited += 1

            if self.capture_screenshots:
                result.screenshots[url] = page.screenshot()

            return self._extract_links(page, url)
        finally:
            page.remove_listener("response", _response_handler)

    def _is_cloudflare_challenge(self, page: Any) -> bool:
        """Return True if the current page is a Cloudflare bot-challenge page."""
        try:
            title = page.title()
            if "just a moment" in title.lower() or "checking your browser" in title.lower():
                return True
            # Look for the CF challenge form or turnstile widget
            return bool(page.query_selector("#challenge-form, #turnstile-wrapper, .cf-browser-verification"))
        except Exception:
            return False

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

            captured.append(
                CapturedRequest(
                    method=method,
                    url=url,
                    status=status,
                    content_type=content_type,
                    is_api_call=is_api,
                )
            )
        except (AttributeError, TypeError, OSError):
            pass  # Ignore capture errors for non-critical network tracking

    def _extract_elements(self, page: Any) -> List[PageElementArtifact]:
        """Extract interactive elements from the live page via JS evaluation."""
        raw_elements = page.evaluate("""() => {
            const elements = [];
            const selectors = 'input, button, a, select, textarea, [role="button"]';

            function buildCssSelector(el) {
                if (el.id) return '#' + el.id;
                if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                if (el.getAttribute('aria-label'))
                    return `[aria-label="${el.getAttribute('aria-label')}"]`;
                if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/)[0];
                    if (cls) return '.' + cls;
                }
                return el.tagName.toLowerCase();
            }

            function buildXPath(el) {
                const tag = el.tagName.toLowerCase();
                if (el.id) return `//*[@id="${el.id}"]`;
                if (el.dataset.testid) return `//*[@data-testid="${el.dataset.testid}"]`;
                if (el.name) return `//${tag}[@name="${el.name}"]`;
                if (el.getAttribute('aria-label'))
                    return `//*[@aria-label="${el.getAttribute('aria-label')}"]`;
                const text = el.textContent?.trim();
                if (text && text.length <= 40 && ['button','a','label'].includes(tag)) {
                    const safe = text.replace(/"/g, "'");
                    return `//${tag}[normalize-space(.)="${safe}"]`;
                }
                if (el.className && typeof el.className === 'string') {
                    const cls = el.className.trim().split(/\\s+/)[0];
                    if (cls) return `//${tag}[contains(@class,"${cls}")]`;
                }
                return `//${tag}`;
            }

            document.querySelectorAll(selectors).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;  // Skip hidden

                let type = el.tagName.toLowerCase();
                if (type === 'a') type = 'link';
                if (el.getAttribute('role') === 'button') type = 'button';

                elements.push({
                    element_type: type,
                    name: el.name || el.id || el.getAttribute('aria-label') || el.textContent?.trim().substring(0, 50) || '',
                    selector: buildCssSelector(el),
                    xpath: buildXPath(el),
                    text: el.textContent?.trim().substring(0, 200) || el.placeholder || el.value || '',
                    attributes: {
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        href: el.href || '',
                        role: el.getAttribute('role') || '',
                        'data-testid': el.dataset.testid || '',
                        'aria-label': el.getAttribute('aria-label') || '',
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
                xpath=e.get("xpath", ""),
                text=e["text"],
                attributes={k: v for k, v in e.get("attributes", {}).items() if v},
            )
            for e in raw_elements
        ]

    def _extract_forms(self, page: Any) -> List[Dict[str, Any]]:
        """Extract forms from the live page."""
        return list(
            page.evaluate("""() => {
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
        }""")
        )

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
