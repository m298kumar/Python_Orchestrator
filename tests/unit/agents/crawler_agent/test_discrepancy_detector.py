"""
Unit tests for DiscrepancyDetector.
"""

from __future__ import annotations

import pytest

from stlc_platform.agents.crawler_agent.discrepancy_detector import DiscrepancyDetector
from stlc_platform.core.contracts import (
    CrawledPageArtifact,
    PageElementArtifact,
    RequirementArtifact,
    SiteModelArtifact,
)


@pytest.fixture
def detector() -> DiscrepancyDetector:
    return DiscrepancyDetector()


def _make_site_model(
    pages: list | None = None,
) -> SiteModelArtifact:
    """Helper to build a simple SiteModelArtifact."""
    return SiteModelArtifact(
        base_url="http://localhost",
        pages=pages or [],
    )


def _make_page_with_elements(
    url: str = "/login",
    elements: list | None = None,
    forms: list | None = None,
) -> CrawledPageArtifact:
    return CrawledPageArtifact(
        url=url,
        title="Test Page",
        elements=elements or [],
        forms=forms or [],
    )


def _make_requirement(
    req_id: str = "REQ-001",
    title: str = "Login Feature",
    description: str = "",
    acceptance_criteria: list | None = None,
    priority: str = "High",
) -> RequirementArtifact:
    return RequirementArtifact(
        req_id=req_id,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria or [],
        priority=priority,
    )


class TestNoDiscrepancies:
    def test_no_discrepancies_when_all_present(self, detector: DiscrepancyDetector):
        """When referenced elements exist in the site model, report is clean."""
        site = _make_site_model(
            pages=[
                _make_page_with_elements(
                    elements=[
                        PageElementArtifact(
                            element_type="button",
                            name="submit",
                            selector="#submit",
                            text="Submit",
                        ),
                    ],
                    forms=[
                        {
                            "action": "/login",
                            "method": "POST",
                            "fields": [
                                {"name": "username", "type": "text", "required": "true"},
                                {"name": "password", "type": "password", "required": "true"},
                            ],
                        }
                    ],
                )
            ]
        )
        reqs = [
            _make_requirement(
                acceptance_criteria=["The Submit button is visible"],
            )
        ]
        report = detector.detect(site, reqs)
        # "Submit button" -- regex captures "Submit" as name, which exists
        # in our site model elements. So no missing_element discrepancy.
        missing_submit = [
            i for i in report.items
            if i.discrepancy_type == "missing_element"
            and "submit" in i.expected.lower()
        ]
        assert len(missing_submit) == 0


class TestMissingElements:
    def test_detects_missing_button(self, detector: DiscrepancyDetector):
        """AC says 'Submit button' but no submit button in model."""
        site = _make_site_model(
            pages=[_make_page_with_elements(elements=[])]
        )
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks the Checkout button"],
            )
        ]
        report = detector.detect(site, reqs)
        checkout_items = [
            i for i in report.items
            if "checkout" in i.expected.lower() and i.discrepancy_type == "missing_element"
        ]
        assert len(checkout_items) >= 1

    def test_detects_missing_link(self, detector: DiscrepancyDetector):
        """AC says 'forgot password link' but no such link exists."""
        site = _make_site_model(
            pages=[_make_page_with_elements(elements=[])]
        )
        reqs = [
            _make_requirement(
                acceptance_criteria=["User sees forgot password link"],
            )
        ]
        report = detector.detect(site, reqs)
        link_items = [
            i for i in report.items
            if "link" in i.discrepancy_type or "link" in i.expected.lower()
        ]
        assert len(link_items) >= 1


class TestMissingFormFields:
    def test_detects_missing_form_field(self, detector: DiscrepancyDetector):
        """AC references 'email field' but no email field in any form."""
        site = _make_site_model(
            pages=[
                _make_page_with_elements(
                    forms=[
                        {
                            "action": "/register",
                            "method": "POST",
                            "fields": [
                                {"name": "username", "type": "text", "required": "true"},
                            ],
                        }
                    ]
                )
            ]
        )
        reqs = [
            _make_requirement(
                acceptance_criteria=["User enters their email in the email field"],
            )
        ]
        report = detector.detect(site, reqs)
        email_items = [
            i for i in report.items
            if "email" in i.expected.lower() and i.discrepancy_type == "missing_form_field"
        ]
        assert len(email_items) >= 1


class TestSeverityClassification:
    def test_severity_show_stopper_for_critical(self, detector: DiscrepancyDetector):
        """Critical requirement gaps should be show_stopper severity."""
        site = _make_site_model(pages=[_make_page_with_elements(elements=[])])
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks Delete button"],
                priority="Critical",
            )
        ]
        report = detector.detect(site, reqs)
        critical_items = [i for i in report.items if i.severity == "show_stopper"]
        assert len(critical_items) >= 1

    def test_severity_warning_for_high(self, detector: DiscrepancyDetector):
        """High priority requirement gaps should be warning severity."""
        site = _make_site_model(pages=[_make_page_with_elements(elements=[])])
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks Save button"],
                priority="High",
            )
        ]
        report = detector.detect(site, reqs)
        warning_items = [i for i in report.items if i.severity == "warning"]
        assert len(warning_items) >= 1

    def test_severity_info_for_medium(self, detector: DiscrepancyDetector):
        """Medium priority requirement gaps should be info severity."""
        site = _make_site_model(pages=[_make_page_with_elements(elements=[])])
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks Help button"],
                priority="Medium",
            )
        ]
        report = detector.detect(site, reqs)
        info_items = [i for i in report.items if i.severity == "info"]
        assert len(info_items) >= 1


class TestGateDecision:
    def test_gate_decision_block(self, detector: DiscrepancyDetector):
        """Report with show_stopper should return 'block'."""
        site = _make_site_model(pages=[_make_page_with_elements(elements=[])])
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks Critical button"],
                priority="Critical",
            )
        ]
        report = detector.detect(site, reqs)
        assert report.gate_decision == "block"

    def test_gate_decision_proceed_with_warnings(self, detector: DiscrepancyDetector):
        """Report with only warnings should return 'proceed_with_warnings'."""
        site = _make_site_model(pages=[_make_page_with_elements(elements=[])])
        reqs = [
            _make_requirement(
                acceptance_criteria=["User clicks Optional button"],
                priority="High",
            )
        ]
        report = detector.detect(site, reqs)
        assert report.gate_decision == "proceed_with_warnings"

    def test_gate_decision_proceed(self, detector: DiscrepancyDetector):
        """Clean report with no discrepancies should return 'proceed'."""
        site = _make_site_model(
            pages=[
                _make_page_with_elements(
                    elements=[
                        PageElementArtifact(
                            element_type="button",
                            name="login",
                            selector="#login",
                            text="Login",
                        ),
                    ]
                )
            ]
        )
        # Requirements that don't reference any specific elements
        reqs = [
            _make_requirement(
                acceptance_criteria=["System processes the request"],
            )
        ]
        report = detector.detect(site, reqs)
        assert report.gate_decision == "proceed"
