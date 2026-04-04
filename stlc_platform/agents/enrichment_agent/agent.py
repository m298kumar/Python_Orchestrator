"""
Enrichment Agent
================
Cross-agent feedback: takes existing test cases and a discrepancy report
(from the crawler agent) and synthesises additional test cases that verify
each discrepancy.  All original test cases pass through unchanged.

This is an optional enrichment stage — if no discrepancy report is supplied
the agent simply returns the original test cases as-is.
"""

from __future__ import annotations

from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.contracts import (
    DiscrepancyArtifact,
    DiscrepancyReportArtifact,
    TestCaseArtifact,
    TestStepArtifact,
)

# Mapping from discrepancy_type to a human-readable verb used in TC titles
_TYPE_LABELS: Dict[str, str] = {
    "missing_element": "Missing UI element",
    "missing_page": "Missing page",
    "missing_form_field": "Missing form field",
    "broken_link": "Broken link",
    "unexpected_page": "Unexpected page",
}

_SEVERITY_TO_PRIORITY: Dict[str, str] = {
    "show_stopper": "Critical",
    "warning": "High",
    "info": "Medium",
}


class EnrichmentAgent(BaseAgent):
    """
    Enriches a test-case list with additional TCs derived from crawler
    discrepancies so that every gap between requirements and the live
    application is covered by at least one test case.
    """

    agent_id: str = "enrich_test_cases"
    agent_version: str = "1.0.0"

    # ── BaseAgent interface ───────────────────────────────────────────

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        """Validate input artifacts.

        ``test_cases`` is required; ``discrepancy_report`` is optional.
        """
        errors: List[str] = []
        warnings: List[str] = []

        test_cases = artifacts.get("test_cases")
        if test_cases is None:
            errors.append("'test_cases' is required.")
        elif not isinstance(test_cases, list):
            errors.append("'test_cases' must be a list.")

        disc = artifacts.get("discrepancy_report")
        if disc is not None and not isinstance(disc, DiscrepancyReportArtifact):
            warnings.append(
                "'discrepancy_report' should be a DiscrepancyReportArtifact."
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def execute(self, artifacts: Dict[str, Any], config: Dict[str, Any]) -> AgentResult:
        """Enrich *test_cases* with discrepancy-derived TCs."""
        test_cases: List[TestCaseArtifact] = artifacts["test_cases"]
        discrepancy_report: DiscrepancyReportArtifact | None = artifacts.get(
            "discrepancy_report"
        )

        # Fast path: no discrepancies to process
        if not discrepancy_report or not discrepancy_report.items:
            return AgentResult(
                success=True,
                artifacts={"test_cases": list(test_cases)},
                metadata={
                    "original_count": len(test_cases),
                    "discrepancy_tcs_added": 0,
                },
            )

        enriched: List[TestCaseArtifact] = list(test_cases)
        next_number = len(enriched) + 1

        # Track which TC IDs are from original vs. discrepancy sources
        original_ids = [getattr(tc, "tc_id", "") for tc in test_cases]
        discrepancy_ids: List[str] = []

        for disc in discrepancy_report.items:
            tc = self._synthesize_discrepancy_tc(disc, next_number)
            enriched.append(tc)
            discrepancy_ids.append(tc.tc_id)
            next_number += 1

        return AgentResult(
            success=True,
            artifacts={"test_cases": enriched},
            metadata={
                "original_count": len(test_cases),
                "discrepancy_tcs_added": len(discrepancy_ids),
                "original_tc_ids": original_ids,
                "discrepancy_tc_ids": discrepancy_ids,
            },
        )

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            input_types=["test_cases", "discrepancy_report"],
            output_types=["test_cases"],
            description=(
                "Cross-agent enrichment: adds test cases for every crawler "
                "discrepancy so that gaps between requirements and the live "
                "application are covered."
            ),
            default_model_tier="lightweight",
        )

    # ── Internal helpers ──────────────────────────────────────────────

    def _synthesize_discrepancy_tc(
        self, disc: DiscrepancyArtifact, tc_number: int
    ) -> TestCaseArtifact:
        """Create a ``TestCaseArtifact`` from a single discrepancy."""
        disc_type = disc.discrepancy_type
        label = _TYPE_LABELS.get(disc_type, disc_type.replace("_", " ").title())
        priority = _SEVERITY_TO_PRIORITY.get(disc.severity, "Medium")

        title = f"Verify {label}: {disc.expected}"
        description = disc.details or f"{label} — expected: {disc.expected}, actual: {disc.actual}"

        # Build concrete test steps from the discrepancy fields
        steps = self._build_steps(disc)

        # GWT triple for BDD consumption downstream
        given = f"the application page{' at ' + disc.page_url if disc.page_url else ''} is loaded"
        when = f"the tester checks for {disc.expected}"
        then = f"the element or page should be present (currently: {disc.actual})"

        return TestCaseArtifact(
            tc_id=f"TC-DISC-{tc_number:04d}",
            req_id=disc.requirement_id,
            title=title,
            description=description,
            preconditions=f"Application is accessible{' at ' + disc.page_url if disc.page_url else ''}",
            test_type="functional",
            priority=priority,
            steps=steps,
            expected_outcome=f"{disc.expected} is present and functional",
            tags=["discrepancy", "auto-generated", disc_type],
            category="discrepancy",
            component="",
            given=given,
            when=when,
            then=then,
            test_level="e2e",
        )

    @staticmethod
    def _build_steps(disc: DiscrepancyArtifact) -> List[TestStepArtifact]:
        """Return 2-3 concrete test steps for the discrepancy."""
        steps: List[TestStepArtifact] = []

        # Step 1: Navigate
        if disc.page_url:
            steps.append(
                TestStepArtifact(
                    action=f"Navigate to {disc.page_url}",
                    expected_result="Page loads successfully",
                )
            )
        else:
            steps.append(
                TestStepArtifact(
                    action="Navigate to the relevant application page",
                    expected_result="Page loads successfully",
                )
            )

        # Step 2: Look for the expected element / page / field
        steps.append(
            TestStepArtifact(
                action=f"Locate {disc.expected}",
                expected_result=f"{disc.expected} is visible and accessible",
            )
        )

        # Step 3: Verify behaviour
        steps.append(
            TestStepArtifact(
                action=f"Verify that {disc.expected} behaves as specified in requirement {disc.requirement_id}",
                expected_result=f"{disc.expected} meets the requirement specification",
            )
        )

        return steps
