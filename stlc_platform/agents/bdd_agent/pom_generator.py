"""
Page Object Model Generator
============================
Extracts page/screen names from test case components and generates
POM class stubs with locator placeholders and action methods.

Supports Python (Playwright/Selenium) and Java (Selenium) output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Set

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    TestCaseArtifact,
)

# -- Paths --
_BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"
_DEFAULT_OVERRIDES = (
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "prompt_overrides" / "bdd"
)


@dataclass
class PageObjectStub:
    """A generated Page Object Model class stub."""

    page_name: str
    class_name: str
    filename: str
    language: str
    content: str
    locator_count: int = 0
    action_count: int = 0


@dataclass
class PageInfo:
    """Intermediate representation of a page extracted from test cases."""

    name: str
    class_name: str
    elements: List[Dict[str, str]] = field(default_factory=list)
    actions: List[Dict[str, str]] = field(default_factory=list)


class POMGenerator:
    """
    Generates Page Object Model class stubs from test case components.

    Workflow:
      1. Extract page/screen names from TestCaseArtifact.component fields
      2. Extract actions from step text (Given/When/Then)
      3. Optionally merge real selectors from CrawledPageArtifact
      4. Render POM class stubs via Jinja2 templates

    Supported output:
      - Python (Playwright or Selenium)
      - Java (Selenium)
    """

    SUPPORTED_LANGUAGES: ClassVar[List[str]] = ["python", "java"]

    def __init__(
        self,
        language: str = "python",
        automation_lib: str = "playwright",
        template_dir: Optional[Path] = None,
        override_dir: Optional[Path] = None,
    ):
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: '{language}'. Supported: {self.SUPPORTED_LANGUAGES}"
            )
        self.language = language
        self.automation_lib = automation_lib

        loaders = []
        override = override_dir or _DEFAULT_OVERRIDES
        if override.is_dir():
            loaders.append(FileSystemLoader(str(override)))
        builtin = template_dir or _BUILTIN_TEMPLATES
        loaders.append(FileSystemLoader(str(builtin)))

        self._env = Environment(
            loader=ChoiceLoader(loaders),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate(
        self,
        test_cases: List[TestCaseArtifact],
        crawled_pages: Optional[List[CrawledPageArtifact]] = None,
    ) -> List[PageObjectStub]:
        """
        Generate POM stubs from test cases, optionally enriched with
        crawled page selectors.

        Args:
            test_cases: Test case artifacts with component fields.
            crawled_pages: Optional crawled pages for real selector data.

        Returns:
            List of PageObjectStub, one per discovered page/component.
        """
        # Step 1: Extract pages from test case components
        pages = self._extract_pages(test_cases)

        # Step 2: Merge crawled selectors if available
        if crawled_pages:
            self._merge_crawled_selectors(pages, crawled_pages)

        # Step 3: Render templates
        results = []
        for page_info in pages.values():
            stub = self._render_page(page_info)
            results.append(stub)

        return results

    def _extract_pages(self, test_cases: List[TestCaseArtifact]) -> Dict[str, PageInfo]:
        """Extract page names and actions from test case components and steps."""
        pages: Dict[str, PageInfo] = {}

        for tc in test_cases:
            page = self._get_or_create_page(pages, tc)
            self._collect_actions(page, tc)
            self._collect_elements(page, tc)

        return pages

    def _get_or_create_page(self, pages: Dict[str, PageInfo], tc: TestCaseArtifact) -> PageInfo:
        """Resolve the page for a test case, creating it if needed."""
        component = tc.component.strip() if tc.component else ""
        if not component:
            component = self._infer_page_from_text(tc.title)
        if not component:
            component = "BasePage"

        page_key = self._normalize_name(component)
        if page_key not in pages:
            class_name = self._to_class_name(component)
            pages[page_key] = PageInfo(name=component, class_name=class_name)
        return pages[page_key]

    def _collect_actions(self, page: PageInfo, tc: TestCaseArtifact) -> None:
        """Extract and deduplicate actions from test case GWT steps."""
        for step_text in [tc.given, tc.when, tc.then]:
            if not step_text:
                continue
            existing = {a["name"] for a in page.actions}
            for action in self._extract_actions(step_text):
                if action not in existing:
                    page.actions.append(
                        {
                            "name": action,
                            "method_name": self._to_method_name(action),
                        }
                    )
                    existing.add(action)

    def _collect_elements(self, page: PageInfo, tc: TestCaseArtifact) -> None:
        """Extract and deduplicate elements from test case GWT steps."""
        for step_text in [tc.given, tc.when, tc.then]:
            if not step_text:
                continue
            existing_names = {e["name"] for e in page.elements}
            for elem in self._extract_elements(step_text):
                if elem["name"] not in existing_names:
                    page.elements.append(elem)
                    existing_names.add(elem["name"])

    def _merge_crawled_selectors(
        self,
        pages: Dict[str, PageInfo],
        crawled_pages: List[CrawledPageArtifact],
    ) -> None:
        """Merge real selectors from crawled pages into POM page info."""
        selector_lookup = self._build_selector_lookup(crawled_pages)

        # Merge into page elements
        for page in pages.values():
            for element in page.elements:
                elem_name = element["name"].lower().strip()
                if element.get("selector", "").startswith("TODO"):
                    if elem_name in selector_lookup:
                        element["selector"] = selector_lookup[elem_name]

    def _build_selector_lookup(self, crawled_pages: List[CrawledPageArtifact]) -> Dict[str, str]:
        """Build a lookup mapping element name/text to CSS selector."""
        lookup: Dict[str, str] = {}
        for cp in crawled_pages:
            for elem in cp.elements:
                self._index_element(lookup, elem)
        return lookup

    def _index_element(self, lookup: Dict[str, str], elem: Any) -> None:
        """Add a single crawled element's name and text to the selector lookup."""
        if isinstance(elem, PageElementArtifact):
            key_name = elem.name.lower().strip() if elem.name else ""
            key_text = elem.text.lower().strip() if elem.text else ""
            selector = elem.selector or ""
        elif isinstance(elem, dict):
            key_name = str(elem.get("name", "")).lower().strip()
            key_text = str(elem.get("text", "")).lower().strip()
            selector = str(elem.get("selector", ""))
        else:
            return
        if key_name and selector:
            lookup[key_name] = selector
        if key_text and selector:
            lookup[key_text] = selector

    def _render_page(self, page_info: PageInfo) -> PageObjectStub:
        """Render a single POM class from page info."""
        if self.language == "java":
            template_name = "pom_java.java.j2"
            ext = ".java"
        else:
            template_name = "pom_python.py.j2"
            ext = ".py"

        template = self._env.get_template(template_name)
        content = template.render(
            page_name=page_info.name,
            class_name=page_info.class_name,
            elements=page_info.elements,
            actions=page_info.actions,
            automation_lib=self.automation_lib,
        )

        filename = self._to_filename(page_info.class_name, ext)

        return PageObjectStub(
            page_name=page_info.name,
            class_name=page_info.class_name,
            filename=filename,
            language=self.language,
            content=content,
            locator_count=len(page_info.elements),
            action_count=len(page_info.actions),
        )

    # -- Extraction helpers --

    _ACTION_VERBS = re.compile(
        r"\b(click|tap|enter|type|select|check|uncheck|toggle|submit|"
        r"navigate|scroll|drag|drop|hover|upload|download|open|close|"
        r"press|clear|fill|search|filter|sort|expand|collapse)\b",
        re.IGNORECASE,
    )

    _ELEMENT_PATTERNS = re.compile(
        r"\b(button|link|input|field|dropdown|checkbox|radio|"
        r"menu|tab|modal|dialog|form|table|header|footer|"
        r"sidebar|navbar|textarea|label|icon|image|card)\b",
        re.IGNORECASE,
    )

    def _extract_actions(self, text: str) -> List[str]:
        """Extract action method names from step text."""
        actions: List[str] = []
        # Find verb + object patterns
        sentences = re.split(r"[,;]|\band\b", text, flags=re.IGNORECASE)
        for sentence in sentences:
            sentence = sentence.strip()
            verb_match = self._ACTION_VERBS.search(sentence)
            if verb_match:
                # Get the rest of the sentence after the verb
                verb = verb_match.group(1).lower()
                rest = sentence[verb_match.end() :].strip()
                # Take first few meaningful words
                words = re.findall(r"[a-zA-Z]+", rest)[:3]
                action = f"{verb}_{'_'.join(words)}" if words else verb
                action = action.lower().strip("_")
                if action and action not in actions:
                    actions.append(action)
        return actions

    def _extract_elements(self, text: str) -> List[Dict[str, str]]:
        """Extract UI element references from step text."""
        elements: List[Dict[str, str]] = []
        seen: Set[str] = set()

        # Look for quoted element names
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
        for q in quoted:
            name = q.strip()
            if name and name.lower() not in seen and len(name) < 50:
                seen.add(name.lower())
                const_name = self._to_constant_name(name)
                elements.append(
                    {
                        "name": name,
                        "const_name": const_name,
                        "selector": f'TODO: "{name}"',
                        "element_type": "element",
                    }
                )

        # Look for element type + name patterns (e.g., "login button", "search field")
        for match in self._ELEMENT_PATTERNS.finditer(text):
            elem_type = match.group(1).lower()
            # Get preceding word(s) as the element name
            before = text[: match.start()].strip().split()
            if before:
                name_word = before[-1]
                full_name = f"{name_word}_{elem_type}"
                if full_name.lower() not in seen:
                    seen.add(full_name.lower())
                    const_name = self._to_constant_name(full_name)
                    elements.append(
                        {
                            "name": full_name,
                            "const_name": const_name,
                            "selector": f'TODO: "{full_name}"',
                            "element_type": elem_type,
                        }
                    )

        return elements

    def _infer_page_from_text(self, text: str) -> str:
        """Try to infer a page name from test case title."""
        page_words = re.findall(
            r"\b(\w+)\s+(?:page|screen|view|form|dialog|modal|panel)\b",
            text,
            re.IGNORECASE,
        )
        if page_words:
            return f"{page_words[0].title()} Page"
        return ""

    # -- Name conversion helpers --

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for use as a dict key."""
        return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()

    def _to_class_name(self, name: str) -> str:
        """Convert a name to PascalCase class name."""
        words = re.findall(r"[a-zA-Z0-9]+", name)
        pascal = "".join(w.capitalize() for w in words)
        if not pascal.endswith("Page"):
            pascal += "Page"
        return pascal

    def _to_method_name(self, action: str) -> str:
        """Convert an action description to a method name."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", action).strip("_").lower()
        if len(slug) > 50:
            slug = slug[:50].rstrip("_")
        return slug or "perform_action"

    def _to_constant_name(self, name: str) -> str:
        """Convert to UPPER_SNAKE_CASE for locator constants."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").upper()
        return slug or "ELEMENT"

    def _to_filename(self, class_name: str, ext: str) -> str:
        """Convert class name to a filename."""
        # PascalCase -> snake_case
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        return f"{snake}{ext}"
