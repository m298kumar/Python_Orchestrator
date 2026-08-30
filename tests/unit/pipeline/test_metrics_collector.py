"""Unit tests for MetricsCollector and LLM pricing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import pytest
from stlc_platform.core.llm.pricing import estimate_cost
from stlc_platform.pipeline.metrics_collector import (
    MetricsCollector,
    RunMetrics,
    classify_quality,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


@dataclass
class FakeRunArtifact:
    run_id: str = "abc123"
    pipeline_name: str = "test_pipeline"
    total_duration_seconds: float = 12.5
    total_tokens_used: int = 500
    stage_durations: Dict[str, float] = field(default_factory=dict)
    stages_completed: List[str] = field(default_factory=lambda: ["s1", "s2"])
    stages_failed: List[str] = field(default_factory=list)
    stages_skipped: List[str] = field(default_factory=list)


# ── Quality classification ───────────────────────────────────────────────────


class TestClassifyQuality:
    def test_excellent(self):
        assert classify_quality(0.90) == "excellent"

    def test_good(self):
        assert classify_quality(0.70) == "good"

    def test_fair(self):
        assert classify_quality(0.50) == "fair"

    def test_poor(self):
        assert classify_quality(0.20) == "poor"

    def test_boundary_excellent(self):
        assert classify_quality(0.85) == "excellent"

    def test_boundary_good(self):
        assert classify_quality(0.65) == "good"

    def test_boundary_fair(self):
        assert classify_quality(0.40) == "fair"


# ── MetricsCollector ─────────────────────────────────────────────────────────


class TestMetricsCollector:
    def test_collect_with_quality_scores(self):
        collector = MetricsCollector()
        artifact = FakeRunArtifact()
        metrics = collector.collect(
            artifact,
            quality_scores=[0.90, 0.70, 0.50, 0.20],
            token_count=1000,
            input_tokens=700,
            output_tokens=300,
            llm_provider="openai",
            llm_model="gpt-4.1-mini",
        )
        assert metrics.run_id == "abc123"
        assert metrics.total_test_cases == 4
        assert metrics.avg_quality_score == pytest.approx(0.575, abs=0.001)
        assert metrics.quality_distribution["excellent"] == 1
        assert metrics.quality_distribution["good"] == 1
        assert metrics.quality_distribution["fair"] == 1
        assert metrics.quality_distribution["poor"] == 1
        assert metrics.tokens_used == 1000
        assert metrics.input_tokens == 700
        assert metrics.output_tokens == 300
        assert metrics.llm_provider == "openai"
        assert metrics.llm_model == "gpt-4.1-mini"
        assert metrics.stages_completed == 2

    def test_collect_no_quality_scores(self):
        collector = MetricsCollector()
        artifact = FakeRunArtifact()
        metrics = collector.collect(artifact)
        assert metrics.total_test_cases == 0
        assert metrics.avg_quality_score == 0.0
        assert metrics.tokens_used == 500  # falls back to artifact

    def test_persist_and_get_run(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        artifact = FakeRunArtifact(run_id="run42")
        metrics = collector.collect(artifact, quality_scores=[0.80])
        path = collector.persist(metrics)
        assert path.exists()

        loaded = collector.get_run("run42")
        assert loaded is not None
        assert loaded.run_id == "run42"
        assert loaded.avg_quality_score == pytest.approx(0.80, abs=0.001)

    def test_get_run_not_found(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        assert collector.get_run("nonexistent") is None

    def test_get_trends_ordered_newest_first(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        for i in range(5):
            artifact = FakeRunArtifact(run_id=f"run{i}")
            m = collector.collect(artifact, quality_scores=[0.5 + i * 0.1])
            # Set explicit timestamps so ordering is deterministic
            m.timestamp = f"2026-03-26T10:00:0{i}.000000+00:00"
            collector.persist(m)

        trends = collector.get_trends(last_n=3)
        assert len(trends) == 3
        # Sorted by timestamp newest-first → run4
        assert trends[0].run_id == "run4"

    def test_get_trends_empty_dir(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path / "empty")
        assert collector.get_trends() == []

    def test_detect_degradation_warning(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        history = [
            RunMetrics(run_id=f"h{i}", timestamp="", avg_quality_score=0.80) for i in range(5)
        ]
        current = RunMetrics(run_id="cur", timestamp="", avg_quality_score=0.60)
        warning = collector.detect_degradation(current, history)
        assert warning is not None
        assert "degradation" in warning.lower()
        assert "25.0%" in warning

    def test_detect_degradation_no_warning(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        history = [
            RunMetrics(run_id=f"h{i}", timestamp="", avg_quality_score=0.80) for i in range(5)
        ]
        current = RunMetrics(run_id="cur", timestamp="", avg_quality_score=0.75)
        warning = collector.detect_degradation(current, history)
        assert warning is None

    def test_detect_degradation_no_history(self, tmp_path):
        collector = MetricsCollector(metrics_dir=tmp_path)
        current = RunMetrics(run_id="cur", timestamp="", avg_quality_score=0.60)
        warning = collector.detect_degradation(current, [])
        assert warning is None


# ── LLM Pricing ──────────────────────────────────────────────────────────────


class TestLLMPricing:
    def test_ollama_free(self):
        cost = estimate_cost("ollama", "phi4-mini", 10000, 5000)
        assert cost == 0.0

    def test_openai_gpt4o(self):
        cost = estimate_cost("openai", "gpt-4o", 1000, 1000)
        expected = (1000 / 1000) * 0.0025 + (1000 / 1000) * 0.01
        assert cost == pytest.approx(expected, abs=1e-6)

    def test_anthropic_sonnet(self):
        cost = estimate_cost("anthropic", "claude-sonnet-4-20250514", 2000, 500)
        expected = (2000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert cost == pytest.approx(expected, abs=1e-6)

    def test_unknown_provider_returns_zero(self):
        assert estimate_cost("unknown_provider", "model", 1000, 1000) == 0.0

    def test_unknown_model_uses_default(self):
        cost = estimate_cost("openai", "future-model-xyz", 1000, 1000)
        # Should use _default pricing
        expected = (1000 / 1000) * 0.0025 + (1000 / 1000) * 0.01
        assert cost == pytest.approx(expected, abs=1e-6)
