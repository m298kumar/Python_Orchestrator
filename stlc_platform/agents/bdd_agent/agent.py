"""
BDD Agent
=========
BaseAgent implementation that wires up the FeatureFileGenerator and
StepDefinitionGenerator to produce BDD artifacts from test cases.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.agents.bdd_agent.feature_generator import FeatureFileGenerator
from stlc_platform.agents.bdd_agent.gherkin_validator import GherkinValidator
from stlc_platform.agents.bdd_agent.pom_generator import POMGenerator
from stlc_platform.agents.bdd_agent.scaffolder import ProjectScaffolder
from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator
from stlc_platform.agents.bdd_agent.step_parser import StepParser
from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.specifications import SpecificationLoader


class BDDAgent(BaseAgent):
    """
    Agent that generates BDD feature files and step definition skeletons
    from TestCaseArtifact lists.

    Lifecycle:
      1. validate_input() -- check that test_cases list is present
      2. execute() -- generate features + step defs, validate Gherkin
      3. get_capabilities() -- describe input/output types

    Config keys:
      - framework: "behave", "pytest_bdd", "cucumber_java", or "cucumberjs"
                    (default: "behave")
      - language: "python", "java", or "javascript" (default: "python")
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

    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
        validation = self.validate_input(artifacts)
        if not validation.valid:
            return AgentResult(success=False, errors=validation.errors)

        test_cases = artifacts["test_cases"]
        bdd_cfg = {**config, **(config.get("bdd", {}) or {})}
        specification_versions: Dict[str, str] = {}
        quarantined_test_cases: List[str] = []
        if config.get("specifications"):
            try:
                loader = SpecificationLoader(config)
                tc_spec = loader.load("test_cases")
                bdd_spec = loader.load("bdd")
                specification_versions = {
                    tc_spec.specification_id: tc_spec.version,
                    bdd_spec.specification_id: bdd_spec.version,
                }
            except (OSError, ValueError) as exc:
                return AgentResult(success=False, errors=[f"Specification validation failed: {exc}"])
            if loader.enforce:
                threshold = float(
                    (config.get("quality_gate", {}) or {}).get("accept_threshold", 0.65)
                )
                quarantined_test_cases = [
                    tc.tc_id
                    for tc in test_cases
                    if float(getattr(tc, "quality_score", 0.0)) < threshold
                    or any(
                        "semantic" in str(issue).lower()
                        for issue in (getattr(tc, "quality_issues", []) or [])
                    )
                ]
                if quarantined_test_cases:
                    test_cases = [
                        tc for tc in test_cases if tc.tc_id not in quarantined_test_cases
                    ]
                if not test_cases:
                    return AgentResult(
                        success=False,
                        errors=[
                            "BDD input violates the approved test-case specification; "
                            "no eligible test cases remain after quarantining: "
                            f"{', '.join(quarantined_test_cases)}"
                        ],
                    )
        framework = str(bdd_cfg.get("framework", "behave")).lower()
        framework = {
            "cucumber": "cucumber_java",
            "cucumber-java": "cucumber_java",
            "cucumber_js": "cucumberjs",
            "cucumber-js": "cucumberjs",
        }.get(framework, framework)
        language = bdd_cfg.get(
            "language",
            StepDefinitionGenerator.SUPPORTED_FRAMEWORKS.get(framework, "python"),
        )
        automation_lib = bdd_cfg.get("automation_lib", "playwright")
        pom_language = bdd_cfg.get("pom_language", language)
        selector_map = self._build_selector_map(artifacts.get("site_model"))

        try:
            feature_files, validation_warnings = self._generate_and_validate_features(
                test_cases,
                bdd_cfg,
            )
            if quarantined_test_cases:
                validation_warnings.append(
                    "Excluded test cases that failed the semantic quality gate: "
                    + ", ".join(quarantined_test_cases)
                )
            if specification_versions:
                feature_files = [
                    ff.model_copy(update={"specification_versions": specification_versions})
                    for ff in feature_files
                ]
            parameterized_steps = self._parse_and_parameterize_steps(feature_files)
            step_defs = self._generate_step_defs(
                parameterized_steps,
                feature_files,
                framework,
                language,
                automation_lib,
                bdd_cfg,
                selector_map,
            )
            pom_stubs = self._generate_pom_stubs(
                test_cases,
                pom_language,
                automation_lib,
                bdd_cfg,
                artifacts,
            )
            project = self._scaffold_project_if_requested(
                framework,
                bdd_cfg,
                feature_files,
                step_defs,
                pom_stubs,
            )

            return self._build_success_result(
                feature_files,
                step_defs,
                pom_stubs,
                project,
                framework,
                language,
                automation_lib,
                pom_language,
                selector_map,
                validation_warnings,
                specification_versions,
                quarantined_test_cases,
            )
        except Exception as e:
            return AgentResult(success=False, errors=[f"BDD generation failed: {e}"])

    def _build_selector_map(self, site_model) -> Dict[str, str]:
        selector_map: Dict[str, str] = {}
        if not site_model:
            return selector_map
        pages = getattr(site_model, "pages", None)
        if pages is None and isinstance(site_model, dict):
            pages = site_model.get("pages", [])
        for page in (pages or []):
            elements = getattr(page, "elements", None)
            if elements is None and isinstance(page, dict):
                elements = page.get("elements", [])
            for element in (elements or []):
                name = (
                    getattr(element, "name", "")
                    or (element.get("name", "") if isinstance(element, dict) else "")
                    or getattr(element, "text", "")
                    or (element.get("text", "") if isinstance(element, dict) else "")
                )
                selector = (
                    getattr(element, "selector", "")
                    or (element.get("selector", "") if isinstance(element, dict) else "")
                )
                if name and selector:
                    selector_map[name.lower().strip()] = selector
        return selector_map

    def _generate_and_validate_features(self, test_cases, config):
        feature_gen = FeatureFileGenerator(
            template_dir=config.get("template_dir"),
            override_dir=config.get("override_dir"),
        )
        feature_files = feature_gen.generate(test_cases)

        validator = GherkinValidator()
        warnings: List[str] = []
        for ff in feature_files:
            vresult = validator.validate(ff.content)
            if not vresult.valid:
                warnings.extend(f"[{ff.filename}] {e}" for e in vresult.errors)
            warnings.extend(f"[{ff.filename}] WARNING: {w}" for w in vresult.warnings)
        return feature_files, warnings

    def _parse_and_parameterize_steps(self, feature_files):
        parser = StepParser()
        raw_steps = parser.extract_steps(feature_files)
        unique_steps = parser.deduplicate(raw_steps)
        return parser.parameterize(unique_steps)

    def _generate_step_defs(
        self,
        parameterized_steps,
        feature_files,
        framework,
        language,
        automation_lib,
        config,
        selector_map,
    ):
        step_gen = StepDefinitionGenerator(
            framework=framework,
            language=language,
            automation_lib=automation_lib,
            template_dir=config.get("template_dir"),
            override_dir=config.get("override_dir"),
        )
        return step_gen.generate(
            parameterized_steps,
            feature_files,
            selector_map=selector_map or None,
        )

    def _generate_pom_stubs(self, test_cases, language, automation_lib, config, artifacts):
        generate_pom = config.get("generate_pom", True)
        if not generate_pom or language not in POMGenerator.SUPPORTED_LANGUAGES:
            return []

        # Extract crawled pages from the site_model artifact.
        # The pipeline provides site_model (SiteModelArtifact), not a separate
        # "crawled_pages" key — so we pull .pages from it here.
        site_model = artifacts.get("site_model")
        crawled_pages = None
        if site_model is not None:
            # Pydantic object (live pipeline run)
            pages_attr = getattr(site_model, "pages", None)
            if pages_attr is not None:
                crawled_pages = pages_attr
            # Dict (deserialized from disk / ArtifactStore)
            elif isinstance(site_model, dict):
                crawled_pages = site_model.get("pages") or None

        pom_gen = POMGenerator(
            language=language,
            automation_lib=automation_lib,
            template_dir=config.get("template_dir"),
            override_dir=config.get("override_dir"),
        )
        return pom_gen.generate(test_cases, crawled_pages=crawled_pages)

    def _scaffold_project_if_requested(
        self,
        framework,
        config,
        feature_files,
        step_defs,
        pom_stubs,
    ):
        if not config.get("generate_project", False):
            return None
        scaffolder = ProjectScaffolder(framework=framework)
        return scaffolder.scaffold(
            project_name=config.get("project_name", "bdd_tests"),
            features=feature_files,
            step_defs=step_defs,
            pom_stubs=pom_stubs or None,
            base_url=config.get("base_url", "http://localhost:8080"),
        )

    def _build_success_result(
        self,
        feature_files,
        step_defs,
        pom_stubs,
        project,
        framework,
        language,
        automation_lib,
        pom_language,
        selector_map,
        validation_warnings,
        specification_versions=None,
        quarantined_test_cases=None,
    ) -> AgentResult:
        total_scenarios = sum(ff.scenario_count for ff in feature_files)
        total_step_defs = sum(sd.step_count for sd in step_defs)

        result_artifacts = {
            "feature_files": feature_files,
            "step_definitions": step_defs,
        }
        if pom_stubs:
            result_artifacts["pom_stubs"] = pom_stubs
        if project:
            result_artifacts["project"] = project

        return AgentResult(
            success=True,
            artifacts=result_artifacts,
            metadata={
                "total_features": len(feature_files),
                "total_scenarios": total_scenarios,
                "total_step_defs": total_step_defs,
                "total_pom_stubs": len(pom_stubs),
                "project_generated": project is not None,
                "framework": framework,
                "language": language,
                "automation_lib": automation_lib,
                "pom_language": pom_language,
                "selectors_injected": len(selector_map) if selector_map else 0,
                "validation_warnings": validation_warnings,
                "specification_versions": specification_versions or {},
                "quarantined_test_cases": quarantined_test_cases or [],
            },
        )

    def get_capabilities(self) -> AgentCapabilities:
        """Return agent capabilities for pipeline discovery."""
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["TestCaseArtifact"],
            output_types=[
                "FeatureFileArtifact",
                "StepDefinitionArtifact",
                "PageObjectStub",
                "ScaffoldedProject",
            ],
            description=(
                "Generates BDD feature files and step definition skeletons "
                "from test case artifacts. Supports Behave, Pytest-BDD, "
                "Cucumber (Java), and Cucumber.js."
            ),
            required_skills=["coding_standards", "test_design_principles"],
            default_model_tier="lightweight",
        )
