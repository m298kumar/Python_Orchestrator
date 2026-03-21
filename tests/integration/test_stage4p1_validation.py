"""
Stage 4 Phase 1 Integration Tests
===================================
Pipeline DAG execution, artifact flow, resume, CLI, parallel execution,
failure handling, retry, and CI mode.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from click.testing import CliRunner

from stlc_platform.core.base_agent import AgentResult, BaseAgent, ValidationResult
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.dag import PipelineDAG, StageNode
from stlc_platform.pipeline.orchestrator import PipelineOrchestrator


# ── Mock Agents ──────────────────────────────────────────────────────────────


class MockPassAgent(BaseAgent):
    agent_id = "mock_pass"
    agent_version = "1.0.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=True,
            artifacts={"output": f"result_from_{self.agent_id}"},
            metadata={"processed": True},
        )


class MockSlowAgent(BaseAgent):
    agent_id = "mock_slow"
    agent_version = "1.0.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        time.sleep(0.3)
        return AgentResult(
            success=True,
            artifacts={"output": "slow_result"},
            metadata={"slow": True},
        )


class MockFailAgent(BaseAgent):
    agent_id = "mock_fail"
    agent_version = "1.0.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=False,
            errors=["Simulated failure"],
        )


_fail_count = 0


class MockRetryAgent(BaseAgent):
    """Fails on first call, succeeds on retry."""

    agent_id = "mock_retry"
    agent_version = "1.0.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        global _fail_count
        _fail_count += 1
        if _fail_count <= 1:
            return AgentResult(success=False, errors=["Transient failure"])
        return AgentResult(
            success=True,
            artifacts={"output": "recovered"},
        )


def _mock_registry(*agent_pairs):
    """Create a registry with mock agents."""
    registry = AgentRegistry()
    for agent_id, agent_class in agent_pairs:
        registry.register(agent_id, agent_class)
    return registry


# ── Full Pipeline with Mock Agents ──────────────────────────────────────────


class TestFullPipelineWithMockAgents:
    def test_wave_ordering_and_artifact_flow(self):
        dag = PipelineDAG([
            StageNode(stage_id="s1", agent_id="pass_a", input_map={}, output_keys=["output"]),
            StageNode(stage_id="s2", agent_id="pass_b", depends_on=["s1"],
                      input_map={"data": "$s1.output"}, output_keys=["output"]),
        ], pipeline_name="test")

        registry = _mock_registry(("pass_a", MockPassAgent), ("pass_b", MockPassAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry)
        result = orch.run()

        assert result.status == "completed"
        assert "s1" in result.stages_completed
        assert "s2" in result.stages_completed
        assert result.total_duration_seconds >= 0

    def test_parallel_execution_actually_concurrent(self):
        dag = PipelineDAG([
            StageNode(stage_id="slow_a", agent_id="slow", input_map={}),
            StageNode(stage_id="slow_b", agent_id="slow", input_map={}),
        ], pipeline_name="parallel_test")

        registry = _mock_registry(("slow", MockSlowAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry, max_workers=2)

        t0 = time.monotonic()
        result = orch.run()
        elapsed = time.monotonic() - t0

        assert result.status == "completed"
        assert len(result.stages_completed) == 2
        # Two 0.3s stages should complete in < 0.8s if parallel
        assert elapsed < 0.8, f"Elapsed {elapsed:.2f}s — not parallel"


# ── Resume From Mid-Stage ───────────────────────────────────────────────────


class TestResumeFromMidStage:
    def test_resume_skips_completed_stages(self, tmp_path: Path):
        dag = PipelineDAG([
            StageNode(stage_id="s1", agent_id="pass", input_map={}, output_keys=["output"]),
            StageNode(stage_id="s2", agent_id="pass", depends_on=["s1"],
                      input_map={"data": "$s1.output"}, output_keys=["output"]),
            StageNode(stage_id="s3", agent_id="pass", depends_on=["s2"],
                      input_map={"data": "$s2.output"}, output_keys=["output"]),
        ], pipeline_name="resume_test")

        registry = _mock_registry(("pass", MockPassAgent))
        run_dir = tmp_path / "run"

        # First run: complete all stages
        orch1 = PipelineOrchestrator(dag=dag, registry=registry, run_dir=run_dir)
        r1 = orch1.run()
        assert r1.status == "completed"
        assert len(r1.stages_completed) == 3

        # Second run: resume from s3
        orch2 = PipelineOrchestrator(dag=dag, registry=registry, run_dir=run_dir)
        r2 = orch2.run(resume_from="s3")
        assert r2.status == "completed"
        # s1 and s2 loaded from disk, s3 re-executed
        assert "s3" in r2.stages_completed


# ── CLI Tests ───────────────────────────────────────────────────────────────


class TestCLI:
    def test_agents_list_command(self):
        from stlc_platform.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["agents", "list"])
        assert result.exit_code == 0
        assert "bdd_generation" in result.output
        assert "api_test_generation" in result.output
        assert "4 agents registered" in result.output

    def test_run_requires_pipeline_or_agent(self):
        from stlc_platform.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["run"])
        assert result.exit_code == 1
        assert "Specify --pipeline or --agent" in result.output


# ── Failure Handling ────────────────────────────────────────────────────────


class TestFailureHandling:
    def test_failed_stage_skips_downstream(self):
        dag = PipelineDAG([
            StageNode(stage_id="s1", agent_id="fail", input_map={}),
            StageNode(stage_id="s2", agent_id="pass", depends_on=["s1"],
                      input_map={"data": "$s1.output"}),
        ], pipeline_name="fail_test")

        registry = _mock_registry(("fail", MockFailAgent), ("pass", MockPassAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry)
        result = orch.run()

        assert result.status == "failed"
        assert "s1" in result.stages_failed
        assert "s2" in result.stages_skipped

    def test_optional_failure_does_not_skip_independent(self):
        dag = PipelineDAG([
            StageNode(stage_id="opt", agent_id="fail", input_map={}, optional=True),
            StageNode(stage_id="ind", agent_id="pass", input_map={}),
        ], pipeline_name="opt_test")

        registry = _mock_registry(("fail", MockFailAgent), ("pass", MockPassAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry)
        result = orch.run()

        # opt failed but ind is independent — should still complete
        assert "ind" in result.stages_completed


# ── Retry Policy ────────────────────────────────────────────────────────────


class TestRetryPolicy:
    def test_retry_succeeds_on_second_attempt(self):
        global _fail_count
        _fail_count = 0

        dag = PipelineDAG([
            StageNode(stage_id="r1", agent_id="retry", input_map={}, retry_count=1),
        ], pipeline_name="retry_test")

        registry = _mock_registry(("retry", MockRetryAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry)
        result = orch.run()

        assert result.status == "completed"
        assert "r1" in result.stages_completed


# ── CI Mode ─────────────────────────────────────────────────────────────────


class TestCIMode:
    def test_dag_validation_returns_json_compatible_result(self):
        """Verify PipelineRunArtifact is JSON-serializable (CI output)."""
        dag = PipelineDAG([
            StageNode(stage_id="s1", agent_id="pass", input_map={}),
        ], pipeline_name="ci_test")

        registry = _mock_registry(("pass", MockPassAgent))
        orch = PipelineOrchestrator(dag=dag, registry=registry)
        result = orch.run()

        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["status"] == "completed"
        assert parsed["pipeline_name"] == "ci_test"
        assert "total_duration_seconds" in parsed
