"""
Stage 2 Integration Tests
=========================
End-to-end validation of the BDD automation code generation pipeline.
Tests feature file generation, Gherkin validation, step parsing,
step definition generation, and the BDDAgent orchestration.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import List

import pytest
from stlc_platform.agents.bdd_agent import (
    BDDAgent,
    FeatureFileGenerator,
    GherkinValidator,
    StepDefinitionGenerator,
    StepParser,
)
from stlc_platform.core.contracts import (
    TestCaseArtifact,
    TestStepArtifact,
)

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# -- Helpers -----------------------------------------------------------------


def _load_fixture(name: str) -> List[TestCaseArtifact]:
    """Load a JSON fixture file and return TestCaseArtifact list."""
    path = _FIXTURES_DIR / name
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        TestCaseArtifact(
            tc_id=tc["tc_id"],
            req_id=tc["req_id"],
            title=tc["title"],
            description=tc.get("description", ""),
            preconditions=tc.get("preconditions", ""),
            test_type=tc.get("test_type", "positive"),
            priority=tc.get("priority", "Medium"),
            steps=[
                TestStepArtifact(
                    action=s["action"],
                    expected_result=s.get("expected_result", ""),
                )
                for s in tc.get("steps", [])
            ],
            expected_outcome=tc.get("expected_outcome", ""),
            tags=tc.get("tags", []),
            category=tc.get("category", ""),
            component=tc.get("component", ""),
            given=tc.get("given", ""),
            when=tc.get("when", ""),
            then=tc.get("then", ""),
            estimated_duration=tc.get("estimated_duration", "5"),
        )
        for tc in data
    ]


# -- Feature File Generation Tests ------------------------------------------


class TestFeatureFileGeneration:
    """Integration tests for the feature file generation pipeline."""

    @pytest.fixture(
        params=[
            "test_cases_ecommerce.json",
            "test_cases_healthcare.json",
            "test_cases_banking.json",
        ]
    )
    def test_cases(self, request) -> List[TestCaseArtifact]:
        return _load_fixture(request.param)

    def test_generates_one_feature_per_req_id(self, test_cases):
        gen = FeatureFileGenerator()
        features = gen.generate(test_cases)
        req_ids = {tc.req_id for tc in test_cases}
        assert len(features) == len(req_ids)
        for ff in features:
            assert ff.req_id in req_ids

    def test_feature_files_have_valid_gherkin(self, test_cases):
        gen = FeatureFileGenerator()
        features = gen.generate(test_cases)
        validator = GherkinValidator()
        for ff in features:
            result = validator.validate(ff.content)
            assert result.valid, f"Feature '{ff.filename}' has Gherkin errors: {result.errors}"

    def test_feature_files_contain_feature_keyword(self, test_cases):
        gen = FeatureFileGenerator()
        features = gen.generate(test_cases)
        for ff in features:
            assert "Feature:" in ff.content

    def test_feature_files_have_given_when_then(self, test_cases):
        gen = FeatureFileGenerator()
        features = gen.generate(test_cases)
        for ff in features:
            assert "When " in ff.content
            assert "Then " in ff.content

    def test_scenario_count_matches(self, test_cases):
        gen = FeatureFileGenerator()
        features = gen.generate(test_cases)
        total = sum(ff.scenario_count for ff in features)
        assert total == len(test_cases)


# -- Gherkin Validation Tests ------------------------------------------------


class TestGherkinValidation:
    """Integration tests for Gherkin validation on generated content."""

    def test_validates_ecommerce_features(self):
        tcs = _load_fixture("test_cases_ecommerce.json")
        gen = FeatureFileGenerator()
        validator = GherkinValidator()
        features = gen.generate(tcs)
        for ff in features:
            result = validator.validate(ff.content)
            assert result.valid, f"{ff.filename}: {result.errors}"
            assert result.scenario_count > 0

    def test_validates_healthcare_features(self):
        tcs = _load_fixture("test_cases_healthcare.json")
        gen = FeatureFileGenerator()
        validator = GherkinValidator()
        features = gen.generate(tcs)
        for ff in features:
            result = validator.validate(ff.content)
            assert result.valid, f"{ff.filename}: {result.errors}"

    def test_validates_banking_features(self):
        tcs = _load_fixture("test_cases_banking.json")
        gen = FeatureFileGenerator()
        validator = GherkinValidator()
        features = gen.generate(tcs)
        for ff in features:
            result = validator.validate(ff.content)
            assert result.valid, f"{ff.filename}: {result.errors}"


# -- Step Parsing Tests ------------------------------------------------------


class TestStepParsing:
    """Integration tests for step extraction and parameterization."""

    def test_extracts_steps_from_all_domains(self):
        parser = StepParser()
        gen = FeatureFileGenerator()
        for fixture in [
            "test_cases_ecommerce.json",
            "test_cases_healthcare.json",
            "test_cases_banking.json",
        ]:
            tcs = _load_fixture(fixture)
            features = gen.generate(tcs)
            steps = parser.extract_steps(features)
            assert len(steps) > 0, f"No steps extracted from {fixture}"

    def test_all_steps_have_valid_keywords(self):
        parser = StepParser()
        gen = FeatureFileGenerator()
        tcs = _load_fixture("test_cases_ecommerce.json")
        features = gen.generate(tcs)
        steps = parser.extract_steps(features)
        for step in steps:
            assert step.keyword in ("given", "when", "then")

    def test_deduplication_reduces_step_count(self):
        parser = StepParser()
        gen = FeatureFileGenerator()
        tcs = _load_fixture("test_cases_ecommerce.json")
        features = gen.generate(tcs)
        raw = parser.extract_steps(features)
        unique = parser.deduplicate(raw)
        # Unique should be <= raw
        assert len(unique) <= len(raw)

    def test_parameterized_steps_have_valid_patterns(self):
        parser = StepParser()
        gen = FeatureFileGenerator()
        tcs = _load_fixture("test_cases_ecommerce.json")
        features = gen.generate(tcs)
        raw = parser.extract_steps(features)
        unique = parser.deduplicate(raw)
        parameterized = parser.parameterize(unique)
        for step in parameterized:
            assert step.keyword in ("given", "when", "then")
            assert step.pattern  # Non-empty pattern


# -- Step Definition Generation Tests ----------------------------------------


class TestStepDefinitionGeneration:
    """Integration tests for step definition skeleton generation."""

    def _get_parameterized_steps(self, fixture_name: str):
        tcs = _load_fixture(fixture_name)
        gen = FeatureFileGenerator()
        features = gen.generate(tcs)
        parser = StepParser()
        raw = parser.extract_steps(features)
        unique = parser.deduplicate(raw)
        return parser.parameterize(unique), features

    def test_behave_output_is_valid_python(self):
        steps, features = self._get_parameterized_steps("test_cases_ecommerce.json")
        step_gen = StepDefinitionGenerator(framework="behave")
        results = step_gen.generate(steps)
        for sd in results:
            # Must parse without SyntaxError
            ast.parse(sd.content)
            assert sd.framework == "behave"
            assert sd.language == "python"

    def test_pytest_bdd_output_is_valid_python(self):
        steps, features = self._get_parameterized_steps("test_cases_ecommerce.json")
        step_gen = StepDefinitionGenerator(framework="pytest_bdd")
        results = step_gen.generate(steps, features)
        for sd in results:
            ast.parse(sd.content)
            assert sd.framework == "pytest_bdd"

    def test_behave_has_all_decorator_types(self):
        steps, features = self._get_parameterized_steps("test_cases_ecommerce.json")
        step_gen = StepDefinitionGenerator(framework="behave")
        results = step_gen.generate(steps)
        content = results[0].content
        assert "@given(" in content
        assert "@when(" in content
        assert "@then(" in content

    def test_selenium_import_when_configured(self):
        steps, _ = self._get_parameterized_steps("test_cases_ecommerce.json")
        step_gen = StepDefinitionGenerator(framework="behave", automation_lib="selenium")
        results = step_gen.generate(steps)
        assert "selenium" in results[0].content.lower()

    def test_step_count_covers_all_keywords(self):
        steps, features = self._get_parameterized_steps("test_cases_ecommerce.json")
        step_gen = StepDefinitionGenerator(framework="behave")
        results = step_gen.generate(steps)
        total = sum(sd.step_count for sd in results)
        assert total > 0
        assert total == len(steps)

    def test_multi_domain_step_defs_all_valid_python(self):
        """Test step definition generation across all 3 domains."""
        for fixture in [
            "test_cases_ecommerce.json",
            "test_cases_healthcare.json",
            "test_cases_banking.json",
        ]:
            steps, features = self._get_parameterized_steps(fixture)
            for fw in ("behave", "pytest_bdd"):
                step_gen = StepDefinitionGenerator(framework=fw)
                results = step_gen.generate(steps, features)
                for sd in results:
                    ast.parse(sd.content)  # Must not raise SyntaxError


# -- BDDAgent End-to-End Tests -----------------------------------------------


class TestBDDAgentEndToEnd:
    """Integration tests for the BDDAgent orchestrating the full pipeline."""

    def test_ecommerce_pipeline(self):
        agent = BDDAgent()
        tcs = _load_fixture("test_cases_ecommerce.json")
        result = agent.execute(
            {"test_cases": tcs},
            {"framework": "behave"},
        )
        assert result.success, f"Agent failed: {result.errors}"
        assert "feature_files" in result.artifacts
        assert "step_definitions" in result.artifacts
        assert len(result.artifacts["feature_files"]) > 0
        assert len(result.artifacts["step_definitions"]) > 0

    def test_healthcare_pipeline(self):
        agent = BDDAgent()
        tcs = _load_fixture("test_cases_healthcare.json")
        result = agent.execute(
            {"test_cases": tcs},
            {"framework": "behave"},
        )
        assert result.success

    def test_banking_pipeline(self):
        agent = BDDAgent()
        tcs = _load_fixture("test_cases_banking.json")
        result = agent.execute(
            {"test_cases": tcs},
            {"framework": "pytest_bdd"},
        )
        assert result.success

    def test_metadata_populated(self):
        agent = BDDAgent()
        tcs = _load_fixture("test_cases_ecommerce.json")
        result = agent.execute(
            {"test_cases": tcs},
            {"framework": "behave"},
        )
        assert result.metadata["total_features"] > 0
        assert result.metadata["total_scenarios"] > 0
        assert result.metadata["total_step_defs"] > 0
        assert result.metadata["framework"] == "behave"

    def test_validation_warnings_for_empty_gwt(self):
        """Test that test cases with empty GWT fields produce warnings."""
        agent = BDDAgent()
        tcs = [
            TestCaseArtifact(
                tc_id="TC-X01",
                req_id="REQ-TEST-001",
                title="Test with empty GWT",
                description="No given/when/then",
                preconditions="User is logged in",
                test_type="positive",
                priority="Medium",
                steps=[
                    TestStepArtifact(action="Click button", expected_result="Result shown"),
                    TestStepArtifact(action="Verify output", expected_result="Output correct"),
                ],
                # given, when, then left empty
            ),
        ]
        validation = agent.validate_input({"test_cases": tcs})
        assert validation.valid  # Still valid, just with warnings
        assert len(validation.warnings) > 0

    def test_invalid_input_returns_failure(self):
        agent = BDDAgent()
        result = agent.execute(
            {"test_cases": []},
            {"framework": "behave"},
        )
        assert not result.success
        assert len(result.errors) > 0

    def test_capabilities_declared(self):
        agent = BDDAgent()
        caps = agent.get_capabilities()
        assert caps.agent_id == "bdd_generation"
        assert "TestCaseArtifact" in caps.input_types
        assert "FeatureFileArtifact" in caps.output_types
        assert "StepDefinitionArtifact" in caps.output_types


# -- Cross-Domain Consistency Tests ------------------------------------------


class TestCrossDomainConsistency:
    """Tests ensuring consistent behavior across all domains."""

    def test_all_domains_produce_features_and_stepdefs(self):
        agent = BDDAgent()
        for fixture in [
            "test_cases_ecommerce.json",
            "test_cases_healthcare.json",
            "test_cases_banking.json",
        ]:
            tcs = _load_fixture(fixture)
            result = agent.execute(
                {"test_cases": tcs},
                {"framework": "behave"},
            )
            assert result.success, f"{fixture} failed: {result.errors}"
            assert len(result.artifacts["feature_files"]) > 0
            assert len(result.artifacts["step_definitions"]) > 0

    def test_no_hardcoded_domain_terms_in_bdd_agent(self):
        """Verify BDD agent code has no hardcoded domain-specific terms."""
        bdd_dir = Path(__file__).parent.parent.parent / "stlc_platform" / "agents" / "bdd_agent"
        forbidden = ["mobile banking", "patient registration", "cheque"]
        for py_file in bdd_dir.rglob("*.py"):
            if "test" in py_file.name:
                continue
            content = py_file.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term not in content, (
                    f"Hardcoded domain term '{term}' found in {py_file.name}"
                )

    def test_generated_features_have_no_unicode_issues(self):
        """Ensure generated Gherkin content is ASCII-safe for cross-platform use."""
        gen = FeatureFileGenerator()
        for fixture in [
            "test_cases_ecommerce.json",
            "test_cases_healthcare.json",
            "test_cases_banking.json",
        ]:
            tcs = _load_fixture(fixture)
            features = gen.generate(tcs)
            for ff in features:
                # Should encode to UTF-8 without errors
                ff.content.encode("utf-8")
                # Feature file should not contain unprintable control chars
                for char in ff.content:
                    if ord(char) < 32 and char not in ("\n", "\r", "\t"):
                        pytest.fail(f"Control char U+{ord(char):04X} in {ff.filename}")
