"""
Pipeline DAG
============
Directed Acyclic Graph data structure for pipeline stage ordering.
Uses Kahn's algorithm (BFS topological sort) to produce execution waves
where stages within a wave can run in parallel.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StageNode:
    """A single stage in the pipeline DAG."""

    stage_id: str
    agent_id: str
    depends_on: List[str] = field(default_factory=list)
    input_map: Dict[str, str] = field(default_factory=dict)
    output_keys: List[str] = field(default_factory=list)
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    optional: bool = False
    timeout_seconds: float = 0.0  # 0 = no timeout


class PipelineDAG:
    """DAG of pipeline stages with topological sort and validation."""

    def __init__(self, stages: List[StageNode], pipeline_name: str = "") -> None:
        if not stages:
            raise ValueError("Pipeline must have at least one stage.")
        self.pipeline_name = pipeline_name
        self._stages: Dict[str, StageNode] = {}
        for s in stages:
            if s.stage_id in self._stages:
                raise ValueError(f"Duplicate stage_id: '{s.stage_id}'")
            self._stages[s.stage_id] = s

    @property
    def stage_ids(self) -> List[str]:
        """All stage IDs in insertion order."""
        return list(self._stages.keys())

    def get_stage(self, stage_id: str) -> StageNode:
        """Get a stage by ID."""
        if stage_id not in self._stages:
            raise KeyError(f"Stage '{stage_id}' not found in pipeline.")
        return self._stages[stage_id]

    def validate(self) -> List[str]:
        """Validate the DAG. Returns a list of error strings (empty = valid)."""
        errors: List[str] = []

        # Check all depends_on references exist
        for stage in self._stages.values():
            for dep in stage.depends_on:
                if dep not in self._stages:
                    errors.append(f"Stage '{stage.stage_id}' depends on unknown stage '{dep}'.")

        # Check for cycles via topological sort attempt
        if not errors:
            try:
                self.topological_waves()
            except ValueError as e:
                errors.append(str(e))

        return errors

    def topological_waves(self) -> List[List[str]]:
        """Return stages grouped by execution wave using Kahn's algorithm.

        Stages within the same wave have no dependencies on each other
        and can be executed in parallel.

        Raises ValueError if a cycle is detected.
        """
        # Build adjacency and in-degree
        in_degree: Dict[str, int] = {sid: 0 for sid in self._stages}
        dependents: Dict[str, List[str]] = defaultdict(list)

        for stage in self._stages.values():
            for dep in stage.depends_on:
                dependents[dep].append(stage.stage_id)
                in_degree[stage.stage_id] += 1

        # BFS in waves
        waves: List[List[str]] = []
        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)

        processed = 0
        while queue:
            wave = list(queue)
            queue.clear()
            waves.append(wave)
            processed += len(wave)

            for sid in wave:
                for dependent in dependents[sid]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if processed != len(self._stages):
            remaining = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Pipeline has a cycle involving stages: {remaining}")

        return waves

    def get_dependents(self, stage_id: str) -> List[str]:
        """Return stage IDs that directly depend on the given stage."""
        if stage_id not in self._stages:
            raise KeyError(f"Stage '{stage_id}' not found in pipeline.")
        return [s.stage_id for s in self._stages.values() if stage_id in s.depends_on]
