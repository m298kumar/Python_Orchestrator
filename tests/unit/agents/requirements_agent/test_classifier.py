"""Tests for AC type classifier."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from stlc_platform.agents.requirements_agent.classifier import (
    ACClassifier,
    ACTypeConfig,
    default_ac_types,
)


class TestDefaultACTypes:
    """Test built-in AC type definitions."""

    def test_returns_six_types(self):
        types = default_ac_types()
        assert len(types) == 6

    def test_type_names(self):
        types = default_ac_types()
        names = {t.name for t in types}
        assert names == {
            "security",
            "timing",
            "eligibility",
            "data_valid",
            "ui_behaviour",
            "general",
        }

    def test_general_has_no_keywords(self):
        types = default_ac_types()
        general = [t for t in types if t.name == "general"][0]
        assert general.keywords == []

    def test_security_has_keywords(self):
        types = default_ac_types()
        sec = [t for t in types if t.name == "security"][0]
        assert "biometric" in sec.keywords
        assert "encrypt" in sec.keywords


class TestACClassifier:
    """Test keyword-based classification."""

    @pytest.fixture
    def classifier(self):
        return ACClassifier()

    def test_security_classification(self, classifier):
        result = classifier.classify("User must authenticate with biometric verification")
        assert result.ac_type == "security"
        assert result.confidence == 1.0
        assert result.method == "keyword"

    def test_timing_classification(self, classifier):
        result = classifier.classify("Response must be returned within 3 seconds")
        assert result.ac_type == "timing"
        assert result.confidence == 1.0

    def test_eligibility_classification(self, classifier):
        result = classifier.classify("Only enrolled premium users are eligible for this feature")
        assert result.ac_type == "eligibility"
        assert result.confidence == 1.0

    def test_data_valid_classification(self, classifier):
        result = classifier.classify("Phone number must be exactly 10 digits and numeric")
        assert result.ac_type == "data_valid"
        assert result.confidence == 1.0

    def test_ui_behaviour_classification(self, classifier):
        result = classifier.classify("A success banner is displayed after submission")
        assert result.ac_type == "ui_behaviour"
        assert result.confidence == 1.0

    def test_general_fallback(self, classifier):
        result = classifier.classify("The system shall process the input correctly")
        assert result.ac_type == "general"
        assert result.confidence == 0.3

    def test_priority_security_over_timing(self, classifier):
        """Security should be checked before timing."""
        result = classifier.classify("Session timeout must encrypt data within 30 seconds")
        assert result.ac_type == "security"

    def test_priority_timing_over_eligibility(self, classifier):
        """Timing should be checked before eligibility."""
        result = classifier.classify("Eligible users must receive response within 5 minutes")
        assert result.ac_type == "timing"

    # --- Multi-domain tests ---

    def test_ecommerce_data_valid(self, classifier):
        result = classifier.classify("Credit card number must be exactly 16 digits")
        assert result.ac_type == "data_valid"

    def test_healthcare_security(self, classifier):
        result = classifier.classify("Patient records must be encrypted at rest using AES-256")
        assert result.ac_type == "security"

    def test_banking_timing(self, classifier):
        result = classifier.classify("Fund transfer must complete within 2 business hours")
        assert result.ac_type == "timing"

    def test_insurance_eligibility(self, classifier):
        result = classifier.classify(
            "Only customers with active subscription are eligible for claims"
        )
        assert result.ac_type == "eligibility"

    def test_education_ui_behaviour(self, classifier):
        result = classifier.classify("Course progress badge is displayed on the student dashboard")
        assert result.ac_type == "ui_behaviour"


class TestCustomACTypes:
    """Test configuring custom AC types."""

    def test_custom_type(self):
        custom_types = [
            ACTypeConfig(
                name="performance",
                description="Performance-related criteria",
                keywords=["throughput", "concurrent", "load"],
                priority=0,
            ),
            ACTypeConfig(name="general", description="Fallback", keywords=[], priority=99),
        ]
        classifier = ACClassifier(ac_types=custom_types)
        result = classifier.classify("System must handle 1000 concurrent users")
        assert result.ac_type == "performance"

    def test_from_config(self):
        config_list = [
            {
                "name": "accessibility",
                "description": "A11y",
                "keywords": ["aria", "screen reader", "wcag"],
            },
            {"name": "general", "description": "Fallback"},
        ]
        classifier = ACClassifier.from_config(config_list)
        result = classifier.classify("All buttons must have aria labels for screen reader users")
        assert result.ac_type == "accessibility"

    def test_type_names_property(self):
        classifier = ACClassifier()
        names = classifier.type_names
        assert "security" in names
        assert "general" in names


class TestLLMFallback:
    """Test LLM fallback classification."""

    def test_classify_with_llm_success(self):
        classifier = ACClassifier()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "security"

        result = classifier.classify_with_llm("some ambiguous AC", mock_llm)
        assert result.ac_type == "security"
        assert result.method == "llm"
        assert result.confidence == 0.8

    def test_classify_with_llm_unknown_type(self):
        classifier = ACClassifier()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "unknown_type_xyz"

        result = classifier.classify_with_llm("some AC", mock_llm)
        assert result.ac_type == "general"
        assert result.confidence == 0.3

    def test_classify_with_llm_error(self):
        classifier = ACClassifier()
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("API error")

        result = classifier.classify_with_llm("some AC", mock_llm)
        assert result.ac_type == "general"

    def test_classify_smart_keyword_sufficient(self):
        classifier = ACClassifier()
        result = classifier.classify_smart("User must use biometric auth")
        assert result.ac_type == "security"
        assert result.method == "keyword"

    def test_classify_smart_falls_to_llm(self):
        classifier = ACClassifier()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "data_valid"

        result = classifier.classify_smart("some generic criterion", mock_llm)
        assert result.ac_type == "data_valid"
        assert result.method == "llm"

    def test_classify_smart_no_llm_stays_general(self):
        classifier = ACClassifier()
        result = classifier.classify_smart("some generic criterion", llm_client=None)
        assert result.ac_type == "general"
        assert result.confidence == 0.3
