"""
Page Parser
============
Parses a single HTML string into a CrawledPageArtifact using BeautifulSoup.
Extracts elements (inputs, buttons, links, forms, etc.), generates CSS
selectors, and collects outbound links for navigation graph building.

Uses the stdlib ``html.parser`` backend -- zero native dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from stlc_platform.core.contracts import CrawledPageArtifact, PageElementArtifact


# Element types we care about and their HTML tag mappings
_TAG_TYPE_MAP: Dict[str, str] = {
    "input": "input",
    "button": "button",
    "a": "link",
    "select": "select",
    "textarea": "textarea",
    "img": "image",
}

# Additional selectors for interactive elements
_EXTRA_SELECTORS = [
    '[role="button"]',
    '[type="submit"]',
]

# Link schemes to exclude
_EXCLUDED_SCHEMES = {"javascript", "mailto", "tel", "data"}


class PageParser:
    """Parse raw HTML into structured page artifacts."""

    def parse(self, html: str, url: str = "") -> CrawledPageArtifact:
        """
        Parse an HTML string into a CrawledPageArtifact.

        Args:
            html: Raw HTML content.
            url: The URL this page was fetched from (for link normalization).

        Returns:
            A fully populated CrawledPageArtifact.
        """
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

        elements = self._extract_elements(soup)
        forms = self._extract_forms(soup)

        return CrawledPageArtifact(
            url=url,
            title=title,
            elements=elements,
            forms=forms,
            api_calls=[],
        )

    # ------------------------------------------------------------------
    # Element extraction
    # ------------------------------------------------------------------

    def _extract_elements(self, soup: BeautifulSoup) -> List[PageElementArtifact]:
        """Extract all interactive/visible elements from the page."""
        elements: List[PageElementArtifact] = []
        seen_keys: set = set()

        # Standard tags
        for tag_name, element_type in _TAG_TYPE_MAP.items():
            for tag in soup.find_all(tag_name):
                elem = self._tag_to_element(tag, element_type)
                if elem:
                    # Deduplicate by composite key (type + selector + name + text)
                    key = (elem.element_type, elem.selector, elem.name, elem.text)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        elements.append(elem)

        # Extra selectors (role="button", type="submit" on non-button tags)
        for css_sel in _EXTRA_SELECTORS:
            for tag in soup.select(css_sel):
                tag_name_lower = tag.name.lower() if tag.name else ""
                # Skip if already captured via standard tag map
                if tag_name_lower in _TAG_TYPE_MAP:
                    continue
                elem = self._tag_to_element(tag, "button")
                if elem:
                    key = (elem.element_type, elem.selector, elem.name, elem.text)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        elements.append(elem)

        return elements

    def _tag_to_element(
        self, tag: Tag, element_type: str
    ) -> Optional[PageElementArtifact]:
        """Convert a BS4 Tag to a PageElementArtifact."""
        if not isinstance(tag, Tag):
            return None

        selector = self._build_selector(tag)
        name = self._get_element_name(tag)
        text = self._get_element_text(tag)

        # Collect interesting attributes
        attrs: Dict[str, str] = {}
        for attr_name in ("type", "placeholder", "value", "href", "src",
                          "action", "method", "role", "aria-label",
                          "data-testid", "required"):
            val = tag.get(attr_name)
            if val:
                attrs[attr_name] = str(val) if not isinstance(val, list) else " ".join(val)

        return PageElementArtifact(
            element_type=element_type,
            name=name,
            selector=selector,
            text=text,
            attributes=attrs,
        )

    # ------------------------------------------------------------------
    # CSS selector generation
    # ------------------------------------------------------------------

    def _build_selector(self, tag: Tag) -> str:
        """
        Build the most specific CSS selector for a tag.

        Priority: #id > [data-testid] > [name] > .class > tag
        """
        # 1. id
        tag_id = tag.get("id")
        if tag_id:
            return f"#{tag_id}"

        # 2. data-testid
        testid = tag.get("data-testid")
        if testid:
            return f'[data-testid="{testid}"]'

        # 3. name attribute
        name = tag.get("name")
        if name:
            tag_name = tag.name or "input"
            return f'{tag_name}[name="{name}"]'

        # 4. class (use first non-empty class)
        classes = tag.get("class")
        if classes and isinstance(classes, list):
            # Filter out empty strings
            non_empty = [c for c in classes if c.strip()]
            if non_empty:
                return f".{non_empty[0]}"

        # 5. Fallback: tag name
        return tag.name or "unknown"

    # ------------------------------------------------------------------
    # Form extraction
    # ------------------------------------------------------------------

    def _extract_forms(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract all forms with their fields."""
        forms: List[Dict[str, Any]] = []

        for form_tag in soup.find_all("form"):
            action = form_tag.get("action", "")
            method = str(form_tag.get("method") or "GET").upper()

            fields: List[Dict[str, str]] = []
            for field_tag in form_tag.find_all(["input", "select", "textarea"]):
                field_name = str(field_tag.get("name", ""))
                field_type = str(field_tag.get("type", "text"))
                if field_tag.name == "select":
                    field_type = "select"
                elif field_tag.name == "textarea":
                    field_type = "textarea"

                required = "required" in field_tag.attrs or field_tag.get("required") is not None

                # Skip hidden fields and submit buttons from field list
                if field_type in ("hidden", "submit"):
                    continue

                fields.append({
                    "name": field_name,
                    "type": field_type,
                    "required": str(required).lower(),
                })

            forms.append({
                "action": str(action),
                "method": method,
                "fields": fields,
            })

        return forms

    # ------------------------------------------------------------------
    # Link extraction
    # ------------------------------------------------------------------

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract and normalize all outbound links.

        Filters out javascript:, mailto:, tel:, and anchor-only (#) links.
        Converts relative URLs to absolute using base_url.
        Deduplicates.
        """
        links: List[str] = []
        seen: set = set()

        for a_tag in soup.find_all("a", href=True):
            href = str(a_tag["href"]).strip()

            # Skip empty, anchor-only, and excluded schemes
            if not href or href.startswith("#"):
                continue

            parsed = urlparse(href)
            if parsed.scheme.lower() in _EXCLUDED_SCHEMES:
                continue

            # Normalize relative URLs
            if base_url and not parsed.scheme:
                href = urljoin(base_url, href)

            if href not in seen:
                seen.add(href)
                links.append(href)

        return links

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _get_element_text(self, tag: Tag) -> str:
        """Get visible text of an element, truncated to 200 chars."""
        text = tag.get_text(strip=True)
        if not text:
            # Fallback to placeholder or value for inputs
            text = str(tag.get("placeholder", "") or tag.get("value", ""))
        if isinstance(text, list):
            text = " ".join(text)
        return str(text)[:200]

    def _get_element_name(self, tag: Tag) -> str:
        """
        Derive a human-readable name for the element.

        Priority: name attr > id > aria-label > text content
        """
        name = tag.get("name", "")
        if name:
            return str(name)

        tag_id = tag.get("id", "")
        if tag_id:
            return str(tag_id)

        aria = tag.get("aria-label", "")
        if aria:
            return str(aria)

        # Fallback to text content
        text = tag.get_text(strip=True)
        if text:
            return str(text)[:50]

        return ""
