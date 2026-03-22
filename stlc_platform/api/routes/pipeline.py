"""
Pipeline Routes
===============
Run, list, and manage STLC pipeline executions.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from stlc_platform.api.deps import get_run_manager
from stlc_platform.api.schemas import (
    PipelineRunRequest,
    PipelineRunStatus,
    PipelineRunSummary,
)
from stlc_platform.api.tasks import submit_pipeline_run

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunStatus, status_code=201)
def create_run(req: PipelineRunRequest) -> PipelineRunStatus:
    """Create and trigger a new pipeline run."""
    mgr = get_run_manager()
    run_id = mgr.create_run(pipeline_name=req.pipeline_path)

    submit_pipeline_run(
        run_id=run_id,
        pipeline_path=req.pipeline_path,
        config=req.config,
        resume_from=req.resume_from,
        max_workers=req.max_workers,
        profile=req.profile,
    )

    run = mgr.get_run(run_id)
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
def list_runs() -> list[PipelineRunSummary]:
    """List all pipeline runs (most recent first)."""
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
            )
        )
    return result


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
    )


@router.post("/runs/{run_id}/resume", response_model=PipelineRunStatus, status_code=200)
def resume_run(run_id: str, resume_from: str | None = None) -> PipelineRunStatus:
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

    submit_pipeline_run(
        run_id=run_id,
        pipeline_path=r["pipeline_name"],
        config=r.get("metadata", {}).get("config", {}),
        resume_from=stage,
    )

    updated = mgr.get_run(run_id)
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
