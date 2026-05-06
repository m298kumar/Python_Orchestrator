"""
Unit tests for PageParser.
"""

from __future__ import annotations

import pytest
from stlc_platform.agents.crawler_agent.page_parser import PageParser


@pytest.fixture
def parser() -> PageParser:
    return PageParser()


# ---------------------------------------------------------------------------
# Simple HTML snippets for focused tests
# ---------------------------------------------------------------------------

TITLE_HTML = "<html><head><title>My Page</title></head><body></body></html>"
INPUT_HTML = '<input type="text" id="email" name="email" placeholder="Enter email">'
BUTTON_HTML = '<button type="submit" data-testid="submit-btn">Submit</button>'
LINK_HTML = '<a href="/about">About Us</a>'
FORM_HTML = """
<form action="/login" method="POST">
  <input type="text" name="user" required>
  <input type="password" name="pass">
  <input type="hidden" name="csrf" value="abc123">
  <input type="submit" value="Login">
</form>
"""
SELECTOR_ID_HTML = '<button id="save-btn">Save</button>'
SELECTOR_TESTID_HTML = '<button data-testid="cancel-btn">Cancel</button>'
SELECTOR_NAME_HTML = '<input name="search_query">'
SELECTOR_CLASS_HTML = '<div class="action-btn clickable">Click</div>'


class TestParseTitle:
    def test_extracts_title(self, parser: PageParser):
        result = parser.parse(TITLE_HTML, url="http://example.com")
        assert result.title == "My Page"

    def test_empty_html_returns_empty_title(self, parser: PageParser):
        result = parser.parse("", url="")
        assert result.title == ""
        assert result.elements == []
        assert result.forms == []


class TestExtractElements:
    def test_extracts_inputs(self, parser: PageParser):
        result = parser.parse(f"<html><body>{INPUT_HTML}</body></html>")
        inputs = [e for e in result.elements if e.element_type == "input"]
        assert len(inputs) == 1
        assert inputs[0].name == "email"

    def test_extracts_buttons(self, parser: PageParser):
        result = parser.parse(f"<html><body>{BUTTON_HTML}</body></html>")
        buttons = [e for e in result.elements if e.element_type == "button"]
        assert len(buttons) == 1
        assert buttons[0].text == "Submit"

    def test_extracts_links(self, parser: PageParser):
        result = parser.parse(f"<html><body>{LINK_HTML}</body></html>")
        links = [e for e in result.elements if e.element_type == "link"]
        assert len(links) == 1
        assert links[0].text == "About Us"

    def test_extracts_select(self, parser: PageParser):
        html = '<select name="country"><option>US</option></select>'
        result = parser.parse(f"<html><body>{html}</body></html>")
        selects = [e for e in result.elements if e.element_type == "select"]
        assert len(selects) == 1


class TestSelectorPriority:
    def test_id_highest_priority(self, parser: PageParser):
        result = parser.parse(f"<html><body>{SELECTOR_ID_HTML}</body></html>")
        btn = [e for e in result.elements if e.element_type == "button"][0]
        assert btn.selector == "#save-btn"

    def test_data_testid_second_priority(self, parser: PageParser):
        result = parser.parse(f"<html><body>{SELECTOR_TESTID_HTML}</body></html>")
        btn = [e for e in result.elements if e.element_type == "button"][0]
        assert btn.selector == '[data-testid="cancel-btn"]'

    def test_name_third_priority(self, parser: PageParser):
        result = parser.parse(f"<html><body>{SELECTOR_NAME_HTML}</body></html>")
        inp = [e for e in result.elements if e.element_type == "input"][0]
        assert inp.selector == 'input[name="search_query"]'

    def test_class_fallback(self, parser: PageParser):
        # div is not in our standard tag map, but test the selector builder
        # via a tag we do extract (e.g., button with only a class)
        html = '<button class="primary-action">Go</button>'
        result = parser.parse(f"<html><body>{html}</body></html>")
        btn = [e for e in result.elements if e.element_type == "button"][0]
        assert btn.selector == ".primary-action"


class TestFormExtraction:
    def test_extracts_form_structure(self, parser: PageParser):
        result = parser.parse(f"<html><body>{FORM_HTML}</body></html>")
        assert len(result.forms) == 1
        form = result.forms[0]
        assert form["action"] == "/login"
        assert form["method"] == "POST"
        # hidden and submit fields should be excluded
        field_names = [f["name"] for f in form["fields"]]
        assert "user" in field_names
        assert "pass" in field_names
        assert "csrf" not in field_names  # hidden excluded


class TestFullPageParsing:
    def test_login_page_fixture(self, parser: PageParser):
        """Parse the login.html fixture and verify key elements."""
        from pathlib import Path

        fixture_path = (
            Path(__file__).resolve().parents[3] / "fixtures" / "html_pages" / "login.html"
        )
        html = fixture_path.read_text(encoding="utf-8")
        result = parser.parse(html, url="http://localhost/login")

        assert result.title == "Login - MyApp"
        assert len(result.forms) == 1
        assert result.forms[0]["method"] == "POST"

        # Should have username, password inputs and submit button
        element_types = [e.element_type for e in result.elements]
        assert "input" in element_types
        assert "button" in element_types
        assert "link" in element_types
