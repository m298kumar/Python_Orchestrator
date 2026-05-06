"""
Stage 1 Integration Tests
=========================
End-to-end validation of the domain-agnostic test generation engine.
Tests multi-domain detection, multi-provider factory, template rendering,
full pipeline execution, and sanitiser integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytest
from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent
from stlc_platform.agents.requirements_agent.classifier import ACClassifier
from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector
from stlc_platform.agents.requirements_agent.prompts import PromptRenderer
from stlc_platform.agents.requirements_agent.sanitiser import TestCaseSanitiser
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.core.llm import OllamaClient, create_llm_client
from stlc_platform.core.llm.base_client import BaseLLMClient

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ── Mock LLM Client ─────────────────────────────────────────────────────────


class MockLLMClient(BaseLLMClient):
    """Mock LLM that returns pre-canned test case JSON."""

    def __init__(self):
        self.base_url = "mock://localhost"

    def check_connection(self) -> bool:
        return True

    def list_models(self) -> list:
        return ["mock-model"]

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        return json.dumps(
            {
                "title": "Mock Test Case",
                "description": "This verifies the feature works as expected",
                "preconditions": "User is logged in with valid account",
                "steps": [
                    {
                        "action": "Navigate to the relevant screen",
                        "expected_result": "Screen loads successfully",
                    },
                    {
                        "action": "Enter valid test data in the input field",
                        "expected_result": "Data is accepted",
                    },
                    {"action": "Click the submit button", "expected_result": "Form is submitted"},
                    {
                        "action": "Verify confirmation is displayed",
                        "expected_result": "Confirmation message shown",
                    },
                ],
                "expected_outcome": "Feature completes successfully",
                "component": "Test Screen",
                "given": "A valid user is logged in",
                "when": "The user performs the action",
                "then": "The system responds correctly",
                "priority": "High",
                "tags": ["integration", "positive"],
                "estimated_duration": "5",
            }
        )


@dataclass
class SimpleRequirement:
    """Lightweight requirement for integration tests."""

    req_id: str
    title: str
    description: str
    priority: str = "High"
    category: str = "General"
    acceptance_criteria: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


def _load_fixture(name: str) -> List[SimpleRequirement]:
    """Load requirements from a fixture JSON file."""
    path = _FIXTURES_DIR / name
    with open(path) as f:
        data = json.load(f)
    return [
        SimpleRequirement(
            req_id=item["req_id"],
            title=item["title"],
            description=item["description"],
            priority=item.get("priority", "High"),
            category=item.get("category", "General"),
            acceptance_criteria=item.get("acceptance_criteria", []),
            tags=item.get("tags", []),
        )
        for item in data
    ]


# ── Multi-Domain Tests ──────────────────────────────────────────────────────


class TestMultiDomainDetection:
    """Verify domain detection works across 3 different domains."""

    @pytest.fixture
    def detector(self):
        return DomainDetector()

    def test_ecommerce_domain(self, detector):
        reqs = _load_fixture("requirements_ecommerce.json")
        domain = detector.detect(reqs)
        assert "commerce" in domain.lower() or "retail" in domain.lower()

    def test_healthcare_domain(self, detector):
        reqs = _load_fixture("requirements_healthcare.json")
        domain = detector.detect(reqs)
        assert "health" in domain.lower()

    def test_banking_domain(self, detector):
        reqs = _load_fixture("requirements_banking.json")
        domain = detector.detect(reqs)
        assert "financial" in domain.lower() or "banking" in domain.lower()

    def test_all_three_domains_distinct(self, detector):
        """Each domain fixture produces a distinct label."""
        domains = set()
        for fixture in [
            "requirements_ecommerce.json",
            "requirements_healthcare.json",
            "requirements_banking.json",
        ]:
            reqs = _load_fixture(fixture)
            domains.add(detector.detect(reqs))
        assert len(domains) == 3


# ── Multi-Provider Factory Tests ────────────────────────────────────────────


class TestMultiProviderFactory:
    """Verify factory returns correct class per provider string."""

    def test_ollama_factory(self):
        client = create_llm_client("ollama")
        assert isinstance(client, OllamaClient)

    def test_openai_factory_class_check(self):
        from stlc_platform.core.llm import OpenAIClient

        if OpenAIClient is not None:
            assert issubclass(OpenAIClient, BaseLLMClient)

    def test_anthropic_factory_class_check(self):
        from stlc_platform.core.llm import AnthropicClient

        if AnthropicClient is not None:
            assert issubclass(AnthropicClient, BaseLLMClient)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            create_llm_client("unknown_provider_xyz")


# ── Template Rendering Tests ────────────────────────────────────────────────


class TestTemplateRendering:
    """Verify all prompt template combinations render without error."""

    @pytest.fixture
    def renderer(self):
        return PromptRenderer()

    def test_system_prompt_all_platforms(self, renderer):
        for platform in ["web", "mobile", "api", "desktop"]:
            result = renderer.render_system_prompt(
                domain="testing",
                tech_stack={"platform": platform},
            )
            assert len(result) > 100
            assert "RULE 1" in result

    @pytest.mark.parametrize("test_type", ["positive", "negative", "edge_case"])
    @pytest.mark.parametrize(
        "ac_type",
        [
            "eligibility",
            "ui_behaviour",
            "timing",
            "data_valid",
            "security",
            "general",
        ],
    )
    def test_all_hint_combinations(self, renderer, test_type, ac_type):
        hints = renderer.render_type_hints(
            test_type=test_type,
            ac_type=ac_type,
            ac="User must complete the process within 5 minutes",
            feature="Feature Under Test",
            nav_target="Target Screen",
        )
        assert "desc" in hints
        assert "steps" in hints

    def test_user_prompt_gherkin_format(self, renderer):
        req = SimpleRequirement(
            req_id="REQ-INT-001",
            title="Integration Test Feature",
            description="Test description",
            acceptance_criteria=["AC1 text"],
        )
        slot = {
            "test_type": "positive",
            "target_ac": "AC1 text",
            "title": "Test",
            "ac_type": "general",
        }
        result = renderer.render_user_prompt(
            requirement=req,
            slot=slot,
            test_number=1,
            total=1,
            tc_format="gherkin",
        )
        assert "GIVEN / WHEN / THEN" in result

    def test_no_domain_hardcoding_in_system_prompt(self, renderer):
        result = renderer.render_system_prompt()
        lower = result.lower()
        assert "cheque" not in lower
        assert "deposit" not in lower
        assert "banking" not in lower
        assert "patient registration" not in lower


# ── Full Pipeline Tests ─────────────────────────────────────────────────────


class TestFullPipeline:
    """Test the complete generation pipeline with mocked LLM."""

    def test_pipeline_ecommerce(self):
        reqs = _load_fixture("requirements_ecommerce.json")
        agent = TestGenerationAgent()
        result = agent.execute(
            artifacts={"requirements": reqs, "llm_client": MockLLMClient()},
            config={"max_tests": 2, "include_negative": True, "include_edge": False},
        )
        assert result.success is True
        tcs = result.artifacts["test_cases"]
        # AC-aware coverage: at least one TC per acceptance criterion
        # Each req has 3 ACs, so effective_max = max(2, 3) = 3 per req
        assert len(tcs) == len(reqs) * 3
        assert all(isinstance(tc, TestCaseArtifact) for tc in tcs)

    def test_pipeline_healthcare(self):
        reqs = _load_fixture("requirements_healthcare.json")
        agent = TestGenerationAgent()
        result = agent.execute(
            artifacts={"requirements": reqs, "llm_client": MockLLMClient()},
            config={"max_tests": 1, "include_negative": False, "include_edge": False},
        )
        assert result.success is True
        tcs = result.artifacts["test_cases"]
        # AC-aware: each req has 3 ACs, effective_max = max(1, 3) = 3
        assert len(tcs) == len(reqs) * 3

    def test_pipeline_banking(self):
        reqs = _load_fixture("requirements_banking.json")
        agent = TestGenerationAgent()
        result = agent.execute(
            artifacts={"requirements": reqs, "llm_client": MockLLMClient()},
            config={"max_tests": 1, "include_negative": False, "include_edge": False},
        )
        assert result.success is True
        tcs = result.artifacts["test_cases"]
        # AC-aware: each req has 3 ACs, effective_max = max(1, 3) = 3
        assert len(tcs) == len(reqs) * 3

    def test_pipeline_outputs_valid_artifacts(self):
        reqs = _load_fixture("requirements_ecommerce.json")[:1]
        agent = TestGenerationAgent()
        result = agent.execute(
            artifacts={"requirements": reqs, "llm_client": MockLLMClient()},
            config={"max_tests": 3, "include_negative": True, "include_edge": True},
        )
        assert result.success is True
        for tc in result.artifacts["test_cases"]:
            assert tc.tc_id.startswith("TC-")
            assert tc.req_id == "REQ-EC-001"
            assert tc.test_type in ("positive", "negative", "edge_case")
            assert len(tc.steps) >= 2
            assert tc.description != ""

    def test_pipeline_metadata(self):
        reqs = _load_fixture("requirements_healthcare.json")
        agent = TestGenerationAgent()
        result = agent.execute(
            artifacts={"requirements": reqs, "llm_client": MockLLMClient()},
            config={"max_tests": 1, "include_negative": False, "include_edge": False},
        )
        assert result.metadata["total_requirements"] == 3
        # AC-aware: each req has 3 ACs, effective_max = max(1, 3) = 3
        assert result.metadata["total_test_cases"] == 9


# ── Sanitiser Integration Tests ─────────────────────────────────────────────


class TestSanitiserIntegration:
    """Test that sanitiser correctly cleans known-bad LLM output."""

    def test_sanitise_instruction_text_in_description(self):
        sanitiser = TestCaseSanitiser()
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test Title",
            description="one sentence explaining what this test verifies and why it matters",
            preconditions="Valid preconditions for testing",
            test_type="positive",
            priority="High",
            steps=[
                TestStepArtifact(action="Navigate to login page", expected_result="Page loads"),
                TestStepArtifact(
                    action="Enter valid credentials", expected_result="Fields populated"
                ),
                TestStepArtifact(action="Click submit", expected_result="Dashboard shown"),
            ],
            expected_outcome="User logged in successfully",
            category="Authentication",
        )
        slot = {
            "test_type": "positive",
            "target_ac": "User can login",
            "title": "Test",
            "ac_type": "general",
        }
        result = sanitiser.sanitise(
            tc,
            slot,
            SimpleRequirement(
                req_id="REQ-001",
                title="Login",
                description="D",
                category="Auth",
            ),
        )
        # Description should be replaced since it contains instruction text
        assert "one sentence explaining" not in result.description.lower()

    def test_sanitise_trivial_outcome(self):
        sanitiser = TestCaseSanitiser()
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test Title",
            description="Valid description for the test case verification",
            preconditions="User is logged in",
            test_type="positive",
            priority="High",
            steps=[
                TestStepArtifact(action="Navigate to page", expected_result="Page loads"),
                TestStepArtifact(action="Click button", expected_result="Action completed"),
                TestStepArtifact(action="Verify result", expected_result="Result displayed"),
            ],
            expected_outcome="pass",
            category="General",
        )
        slot = {
            "test_type": "positive",
            "target_ac": "Feature works correctly",
            "title": "Test",
            "ac_type": "general",
        }
        result = sanitiser.sanitise(
            tc,
            slot,
            SimpleRequirement(
                req_id="REQ-001",
                title="Feature",
                description="D",
                category="General",
            ),
        )
        # Trivial outcome "pass" should be replaced
        assert result.expected_outcome.lower() != "pass"

    def test_sanitise_generic_steps(self):
        sanitiser = TestCaseSanitiser()
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test Title",
            description="Valid description for testing purposes",
            preconditions="Preconditions are set",
            test_type="positive",
            priority="High",
            steps=[
                TestStepArtifact(action="perform the action", expected_result="verify the outcome"),
                TestStepArtifact(action="trigger the feature", expected_result="check the result"),
            ],
            expected_outcome="Feature works",
            category="General",
        )
        slot = {
            "test_type": "positive",
            "target_ac": "Feature works",
            "title": "Test",
            "ac_type": "general",
        }
        result = sanitiser.sanitise(
            tc,
            slot,
            SimpleRequirement(
                req_id="REQ-001",
                title="Feature",
                description="D",
                category="General",
            ),
        )
        # Generic steps should be replaced with synthesised steps (at least 3 steps)
        assert len(result.steps) >= 3  # synthesised always produces 4-5 steps
        # At least one step should reference the actual requirement context
        actions = " ".join(s.action for s in result.steps).lower()
        assert "log in" in actions or "navigate" in actions or "feature" in actions


# ── Classifier Multi-Domain Tests ───────────────────────────────────────────


class TestClassifierMultiDomain:
    """Verify classifier works across domain-agnostic AC types."""

    @pytest.fixture
    def classifier(self):
        return ACClassifier()

    def test_security_ac(self, classifier):
        r = classifier.classify("User must authenticate via OTP before proceeding")
        assert r.ac_type == "security"

    def test_timing_ac(self, classifier):
        r = classifier.classify("Response must be returned within 3 seconds")
        assert r.ac_type == "timing"

    def test_data_validation_ac(self, classifier):
        r = classifier.classify("Email field must be validated against standard format")
        assert r.ac_type == "data_valid"

    def test_ui_behaviour_ac(self, classifier):
        r = classifier.classify("Success message is displayed after form submission")
        assert r.ac_type == "ui_behaviour"

    def test_eligibility_ac(self, classifier):
        r = classifier.classify("Only users with premium subscription are eligible to access")
        assert r.ac_type == "eligibility"

    def test_general_ac(self, classifier):
        r = classifier.classify("The system processes the request and returns a result")
        assert r.ac_type == "general"
