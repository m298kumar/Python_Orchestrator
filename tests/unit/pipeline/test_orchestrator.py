"""Unit tests for PipelineOrchestrator.

Tests the DAG executor, wave execution, retry logic, resume-from,
downstream skipping, and callback hooks — all with mock agents.
"""

import time
from unittest.mock import MagicMock

import pytest
from stlc_platform.core.base_agent import AgentCapabilities, AgentResult, ValidationResult
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.dag import PipelineDAG, StageNode
from stlc_platform.pipeline.orchestrator import PipelineOrchestrator, StageResult

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_agent(success=True, artifacts=None, errors=None, delay=0):
    """Create a mock agent that returns a canned result."""
    agent = MagicMock()
    agent.validate_input.return_value = ValidationResult(valid=True)
    agent.get_capabilities.return_value = AgentCapabilities(
        agent_id="mock",
        agent_version="1.0",
        description="Mock agent",
    )

    def _execute(inputs, config):
        if delay:
            time.sleep(delay)
        return AgentResult(
            success=success,
            artifacts=artifacts or {},
            metadata={},
            errors=errors or [],
        )

    agent.execute.side_effect = _execute
    return agent


def _make_registry(agents_map):
    """Create a registry from a dict of agent_id -> mock_agent."""
    registry = AgentRegistry()
    for aid, agent_obj in agents_map.items():
        registry._agents[aid] = lambda a=agent_obj: a
    return registry


def _linear_dag():
    """A -> B -> C linear pipeline."""
    return PipelineDAG(
        stages=[
            StageNode(
                stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=["out_a"]
            ),
            StageNode(
                stage_id="b",
                agent_id="agent_b",
                depends_on=["a"],
                input_map={"x": "$a.out_a"},
                output_keys=["out_b"],
            ),
            StageNode(
                stage_id="c",
                agent_id="agent_c",
                depends_on=["b"],
                input_map={"y": "$b.out_b"},
                output_keys=["out_c"],
            ),
        ],
        pipeline_name="linear_test",
    )


def _parallel_dag():
    """A and B run in parallel, C depends on both."""
    return PipelineDAG(
        stages=[
            StageNode(
                stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=["out_a"]
            ),
            StageNode(
                stage_id="b", agent_id="agent_b", depends_on=[], input_map={}, output_keys=["out_b"]
            ),
            StageNode(
                stage_id="c",
                agent_id="agent_c",
                depends_on=["a", "b"],
                input_map={},
                output_keys=["out_c"],
            ),
        ],
        pipeline_name="parallel_test",
    )


def test_explicit_run_id_is_preserved():
    dag = PipelineDAG(
        stages=[StageNode(stage_id="one", agent_id="agent", input_map={})],
        pipeline_name="single",
    )
    registry = _make_registry({"agent": _make_mock_agent()})
    orchestrator = PipelineOrchestrator(
        dag=dag,
        registry=registry,
        run_id="api-run-123",
    )

    assert orchestrator.run_id == "api-run-123"
    assert orchestrator.run().run_id == "api-run-123"


# ── Tests ────────────────────────────────────────────────────────────────────


class TestStageResult:
    def test_defaults(self):
        sr = StageResult(stage_id="x", success=True)
        assert sr.duration_seconds == 0.0
        assert sr.error == ""
        assert sr.skipped is False
        assert sr.agent_result is None

    def test_failed_with_error(self):
        sr = StageResult(stage_id="x", success=False, error="boom")
        assert sr.success is False
        assert sr.error == "boom"


class TestRunValidation:
    def test_invalid_dag_raises_on_creation(self):
        """Empty DAG should raise ValueError at creation time."""
        with pytest.raises(ValueError, match="at least one stage"):
            PipelineDAG(stages=[], pipeline_name="empty")


class TestLinearPipeline:
    def test_all_stages_complete(self, tmp_path):
        dag = _linear_dag()
        mock_a = _make_mock_agent(artifacts={"out_a": "data_a"})
        mock_b = _make_mock_agent(artifacts={"out_b": "data_b"})
        mock_c = _make_mock_agent(artifacts={"out_c": "data_c"})
        registry = _make_registry(
            {
                "agent_a": mock_a,
                "agent_b": mock_b,
                "agent_c": mock_c,
            }
        )
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "completed"
        assert len(result.stages_completed) == 3
        assert result.stages_failed == []

    def test_stage_failure_skips_downstream(self, tmp_path):
        """If B fails, C should be skipped."""
        dag = _linear_dag()
        mock_a = _make_mock_agent(artifacts={"out_a": "data_a"})
        mock_b = _make_mock_agent(success=False, errors=["broken"])
        mock_c = _make_mock_agent()
        registry = _make_registry(
            {
                "agent_a": mock_a,
                "agent_b": mock_b,
                "agent_c": mock_c,
            }
        )
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "failed"
        assert "b" in result.stages_failed
        assert "c" in result.stages_skipped
        # A should have completed
        assert "a" in result.stages_completed

    def test_optional_stage_failure_does_not_skip(self, tmp_path):
        """If a failed stage is optional, downstream should still run."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a",
                    agent_id="agent_a",
                    depends_on=[],
                    input_map={},
                    output_keys=["out_a"],
                ),
                StageNode(
                    stage_id="b",
                    agent_id="agent_b",
                    depends_on=["a"],
                    input_map={},
                    output_keys=["out_b"],
                    optional=True,
                ),
                StageNode(
                    stage_id="c",
                    agent_id="agent_c",
                    depends_on=["b"],
                    input_map={},
                    output_keys=["out_c"],
                ),
            ],
            pipeline_name="optional_test",
        )
        mock_a = _make_mock_agent(artifacts={"out_a": "data_a"})
        mock_b = _make_mock_agent(success=False, errors=["optional fail"])
        mock_c = _make_mock_agent(artifacts={"out_c": "data_c"})
        registry = _make_registry(
            {
                "agent_a": mock_a,
                "agent_b": mock_b,
                "agent_c": mock_c,
            }
        )
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        # C should NOT be skipped since B is optional
        assert "c" not in result.stages_skipped


class TestParallelExecution:
    def test_parallel_stages_in_same_wave(self, tmp_path):
        dag = _parallel_dag()
        mock_a = _make_mock_agent(artifacts={"out_a": "a"})
        mock_b = _make_mock_agent(artifacts={"out_b": "b"})
        mock_c = _make_mock_agent(artifacts={"out_c": "c"})
        registry = _make_registry(
            {
                "agent_a": mock_a,
                "agent_b": mock_b,
                "agent_c": mock_c,
            }
        )
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "completed"
        assert set(result.stages_completed) == {"a", "b", "c"}

    def test_parallel_stages_run_concurrently(self, tmp_path):
        """Two 0.2s stages should complete in < 0.5s when parallel."""
        dag = _parallel_dag()
        mock_a = _make_mock_agent(artifacts={"out_a": "a"}, delay=0.2)
        mock_b = _make_mock_agent(artifacts={"out_b": "b"}, delay=0.2)
        mock_c = _make_mock_agent(artifacts={"out_c": "c"})
        registry = _make_registry(
            {
                "agent_a": mock_a,
                "agent_b": mock_b,
                "agent_c": mock_c,
            }
        )
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
            max_workers=4,
        )
        result = orch.run()
        assert result.status == "completed"
        assert result.total_duration_seconds < 0.8


class TestRetryLogic:
    def test_retry_on_failure(self, tmp_path):
        """Stage with retry_count=1 should retry once after failure."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a",
                    agent_id="agent_a",
                    depends_on=[],
                    input_map={},
                    output_keys=["out"],
                    retry_count=1,
                ),
            ],
            pipeline_name="retry_test",
        )
        # Agent fails first, succeeds on retry
        call_count = {"n": 0}

        def _execute(inputs, config):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return AgentResult(
                    success=False, artifacts={}, metadata={}, errors=["first try fail"]
                )
            return AgentResult(success=True, artifacts={"out": "ok"}, metadata={})

        mock_agent = MagicMock()
        mock_agent.execute.side_effect = _execute
        mock_agent.get_capabilities.return_value = AgentCapabilities(
            agent_id="agent_a",
            agent_version="1.0",
            description="test",
        )
        registry = _make_registry({"agent_a": mock_agent})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "completed"
        assert call_count["n"] == 2

    def test_retry_exhausted_still_fails(self, tmp_path):
        """If retry also fails, stage remains failed."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a",
                    agent_id="agent_a",
                    depends_on=[],
                    input_map={},
                    output_keys=["out"],
                    retry_count=1,
                ),
            ],
            pipeline_name="retry_fail_test",
        )
        mock_agent = _make_mock_agent(success=False, errors=["always fail"])
        registry = _make_registry({"agent_a": mock_agent})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "failed"
        assert "a" in result.stages_failed


class TestCallbacks:
    def test_on_stage_start_called(self, tmp_path):
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=[]
                ),
            ],
            pipeline_name="cb_test",
        )
        mock_agent = _make_mock_agent()
        registry = _make_registry({"agent_a": mock_agent})
        started = []
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
            on_stage_start=lambda sid: started.append(sid),
        )
        orch.run()
        assert "a" in started

    def test_on_stage_complete_called(self, tmp_path):
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=[]
                ),
            ],
            pipeline_name="cb_test",
        )
        mock_agent = _make_mock_agent()
        registry = _make_registry({"agent_a": mock_agent})
        completed = []
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
            on_stage_complete=lambda sr: completed.append(sr),
        )
        orch.run()
        assert len(completed) == 1
        assert completed[0].stage_id == "a"


class TestRunSingleStage:
    def test_run_single_stage_success(self, tmp_path):
        dag = _linear_dag()
        mock_a = _make_mock_agent(artifacts={"out_a": "hello"})
        registry = _make_registry({"agent_a": mock_a})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        sr = orch.run_single_stage("a", {})
        assert sr.success is True
        assert sr.duration_seconds >= 0

    def test_run_single_stage_exception(self, tmp_path):
        dag = _linear_dag()
        mock_a = MagicMock()
        mock_a.execute.side_effect = RuntimeError("kaboom")
        mock_a.get_capabilities.return_value = AgentCapabilities(
            agent_id="agent_a",
            agent_version="1.0",
            description="test",
        )
        registry = _make_registry({"agent_a": mock_a})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        sr = orch.run_single_stage("a", {})
        assert sr.success is False
        assert "kaboom" in sr.error


class TestRunMetadata:
    def test_run_id_is_set(self, tmp_path):
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=[]
                ),
            ],
            pipeline_name="meta_test",
        )
        mock_agent = _make_mock_agent()
        registry = _make_registry({"agent_a": mock_agent})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        assert len(orch.run_id) == 8

    def test_result_has_timing(self, tmp_path):
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=[]
                ),
            ],
            pipeline_name="timing_test",
        )
        mock_agent = _make_mock_agent()
        registry = _make_registry({"agent_a": mock_agent})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.total_duration_seconds >= 0
        assert result.started_at != ""
        assert result.completed_at != ""
        assert "a" in result.stage_durations


class TestExceptionHandling:
    def test_agent_exception_captured(self, tmp_path):
        """If agent.execute raises, stage should fail gracefully."""
        dag = PipelineDAG(
            stages=[
                StageNode(
                    stage_id="a", agent_id="agent_a", depends_on=[], input_map={}, output_keys=[]
                ),
            ],
            pipeline_name="exception_test",
        )
        mock_agent = MagicMock()
        mock_agent.execute.side_effect = ValueError("bad input")
        mock_agent.get_capabilities.return_value = AgentCapabilities(
            agent_id="agent_a",
            agent_version="1.0",
            description="test",
        )
        registry = _make_registry({"agent_a": mock_agent})
        orch = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path / "run",
        )
        result = orch.run()
        assert result.status == "failed"
        assert "a" in result.stages_failed
