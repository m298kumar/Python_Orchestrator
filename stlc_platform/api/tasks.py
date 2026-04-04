"""
Background Task Runner
======================
Runs pipeline executions in background threads, broadcasting progress
via WebSocket to connected clients.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from stlc_platform.api.deps import get_agent_registry, get_run_manager, get_ws_manager

logger = logging.getLogger(__name__)

# Shared thread pool for background pipeline runs
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")

# Active orchestrators: run_id -> PipelineOrchestrator (for cancellation support)
_active_orchestrators: Dict[str, Any] = {}


def _populate_route_stores(run_id: str) -> None:
    """Load pipeline artifacts from disk into frontend-facing API route stores.

    Called after a pipeline run completes so that the Test Cases and BDD
    pages immediately show generated output without a server restart.
    """
    try:
        from stlc_platform.api.routes.test_cases import load_test_cases_from_run
        load_test_cases_from_run(run_id)
    except Exception:
        logger.warning("Could not populate test cases for run %s", run_id, exc_info=True)

    try:
        from stlc_platform.api.routes.bdd import load_feature_files_from_run
        load_feature_files_from_run(run_id)
    except Exception:
        logger.warning("Could not populate feature files for run %s", run_id, exc_info=True)


def run_pipeline_background(
    run_id: str,
    pipeline_path: str,
    config: Dict[str, Any],
    resume_from: Optional[str] = None,
    max_workers: int = 4,
    profile: Optional[str] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """
    Execute a pipeline in a background thread.

    This function runs synchronously in a thread. It uses the event loop
    to broadcast WebSocket messages back to the main async context.
    """
    from stlc_platform.pipeline.orchestrator import PipelineOrchestrator
    from stlc_platform.pipeline.pipeline_loader import load_pipeline
    from stlc_platform.pipeline.profile_loader import ProfileLoader
    from stlc_platform.pipeline.skill_loader import SkillLoader

    run_mgr = get_run_manager()
    ws_mgr = get_ws_manager()
    registry = get_agent_registry()

    run_mgr.set_running(run_id)
    start_time = time.monotonic()

    try:
        dag = load_pipeline(pipeline_path)

        # Load base config from stlc_config.yaml, then merge caller overrides
        from stlc_platform.core.config_loader import _find_project_root, _load_yaml, deep_merge
        base_config = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
        merged_config = deep_merge(base_config, config)

        # Inject uploaded requirements from the in-memory store (if any)
        # Convert dicts to Requirement dataclass instances since agents
        # expect objects with attributes (e.g. req.req_id), not dicts.
        from stlc_platform.api.routes.requirements import _requirements
        if _requirements and "requirements" not in merged_config:
            from stlc_platform.agents.requirements_agent.reader import Requirement
            reqs = []
            for d in _requirements.values():
                reqs.append(Requirement(
                    req_id=d.get("req_id", ""),
                    title=d.get("title", ""),
                    description=d.get("description", ""),
                    priority=d.get("priority", "Medium"),
                    category=d.get("category", "Functional"),
                    acceptance_criteria=d.get("acceptance_criteria", []),
                    tags=d.get("tags", []),
                ))
            merged_config["requirements"] = reqs

        config = merged_config

        # Load execution profile
        execution_profile = None
        if profile:
            loader = ProfileLoader()
            execution_profile = loader.load(profile)

        # Skill loader
        domain = config.get("project", {}).get("domain", "")
        skill_loader = SkillLoader(domain=domain)

        run_dir = get_run_manager()._persist_dir / ".stlc_runs" / run_id

        def on_stage_start(stage_id: str) -> None:
            run_mgr.update_run(run_id, current_stage=stage_id)
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_mgr.broadcast_stage_start(run_id, stage_id), loop
                )

        def on_stage_complete(sr) -> None:
            if sr.success:
                stages = run_mgr.get_run(run_id)
                if stages:
                    stages["stages_completed"].append(sr.stage_id)
            else:
                stages = run_mgr.get_run(run_id)
                if stages and not sr.skipped:
                    stages["stages_failed"].append(sr.stage_id)
                elif stages and sr.skipped:
                    stages["stages_skipped"].append(sr.stage_id)

            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_mgr.broadcast_stage_complete(
                        run_id, sr.stage_id, sr.success, sr.duration_seconds
                    ),
                    loop,
                )

        orchestrator = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            config=config,
            run_dir=run_dir,
            max_workers=max_workers,
            on_stage_start=on_stage_start,
            on_stage_complete=on_stage_complete,
            skill_loader=skill_loader,
            execution_profile=execution_profile,
        )
        _active_orchestrators[run_id] = orchestrator

        result = orchestrator.run(resume_from=resume_from)
        _active_orchestrators.pop(run_id, None)
        duration = time.monotonic() - start_time

        # Store result
        run_mgr.store_metadata(run_id, {
            "pipeline_result": result.model_dump(),
        })

        # Populate frontend-facing route stores from disk artifacts
        _populate_route_stores(run_id)

        if result.status == "completed":
            run_mgr.set_completed(run_id, duration)
        else:
            run_mgr.set_failed(
                run_id,
                result.error_message or "Pipeline failed",
                duration,
            )

        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                ws_mgr.broadcast_pipeline_complete(run_id, result.status, duration),
                loop,
            )

            # Broadcast degradation warning if present in result
            if result.error_message and "DEGRADATION ALERT" in (result.error_message or ""):
                asyncio.run_coroutine_threadsafe(
                    ws_mgr.broadcast(run_id, "degradation_warning", {
                        "message": result.error_message,
                    }),
                    loop,
                )

    except Exception as e:
        duration = time.monotonic() - start_time
        logger.exception("Pipeline run %s failed", run_id)
        run_mgr.set_failed(run_id, str(e), duration)

        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                ws_mgr.broadcast(run_id, "pipeline_error", {"error": str(e)}),
                loop,
            )


def cancel_pipeline_run(run_id: str) -> bool:
    """Cancel an active pipeline run. Returns True if an active orchestrator was found."""
    orch = _active_orchestrators.get(run_id)
    if orch is not None:
        orch.cancel()
        return True
    return False


def submit_pipeline_run(
    run_id: str,
    pipeline_path: str,
    config: Dict[str, Any],
    resume_from: Optional[str] = None,
    max_workers: int = 4,
    profile: Optional[str] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """Submit a pipeline run to the background thread pool.

    The caller should pass ``loop`` explicitly (e.g. from an async route
    via ``asyncio.get_running_loop()``). If not provided, the function
    tries to obtain the running loop, falling back to ``None`` so the
    pipeline still executes but without WebSocket broadcasting.
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop (e.g. called from a sync context).
            # Pipeline will run but WebSocket broadcasts will be skipped.
            loop = None

    _executor.submit(
        run_pipeline_background,
        run_id=run_id,
        pipeline_path=pipeline_path,
        config=config,
        resume_from=resume_from,
        max_workers=max_workers,
        profile=profile,
        loop=loop,
    )
