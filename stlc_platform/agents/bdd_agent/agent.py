"""
BDD Agent
=========
BaseAgent implementation that wires up the FeatureFileGenerator and
StepDefinitionGenerator to produce BDD artifacts from test cases.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.agents.bdd_agent.feature_generator import FeatureFileGenerator
from stlc_platform.agents.bdd_agent.gherkin_validator import GherkinValidator
from stlc_platform.agents.bdd_agent.step_parser import StepParser
from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator


class BDDAgent(BaseAgent):
    """
    Agent that generates BDD feature files and step definition skeletons
    from TestCaseArtifact lists.

    Lifecycle:
      1. validate_input() -- check that test_cases list is present
      2. execute() -- generate features + step defs, validate Gherkin
      3. get_capabilities() -- describe input/output types

    Config keys:
      - framework: "behave" or "pytest_bdd" (default: "behave")
      - language: "python" (default: "python")
      - automation_lib: "playwright" or "selenium" (default: "playwright")
    """

    agent_id: str = "bdd_generation"
    agent_version: str = "1.0.0"

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """Validate that the input contains test_cases."""
        errors: List[str] = []
        warnings: List[str] = []

        test_cases = artifacts.get("test_cases")
        if test_cases is None:
            errors.append("'test_cases' is required.")
        elif not isinstance(test_cases, list):
            errors.append("'test_cases' must be a list.")
        elif len(test_cases) == 0:
            errors.append("'test_cases' list must not be empty.")
        else:
            # Check for GWT fields
            gwt_empty = sum(
                1
                for tc in test_cases
                if not getattr(tc, "given", "") and not getattr(tc, "when", "")
            )
            if gwt_empty > 0:
                warnings.append(
                    f"{gwt_empty} test case(s) have empty Given/When fields. "
                    "Feature files will use fallback step generation."
                )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        """
        Generate BDD feature files and step definitions.

        Args:
            artifacts: Must contain "test_cases" (List[TestCaseArtifact]).
            config: Optional overrides (framework, language, automation_lib).

        Returns:
            AgentResult with feature_files and step_definitions.
        """
        # Validate
        validation = self.validate_input(artifacts)
        if not validation.valid:
            return AgentResult(
                success=False,
                errors=validation.errors,
            )

        test_cases = artifacts["test_cases"]
        framework = config.get("framework", "behave")
        language = config.get("language", "python")
        automation_lib = config.get("automation_lib", "playwright")

        try:
            # Step 1: Generate feature files
            feature_gen = FeatureFileGenerator(
                template_dir=config.get("template_dir"),
                override_dir=config.get("override_dir"),
            )
            feature_files = feature_gen.generate(test_cases)

            # Step 2: Validate generated Gherkin
            validator = GherkinValidator()
            validation_warnings: List[str] = []
            for ff in feature_files:
                vresult = validator.validate(ff.content)
                if not vresult.valid:
                    validation_warnings.extend(
                        f"[{ff.filename}] {e}" for e in vresult.errors
                    )
                validation_warnings.extend(
                    f"[{ff.filename}] WARNING: {w}"
                    for w in vresult.warnings
                )

            # Step 3: Parse steps from feature files
            parser = StepParser()
            raw_steps = parser.extract_steps(feature_files)
            unique_steps = parser.deduplicate(raw_steps)
            parameterized_steps = parser.parameterize(unique_steps)

            # Step 4: Generate step definitions
            step_gen = StepDefinitionGenerator(
                framework=framework,
                language=language,
                automation_lib=automation_lib,
                template_dir=config.get("template_dir"),
                override_dir=config.get("override_dir"),
            )
            step_defs = step_gen.generate(
                parameterized_steps, feature_files
            )

            total_scenarios = sum(ff.scenario_count for ff in feature_files)
            total_step_defs = sum(sd.step_count for sd in step_defs)

            return AgentResult(
                success=True,
                artifacts={
                    "feature_files": feature_files,
                    "step_definitions": step_defs,
                },
                metadata={
                    "total_features": len(feature_files),
                    "total_scenarios": total_scenarios,
                    "total_step_defs": total_step_defs,
                    "framework": framework,
                    "language": language,
                    "automation_lib": automation_lib,
                    "validation_warnings": validation_warnings,
                },
            )

        except Exception as e:
            return AgentResult(
                success=False,
                errors=[f"BDD generation failed: {e}"],
            )

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["TestCaseArtifact"],
            output_types=["FeatureFileArtifact", "StepDefinitionArtifact"],
            description=(
                "Generates BDD feature files and step definition skeletons "
                "from test case artifacts. Supports Behave and Pytest-BDD."
            ),
            required_skills=["coding_standards", "test_design_principles"],
            default_model_tier="lightweight",
        )
