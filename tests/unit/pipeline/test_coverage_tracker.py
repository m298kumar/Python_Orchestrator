"""Tests for the CoverageTracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from stlc_platform.pipeline.coverage_tracker import CoverageTracker


@dataclass
class _Req:
    req_id: str = "REQ-001"
    title: str = "Feature"
    description: str = "A feature"
    category: str = "General"
    acceptance_criteria: List[str] = field(
        default_factory=lambda: [
            "User can login with valid credentials",
            "System displays error for invalid password",
        ]
    )


@dataclass
class _Step:
    action: str = ""
    expected_result: str = ""


@dataclass
class _TC:
    tc_id: str = "TC-0001"
    req_id: str = "REQ-001"
    title: str = ""
    description: str = ""
    expected_outcome: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    test_type: str = "positive"
    quality_score: float = 0.8
    steps: List[_Step] = field(default_factory=list)


class TestCoverageTracker:
    def test_empty_requirements_returns_empty_report(self):
        tracker = CoverageTracker()
        report = tracker.analyze([], [])
        assert report.total_requirements == 0
        assert report.total_acs == 0
        assert report.overall_coverage == 0.0

    def test_empty_test_cases_all_uncovered(self):
        tracker = CoverageTracker()
        reqs = [_Req()]
        report = tracker.analyze(reqs, [])
        assert report.total_acs == 2
        assert len(report.uncovered_entries) == 2
        assert report.overall_coverage == 0.0

    def test_full_coverage_all_acs_matched(self):
        tracker = CoverageTracker()
        reqs = [_Req()]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="login with valid credentials works",
                steps=[_Step(action="Enter valid credentials and login")],
            ),
            _TC(
                tc_id="TC-002",
                description="system displays error for invalid password attempt",
                test_type="negative",
                steps=[_Step(action="Enter invalid password and observe error")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        assert len(report.uncovered_entries) == 0
        assert report.overall_coverage > 0

    def test_partial_coverage_some_uncovered(self):
        tracker = CoverageTracker()
        reqs = [_Req()]
        # Only covers first AC
        tcs = [
            _TC(
                tc_id="TC-001",
                description="login with valid credentials",
                steps=[_Step(action="Enter valid credentials and login")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        assert len(report.uncovered_entries) >= 1
        assert report.overall_coverage < 100.0

    def test_weak_coverage_low_quality(self):
        tracker = CoverageTracker(weak_quality_threshold=0.6)
        reqs = [_Req()]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="login with valid credentials",
                quality_score=0.3,
                steps=[_Step(action="Enter valid credentials")],
            ),
            _TC(
                tc_id="TC-002",
                description="system displays error for invalid password",
                quality_score=0.3,
                steps=[_Step(action="Enter invalid password and see error")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        assert len(report.weak_entries) >= 1

    def test_weak_coverage_single_tc(self):
        tracker = CoverageTracker()
        reqs = [_Req(acceptance_criteria=["User can login with valid credentials"])]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="login with valid credentials",
                quality_score=0.9,
                steps=[_Step(action="Enter valid credentials and login")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        # Single TC covering an AC = weak
        assert len(report.weak_entries) == 1

    def test_coverage_percentage_calculation(self):
        tracker = CoverageTracker()
        reqs = [_Req(acceptance_criteria=["AC one about login", "AC two about payment"])]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="test login flow",
                steps=[_Step(action="login to application")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        # 1 of 2 covered = 50%
        assert 40.0 <= report.overall_coverage <= 60.0

    def test_keyword_matching_finds_relevant_tc(self):
        tracker = CoverageTracker(match_threshold=0.3)
        reqs = [
            _Req(acceptance_criteria=["System validates email address format before submission"])
        ]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="validate email address format",
                steps=[_Step(action="Enter email and submit for validation")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        assert len(report.uncovered_entries) == 0

    def test_keyword_matching_rejects_unrelated_tc(self):
        tracker = CoverageTracker(match_threshold=0.3)
        reqs = [
            _Req(acceptance_criteria=["System validates email address format before submission"])
        ]
        tcs = [
            _TC(
                tc_id="TC-001",
                description="navigate to dashboard and check widgets",
                steps=[_Step(action="Click on dashboard link")],
            ),
        ]
        report = tracker.analyze(reqs, tcs)
        assert len(report.uncovered_entries) == 1

    def test_multiple_requirements_mixed_coverage(self):
        tracker = CoverageTracker()
        reqs = [
            _Req(req_id="REQ-001", acceptance_criteria=["User can login with valid credentials"]),
            _Req(req_id="REQ-002", acceptance_criteria=["Admin can delete user accounts"]),
        ]
        tcs = [
            _TC(
                tc_id="TC-001",
                req_id="REQ-001",
                description="login with valid credentials",
                steps=[_Step(action="Enter valid credentials and login")],
            ),
            # No TC for REQ-002
        ]
        report = tracker.analyze(reqs, tcs)
        assert report.total_acs == 2
        assert len(report.uncovered_entries) == 1
        assert report.uncovered_entries[0].req_id == "REQ-002"
