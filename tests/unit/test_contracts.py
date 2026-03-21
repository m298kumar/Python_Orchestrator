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
    APIEndpointArtifact,
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


class TestAPIEndpointArtifact:
    def test_create_minimal(self):
        ep = APIEndpointArtifact(path="/api/users", method="GET")
        assert ep.path == "/api/users"
        assert ep.method == "GET"
        assert ep.path_params == []
        assert ep.query_params == []
        assert ep.auth_required is False
        assert ep.status_codes == []
        assert ep.example_request is None
        assert ep.example_response is None

    def test_example_request_response_preserved(self):
        """Bug fix: example_request/example_response were silently dropped."""
        req = {"name": "John", "email": "john@test.com"}
        resp = {"id": 1, "name": "John", "email": "john@test.com"}
        ep = APIEndpointArtifact(
            path="/api/users",
            method="POST",
            example_request=req,
            example_response=resp,
        )
        assert ep.example_request == req
        assert ep.example_response == resp

    def test_status_codes_accepts_ints(self):
        ep = APIEndpointArtifact(
            path="/api/users", method="GET", status_codes=[200, 404]
        )
        assert ep.status_codes == [200, 404]

    def test_status_codes_coerces_strings_to_ints(self):
        """Pydantic coerces string status codes to int."""
        ep = APIEndpointArtifact(
            path="/api/users", method="GET", status_codes=["200", "404"]
        )
        assert ep.status_codes == [200, 404]

    def test_serialization_roundtrip(self):
        ep = APIEndpointArtifact(
            path="/api/users/{id}",
            method="GET",
            path_params=[{"name": "id", "type": "integer"}],
            status_codes=[200, 404],
            example_request={"id": 1},
            example_response={"name": "John"},
            auth_required=True,
            auth_type="bearer",
        )
        json_str = ep.model_dump_json()
        ep2 = APIEndpointArtifact.model_validate_json(json_str)
        assert ep2.path == ep.path
        assert ep2.example_request == {"id": 1}
        assert ep2.example_response == {"name": "John"}
        assert ep2.status_codes == [200, 404]
        assert ep2.auth_required is True

    def test_backward_compatible_without_new_fields(self):
        """Old data without example_request/response still loads fine."""
        ep = APIEndpointArtifact.model_validate({
            "path": "/api/test",
            "method": "GET",
        })
        assert ep.example_request is None
        assert ep.example_response is None


class TestAPIModelArtifact:
    def test_create_empty(self):
        am = APIModelArtifact()
        assert am.endpoints == []
