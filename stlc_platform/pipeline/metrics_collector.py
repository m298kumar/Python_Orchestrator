"""
Metrics Collector
=================
Collects per-run quality, cost, and performance metrics.
Persists to JSON files for trend analysis and degradation detection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default output directory for metrics
_DEFAULT_METRICS_DIR = Path("output/metrics")


@dataclass
class RunMetrics:
    """Metrics snapshot for a single pipeline run."""

    run_id: str
    timestamp: str
    pipeline_name: str = ""
    total_test_cases: int = 0
    avg_quality_score: float = 0.0
    quality_distribution: Dict[str, int] = field(
        default_factory=lambda: {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
    )
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    cache_hit_rate: float = 0.0
    generation_time_seconds: float = 0.0
    per_stage_durations: Dict[str, float] = field(default_factory=dict)
    per_ac_type_scores: Dict[str, float] = field(default_factory=dict)
    coverage_pct: float = 0.0
    stages_completed: int = 0
    stages_failed: int = 0
    stages_skipped: int = 0


def classify_quality(score: float) -> str:
    """Classify a quality score into a bucket."""
    if score >= 0.85:
        return "excellent"
    if score >= 0.65:
        return "good"
    if score >= 0.40:
        return "fair"
    return "poor"


class MetricsCollector:
    """Collects, persists, and analyses pipeline run metrics."""

    def __init__(self, metrics_dir: Optional[Path] = None) -> None:
        self._metrics_dir = metrics_dir or _DEFAULT_METRICS_DIR

    def collect(
        self,
        run_artifact: Any,
        quality_scores: Optional[List[float]] = None,
        token_count: int = 0,
        estimated_cost: float = 0.0,
        cache_hit_rate: float = 0.0,
        coverage_pct: float = 0.0,
        per_ac_type_scores: Optional[Dict[str, float]] = None,
    ) -> RunMetrics:
        """Build a RunMetrics from a PipelineRunArtifact and optional quality data."""
        scores = quality_scores or []

        distribution: Dict[str, int] = {
            "excellent": 0,
            "good": 0,
            "fair": 0,
            "poor": 0,
        }
        for s in scores:
            distribution[classify_quality(s)] += 1

        avg_score = sum(scores) / len(scores) if scores else 0.0

        return RunMetrics(
            run_id=run_artifact.run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            pipeline_name=getattr(run_artifact, "pipeline_name", ""),
            total_test_cases=len(scores),
            avg_quality_score=round(avg_score, 4),
            quality_distribution=distribution,
            tokens_used=token_count or getattr(run_artifact, "total_tokens_used", 0),
            estimated_cost_usd=round(estimated_cost, 6),
            cache_hit_rate=round(cache_hit_rate, 4),
            generation_time_seconds=getattr(
                run_artifact, "total_duration_seconds", 0.0
            ),
            per_stage_durations=getattr(run_artifact, "stage_durations", {}),
            per_ac_type_scores=per_ac_type_scores or {},
            coverage_pct=round(coverage_pct, 4),
            stages_completed=len(
                getattr(run_artifact, "stages_completed", [])
            ),
            stages_failed=len(getattr(run_artifact, "stages_failed", [])),
            stages_skipped=len(getattr(run_artifact, "stages_skipped", [])),
        )

    # Maximum number of metrics files to retain (oldest are pruned on persist)
    MAX_METRICS_FILES = 200

    def persist(self, metrics: RunMetrics) -> Path:
        """Write metrics to a JSON file. Returns the file path."""
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        path = self._metrics_dir / f"{metrics.run_id}.json"
        path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")
        logger.info("Metrics persisted to %s", path)
        self._prune_old_files()
        return path

    def _prune_old_files(self) -> None:
        """Remove oldest metrics files when count exceeds MAX_METRICS_FILES."""
        files = sorted(self._metrics_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
        excess = len(files) - self.MAX_METRICS_FILES
        if excess > 0:
            for f in files[:excess]:
                f.unlink(missing_ok=True)
            logger.info("Pruned %d old metrics files", excess)

    def get_run(self, run_id: str) -> Optional[RunMetrics]:
        """Load metrics for a specific run."""
        path = self._metrics_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return RunMetrics(**data)

    def get_trends(self, last_n: int = 10) -> List[RunMetrics]:
        """Load the most recent N metrics files, ordered newest-first."""
        if not self._metrics_dir.exists():
            return []

        all_metrics: List[RunMetrics] = []
        for f in self._metrics_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                all_metrics.append(RunMetrics(**data))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping corrupt metrics file: %s", f)

        # Sort by ISO timestamp (newest first)
        all_metrics.sort(key=lambda m: m.timestamp, reverse=True)
        return all_metrics[:last_n]

    def detect_degradation(
        self,
        current: RunMetrics,
        history: Optional[List[RunMetrics]] = None,
        threshold_pct: float = 15.0,
    ) -> Optional[str]:
        """Compare current run against rolling average. Returns warning or None.

        A warning is returned when avg_quality_score drops by more than
        ``threshold_pct`` percent relative to the historical average.
        """
        if history is None:
            history = self.get_trends(last_n=5)

        # Exclude current run from history if present
        past = [m for m in history if m.run_id != current.run_id]
        if not past:
            return None

        avg_hist = sum(m.avg_quality_score for m in past) / len(past)
        if avg_hist == 0:
            return None

        drop_pct = ((avg_hist - current.avg_quality_score) / avg_hist) * 100

        if drop_pct > threshold_pct:
            return (
                f"Quality degradation detected: current avg {current.avg_quality_score:.3f} "
                f"vs historical avg {avg_hist:.3f} "
                f"({drop_pct:.1f}% drop, threshold {threshold_pct}%)"
            )
        return None
