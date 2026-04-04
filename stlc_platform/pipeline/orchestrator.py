"""
Pipeline Orchestrator
=====================
DAG-based pipeline executor with parallel stage support via ThreadPoolExecutor.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from stlc_platform.core.base_agent import AgentResult
from stlc_platform.core.contracts import PipelineRunArtifact
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.artifact_store import ArtifactResolver, ArtifactStore
from stlc_platform.pipeline.circuit_breaker import CircuitBreaker
from stlc_platform.pipeline.coverage_tracker import CoverageTracker
from stlc_platform.pipeline.dag import PipelineDAG
from stlc_platform.pipeline.metrics_collector import MetricsCollector
from stlc_platform.pipeline.profile_loader import ExecutionProfile, ProfileLoader
from stlc_platform.pipeline.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result of executing a single pipeline stage."""

    stage_id: str
    success: bool
    agent_result: Optional[AgentResult] = None
    duration_seconds: float = 0.0
    error: str = ""
    error_type: str = ""
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
        skill_loader: Optional[SkillLoader] = None,
        execution_profile: Optional[ExecutionProfile] = None,
    ) -> None:
        self._dag = dag
        self._registry = registry
        self._config = config or {}
        self._max_workers = max_workers
        self._on_stage_start = on_stage_start
        self._on_stage_complete = on_stage_complete
        self._skill_loader = skill_loader
        self._execution_profile = execution_profile
        self._profile_loader = ProfileLoader()
        self._default_stage_timeout = float(
            self._config.get("stage_timeout_seconds", 0.0)
        )
        cb_cfg = self._config.get("circuit_breaker", {})
        cb_threshold = cb_cfg.get(
            "threshold", self._config.get("circuit_breaker_threshold", 3)
        )
        cb_timeout = cb_cfg.get(
            "reset_timeout", self._config.get("circuit_breaker_timeout", 60.0)
        )
        self._circuit_breaker = CircuitBreaker(
            threshold=int(cb_threshold),
            reset_timeout=float(cb_timeout),
        )

        metrics_cfg = self._config.get("metrics", {})
        metrics_dir = metrics_cfg.get(
            "dir", self._config.get("metrics_dir", "output/metrics")
        )
        self._metrics_collector = MetricsCollector(
            metrics_dir=Path(metrics_dir)
        )

        self._run_id = str(uuid.uuid4())[:8]
        self._store = ArtifactStore(run_dir=run_dir)
        self._resolver = ArtifactResolver(self._store, self._config)

        self._lock = threading.Lock()
        self._stage_results: Dict[str, StageResult] = {}
        self._failed_stages: List[str] = []
        self._skipped_stages: List[str] = []
        self._cancel_event = threading.Event()

    @property
    def run_id(self) -> str:
        return self._run_id

    def cancel(self) -> None:
        """Signal the pipeline to stop after the current wave completes."""
        self._cancel_event.set()

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
            # Check for cancellation before each wave
            if self._cancel_event.is_set():
                logger.info("Pipeline cancelled by user")
                break

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

            logger.info("Executing wave: %s", runnable)
            wave_results = self._execute_wave(runnable)

            succeeded = sum(1 for r in wave_results if r.success)
            failed = sum(1 for r in wave_results if not r.success and not r.skipped)
            skipped = sum(1 for r in wave_results if r.skipped)
            logger.info(
                "Wave complete: %d succeeded, %d failed, %d skipped",
                succeeded, failed, skipped,
            )

            for result in wave_results:
                with self._lock:
                    self._stage_results[result.stage_id] = result
                    if result.success:
                        completed.append(result.stage_id)
                    elif result.skipped:
                        if result.stage_id not in self._skipped_stages:
                            self._skipped_stages.append(result.stage_id)
                        self._mark_downstream_skipped(result.stage_id)
                    else:
                        self._failed_stages.append(result.stage_id)
                        stage = self._dag.get_stage(result.stage_id)
                        if not stage.optional:
                            self._mark_downstream_skipped(result.stage_id)

            # Checkpoint: persist after each wave so a crash doesn't lose
            # all prior progress.  The final persist_to_disk() below will
            # overwrite with the complete state including exported files.
            try:
                self._store.persist_to_disk()
            except OSError as exc:
                logger.warning("Wave checkpoint failed: %s", exc)

        # Final persist (includes export of .feature / .csv files)
        self._store.persist_to_disk()

        total_duration = time.monotonic() - start_time
        if self._cancel_event.is_set():
            status = "cancelled"
        elif self._failed_stages:
            status = "failed"
        else:
            status = "completed"

        stage_durations = {
            sid: r.duration_seconds
            for sid, r in self._stage_results.items()
            if not r.skipped
        }
        total_tokens = sum(
            getattr(r.agent_result, "tokens_used", 0)
            for r in self._stage_results.values()
            if r.agent_result
        )

        run_artifact = PipelineRunArtifact(
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

        # ── Post-run: coverage analysis, metrics & degradation alerting ──
        quality_scores: List[float] = []
        coverage_pct = 0.0
        estimated_cost = 0.0

        cache_hit_rate = 0.0

        try:
            quality_scores = self._extract_quality_scores()
        except (KeyError, AttributeError, TypeError) as exc:
            logger.warning("Post-run quality extraction failed: %s", exc)

        try:
            coverage_pct = self._run_coverage_analysis()
        except (KeyError, ValueError, AttributeError) as exc:
            logger.warning("Post-run coverage analysis failed: %s", exc)

        try:
            estimated_cost = self._estimate_run_cost(total_tokens)
        except (ImportError, KeyError, ValueError) as exc:
            logger.warning("Post-run cost estimation failed: %s", exc)

        try:
            cache_hit_rate = self._collect_cache_hit_rate()
        except (KeyError, AttributeError, TypeError) as exc:
            logger.warning("Post-run cache hit rate collection failed: %s", exc)

        try:
            metrics = self._metrics_collector.collect(
                run_artifact,
                quality_scores=quality_scores,
                token_count=total_tokens,
                estimated_cost=estimated_cost,
                coverage_pct=coverage_pct,
                cache_hit_rate=cache_hit_rate,
            )
            self._metrics_collector.persist(metrics)
            warning = self._metrics_collector.detect_degradation(metrics)
            if warning:
                logger.warning("DEGRADATION ALERT: %s", warning)
                # Degradation broadcast is handled in tasks.py via
                # the run_artifact.error_message field below.
                run_artifact.error_message = (
                    run_artifact.error_message + f" | {warning}"
                    if run_artifact.error_message
                    else warning
                )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Metrics collection failed: %s", exc)

        return run_artifact

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
                error_type=type(e).__name__,
            )

        if self._on_stage_complete:
            self._on_stage_complete(sr)

        return sr

    def _get_stage_timeout(self, stage_id: str) -> Optional[float]:
        """Return the timeout for a stage, or None if no timeout configured."""
        stage = self._dag.get_stage(stage_id)
        timeout = stage.timeout_seconds or self._default_stage_timeout
        return timeout if timeout > 0 else None

    def _execute_wave(self, wave: List[str]) -> List[StageResult]:
        """Execute a wave of independent stages in parallel."""
        if len(wave) == 1:
            return [self._execute_stage_with_timeout(wave[0])]

        results: List[StageResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures: Dict[Future, str] = {
                executor.submit(self._execute_stage, sid): sid
                for sid in wave
            }
            for future in as_completed(futures):
                sid = futures[future]
                timeout = self._get_stage_timeout(sid)
                try:
                    results.append(future.result(timeout=timeout))
                except TimeoutError:
                    logger.error(
                        "Stage '%s' timed out after %.0fs", sid, timeout
                    )
                    results.append(StageResult(
                        stage_id=sid,
                        success=False,
                        duration_seconds=timeout or 0.0,
                        error=f"Stage timed out after {timeout}s",
                    ))

        return results

    def _execute_stage_with_timeout(self, stage_id: str) -> StageResult:
        """Execute a single stage, enforcing timeout if configured."""
        timeout = self._get_stage_timeout(stage_id)
        if timeout is None:
            return self._execute_stage(stage_id)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future: Future = executor.submit(self._execute_stage, stage_id)
            try:
                return future.result(timeout=timeout)
            except TimeoutError:
                logger.error(
                    "Stage '%s' timed out after %.0fs", stage_id, timeout
                )
                return StageResult(
                    stage_id=stage_id,
                    success=False,
                    duration_seconds=timeout,
                    error=f"Stage timed out after {timeout}s",
                )

    def _execute_stage(self, stage_id: str) -> StageResult:
        """Execute a single stage: resolve inputs, validate, execute agent."""
        stage = self._dag.get_stage(stage_id)

        if self._on_stage_start:
            self._on_stage_start(stage_id)

        t0 = time.monotonic()

        try:
            # Resolve input references — skip optional stages with missing inputs
            try:
                resolved_inputs = self._resolver.resolve(stage.input_map)
            except KeyError as resolve_err:
                if stage.optional:
                    logger.info(
                        "Skipping optional stage '%s': %s", stage_id, resolve_err
                    )
                    sr = StageResult(
                        stage_id=stage_id,
                        success=False,
                        skipped=True,
                        duration_seconds=round(time.monotonic() - t0, 3),
                        error=f"Skipped (missing input): {resolve_err}",
                    )
                    if self._on_stage_complete:
                        self._on_stage_complete(sr)
                    return sr
                raise  # re-raise for non-optional stages

            # Apply execution profile filter to inputs
            if self._execution_profile:
                resolved_inputs = self._profile_loader.apply_filter(
                    self._execution_profile, resolved_inputs
                )

            # Get agent and execute
            agent = self._registry.get(stage.agent_id)
            stage_config = {**self._config, **stage.config_overrides}

            # Inject skill context if skill loader is available
            if self._skill_loader:
                caps = agent.get_capabilities()
                skills_context = self._skill_loader.load_for_agent(caps)
                if skills_context:
                    stage_config["skills"] = skills_context

            # Inject execution profile into config for agent awareness
            if self._execution_profile:
                stage_config["execution_profile"] = {
                    "name": self._execution_profile.name,
                    "filters": self._execution_profile.filters,
                    "max_tests": self._execution_profile.max_tests,
                }

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
            if not result.success:
                logger.warning("Stage '%s' agent returned failure: %s", stage_id, sr.error)

        except Exception as e:
            duration = time.monotonic() - t0
            logger.error("Stage '%s' failed: %s", stage_id, e, exc_info=True)
            sr = StageResult(
                stage_id=stage_id,
                success=False,
                duration_seconds=round(duration, 3),
                error=str(e),
                error_type=type(e).__name__,
            )

        # Retry logic with circuit breaker
        if not sr.success and stage.retry_count > 0:
            et = sr.error_type or "unknown"
            self._circuit_breaker.record_failure(stage_id, et)

            for attempt in range(stage.retry_count):
                if self._circuit_breaker.is_open(stage_id):
                    diag = self._circuit_breaker.get_diagnostic(stage_id)
                    logger.warning("Circuit breaker tripped — skipping retry: %s", diag)
                    break

                retry_sr = self._retry_stage(stage_id)
                if retry_sr.success:
                    self._circuit_breaker.record_success(stage_id)
                    sr = retry_sr
                    break
                else:
                    retry_et = retry_sr.error_type or "unknown"
                    opened = self._circuit_breaker.record_failure(stage_id, retry_et)
                    if opened:
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

    def _extract_quality_scores(self) -> List[float]:
        """Extract quality_score from test case artifacts produced by any stage."""
        scores: List[float] = []
        for sr in self._stage_results.values():
            if not sr.agent_result or not sr.success:
                continue
            test_cases = sr.agent_result.artifacts.get("test_cases", [])
            for tc in test_cases:
                score = getattr(tc, "quality_score", None)
                if score is None and isinstance(tc, dict):
                    score = tc.get("quality_score")
                if score is not None and isinstance(score, (int, float)):
                    scores.append(float(score))
        return scores

    def _run_coverage_analysis(self) -> float:
        """Run CoverageTracker if requirements and test cases are available."""
        requirements = self._config.get("requirements", [])
        if not requirements:
            return 0.0

        # Collect test cases from all stages
        all_tcs: List[Any] = []
        for sr in self._stage_results.values():
            if sr.agent_result and sr.success:
                tcs = sr.agent_result.artifacts.get("test_cases", [])
                all_tcs.extend(tcs)

        if not all_tcs:
            return 0.0

        coverage_cfg = self._config.get("coverage", {})
        tracker = CoverageTracker(
            weak_quality_threshold=float(coverage_cfg.get("weak_quality_threshold", 0.5)),
            min_coverage_types=int(coverage_cfg.get("min_coverage_types", 1)),
        )
        report = tracker.analyze(requirements, all_tcs)

        # Store coverage report in artifact store for downstream use
        self._store.store("_coverage", {
            "overall_coverage": report.overall_coverage,
            "total_acs": report.total_acs,
            "uncovered_count": len(report.uncovered_entries),
            "weak_count": len(report.weak_entries),
        })

        # Auto-fill gaps: re-invoke generator for uncovered ACs
        if coverage_cfg.get("auto_fill_gaps", False) and report.uncovered_entries:
            self._fill_coverage_gaps(report, requirements, all_tcs)
            # Recalculate coverage after gap-fill
            updated_tcs: List[Any] = []
            for sr in self._stage_results.values():
                if sr.agent_result and sr.success:
                    updated_tcs.extend(sr.agent_result.artifacts.get("test_cases", []))
            if updated_tcs:
                updated_report = tracker.analyze(requirements, updated_tcs)
                report = updated_report
                self._store.store("_coverage", {
                    "overall_coverage": report.overall_coverage,
                    "total_acs": report.total_acs,
                    "uncovered_count": len(report.uncovered_entries),
                    "weak_count": len(report.weak_entries),
                })

        return report.overall_coverage

    def _estimate_run_cost(self, total_tokens: int) -> float:
        """Estimate LLM cost for this run based on provider/model config.

        The input/output token split ratio is configurable via
        ``metrics.input_token_ratio`` (default 0.4 = 40% input, 60% output).
        """
        try:
            from stlc_platform.core.llm.pricing import estimate_cost

            llm_cfg = self._config.get("llm", self._config.get("ollama", {}))
            provider = llm_cfg.get("provider", "ollama")
            model = llm_cfg.get("model", "")
            metrics_cfg = self._config.get("metrics", {})
            input_ratio = float(metrics_cfg.get("input_token_ratio", 0.4))
            input_ratio = max(0.0, min(1.0, input_ratio))
            input_tokens = int(total_tokens * input_ratio)
            output_tokens = total_tokens - input_tokens
            return estimate_cost(provider, model, input_tokens, output_tokens)
        except (ImportError, KeyError, ValueError, TypeError) as exc:
            logger.debug("Cost estimation unavailable: %s", exc)
            return 0.0

    def _collect_cache_hit_rate(self) -> float:
        """Collect cache hit rate from LLM clients used across stages."""
        total_hits = 0
        total_misses = 0

        for sr in self._stage_results.values():
            if not sr.agent_result or not sr.success:
                continue
            # Check metadata for cache stats reported by agents
            hits = sr.agent_result.metadata.get("cache_hits", 0)
            misses = sr.agent_result.metadata.get("cache_misses", 0)
            total_hits += hits
            total_misses += misses

        # Also try to read from the runtime LLM client cache directly
        try:
            llm_client = self._resolver.resolve(
                {"llm_client": "$runtime.llm_client"}
            ).get("llm_client")
            if llm_client and hasattr(llm_client, "_cache") and llm_client._cache:
                cache = llm_client._cache
                if hasattr(cache, "hit_rate"):
                    return cache.hit_rate
                if hasattr(cache, "_hits") and hasattr(cache, "_misses"):
                    total_hits += cache._hits
                    total_misses += cache._misses
        except (KeyError, AttributeError, ValueError) as exc:
            logger.debug("LLM cache stats unavailable: %s", exc)

        total = total_hits + total_misses
        return total_hits / total if total > 0 else 0.0

    def _fill_coverage_gaps(
        self,
        report: Any,
        requirements: List[Any],
        existing_tcs: List[Any],
    ) -> None:
        """Re-invoke the requirements agent for uncovered ACs.

        Builds a filtered requirements list containing only the uncovered ACs,
        then runs the test_generation agent to fill the gaps.  New TCs are
        merged into the ``parse_requirements`` stage artifacts.
        """
        from stlc_platform.core.contracts import RequirementArtifact

        uncovered = report.uncovered_entries
        logger.info(
            "Auto-fill gaps: %d uncovered ACs, invoking gap-fill generation",
            len(uncovered),
        )

        # Group uncovered ACs by req_id
        gap_acs_by_req: Dict[str, List[str]] = {}
        for entry in uncovered:
            gap_acs_by_req.setdefault(entry.req_id, []).append(entry.ac_text)

        # Build filtered requirement objects with only uncovered ACs
        gap_requirements: List[Any] = []
        for req in requirements:
            req_id = getattr(req, "req_id", "")
            if req_id in gap_acs_by_req:
                # Create a copy with only uncovered ACs
                gap_req = RequirementArtifact(
                    req_id=req_id,
                    title=getattr(req, "title", ""),
                    description=getattr(req, "description", ""),
                    priority=getattr(req, "priority", "Medium"),
                    category=getattr(req, "category", "Functional"),
                    acceptance_criteria=gap_acs_by_req[req_id],
                    tags=getattr(req, "tags", []),
                )
                gap_requirements.append(gap_req)

        if not gap_requirements:
            return

        try:
            agent = self._registry.get("test_generation")
        except KeyError:
            logger.warning("auto_fill_gaps: test_generation agent not registered")
            return

        # Build artifacts for gap-fill run
        gap_artifacts: Dict[str, Any] = {
            "requirements": gap_requirements,
        }

        # Carry forward llm_client and vector_store from config/resolver
        try:
            gap_artifacts["llm_client"] = self._resolver.resolve(
                {"llm_client": "$runtime.llm_client"}
            ).get("llm_client")
        except (KeyError, ValueError) as exc:
            logger.debug("Gap-fill: llm_client unavailable: %s", exc)
        try:
            gap_artifacts["vector_store"] = self._resolver.resolve(
                {"vector_store": "$runtime.vector_store"}
            ).get("vector_store")
        except (KeyError, ValueError) as exc:
            logger.debug("Gap-fill: vector_store unavailable: %s", exc)

        gap_config = {**self._config, "max_tests": 3}

        try:
            result = agent.execute(gap_artifacts, gap_config)
            if result.success:
                gap_tcs = result.artifacts.get("test_cases", [])
                logger.info("Auto-fill generated %d gap-filling TCs", len(gap_tcs))

                # Merge into parse_requirements stage artifacts
                existing = self._store.get("parse_requirements") or {}
                existing_list = existing.get("test_cases", [])
                if isinstance(existing_list, list):
                    existing_list.extend(gap_tcs)
                    self._store.store("parse_requirements", {
                        **existing,
                        "test_cases": existing_list,
                    })
            else:
                logger.warning("Auto-fill generation failed: %s", result.errors)
        except Exception as exc:
            logger.warning("Auto-fill gap-fill error: %s", exc)

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
