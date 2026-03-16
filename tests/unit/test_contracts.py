"""
Tests for artifact contracts.
Validates that all Pydantic models work correctly with valid and invalid data.
"""

import pytest
from pydantic import ValidationError

from stlc_platform.core.contracts import (
    RequirementArtifact,
    TestCaseArtifact,
    TestStepArtifact,
    FeatureFileArtifact,
    SiteModelArtifact,
    APIModelArtifact,
    PipelineRunArtifact,
)


class TestRequirementArtifact:
    def test_create_minimal(self):
        r = RequirementArtifact(
            req_id="REQ-001", title="Test", description="A test requirement"
        )
        assert r.req_id == "REQ-001"
        assert r.priority == "Medium"
        assert r.category == "Functional"
        assert r.schema_version == "1.0"

    def test_create_full(self):
        r = RequirementArtifact(
            req_id="REQ-002",
            title="Login Feature",
            description="Users must log in",
            priority="High",
            category="Security",
            acceptance_criteria=["AC1", "AC2"],
            tags=["login"],
        )
        assert r.acceptance_criteria == ["AC1", "AC2"]
        assert r.tags == ["login"]

    def test_to_chroma_document(self):
        r = RequirementArtifact(
            req_id="REQ-001",
            title="Test",
            description="Desc",
            acceptance_criteria=["AC1"],
        )
        doc = r.to_chroma_document()
        assert "REQ-001" in doc
        assert "AC1" in doc

    def test_to_dict(self):
        r = RequirementArtifact(
            req_id="REQ-001", title="Test", description="Desc"
        )
        d = r.to_dict()
        assert d["req_id"] == "REQ-001"
        assert "schema_version" not in d

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            RequirementArtifact(req_id="REQ-001", title="Test")  # missing description


class TestTestCaseArtifact:
    def test_create_with_steps(self):
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test case",
            description="A test",
            preconditions="User logged in",
            test_type="positive",
            priority="High",
            steps=[
                TestStepArtifact(action="Click login", expected_result="Form appears")
            ],
        )
        assert len(tc.steps) == 1
        assert tc.steps[0].action == "Click login"

    def test_default_values(self):
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test",
            description="Desc",
            preconditions="Pre",
            test_type="positive",
            priority="High",
        )
        assert tc.steps == []
        assert tc.estimated_duration == "5"
        assert tc.given == ""

    def test_serialization_roundtrip(self):
        tc = TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Test",
            description="Desc",
            preconditions="Pre",
            test_type="positive",
            priority="High",
            steps=[TestStepArtifact(action="Act", expected_result="Res")],
        )
        json_str = tc.model_dump_json()
        tc2 = TestCaseArtifact.model_validate_json(json_str)
        assert tc2.tc_id == tc.tc_id
        assert len(tc2.steps) == 1


class TestPipelineRunArtifact:
    def test_create(self):
        pr = PipelineRunArtifact(
            run_id="run-001", pipeline_name="full_stlc"
        )
        assert pr.status == "pending"
        assert pr.stages_completed == []


class TestFeatureFileArtifact:
    def test_create(self):
        ff = FeatureFileArtifact(
            req_id="REQ-001",
            filename="login.feature",
            content="Feature: Login",
        )
        assert ff.scenario_count == 0


class TestSiteModelArtifact:
    def test_create_empty(self):
        sm = SiteModelArtifact(base_url="https://example.com")
        assert sm.pages == []


class TestAPIModelArtifact:
    def test_create_empty(self):
        am = APIModelArtifact()
        assert am.endpoints == []
