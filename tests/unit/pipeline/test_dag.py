"""Unit tests for the Pipeline DAG."""

from __future__ import annotations

import pytest
from stlc_platform.pipeline.dag import PipelineDAG, StageNode


def _node(stage_id: str, depends_on: list = None, **kw) -> StageNode:
    return StageNode(
        stage_id=stage_id,
        agent_id=kw.get("agent_id", "mock_agent"),
        depends_on=depends_on or [],
        input_map=kw.get("input_map", {}),
        output_keys=kw.get("output_keys", []),
    )


class TestTopologicalSort:
    def test_simple_linear_dag(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b", ["a"]),
                _node("c", ["b"]),
            ]
        )
        waves = dag.topological_waves()
        assert waves == [["a"], ["b"], ["c"]]

    def test_parallel_waves(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b"),
                _node("c", ["a", "b"]),
            ]
        )
        waves = dag.topological_waves()
        assert len(waves) == 2
        assert set(waves[0]) == {"a", "b"}
        assert waves[1] == ["c"]

    def test_diamond_dag(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b", ["a"]),
                _node("c", ["a"]),
                _node("d", ["b", "c"]),
            ]
        )
        waves = dag.topological_waves()
        assert len(waves) == 3
        assert waves[0] == ["a"]
        assert set(waves[1]) == {"b", "c"}
        assert waves[2] == ["d"]

    def test_single_stage(self):
        dag = PipelineDAG([_node("only")])
        waves = dag.topological_waves()
        assert waves == [["only"]]


class TestValidation:
    def test_cycle_detection(self):
        dag = PipelineDAG(
            [
                _node("a", ["b"]),
                _node("b", ["a"]),
            ]
        )
        errors = dag.validate()
        assert len(errors) == 1
        assert "cycle" in errors[0].lower()

    def test_missing_dependency(self):
        dag = PipelineDAG(
            [
                _node("a", ["nonexistent"]),
            ]
        )
        errors = dag.validate()
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_empty_dag_raises(self):
        with pytest.raises(ValueError, match="at least one stage"):
            PipelineDAG([])

    def test_valid_dag_has_no_errors(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b", ["a"]),
            ]
        )
        assert dag.validate() == []


class TestGetDependents:
    def test_returns_correct_downstream(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b", ["a"]),
                _node("c", ["a"]),
                _node("d", ["b"]),
            ]
        )
        deps = dag.get_dependents("a")
        assert set(deps) == {"b", "c"}

    def test_leaf_has_no_dependents(self):
        dag = PipelineDAG(
            [
                _node("a"),
                _node("b", ["a"]),
            ]
        )
        assert dag.get_dependents("b") == []
