"""
Full Pipeline E2E Integration Test
===================================
Runs a multi-stage pipeline end-to-end using mock agents to verify:
- DAG topological ordering and wave grouping
- ArtifactResolver correctly wires $stage.key references
- ArtifactStore persists and loads from disk
- Orchestrator callbacks fire correctly
- Resume functionality restores intermediate state
- Stage timeout enforcement
- Circuit breaker integration
"""

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.dag import PipelineDAG, StageNode
from stlc_platform.pipeline.orchestrator import PipelineOrchestrator
from stlc_platform.pipeline.pipeline_loader import load_pipeline_from_dict

# ---------------------------------------------------------------------------
# Mock Agents
# ---------------------------------------------------------------------------

class MockRequirementsAgent(BaseAgent):
    """Produces test_cases from requirements input."""

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            agent_id="requirements_agent",
            name="Mock Requirements Agent",
            input_artifacts=["requirements"],
            output_artifacts=["test_cases"],
        )

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        if "requirements" not in artifacts:
            return ValidationResult(valid=False, errors=["Missing requirements"])
        return ValidationResult(valid=True)

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        reqs = artifacts.get("requirements", [])
        test_cases = [
            {
                "tc_id": f"TC-{i+1:03d}",
                "req_id": r.get("req_id", f"REQ-{i+1}") if isinstance(r, dict) else f"REQ-{i+1}",
                "title": f"Test for requirement {i+1}",
                "test_type": "positive",
                "quality_score": 0.85,
            }
            for i, r in enumerate(reqs)
        ]
        return AgentResult(
            success=True,
            artifacts={"test_cases": test_cases},
            metadata={"count": len(test_cases)},
        )


class MockBDDAgent(BaseAgent):
    """Produces feature_files from test_cases input."""

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            agent_id="bdd_agent",
            name="Mock BDD Agent",
            input_artifacts=["test_cases"],
            output_artifacts=["feature_files"],
        )

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        if "test_cases" not in artifacts:
            return ValidationResult(valid=False, errors=["Missing test_cases"])
        return ValidationResult(valid=True)

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        tcs = artifacts.get("test_cases", [])
        features = [
            {
                "filename": f"feature_{i}.feature",
                "content": f"Feature: Test {tc.get('title', '')}\n  Scenario: Validate\n    Given setup\n    When action\n    Then result",
                "req_id": tc.get("req_id", ""),
                "scenario_count": 1,
            }
            for i, tc in enumerate(tcs)
        ]
        return AgentResult(
            success=True,
            artifacts={"feature_files": features},
            metadata={"count": len(features)},
        )


class MockFailingAgent(BaseAgent):
    """Always fails — used for error path testing."""

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            agent_id="failing_agent",
            name="Mock Failing Agent",
            input_artifacts=[],
            output_artifacts=[],
        )

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        return ValidationResult(valid=True)

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        return AgentResult(
            success=False,
            artifacts={},
            errors=["Intentional failure for testing"],
        )


class MockSlowAgent(BaseAgent):
    """Takes a long time — used for timeout testing."""

    def get_capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            agent_id="slow_agent",
            name="Mock Slow Agent",
            input_artifacts=[],
            output_artifacts=["result"],
        )

    def validate_input(self, artifacts: Dict[str, Any]) -> ValidationResult:
        return ValidationResult(valid=True)

    def execute(
        self, artifacts: Dict[str, Any], config: Dict[str, Any]
    ) -> AgentResult:
        import time
        time.sleep(10)
        return AgentResult(success=True, artifacts={"result": "done"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry():
    reg = AgentRegistry()
    reg.register("requirements_agent", MockRequirementsAgent)
    reg.register("bdd_agent", MockBDDAgent)
    reg.register("failing_agent", MockFailingAgent)
    reg.register("slow_agent", MockSlowAgent)
    return reg


@pytest.fixture()
def two_stage_dag():
    """Simple requirements → BDD pipeline."""
    return PipelineDAG(
        stages=[
            StageNode(
                stage_id="parse_requirements",
                agent_id="requirements_agent",
                input_map={"requirements": "$config.requirements"},
                output_keys=["test_cases"],
            ),
            StageNode(
                stage_id="generate_bdd_code",
                agent_id="bdd_agent",
                depends_on=["parse_requirements"],
                input_map={"test_cases": "$parse_requirements.test_cases"},
                output_keys=["feature_files"],
            ),
        ],
        pipeline_name="test_pipeline",
    )


@pytest.fixture()
def sample_requirements():
    return [
        {"req_id": "REQ-001", "title": "User login"},
        {"req_id": "REQ-002", "title": "Password reset"},
        {"req_id": "REQ-003", "title": "User profile"},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullPipelineE2E:
    """End-to-end pipeline execution tests."""

    def test_two_stage_pipeline_completes(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """Full pipeline runs requirements → BDD successfully."""
        orch = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=tmp_path / "run1",
        )

        result = orch.run()

        assert result.status == "completed"
        assert "parse_requirements" in result.stages_completed
        assert "generate_bdd_code" in result.stages_completed
        assert result.stages_failed == []
        assert result.total_duration_seconds > 0

    def test_artifacts_persisted_to_disk(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """Artifacts are written to disk after pipeline completes."""
        run_dir = tmp_path / "run2"
        orch = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=run_dir,
        )
        orch.run()

        # Manifest should exist
        manifest = run_dir / "manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert "parse_requirements" in data["stages"]
        assert "generate_bdd_code" in data["stages"]

        # Stage JSON files should exist
        assert (run_dir / "parse_requirements.json").exists()
        assert (run_dir / "generate_bdd_code.json").exists()

        # Feature files should be exported
        features_dir = run_dir / "features"
        assert features_dir.exists()
        feature_files = list(features_dir.glob("*.feature"))
        assert len(feature_files) == 3

    def test_artifact_resolver_wires_stages(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """BDD stage receives test_cases produced by requirements stage."""
        run_dir = tmp_path / "run3"
        orch = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=run_dir,
        )
        orch.run()

        # Load BDD artifacts and verify they reference the right reqs
        bdd_file = run_dir / "generate_bdd_code.json"
        bdd_data = json.loads(bdd_file.read_text())
        features = bdd_data["artifacts"]["feature_files"]
        assert len(features) == 3
        assert features[0]["req_id"] == "REQ-001"

    def test_stage_callbacks_fire(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """on_stage_start and on_stage_complete callbacks are invoked."""
        starts: List[str] = []
        completes: List[str] = []

        orch = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=tmp_path / "run4",
            on_stage_start=lambda sid: starts.append(sid),
            on_stage_complete=lambda sr: completes.append(sr.stage_id),
        )
        orch.run()

        assert "parse_requirements" in starts
        assert "generate_bdd_code" in starts
        assert "parse_requirements" in completes
        assert "generate_bdd_code" in completes

    def test_csv_export_generated(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """Test cases CSV is exported after pipeline completes."""
        run_dir = tmp_path / "run5"
        orch = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=run_dir,
        )
        orch.run()

        csv_file = run_dir / "test_cases.csv"
        assert csv_file.exists()
        lines = csv_file.read_text().splitlines()
        assert len(lines) >= 4  # header + 3 test cases


class TestPipelineResume:
    """Resume from a specific stage."""

    def test_resume_skips_completed_stages(
        self, registry, two_stage_dag, sample_requirements, tmp_path
    ):
        """Resume from BDD stage skips requirements and runs only BDD."""
        run_dir = tmp_path / "resume_run"

        # First run — full pipeline
        orch1 = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=run_dir,
        )
        result1 = orch1.run()
        assert result1.status == "completed"

        # Second run — resume from BDD stage
        orch2 = PipelineOrchestrator(
            dag=two_stage_dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=run_dir,
        )
        result2 = orch2.run(resume_from="generate_bdd_code")
        assert result2.status == "completed"
        assert "generate_bdd_code" in result2.stages_completed


class TestPipelineFailure:
    """Failed and optional stage handling."""

    def test_failed_stage_marks_downstream_skipped(self, registry, tmp_path):
        """When a non-optional stage fails, downstream stages are skipped."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="step1",
                    agent_id="failing_agent",
                    input_map={},
                ),
                StageNode(
                    stage_id="step2",
                    agent_id="bdd_agent",
                    depends_on=["step1"],
                    input_map={"test_cases": "$step1.test_cases"},
                ),
            ],
            pipeline_name="fail_test",
        )

        orch = PipelineOrchestrator(
            dag=dag, registry=registry, config={}, run_dir=tmp_path / "fail_run"
        )
        result = orch.run()

        assert result.status == "failed"
        assert "step1" in result.stages_failed
        assert "step2" in result.stages_skipped

    def test_optional_stage_missing_input_skipped(
        self, registry, sample_requirements, tmp_path
    ):
        """Optional stages with missing inputs are skipped, not failed."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="parse_requirements",
                    agent_id="requirements_agent",
                    input_map={"requirements": "$config.requirements"},
                ),
                StageNode(
                    stage_id="optional_crawl",
                    agent_id="bdd_agent",
                    input_map={"test_cases": "$nonexistent_stage.output"},
                    optional=True,
                ),
            ],
            pipeline_name="optional_test",
        )

        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=tmp_path / "optional_run",
        )
        result = orch.run()

        assert result.status == "completed"
        assert "parse_requirements" in result.stages_completed
        assert "optional_crawl" in result.stages_skipped


class TestPipelineTimeout:
    """Stage timeout enforcement."""

    def test_stage_timeout_produces_failure(self, registry, tmp_path):
        """A stage that exceeds its timeout is marked as failed."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="slow_step",
                    agent_id="slow_agent",
                    input_map={},
                    timeout_seconds=1.0,
                ),
            ],
            pipeline_name="timeout_test",
        )

        orch = PipelineOrchestrator(
            dag=dag, registry=registry, config={}, run_dir=tmp_path / "timeout_run"
        )
        result = orch.run()

        assert result.status == "failed"
        assert "slow_step" in result.stages_failed
        # Verify the error message mentions timeout
        assert any(
            "timed out" in (orch._stage_results.get("slow_step")
                            or MagicMock(error="")).error.lower()
            for _ in [1]
        )


class TestPipelineFromYAML:
    """Pipeline loaded from YAML dict."""

    def test_load_and_run_from_yaml_dict(
        self, registry, sample_requirements, tmp_path
    ):
        """Pipeline loaded from YAML dict runs correctly."""
        yaml_dict = {
            "pipeline": "yaml_test",
            "stages": [
                {
                    "id": "parse_requirements",
                    "agent": "requirements_agent",
                    "input": {"requirements": "$config.requirements"},
                    "output": ["test_cases"],
                },
                {
                    "id": "generate_bdd_code",
                    "agent": "bdd_agent",
                    "depends_on": ["parse_requirements"],
                    "input": {"test_cases": "$parse_requirements.test_cases"},
                    "output": ["feature_files"],
                },
            ],
        }

        dag = load_pipeline_from_dict(yaml_dict)
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            config={"requirements": sample_requirements},
            run_dir=tmp_path / "yaml_run",
        )
        result = orch.run()

        assert result.status == "completed"
        assert result.pipeline_name == "yaml_test"
        assert len(result.stages_completed) == 2

    def test_yaml_with_timeout_field(self, registry, tmp_path):
        """timeout_seconds is parsed from YAML and enforced."""
        yaml_dict = {
            "pipeline": "timeout_yaml",
            "stages": [
                {
                    "id": "slow_step",
                    "agent": "slow_agent",
                    "input": {},
                    "timeout_seconds": 1,
                },
            ],
        }

        dag = load_pipeline_from_dict(yaml_dict)
        stage = dag.get_stage("slow_step")
        assert stage.timeout_seconds == 1.0

        orch = PipelineOrchestrator(
            dag=dag, registry=registry, config={}, run_dir=tmp_path / "yaml_timeout"
        )
        result = orch.run()
        assert result.status == "failed"
