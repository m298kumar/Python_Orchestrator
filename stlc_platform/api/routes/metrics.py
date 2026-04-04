"""
Metrics Routes
==============
Endpoints for pipeline run metrics, quality trends, and cost tracking.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from stlc_platform.api.deps import get_metrics_collector
from stlc_platform.api.schemas import (
    MetricsComparisonResponse,
    MetricsResponse,
    MetricsTrendResponse,
)
from stlc_platform.pipeline.metrics_collector import MetricsCollector

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def get_collector() -> MetricsCollector:
    """FastAPI dependency — returns the singleton MetricsCollector."""
    return get_metrics_collector()


@router.get("", response_model=List[MetricsResponse])
def list_metrics(
    last_n: int = Query(default=20, ge=1, le=100, description="Number of recent runs"),
    collector: MetricsCollector = Depends(get_collector),
) -> List[MetricsResponse]:
    """List metrics for recent pipeline runs."""
    runs = collector.get_trends(last_n=last_n)
    return [MetricsResponse(**_to_dict(m)) for m in runs]


@router.get("/trends", response_model=MetricsTrendResponse)
def get_trends(
    last_n: int = Query(default=10, ge=2, le=50, description="Number of runs to analyse"),
    collector: MetricsCollector = Depends(get_collector),
) -> MetricsTrendResponse:
    """Quality and cost trends over recent runs."""
    runs = collector.get_trends(last_n=last_n)
    if not runs:
        return MetricsTrendResponse(
            run_count=0,
            avg_quality_score=0.0,
            avg_generation_time=0.0,
            total_tokens=0,
            total_cost_usd=0.0,
            quality_trend=[],
            degradation_warning=None,
        )

    avg_quality = sum(r.avg_quality_score for r in runs) / len(runs)
    avg_time = sum(r.generation_time_seconds for r in runs) / len(runs)
    total_tokens = sum(r.tokens_used for r in runs)
    total_cost = sum(r.estimated_cost_usd for r in runs)
    quality_trend = [
        {"run_id": r.run_id, "score": r.avg_quality_score} for r in runs
    ]

    # Detect degradation on latest run
    warning = None
    if len(runs) >= 2:
        warning = collector.detect_degradation(runs[0], runs[1:])

    return MetricsTrendResponse(
        run_count=len(runs),
        avg_quality_score=round(avg_quality, 4),
        avg_generation_time=round(avg_time, 3),
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        quality_trend=quality_trend,
        degradation_warning=warning,
    )


@router.get("/{run_id}", response_model=MetricsResponse)
def get_run_metrics(
    run_id: str,
    collector: MetricsCollector = Depends(get_collector),
) -> MetricsResponse:
    """Get metrics for a specific pipeline run."""
    metrics = collector.get_run(run_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Metrics for run '{run_id}' not found")
    return MetricsResponse(**_to_dict(metrics))


@router.get("/compare", response_model=MetricsComparisonResponse)
def compare_runs(
    run_a: str = Query(..., description="First run ID"),
    run_b: str = Query(..., description="Second run ID"),
    collector: MetricsCollector = Depends(get_collector),
) -> MetricsComparisonResponse:
    """Compare metrics between two pipeline runs."""
    ma = collector.get_run(run_a)
    if ma is None:
        raise HTTPException(status_code=404, detail=f"Metrics for run '{run_a}' not found")
    mb = collector.get_run(run_b)
    if mb is None:
        raise HTTPException(status_code=404, detail=f"Metrics for run '{run_b}' not found")

    da, db = _to_dict(ma), _to_dict(mb)
    deltas: dict = {}
    for key in ("avg_quality_score", "tokens_used", "estimated_cost_usd",
                "generation_time_seconds", "coverage_pct", "total_test_cases"):
        va, vb = da.get(key, 0), db.get(key, 0)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            deltas[key] = round(va - vb, 6)

    return MetricsComparisonResponse(
        run_a=MetricsResponse(**da),
        run_b=MetricsResponse(**db),
        deltas=deltas,
    )


def _to_dict(m):
    """Convert RunMetrics dataclass to dict for Pydantic model."""
    from dataclasses import asdict
    return asdict(m)
