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

    Called after a pipeline run completes so that Test Cases, BDD, and API
    Test pages immediately show generated output without a server restart.
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

    try:
        from stlc_platform.api.routes.api_tests import load_api_tests_from_run

        load_api_tests_from_run(run_id)
    except Exception:
        logger.warning("Could not populate API tests for run %s", run_id, exc_info=True)

    try:
        from stlc_platform.api.routes.crawler import load_crawler_from_run

        load_crawler_from_run(run_id)
    except Exception:
        logger.warning("Could not populate crawler data for run %s", run_id, exc_info=True)


def _load_merged_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Load base stlc_config.yaml and merge caller overrides on top."""
    from stlc_platform.core.config_loader import _find_project_root, _load_yaml, deep_merge

    base_config = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
    return deep_merge(base_config, config)


def _extract_urls_from_requirements(merged_config: Dict[str, Any]) -> None:
    """Scan requirements for URLs/API paths and inject into config for crawler and API agent.

    - Full URLs (http/https) → injects ``base_url`` for the crawler agent if not already set.
    - API-style paths (containing /api/, ?route=api/, REST verbs) → builds a minimal
      OpenAPI 3.0 spec and injects as ``openapi_spec`` for the API test agent if not set.

    Mutates *merged_config* in place. Runs after _inject_requirements so requirements
    are already present in the config.
    """
    import re
    from urllib.parse import urlparse

    reqs = merged_config.get("requirements", [])
    if not reqs:
        # Also check raw in-memory store
        from stlc_platform.api.routes.requirements import _requirements

        reqs = list(_requirements.values()) if _requirements else []

    if not reqs:
        return

    full_url_re = re.compile(r'https?://[^\s<>"\'(),;]+')
    path_re = re.compile(r"(/[a-zA-Z0-9_./?=&%#-]{3,})")
    api_path_re = re.compile(
        r"(/(?:api|v\d+)/[a-zA-Z0-9_./?=&%-]+|/index\.php\?route=api/[a-zA-Z0-9_/]+)",
        re.IGNORECASE,
    )

    full_urls: set = set()
    api_paths: set = set()

    for req in reqs:
        # Support both Requirement objects (with .description) and dicts
        if hasattr(req, "description"):
            texts = [req.description or ""]
            ac = req.acceptance_criteria or []
            texts += ac if isinstance(ac, list) else [ac]
        else:
            texts = [req.get("description", "")]
            ac = req.get("acceptance_criteria", [])
            texts += ac if isinstance(ac, list) else [ac]

        for text in texts:
            if not isinstance(text, str):
                continue
            for url in full_url_re.findall(text):
                full_urls.add(url.rstrip(".,;)>"))
            for path in path_re.findall(text):
                path = path.rstrip(".,;)>")
                if api_path_re.match(path):
                    api_paths.add(path)

    # Inject crawler base_url if not already configured
    crawler_cfg = merged_config.setdefault("crawler", {})
    if not crawler_cfg.get("base_url") and not crawler_cfg.get("html_pages"):
        if full_urls:
            parsed = urlparse(next(iter(full_urls)))
            base = f"{parsed.scheme}://{parsed.netloc}"
            crawler_cfg["base_url"] = base
            logger.info("Extracted crawler base_url from requirements: %s", base)

    # Build minimal OpenAPI spec from discovered API paths if none configured
    api_cfg = merged_config.setdefault("api_testing", {})
    if not api_cfg.get("openapi_spec") and api_paths:
        base_url = merged_config.get("base_url", "")
        paths_section: Dict[str, Any] = {}
        for path in sorted(api_paths):
            # Normalise ?route=api/login → /api/login for OpenAPI path key
            if "route=api/" in path:
                norm = "/" + path.split("route=api/", 1)[1].split("&")[0]
            else:
                norm = path.split("?")[0]
            paths_section[norm] = {
                "post": {
                    "summary": f"Auto-discovered endpoint: {norm}",
                    "responses": {"200": {"description": "Success"}},
                },
                "get": {
                    "summary": f"Auto-discovered endpoint: {norm}",
                    "responses": {"200": {"description": "Success"}},
                },
            }
        spec: Dict[str, Any] = {
            "openapi": "3.0.0",
            "info": {"title": "Auto-discovered API", "version": "1.0.0"},
            "servers": [{"url": base_url}] if base_url else [],
            "paths": paths_section,
        }
        # Inject under api_testing.openapi_spec so the pipeline resolver finds it at
        # "$?config.api_testing.openapi_spec" (full_stlc.yaml: discover_apis stage)
        merged_config.setdefault("api_testing", {})["openapi_spec"] = spec
        logger.info(
            "Built minimal OpenAPI spec from %d API paths found in requirements", len(api_paths)
        )


def _inject_requirements(merged_config: Dict[str, Any]) -> None:
    """Inject uploaded requirements from the in-memory store into config.

    Converts dicts to Requirement dataclass instances since agents
    expect objects with attributes (e.g. req.req_id), not dicts.
    Mutates *merged_config* in place.
    """
    from stlc_platform.api.routes.requirements import _requirements

    if not _requirements or "requirements" in merged_config:
        return
    from stlc_platform.agents.requirements_agent.reader import Requirement

    reqs = []
    for d in _requirements.values():
        reqs.append(
            Requirement(
                req_id=d.get("req_id", ""),
                title=d.get("title", ""),
                description=d.get("description", ""),
                priority=d.get("priority", "Medium"),
                category=d.get("category", "Functional"),
                acceptance_criteria=d.get("acceptance_criteria", []),
                tags=d.get("tags", []),
            )
        )
    merged_config["requirements"] = reqs


def _record_stage_result(run_mgr: Any, run_id: str, sr: Any) -> None:
    """Update run manager with stage completion status."""
    stages = run_mgr.get_run(run_id)
    if not stages:
        return
    if sr.success:
        stages["stages_completed"].append(sr.stage_id)
    elif sr.skipped:
        stages["stages_skipped"].append(sr.stage_id)
    else:
        stages["stages_failed"].append(sr.stage_id)


def _make_stage_callbacks(
    run_id: str,
    run_mgr: Any,
    ws_mgr: Any,
    loop: Optional[asyncio.AbstractEventLoop],
):
    """Create on_stage_start and on_stage_complete callbacks."""

    def on_stage_start(stage_id: str) -> None:
        run_mgr.update_run(run_id, current_stage=stage_id)
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(ws_mgr.broadcast_stage_start(run_id, stage_id), loop)

    def on_stage_complete(sr) -> None:
        _record_stage_result(run_mgr, run_id, sr)
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                ws_mgr.broadcast_stage_complete(
                    run_id, sr.stage_id, sr.success, sr.duration_seconds
                ),
                loop,
            )

    return on_stage_start, on_stage_complete


def _handle_pipeline_result(
    result: Any,
    run_id: str,
    duration: float,
    run_mgr: Any,
    ws_mgr: Any,
    loop: Optional[asyncio.AbstractEventLoop],
) -> None:
    """Store pipeline result, populate route stores, and broadcast completion."""
    run_mgr.store_metadata(
        run_id,
        {
            "pipeline_result": result.model_dump(),
        },
    )

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

        if result.error_message and "DEGRADATION ALERT" in (result.error_message or ""):
            asyncio.run_coroutine_threadsafe(
                ws_mgr.broadcast(
                    run_id,
                    "degradation_warning",
                    {
                        "message": result.error_message,
                    },
                ),
                loop,
            )


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
        config = _load_merged_config(config)
        _inject_requirements(config)

        # Fail fast with a clear message if no requirements have been uploaded.
        # Without this, the pipeline fails deep inside the artifact resolver with a
        # cryptic "Config path 'requirements' not found" KeyError.
        if not config.get("requirements"):
            msg = (
                "No requirements found. Please upload requirements via the Requirements page "
                "before running the pipeline."
            )
            logger.error("Pipeline run %s aborted: %s", run_id, msg)
            run_mgr.set_failed(run_id, msg, time.monotonic() - start_time)
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    ws_mgr.broadcast(run_id, "pipeline_error", {"error": msg}),
                    loop,
                )
            return

        _extract_urls_from_requirements(config)

        execution_profile = None
        if profile:
            loader = ProfileLoader()
            execution_profile = loader.load(profile)

        domain = config.get("project", {}).get("domain", "")
        skill_loader = SkillLoader(domain=domain)
        run_dir = get_run_manager()._persist_dir / ".stlc_runs" / run_id

        on_stage_start, on_stage_complete = _make_stage_callbacks(
            run_id,
            run_mgr,
            ws_mgr,
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

        _handle_pipeline_result(result, run_id, duration, run_mgr, ws_mgr, loop)

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
