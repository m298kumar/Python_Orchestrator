"""
Pipeline Orchestrator
=====================
DAG-based pipeline executor with parallel stage support via ThreadPoolExecutor.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from stlc_platform.core.base_agent import AgentResult
from stlc_platform.core.contracts import PipelineRunArtifact
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.artifact_store import ArtifactResolver, ArtifactStore
from stlc_platform.pipeline.dag import PipelineDAG


@dataclass
class StageResult:
    """Result of executing a single pipeline stage."""

    stage_id: str
    success: bool
    agent_result: Optional[AgentResult] = None
    duration_seconds: float = 0.0
    error: str = ""
    skipped: bool = False


class PipelineOrchestrator:
    """DAG-based pipeline executor with parallel stage support."""

    def __init__(
        self,
        dag: PipelineDAG,
        registry: AgentRegistry,
        config: Optional[Dict[str, Any]] = None,
        run_dir: Optional[Path] = None,
        max_workers: int = 4,
        on_stage_start: Optional[Callable[[str], None]] = None,
        on_stage_complete: Optional[Callable[[StageResult], None]] = None,
    ) -> None:
        self._dag = dag
        self._registry = registry
        self._config = config or {}
        self._max_workers = max_workers
        self._on_stage_start = on_stage_start
        self._on_stage_complete = on_stage_complete

        self._run_id = str(uuid.uuid4())[:8]
        self._store = ArtifactStore(run_dir=run_dir)
        self._resolver = ArtifactResolver(self._store, self._config)

        self._stage_results: Dict[str, StageResult] = {}
        self._failed_stages: List[str] = []
        self._skipped_stages: List[str] = []

    @property
    def run_id(self) -> str:
        return self._run_id

    def run(self, resume_from: Optional[str] = None) -> PipelineRunArtifact:
        """Execute the full pipeline, optionally resuming from a stage."""
        start_time = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()

        # Validate DAG
        errors = self._dag.validate()
        if errors:
            return PipelineRunArtifact(
                run_id=self._run_id,
                pipeline_name=self._dag.pipeline_name,
                status="failed",
                error_message=f"DAG validation failed: {'; '.join(errors)}",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Resume: load prior artifacts from disk
        stages_to_skip: set = set()
        if resume_from:
            loaded = self._store.load_from_disk()
            stages_to_skip = set(loaded)
            if resume_from in stages_to_skip:
                stages_to_skip.discard(resume_from)

        # Execute waves
        waves = self._dag.topological_waves()
        completed: List[str] = []

        for wave in waves:
            # Filter out already-completed (resume) and skipped stages
            runnable = [
                sid for sid in wave
                if sid not in stages_to_skip and sid not in self._skipped_stages
            ]
            skipped_in_wave = [
                sid for sid in wave if sid in stages_to_skip
            ]
            completed.extend(skipped_in_wave)

            if not runnable:
                continue

            wave_results = self._execute_wave(runnable)

            for result in wave_results:
                self._stage_results[result.stage_id] = result
                if result.success:
                    completed.append(result.stage_id)
                else:
                    self._failed_stages.append(result.stage_id)
                    # Skip downstream stages of failed non-optional stages
                    stage = self._dag.get_stage(result.stage_id)
                    if not stage.optional:
                        self._mark_downstream_skipped(result.stage_id)

        # Persist final state
        self._store.persist_to_disk()

        total_duration = time.monotonic() - start_time
        status = "completed" if not self._failed_stages else "failed"

        stage_durations = {
            sid: r.duration_seconds
            for sid, r in self._stage_results.items()
            if not r.skipped
        }
        total_tokens = sum(
            r.agent_result.tokens_used
            for r in self._stage_results.values()
            if r.agent_result
        )

        return PipelineRunArtifact(
            run_id=self._run_id,
            pipeline_name=self._dag.pipeline_name,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            stages_completed=completed,
            stages_failed=self._failed_stages,
            stages_skipped=self._skipped_stages,
            total_duration_seconds=round(total_duration, 3),
            total_tokens_used=total_tokens,
            stage_durations=stage_durations,
        )

    def run_single_stage(
        self, stage_id: str, input_artifacts: Dict[str, Any]
    ) -> StageResult:
        """Execute a single stage with provided artifacts."""
        stage = self._dag.get_stage(stage_id)
        agent = self._registry.get(stage.agent_id)

        if self._on_stage_start:
            self._on_stage_start(stage_id)

        t0 = time.monotonic()
        try:
            # Merge config overrides
            stage_config = {**self._config, **stage.config_overrides}
            result = agent.execute(input_artifacts, stage_config)
            duration = time.monotonic() - t0
            result.duration_seconds = duration

            # Store artifacts
            if result.success:
                self._store.store(stage_id, result.artifacts, result.metadata)

            sr = StageResult(
                stage_id=stage_id,
                success=result.success,
                agent_result=result,
                duration_seconds=round(duration, 3),
                error="; ".join(result.errors) if result.errors else "",
            )
        except Exception as e:
            duration = time.monotonic() - t0
            sr = StageResult(
                stage_id=stage_id,
                success=False,
                duration_seconds=round(duration, 3),
                error=str(e),
            )

        if self._on_stage_complete:
            self._on_stage_complete(sr)

        return sr

    def _execute_wave(self, wave: List[str]) -> List[StageResult]:
        """Execute a wave of independent stages in parallel."""
        if len(wave) == 1:
            return [self._execute_stage(wave[0])]

        results: List[StageResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._execute_stage, sid): sid
                for sid in wave
            }
            for future in as_completed(futures):
                results.append(future.result())

        return results

    def _execute_stage(self, stage_id: str) -> StageResult:
        """Execute a single stage: resolve inputs, validate, execute agent."""
        stage = self._dag.get_stage(stage_id)

        if self._on_stage_start:
            self._on_stage_start(stage_id)

        t0 = time.monotonic()

        try:
            # Resolve input references
            resolved_inputs = self._resolver.resolve(stage.input_map)

            # Get agent and execute
            agent = self._registry.get(stage.agent_id)
            stage_config = {**self._config, **stage.config_overrides}
            result = agent.execute(resolved_inputs, stage_config)
            duration = time.monotonic() - t0
            result.duration_seconds = duration

            if result.success:
                self._store.store(stage_id, result.artifacts, result.metadata)

            sr = StageResult(
                stage_id=stage_id,
                success=result.success,
                agent_result=result,
                duration_seconds=round(duration, 3),
                error="; ".join(result.errors) if result.errors else "",
            )

        except Exception as e:
            duration = time.monotonic() - t0
            sr = StageResult(
                stage_id=stage_id,
                success=False,
                duration_seconds=round(duration, 3),
                error=str(e),
            )

        # Retry logic
        if not sr.success and stage.retry_count > 0:
            for attempt in range(stage.retry_count):
                retry_sr = self._retry_stage(stage_id)
                if retry_sr.success:
                    sr = retry_sr
                    break

        if self._on_stage_complete:
            self._on_stage_complete(sr)

        return sr

    def _retry_stage(self, stage_id: str) -> StageResult:
        """Retry a failed stage."""
        stage = self._dag.get_stage(stage_id)
        t0 = time.monotonic()
        try:
            resolved_inputs = self._resolver.resolve(stage.input_map)
            agent = self._registry.get(stage.agent_id)
            stage_config = {**self._config, **stage.config_overrides}
            result = agent.execute(resolved_inputs, stage_config)
            duration = time.monotonic() - t0
            result.duration_seconds = duration

            if result.success:
                self._store.store(stage_id, result.artifacts, result.metadata)

            return StageResult(
                stage_id=stage_id,
                success=result.success,
                agent_result=result,
                duration_seconds=round(duration, 3),
                error="; ".join(result.errors) if result.errors else "",
            )
        except Exception as e:
            return StageResult(
                stage_id=stage_id,
                success=False,
                duration_seconds=round(time.monotonic() - t0, 3),
                error=str(e),
            )

    def _mark_downstream_skipped(self, failed_stage_id: str) -> None:
        """Mark all downstream stages as skipped."""
        dependents = self._dag.get_dependents(failed_stage_id)
        for dep in dependents:
            if dep not in self._skipped_stages:
                self._skipped_stages.append(dep)
                self._stage_results[dep] = StageResult(
                    stage_id=dep, success=False, skipped=True
                )
                self._mark_downstream_skipped(dep)
