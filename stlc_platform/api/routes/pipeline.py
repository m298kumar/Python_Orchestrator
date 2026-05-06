"""
Pipeline Routes
===============
Run, list, and manage STLC pipeline executions.
"""

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from stlc_platform.api.deps import get_run_manager

# Allowed directory for pipeline definitions
_PIPELINES_DIR = Path("config/pipelines").resolve()


def _validate_pipeline_path(pipeline_path: str) -> Path:
    """Validate that pipeline_path is confined to config/pipelines/."""
    resolved = (_PIPELINES_DIR / Path(pipeline_path).name).resolve()
    if not str(resolved).startswith(str(_PIPELINES_DIR)):
        raise HTTPException(status_code=400, detail="Invalid pipeline path")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"Pipeline file not found: {resolved.name}")
    return resolved


# Run ID validation pattern (alphanumeric, hyphens, underscores, max 64 chars)
_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
from stlc_platform.api.schemas import (
    PipelineRunRequest,
    PipelineRunStatus,
    PipelineRunSummary,
)
from stlc_platform.api.tasks import cancel_pipeline_run, submit_pipeline_run

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunStatus, status_code=201)
async def create_run(req: PipelineRunRequest) -> PipelineRunStatus:
    """Create and trigger a new pipeline run."""
    validated_path = _validate_pipeline_path(req.pipeline_path)
    mgr = get_run_manager()
    run_id = mgr.create_run(pipeline_name=validated_path.name)

    loop = asyncio.get_running_loop()
    submit_pipeline_run(
        run_id=run_id,
        pipeline_path=str(validated_path),
        config=req.config,
        resume_from=req.resume_from,
        max_workers=req.max_workers,
        profile=req.profile,
        loop=loop,
    )

    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return PipelineRunStatus(
        run_id=run_id,
        pipeline_name=run["pipeline_name"],
        status=run["status"],
        started_at=run["started_at"],
        completed_at=run["completed_at"],
        stages_completed=run["stages_completed"],
        stages_failed=run["stages_failed"],
        stages_skipped=run["stages_skipped"],
        current_stage=run["current_stage"],
        total_duration_seconds=run["total_duration_seconds"],
        error_message=run["error_message"],
    )


@router.get("/runs", response_model=list[PipelineRunSummary])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> list[PipelineRunSummary]:
    """List all pipeline runs (most recent first) with pagination."""
    mgr = get_run_manager()
    result = []
    for r in mgr.list_runs():
        result.append(
            PipelineRunSummary(
                run_id=r["run_id"],
                pipeline_name=r["pipeline_name"],
                status=r["status"],
                started_at=r["started_at"],
                stages_completed_count=len(r["stages_completed"]),
                total_duration_seconds=r["total_duration_seconds"],
                archived=r.get("archived", False),
                archived_at=r.get("archived_at"),
            )
        )
    return result[offset : offset + limit]


@router.get("/runs/{run_id}", response_model=PipelineRunStatus)
def get_run(run_id: str) -> PipelineRunStatus:
    """Get detailed status of a specific pipeline run."""
    mgr = get_run_manager()
    r = mgr.get_run(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return PipelineRunStatus(
        run_id=r["run_id"],
        pipeline_name=r["pipeline_name"],
        status=r["status"],
        started_at=r["started_at"],
        completed_at=r["completed_at"],
        stages_completed=r["stages_completed"],
        stages_failed=r["stages_failed"],
        stages_skipped=r["stages_skipped"],
        current_stage=r["current_stage"],
        total_duration_seconds=r["total_duration_seconds"],
        error_message=r["error_message"],
        archived=r.get("archived", False),
        archived_at=r.get("archived_at"),
    )


@router.post("/runs/{run_id}/cancel", response_model=PipelineRunStatus, status_code=200)
def cancel_run(run_id: str) -> PipelineRunStatus:
    """Cancel a running pipeline. The pipeline will stop after the current stage completes."""
    mgr = get_run_manager()
    r = mgr.get_run(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if r["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Run '{run_id}' is {r['status']}, cannot cancel",
        )

    cancel_pipeline_run(run_id)
    mgr.set_cancelled(run_id)
    updated = mgr.get_run(run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return PipelineRunStatus(
        run_id=updated["run_id"],
        pipeline_name=updated["pipeline_name"],
        status=updated["status"],
        started_at=updated["started_at"],
        completed_at=updated["completed_at"],
        stages_completed=updated["stages_completed"],
        stages_failed=updated["stages_failed"],
        stages_skipped=updated["stages_skipped"],
        current_stage=updated["current_stage"],
        total_duration_seconds=updated["total_duration_seconds"],
        error_message=updated["error_message"],
    )


@router.post("/runs/{run_id}/resume", response_model=PipelineRunStatus, status_code=200)
async def resume_run(run_id: str, resume_from: str | None = None) -> PipelineRunStatus:
    """Resume a failed pipeline run from a specific stage."""
    mgr = get_run_manager()
    r = mgr.get_run(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if r["status"] not in ("failed",):
        raise HTTPException(
            status_code=400, detail=f"Run '{run_id}' is {r['status']}, not resumable"
        )

    # Determine resume stage: explicit param, or first failed stage
    stage = resume_from
    if not stage and r["stages_failed"]:
        stage = r["stages_failed"][0]
    if not stage:
        raise HTTPException(
            status_code=400,
            detail="No failed stage to resume from and no stage specified",
        )

    # Reset run state for resume
    mgr.update_run(run_id, status="pending", error_message=None, stages_failed=[])

    loop = asyncio.get_running_loop()
    submit_pipeline_run(
        run_id=run_id,
        pipeline_path=r["pipeline_name"],
        config=r.get("metadata", {}).get("config", {}),
        resume_from=stage,
        loop=loop,
    )

    updated = mgr.get_run(run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return PipelineRunStatus(
        run_id=updated["run_id"],
        pipeline_name=updated["pipeline_name"],
        status=updated["status"],
        started_at=updated["started_at"],
        completed_at=updated["completed_at"],
        stages_completed=updated["stages_completed"],
        stages_failed=updated["stages_failed"],
        stages_skipped=updated["stages_skipped"],
        current_stage=updated["current_stage"],
        total_duration_seconds=updated["total_duration_seconds"],
        error_message=updated["error_message"],
    )


@router.post("/runs/{run_id}/archive", response_model=PipelineRunSummary, status_code=200)
def archive_run_endpoint(run_id: str) -> PipelineRunSummary:
    """Soft-archive a pipeline run so it is hidden from active views."""
    mgr = get_run_manager()
    if not mgr.archive_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    r = mgr.get_run(run_id)
    return PipelineRunSummary(
        run_id=r["run_id"],
        pipeline_name=r["pipeline_name"],
        status=r["status"],
        started_at=r["started_at"],
        stages_completed_count=len(r["stages_completed"]),
        total_duration_seconds=r["total_duration_seconds"],
        archived=r.get("archived", True),
        archived_at=r.get("archived_at"),
    )


@router.post("/runs/{run_id}/restore", response_model=PipelineRunSummary, status_code=200)
def restore_run_endpoint(run_id: str) -> PipelineRunSummary:
    """Restore a soft-archived pipeline run back to active."""
    mgr = get_run_manager()
    if not mgr.restore_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    r = mgr.get_run(run_id)
    return PipelineRunSummary(
        run_id=r["run_id"],
        pipeline_name=r["pipeline_name"],
        status=r["status"],
        started_at=r["started_at"],
        stages_completed_count=len(r["stages_completed"]),
        total_duration_seconds=r["total_duration_seconds"],
        archived=r.get("archived", False),
        archived_at=r.get("archived_at"),
    )


@router.delete("/runs/{run_id}", status_code=200)
def delete_run_endpoint(run_id: str) -> dict:
    """Hard-delete a single pipeline run and all its artifacts from disk."""
    mgr = get_run_manager()
    r = mgr.get_run(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if r.get("status") in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Run '{run_id}' is currently {r['status']}. Cancel it first.",
        )
    # Clear associated in-memory stores
    _clear_run_from_stores(run_id)
    mgr.delete_run(run_id)
    return {"deleted": run_id}


@router.delete("/runs", status_code=200)
def clear_all_runs_endpoint() -> dict:
    """Hard-delete ALL terminal pipeline runs and their artifacts."""
    mgr = get_run_manager()
    # Gather run_ids that will be deleted (terminal ones)
    all_runs = mgr.list_runs()
    terminal_ids = [r["run_id"] for r in all_runs if r.get("status") not in ("pending", "running")]
    for rid in terminal_ids:
        _clear_run_from_stores(rid)
    deleted = mgr.clear_all_runs()
    return {"deleted": deleted}


def _clear_run_from_stores(run_id: str) -> None:
    """Clear a single run's data from all in-memory route-level stores."""
    try:
        from stlc_platform.api.deps import get_ff_store, get_tc_store
        get_tc_store().clear_run(run_id)
        get_ff_store().clear_run(run_id)
    except Exception:
        pass
    try:
        from stlc_platform.api.routes.api_tests import clear_run as clear_api_tests_run
        clear_api_tests_run(run_id)
    except Exception:
        pass
    try:
        from stlc_platform.api.routes.crawler import clear_run as clear_crawler_run
        clear_crawler_run(run_id)
    except Exception:
        pass
