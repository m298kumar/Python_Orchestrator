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
        run_id: Optional[str] = None,
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
        self._default_stage_timeout = float(self._config.get("stage_timeout_seconds", 0.0))
        cb_cfg = self._config.get("circuit_breaker", {})
        cb_threshold = cb_cfg.get("threshold", self._config.get("circuit_breaker_threshold", 3))
        cb_timeout = cb_cfg.get("reset_timeout", self._config.get("circuit_breaker_timeout", 60.0))
        self._circuit_breaker = CircuitBreaker(
            threshold=int(cb_threshold),
            reset_timeout=float(cb_timeout),
        )

        metrics_cfg = self._config.get("metrics", {})
        metrics_dir = metrics_cfg.get("dir", self._config.get("metrics_dir", "output/metrics"))
        self._metrics_collector = MetricsCollector(metrics_dir=Path(metrics_dir))

        self._run_id = run_id or str(uuid.uuid4())[:8]
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
        start_time = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()

        errors = self._dag.validate()
        if errors:
            return self._build_failed_run_artifact(
                started_at,
                f"DAG validation failed: {'; '.join(errors)}",
            )

        stages_to_skip = self._load_resume_state(resume_from)
        completed = self._execute_all_waves(stages_to_skip)

        total_duration = time.monotonic() - start_time
        status = self._determine_run_status()
        stage_durations = self._collect_stage_durations()
        input_tokens, output_tokens, total_tokens = self._collect_token_usage()

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

        self._run_post_run_analysis(run_artifact, input_tokens, output_tokens, total_tokens)
        return run_artifact

    def _build_failed_run_artifact(
        self,
        started_at: str,
        error_message: str,
    ) -> PipelineRunArtifact:
        return PipelineRunArtifact(
            run_id=self._run_id,
            pipeline_name=self._dag.pipeline_name,
            status="failed",
            error_message=error_message,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _load_resume_state(self, resume_from: Optional[str]) -> set:
        stages_to_skip: set = set()
        if resume_from:
            loaded = self._store.load_from_disk()
            stages_to_skip = set(loaded)
            if resume_from in stages_to_skip:
                stages_to_skip.discard(resume_from)
        return stages_to_skip

    def _execute_all_waves(self, stages_to_skip: set) -> List[str]:
        waves = self._dag.topological_waves()
        completed: List[str] = []

        for wave in waves:
            if self._cancel_event.is_set():
                logger.info("Pipeline cancelled by user")
                break

            runnable = [
                sid for sid in wave if sid not in stages_to_skip and sid not in self._skipped_stages
            ]
            skipped_in_wave = [sid for sid in wave if sid in stages_to_skip]
            completed.extend(skipped_in_wave)

            if not runnable:
                continue

            logger.info("Executing wave: %s", runnable)
            wave_results = self._execute_wave(runnable)
            self._process_wave_results(wave_results, completed)

            try:
                self._store.persist_to_disk()
            except OSError as exc:
                logger.warning("Wave checkpoint failed: %s", exc)

        self._store.persist_to_disk()
        return completed

    def _process_wave_results(self, wave_results: List[StageResult], completed: List[str]) -> None:
        succeeded = sum(1 for r in wave_results if r.success)
        failed = sum(1 for r in wave_results if not r.success and not r.skipped)
        skipped = sum(1 for r in wave_results if r.skipped)
        logger.info(
            "Wave complete: %d succeeded, %d failed, %d skipped",
            succeeded,
            failed,
            skipped,
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

    def _determine_run_status(self) -> str:
        if self._cancel_event.is_set():
            return "cancelled"
        if self._failed_stages:
            return "failed"
        return "completed"

    def _collect_stage_durations(self) -> Dict[str, float]:
        return {sid: r.duration_seconds for sid, r in self._stage_results.items() if not r.skipped}

    def _collect_total_tokens(self) -> int:
        return self._collect_token_usage()[2]

    def _collect_token_usage(self) -> tuple[int, int, int]:
        """Aggregate exact provider-reported usage from successful stages."""
        input_tokens = 0
        output_tokens = 0
        unclassified_tokens = 0
        for result in self._stage_results.values():
            agent_result = result.agent_result
            if not agent_result or not result.success:
                continue
            stage_input = int(agent_result.metadata.get("input_tokens", 0) or 0)
            stage_output = int(agent_result.metadata.get("output_tokens", 0) or 0)
            input_tokens += stage_input
            output_tokens += stage_output
            reported_total = int(getattr(agent_result, "tokens_used", 0) or 0)
            if not stage_input and not stage_output:
                unclassified_tokens += reported_total
        return input_tokens, output_tokens, input_tokens + output_tokens + unclassified_tokens

    def _run_post_run_analysis(
        self,
        run_artifact: PipelineRunArtifact,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> None:
        quality_scores = self._safe_extract_quality_scores()
        coverage_pct = self._safe_run_coverage_analysis()
        estimated_cost = self._safe_estimate_run_cost(
            input_tokens, output_tokens, total_tokens
        )
        cache_hit_rate = self._safe_collect_cache_hit_rate()
        llm_cfg = self._config.get("llm", self._config.get("ollama", {}))

        try:
            metrics = self._metrics_collector.collect(
                run_artifact,
                quality_scores=quality_scores,
                token_count=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
                llm_provider=str(llm_cfg.get("provider", "ollama")),
                llm_model=str(llm_cfg.get("model", "")),
                coverage_pct=coverage_pct,
                cache_hit_rate=cache_hit_rate,
            )
            self._metrics_collector.persist(metrics)
            warning = self._metrics_collector.detect_degradation(metrics)
            if warning:
                logger.warning("DEGRADATION ALERT: %s", warning)
                run_artifact.error_message = (
                    run_artifact.error_message + f" | {warning}"
                    if run_artifact.error_message
                    else warning
                )
        except (OSError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Metrics collection failed: %s", exc)

    def _safe_extract_quality_scores(self) -> List[float]:
        try:
            return self._extract_quality_scores()
        except (KeyError, AttributeError, TypeError) as exc:
            logger.warning("Post-run quality extraction failed: %s", exc)
            return []

    def _safe_run_coverage_analysis(self) -> float:
        try:
            return self._run_coverage_analysis()
        except (KeyError, ValueError, AttributeError) as exc:
            logger.warning("Post-run coverage analysis failed: %s", exc)
            return 0.0

    def _safe_estimate_run_cost(
        self, input_tokens: int, output_tokens: int, total_tokens: int
    ) -> float:
        try:
            return self._estimate_run_cost(input_tokens, output_tokens, total_tokens)
        except (ImportError, KeyError, ValueError) as exc:
            logger.warning("Post-run cost estimation failed: %s", exc)
            return 0.0

    def _safe_collect_cache_hit_rate(self) -> float:
        try:
            return self._collect_cache_hit_rate()
        except (KeyError, AttributeError, TypeError) as exc:
            logger.warning("Post-run cache hit rate collection failed: %s", exc)
            return 0.0

    def run_single_stage(self, stage_id: str, input_artifacts: Dict[str, Any]) -> StageResult:
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
                executor.submit(self._execute_stage, sid): sid for sid in wave
            }
            for future in as_completed(futures):
                sid = futures[future]
                timeout = self._get_stage_timeout(sid)
                try:
                    results.append(future.result(timeout=timeout))
                except TimeoutError:
                    logger.error("Stage '%s' timed out after %.0fs", sid, timeout)
                    results.append(
                        StageResult(
                            stage_id=sid,
                            success=False,
                            duration_seconds=timeout or 0.0,
                            error=f"Stage timed out after {timeout}s",
                        )
                    )

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
                logger.error("Stage '%s' timed out after %.0fs", stage_id, timeout)
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
            resolved_inputs = self._resolve_stage_inputs(stage_id, stage)
            if resolved_inputs is None:
                return self._build_skipped_stage_result(stage_id, t0, "Missing inputs")

            stage_config = self._build_stage_config(stage)
            result = self._run_agent(stage_id, stage, resolved_inputs, stage_config, t0)

            skip = self._check_optional_validation_skip(stage_id, stage, result, t0)
            if skip is not None:
                return skip

        except Exception as e:
            duration = time.monotonic() - t0
            logger.error("Stage '%s' failed: %s", stage_id, e, exc_info=True)
            result = StageResult(
                stage_id=stage_id,
                success=False,
                duration_seconds=round(duration, 3),
                error=str(e),
                error_type=type(e).__name__,
            )

        if not result.success and stage.retry_count > 0:
            result = self._retry_with_circuit_breaker(stage_id, stage, result)

        if self._on_stage_complete:
            self._on_stage_complete(result)

        return result

    def _resolve_stage_inputs(self, stage_id: str, stage: Any) -> Optional[Dict[str, Any]]:
        try:
            resolved_inputs = self._resolver.resolve(stage.input_map)
        except KeyError as resolve_err:
            if stage.optional:
                logger.info("Skipping optional stage '%s': %s", stage_id, resolve_err)
                return None
            raise
        # If stage is optional and ALL resolved inputs are None or empty, skip it
        if stage.optional and resolved_inputs and all(not v for v in resolved_inputs.values()):
            logger.info("Skipping optional stage '%s': all inputs resolved to None/empty", stage_id)
            return None
        if self._execution_profile:
            resolved_inputs = self._profile_loader.apply_filter(
                self._execution_profile, resolved_inputs
            )
        return resolved_inputs

    def _build_stage_config(self, stage: Any) -> Dict[str, Any]:
        stage_config = {**self._config, **stage.config_overrides}
        if self._skill_loader:
            caps = self._registry.get(stage.agent_id).get_capabilities()
            skills_context = self._skill_loader.load_for_agent(caps)
            if skills_context:
                stage_config["skills"] = skills_context
        if self._execution_profile:
            stage_config["execution_profile"] = {
                "name": self._execution_profile.name,
                "filters": self._execution_profile.filters,
                "max_tests": self._execution_profile.max_tests,
            }
        return stage_config

    # Sentinel keywords that indicate a validation-level failure (missing dependency,
    # required input absent) that should be treated as a skip for optional stages.
    _VALIDATION_SKIP_MARKERS = ("not installed", "unavailable", "is required", "chromium")

    def _check_optional_validation_skip(
        self,
        stage_id: str,
        stage: Any,
        result: StageResult,
        t0: float,
    ) -> Optional[StageResult]:
        """Return a skipped StageResult if an optional stage failed at validation level.

        This converts a hard failure (e.g. Playwright not installed) into a clean skip
        so the run status is not poisoned and downstream optional stages cascade correctly.
        Returns None if no skip should occur.
        """
        if result.success or not stage.optional or result.agent_result is None:
            return None
        agent_errors = result.agent_result.errors or []
        if any(marker in e for e in agent_errors for marker in self._VALIDATION_SKIP_MARKERS):
            msg = "; ".join(agent_errors)
            logger.info("Skipping optional stage '%s' (validation failure): %s", stage_id, msg)
            return self._build_skipped_stage_result(stage_id, t0, msg)
        return None

    def _build_skipped_stage_result(self, stage_id: str, t0: float, reason: str) -> StageResult:
        sr = StageResult(
            stage_id=stage_id,
            success=False,
            skipped=True,
            duration_seconds=round(time.monotonic() - t0, 3),
            error=f"Skipped (missing input): {reason}",
        )
        if self._on_stage_complete:
            self._on_stage_complete(sr)
        return sr

    def _run_agent(
        self,
        stage_id: str,
        stage: Any,
        resolved_inputs: Dict[str, Any],
        stage_config: Dict[str, Any],
        t0: float,
    ) -> StageResult:
        agent = self._registry.get(stage.agent_id)
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
        return sr

    def _retry_with_circuit_breaker(
        self,
        stage_id: str,
        stage: Any,
        initial_result: StageResult,
    ) -> StageResult:
        et = initial_result.error_type or "unknown"
        self._circuit_breaker.record_failure(stage_id, et)

        for attempt in range(stage.retry_count):
            if self._circuit_breaker.is_open(stage_id):
                diag = self._circuit_breaker.get_diagnostic(stage_id)
                logger.warning("Circuit breaker tripped — skipping retry: %s", diag)
                break

            retry_sr = self._retry_stage(stage_id)
            if retry_sr.success:
                self._circuit_breaker.record_success(stage_id)
                return retry_sr

            retry_et = retry_sr.error_type or "unknown"
            opened = self._circuit_breaker.record_failure(stage_id, retry_et)
            if opened:
                break

        return initial_result

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
        """Extract quality_score from test case artifacts produced by any stage.

        Deduplicates by tc_id so that enrichment/downstream stages re-outputting
        the same test cases do not inflate total_test_cases in metrics (e.g.
        parse_requirements produces 20 TCs, enrich_test_cases re-outputs the same
        20 enriched TCs → without deduplication metrics would report 40).
        """
        seen_tc_ids: set = set()
        scores: List[float] = []
        for sr in self._stage_results.values():
            if not sr.agent_result or not sr.success:
                continue
            test_cases = sr.agent_result.artifacts.get("test_cases", [])
            for tc in test_cases:
                tc_id = getattr(tc, "tc_id", None)
                if tc_id is None and isinstance(tc, dict):
                    tc_id = tc.get("tc_id")
                # Skip duplicate TCs (same tc_id already counted from an earlier stage)
                if tc_id is not None:
                    if tc_id in seen_tc_ids:
                        continue
                    seen_tc_ids.add(tc_id)
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
        self._store.store(
            "_coverage",
            {
                "overall_coverage": report.overall_coverage,
                "total_acs": report.total_acs,
                "uncovered_count": len(report.uncovered_entries),
                "weak_count": len(report.weak_entries),
            },
        )

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
                self._store.store(
                    "_coverage",
                    {
                        "overall_coverage": report.overall_coverage,
                        "total_acs": report.total_acs,
                        "uncovered_count": len(report.uncovered_entries),
                        "weak_count": len(report.weak_entries),
                    },
                )

        return report.overall_coverage

    def _estimate_run_cost(
        self, input_tokens: int, output_tokens: int, total_tokens: int
    ) -> float:
        """Estimate LLM cost for this run based on provider/model config.

        Uses exact input/output counts reported by the configured provider.
        """
        try:
            from stlc_platform.core.llm.pricing import estimate_cost

            llm_cfg = self._config.get("llm", self._config.get("ollama", {}))
            provider = llm_cfg.get("provider", "ollama")
            model = llm_cfg.get("model", "")
            unclassified = max(0, total_tokens - input_tokens - output_tokens)
            if unclassified:
                metrics_cfg = self._config.get("metrics", {})
                input_ratio = float(metrics_cfg.get("input_token_ratio", 0.4))
                input_ratio = max(0.0, min(1.0, input_ratio))
                estimated_input = int(unclassified * input_ratio)
                input_tokens += estimated_input
                output_tokens += unclassified - estimated_input
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
            llm_client = self._resolver.resolve({"llm_client": "$runtime.llm_client"}).get(
                "llm_client"
            )
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

    @staticmethod
    def _build_gap_requirements(
        uncovered_entries: List[Any],
        requirements: List[Any],
    ) -> List[Any]:
        """Build filtered requirement objects containing only uncovered ACs."""
        from stlc_platform.core.contracts import RequirementArtifact

        gap_acs_by_req: Dict[str, List[str]] = {}
        for entry in uncovered_entries:
            gap_acs_by_req.setdefault(entry.req_id, []).append(entry.ac_text)

        gap_requirements: List[Any] = []
        for req in requirements:
            req_id = getattr(req, "req_id", "")
            if req_id in gap_acs_by_req:
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
        return gap_requirements

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
        uncovered = report.uncovered_entries
        logger.info(
            "Auto-fill gaps: %d uncovered ACs, invoking gap-fill generation",
            len(uncovered),
        )

        gap_requirements = self._build_gap_requirements(uncovered, requirements)
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
                    self._store.store(
                        "parse_requirements",
                        {
                            **existing,
                            "test_cases": existing_list,
                        },
                    )
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
                self._stage_results[dep] = StageResult(stage_id=dep, success=False, skipped=True)
                self._mark_downstream_skipped(dep)
