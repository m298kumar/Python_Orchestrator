"""Tests for the EnrichmentAgent."""

from __future__ import annotations

from stlc_platform.agents.enrichment_agent.agent import EnrichmentAgent
from stlc_platform.core.base_agent import AgentCapabilities
from stlc_platform.core.contracts import (
    DiscrepancyArtifact,
    DiscrepancyReportArtifact,
    TestCaseArtifact,
)


def _make_tc(tc_id: str = "TC-0001", req_id: str = "REQ-001") -> TestCaseArtifact:
    return TestCaseArtifact(
        tc_id=tc_id,
        req_id=req_id,
        title="Existing TC",
        description="Already generated",
        preconditions="Preconditions",
        test_type="positive",
        priority="High",
    )


def _make_report(n_items: int = 2) -> DiscrepancyReportArtifact:
    items = []
    for i in range(n_items):
        items.append(DiscrepancyArtifact(
            discrepancy_type="missing_element",
            requirement_id=f"REQ-{i + 1:03d}",
            expected=f"Submit button #{i + 1}",
            actual="Element not found",
            severity="warning",
            page_url=f"https://app.test/page{i + 1}",
            details=f"Expected submit button #{i + 1} on page{i + 1}",
        ))
    return DiscrepancyReportArtifact(
        total_discrepancies=n_items,
        items=items,
    )


class TestValidateInput:

    def test_validate_input_with_test_cases(self):
        agent = EnrichmentAgent()
        result = agent.validate_input({"test_cases": [_make_tc()]})
        assert result.valid is True

    def test_validate_input_missing_test_cases(self):
        agent = EnrichmentAgent()
        result = agent.validate_input({})
        assert result.valid is False
        assert any("test_cases" in e for e in result.errors)


class TestExecute:

    def test_passthrough_without_discrepancies(self):
        agent = EnrichmentAgent()
        tcs = [_make_tc("TC-001"), _make_tc("TC-002")]
        result = agent.execute({"test_cases": tcs}, {})
        assert result.success is True
        assert len(result.artifacts["test_cases"]) == 2
        assert result.metadata["discrepancy_tcs_added"] == 0

    def test_enrichment_adds_discrepancy_tcs(self):
        agent = EnrichmentAgent()
        tcs = [_make_tc()]
        report = _make_report(n_items=3)
        result = agent.execute({"test_cases": tcs, "discrepancy_report": report}, {})
        assert result.success is True
        assert len(result.artifacts["test_cases"]) == 4  # 1 original + 3 discrepancy
        assert result.metadata["discrepancy_tcs_added"] == 3
        assert result.metadata["original_count"] == 1

    def test_discrepancy_tc_has_correct_tags(self):
        agent = EnrichmentAgent()
        report = _make_report(n_items=1)
        result = agent.execute({"test_cases": [], "discrepancy_report": report}, {})
        disc_tc = result.artifacts["test_cases"][0]
        assert "discrepancy" in disc_tc.tags
        assert "auto-generated" in disc_tc.tags
        assert "missing_element" in disc_tc.tags

    def test_discrepancy_tc_has_meaningful_content(self):
        agent = EnrichmentAgent()
        report = _make_report(n_items=1)
        result = agent.execute({"test_cases": [], "discrepancy_report": report}, {})
        disc_tc = result.artifacts["test_cases"][0]
        assert disc_tc.tc_id.startswith("TC-DISC-")
        assert "Submit button" in disc_tc.title
        assert disc_tc.req_id == "REQ-001"
        assert len(disc_tc.steps) >= 2
        assert disc_tc.given != ""
        assert disc_tc.when != ""
        assert disc_tc.then != ""

    def test_metadata_counts_correct(self):
        agent = EnrichmentAgent()
        tcs = [_make_tc("TC-001"), _make_tc("TC-002")]
        report = _make_report(n_items=2)
        result = agent.execute({"test_cases": tcs, "discrepancy_report": report}, {})
        assert result.metadata["original_count"] == 2
        assert result.metadata["discrepancy_tcs_added"] == 2

    def test_empty_report_items_passthrough(self):
        agent = EnrichmentAgent()
        tcs = [_make_tc()]
        report = DiscrepancyReportArtifact()  # no items
        result = agent.execute({"test_cases": tcs, "discrepancy_report": report}, {})
        assert len(result.artifacts["test_cases"]) == 1
        assert result.metadata["discrepancy_tcs_added"] == 0


class TestGetCapabilities:

    def test_get_capabilities(self):
        agent = EnrichmentAgent()
        caps = agent.get_capabilities()
        assert isinstance(caps, AgentCapabilities)
        assert caps.agent_id == "enrich_test_cases"
        assert "test_cases" in caps.input_types
        assert "test_cases" in caps.output_types
