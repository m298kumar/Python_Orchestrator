"""Tests for the DomainDetector class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector


@dataclass
class MockReq:
    """Lightweight requirement stand-in for tests."""

    category: Optional[str] = None
    title: Optional[str] = None


class TestDetect:
    """Test domain detection from requirement objects."""

    @pytest.fixture
    def detector(self):
        return DomainDetector()

    def test_empty_list(self, detector):
        assert detector.detect([]) == ""

    def test_healthcare_by_category(self, detector):
        reqs = [
            MockReq(category="Patient Registration"),
            MockReq(category="Clinical Records"),
        ]
        assert detector.detect(reqs) == "healthcare"

    def test_ecommerce_by_category(self, detector):
        reqs = [
            MockReq(category="Product Catalogue"),
            MockReq(category="Shopping Cart"),
            MockReq(category="Checkout"),
        ]
        assert detector.detect(reqs) == "retail e-commerce"

    def test_financial_by_category(self, detector):
        reqs = [
            MockReq(category="Account Onboarding"),
            MockReq(category="Transaction Processing"),
            MockReq(category="Deposit Management"),
        ]
        assert detector.detect(reqs) == "financial services"

    def test_insurance_by_title(self, detector):
        reqs = [
            MockReq(title="Policy Renewal"),
            MockReq(title="Claim Submission"),
        ]
        assert detector.detect(reqs) == "insurance"

    def test_education_by_category(self, detector):
        reqs = [
            MockReq(category="Student Enrolment"),
            MockReq(category="Course Management"),
        ]
        assert detector.detect(reqs) == "education"

    def test_itsm_by_category(self, detector):
        reqs = [
            MockReq(category="Incident Management"),
            MockReq(category="Helpdesk Ticket"),
        ]
        assert detector.detect(reqs) == "IT service management"

    def test_fallback_to_category_title(self, detector):
        """Unknown domain falls back to first category as title-cased label."""
        reqs = [MockReq(category="telemetry dashboard")]
        result = detector.detect(reqs)
        assert result == "Telemetry Dashboard"

    def test_fallback_to_title_when_no_category(self, detector):
        reqs = [MockReq(title="Logistics Tracking")]
        result = detector.detect(reqs)
        assert result == "Logistics Tracking"

    def test_no_category_no_title(self, detector):
        reqs = [MockReq()]
        assert detector.detect(reqs) == ""

    def test_mixed_signals_highest_score_wins(self, detector):
        """When requirements span domains, the one with the most keyword hits wins."""
        reqs = [
            MockReq(category="Patient Registration"),  # healthcare: 1
            MockReq(category="Clinical Appointment"),  # healthcare: 2
            MockReq(category="Product Display"),  # e-commerce: 1
        ]
        assert detector.detect(reqs) == "healthcare"


class TestDetectFromText:
    """Test detection from raw text strings."""

    def test_healthcare_text(self):
        detector = DomainDetector()
        assert detector.detect_from_text("patient records and diagnosis reports") == "healthcare"

    def test_ecommerce_text(self):
        detector = DomainDetector()
        assert detector.detect_from_text("add to cart and checkout flow") == "retail e-commerce"

    def test_empty_text(self):
        detector = DomainDetector()
        assert detector.detect_from_text("") == ""

    def test_no_match_returns_empty(self):
        detector = DomainDetector()
        assert detector.detect_from_text("quantum computing algorithm optimization") == ""


class TestCustomDomains:
    """Test adding custom domain keyword maps."""

    def test_custom_domain_via_constructor(self):
        detector = DomainDetector(
            domain_keywords={
                "logistics": ["shipment", "warehouse", "freight", "tracking"],
            }
        )
        reqs = [MockReq(category="Shipment Tracking"), MockReq(category="Warehouse Management")]
        assert detector.detect(reqs) == "logistics"

    def test_add_domain(self):
        detector = DomainDetector()
        detector.add_domain("real estate", ["property", "listing", "mortgage", "tenant"])
        reqs = [MockReq(category="Property Listing")]
        assert detector.detect(reqs) == "real estate"

    def test_add_domain_extends_existing(self):
        detector = DomainDetector()
        original_count = len(detector.domain_keywords.get("healthcare", []))
        detector.add_domain("healthcare", ["telehealth", "telemedicine"])
        assert len(detector.domain_keywords["healthcare"]) > original_count
        assert "telehealth" in detector.domain_keywords["healthcare"]

    def test_from_config_none_uses_defaults(self):
        detector = DomainDetector.from_config(None)
        assert "healthcare" in detector.domain_keywords
        assert "retail e-commerce" in detector.domain_keywords

    def test_from_config_custom_replaces_defaults(self):
        detector = DomainDetector.from_config(
            {
                "gaming": ["multiplayer", "inventory", "quest"],
            }
        )
        assert "gaming" in detector.domain_keywords
        assert "healthcare" not in detector.domain_keywords


class TestNoDomainHardcoding:
    """Verify the detector itself doesn't use hardcoded domain in code logic."""

    def test_all_domains_configurable(self):
        """All domain detection is driven by the keyword dict, not if/elif logic."""
        detector = DomainDetector(domain_keywords={})
        reqs = [MockReq(category="Patient Registration")]
        # With empty keywords, should fallback, not match 'healthcare'
        result = detector.detect(reqs)
        assert result != "healthcare"
        assert result == "Patient Registration"

    def test_swapping_keywords_changes_detection(self):
        """Prove detection is keyword-driven by swapping keywords."""
        detector = DomainDetector(
            domain_keywords={
                "healthcare": ["product", "cart"],  # intentionally swapped
                "retail e-commerce": ["patient", "clinical"],  # swapped
            }
        )
        reqs = [MockReq(category="Patient Registration")]
        # "patient" now maps to e-commerce because keywords were swapped
        assert detector.detect(reqs) == "retail e-commerce"
