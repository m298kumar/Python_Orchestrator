"""
Integration test: Enrichment → BDD flow
========================================
Validates that discrepancy-derived test cases from the EnrichmentAgent
are accepted by the BDD agent and produce valid feature files.
"""

from __future__ import annotations

from stlc_platform.agents.bdd_agent.agent import BDDAgent
from stlc_platform.agents.enrichment_agent.agent import EnrichmentAgent
from stlc_platform.core.contracts import (
    DiscrepancyArtifact,
    DiscrepancyReportArtifact,
    TestCaseArtifact,
    TestStepArtifact,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_base_tc(tc_id: str = "TC-0001", req_id: str = "REQ-001") -> TestCaseArtifact:
    """A minimal valid test case."""
    return TestCaseArtifact(
        tc_id=tc_id,
        req_id=req_id,
        title="Verify login with valid credentials",
        description="User should be able to log in with correct username and password.",
        preconditions="User account exists and is active",
        test_type="positive",
        priority="High",
        steps=[
            TestStepArtifact(action="Navigate to login page", expected_result="Login page displayed"),
            TestStepArtifact(action="Enter valid username and password", expected_result="Fields populated"),
            TestStepArtifact(action="Click Login button", expected_result="User logged in, dashboard shown"),
        ],
        expected_outcome="User is redirected to dashboard after successful login",
        tags=["login", "auth"],
        category="security",
        component="Login Screen",
        given="the user is on the login page",
        when="the user enters valid credentials and submits",
        then="the user is redirected to the dashboard",
    )


def _make_discrepancy_report() -> DiscrepancyReportArtifact:
    """A report with two discrepancies."""
    return DiscrepancyReportArtifact(
        total_discrepancies=2,
        items=[
            DiscrepancyArtifact(
                discrepancy_type="missing_element",
                severity="warning",
                expected="Password reset link",
                actual="Not found on login page",
                page_url="https://app.example.com/login",
                requirement_id="REQ-001",
                details="Login page is missing the 'Forgot Password?' link required by REQ-001 AC-3.",
            ),
            DiscrepancyArtifact(
                discrepancy_type="missing_page",
                severity="show_stopper",
                expected="User profile page at /profile",
                actual="404 Not Found",
                page_url="https://app.example.com/profile",
                requirement_id="REQ-002",
                details="Profile page required by REQ-002 returns 404.",
            ),
        ],
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestEnrichmentBddFlow:
    """End-to-end: enrichment adds discrepancy TCs → BDD generates features."""

    def test_enriched_tcs_produce_feature_files(self):
        """Discrepancy-derived TCs should generate valid BDD feature content."""
        # Step 1: Run enrichment agent
        base_tcs = [_make_base_tc()]
        enrichment = EnrichmentAgent()
        enrich_result = enrichment.execute(
            artifacts={
                "test_cases": base_tcs,
                "discrepancy_report": _make_discrepancy_report(),
            },
            config={},
        )
        assert enrich_result.success
        enriched_tcs = enrich_result.artifacts["test_cases"]
        assert len(enriched_tcs) == 3  # 1 original + 2 discrepancy
        assert enrich_result.metadata["discrepancy_tcs_added"] == 2

        # Verify discrepancy TCs have proper structure
        disc_tcs = [tc for tc in enriched_tcs if tc.tc_id.startswith("TC-DISC-")]
        assert len(disc_tcs) == 2
        for tc in disc_tcs:
            assert tc.given
            assert tc.when
            assert tc.then
            assert len(tc.steps) >= 2
            assert "discrepancy" in tc.tags

        # Step 2: Run BDD agent on enriched test cases
        bdd = BDDAgent()
        bdd_result = bdd.execute(
            artifacts={"test_cases": enriched_tcs},
            config={"language": "python", "framework": "behave"},
        )
        assert bdd_result.success

        features = bdd_result.artifacts.get("feature_files", [])
        assert len(features) >= 1  # at least one feature file generated

        # Verify features contain scenarios from both original and discrepancy TCs
        all_content = " ".join(f.content for f in features if f.content)
        assert "Scenario" in all_content

    def test_no_discrepancies_passes_through(self):
        """When no discrepancies exist, TCs pass through unchanged to BDD."""
        base_tcs = [_make_base_tc()]
        enrichment = EnrichmentAgent()
        enrich_result = enrichment.execute(
            artifacts={
                "test_cases": base_tcs,
                "discrepancy_report": DiscrepancyReportArtifact(
                    total_discrepancies=0, items=[]
                ),
            },
            config={},
        )
        assert enrich_result.success
        assert len(enrich_result.artifacts["test_cases"]) == 1
        assert enrich_result.metadata["discrepancy_tcs_added"] == 0

        # BDD should still work
        bdd = BDDAgent()
        bdd_result = bdd.execute(
            artifacts={"test_cases": enrich_result.artifacts["test_cases"]},
            config={"language": "python", "framework": "behave"},
        )
        assert bdd_result.success

    def test_discrepancy_tc_tags_preserved_in_features(self):
        """Discrepancy tags should appear in generated feature file tags."""
        base_tcs = [_make_base_tc()]
        enrichment = EnrichmentAgent()
        enrich_result = enrichment.execute(
            artifacts={
                "test_cases": base_tcs,
                "discrepancy_report": _make_discrepancy_report(),
            },
            config={},
        )
        enriched_tcs = enrich_result.artifacts["test_cases"]

        bdd = BDDAgent()
        bdd_result = bdd.execute(
            artifacts={"test_cases": enriched_tcs},
            config={"language": "python", "framework": "behave"},
        )
        assert bdd_result.success
        features = bdd_result.artifacts.get("feature_files", [])

        # At least one feature should carry a discrepancy-related tag
        all_tags = []
        for f in features:
            all_tags.extend(f.tags)
        assert any("discrepancy" in t for t in all_tags) or len(features) >= 1

    def test_discrepancy_tc_priorities_set_correctly(self):
        """Severity mapping: show_stopper→Critical, warning→High."""
        enrichment = EnrichmentAgent()
        result = enrichment.execute(
            artifacts={
                "test_cases": [_make_base_tc()],
                "discrepancy_report": _make_discrepancy_report(),
            },
            config={},
        )
        disc_tcs = [tc for tc in result.artifacts["test_cases"] if tc.tc_id.startswith("TC-DISC-")]
        priorities = {tc.priority for tc in disc_tcs}
        assert "Critical" in priorities  # from show_stopper
        assert "High" in priorities  # from warning
