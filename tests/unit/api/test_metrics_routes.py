"""
Tests for /api/metrics/* endpoints.

Uses FastAPI dependency overrides to inject a mock MetricsCollector
so tests don't depend on the filesystem.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.main import app
from stlc_platform.api.routes.metrics import get_collector
from stlc_platform.pipeline.metrics_collector import MetricsCollector, RunMetrics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_metrics(run_id: str = "abc123", **overrides) -> RunMetrics:
    defaults = {
        "run_id": run_id,
        "timestamp": "2026-03-27T10:00:00+00:00",
        "pipeline_name": "full_stlc",
        "total_test_cases": 10,
        "avg_quality_score": 0.82,
        "quality_distribution": {"excellent": 3, "good": 4, "fair": 2, "poor": 1},
        "tokens_used": 5000,
        "estimated_cost_usd": 0.012,
        "cache_hit_rate": 0.4,
        "generation_time_seconds": 12.5,
        "per_stage_durations": {"parse_requirements": 5.0, "generate_bdd_code": 7.5},
        "per_ac_type_scores": {"positive": 0.9, "negative": 0.7},
        "coverage_pct": 85.0,
        "stages_completed": 3,
        "stages_failed": 0,
        "stages_skipped": 1,
    }
    defaults.update(overrides)
    return RunMetrics(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_collector():
    """Create a mock MetricsCollector."""
    return MagicMock(spec=MetricsCollector)


@pytest.fixture()
def client(mock_collector):
    """Test client with overridden metrics dependency."""
    app.dependency_overrides[get_collector] = lambda: mock_collector
    yield TestClient(app)
    app.dependency_overrides.pop(get_collector, None)


# ---------------------------------------------------------------------------
# GET /api/metrics
# ---------------------------------------------------------------------------

class TestListMetrics:
    def test_list_returns_metrics(self, client, mock_collector):
        runs = [_make_run_metrics("run-1"), _make_run_metrics("run-2")]
        mock_collector.get_trends.return_value = runs

        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["run_id"] == "run-1"
        assert data[1]["run_id"] == "run-2"

    def test_list_empty(self, client, mock_collector):
        mock_collector.get_trends.return_value = []
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_respects_last_n(self, client, mock_collector):
        mock_collector.get_trends.return_value = []
        client.get("/api/metrics?last_n=5")
        mock_collector.get_trends.assert_called_once_with(last_n=5)

    def test_list_validates_last_n_min(self, client, mock_collector):
        resp = client.get("/api/metrics?last_n=0")
        assert resp.status_code == 422

    def test_list_validates_last_n_max(self, client, mock_collector):
        resp = client.get("/api/metrics?last_n=200")
        assert resp.status_code == 422

    def test_list_metrics_fields(self, client, mock_collector):
        m = _make_run_metrics()
        mock_collector.get_trends.return_value = [m]
        resp = client.get("/api/metrics")
        data = resp.json()[0]
        assert data["pipeline_name"] == "full_stlc"
        assert data["total_test_cases"] == 10
        assert data["avg_quality_score"] == 0.82
        assert data["tokens_used"] == 5000
        assert data["coverage_pct"] == 85.0
        assert data["stages_completed"] == 3
        assert data["stages_failed"] == 0
        assert data["stages_skipped"] == 1


# ---------------------------------------------------------------------------
# GET /api/metrics/trends
# ---------------------------------------------------------------------------

class TestGetTrends:
    def test_trends_with_data(self, client, mock_collector):
        runs = [
            _make_run_metrics("r1", avg_quality_score=0.80, tokens_used=1000,
                              generation_time_seconds=10.0, estimated_cost_usd=0.01),
            _make_run_metrics("r2", avg_quality_score=0.90, tokens_used=2000,
                              generation_time_seconds=20.0, estimated_cost_usd=0.02),
        ]
        mock_collector.get_trends.return_value = runs
        mock_collector.detect_degradation.return_value = None

        resp = client.get("/api/metrics/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 2
        assert data["avg_quality_score"] == 0.85
        assert data["total_tokens"] == 3000
        assert data["total_cost_usd"] == 0.03
        assert len(data["quality_trend"]) == 2
        assert data["degradation_warning"] is None

    def test_trends_empty(self, client, mock_collector):
        mock_collector.get_trends.return_value = []
        resp = client.get("/api/metrics/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 0
        assert data["avg_quality_score"] == 0.0
        assert data["quality_trend"] == []

    def test_trends_with_degradation(self, client, mock_collector):
        runs = [
            _make_run_metrics("r1", avg_quality_score=0.50),
            _make_run_metrics("r2", avg_quality_score=0.90),
        ]
        mock_collector.get_trends.return_value = runs
        mock_collector.detect_degradation.return_value = "Quality dropped 44%"

        resp = client.get("/api/metrics/trends")
        data = resp.json()
        assert data["degradation_warning"] == "Quality dropped 44%"

    def test_trends_validates_last_n_min(self, client, mock_collector):
        resp = client.get("/api/metrics/trends?last_n=1")
        assert resp.status_code == 422

    def test_trends_validates_last_n_max(self, client, mock_collector):
        resp = client.get("/api/metrics/trends?last_n=100")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/metrics/{run_id}
# ---------------------------------------------------------------------------

class TestGetRunMetrics:
    def test_get_existing_run(self, client, mock_collector):
        m = _make_run_metrics("abc123")
        mock_collector.get_run.return_value = m

        resp = client.get("/api/metrics/abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "abc123"
        assert data["avg_quality_score"] == 0.82

    def test_get_nonexistent_run(self, client, mock_collector):
        mock_collector.get_run.return_value = None

        resp = client.get("/api/metrics/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_get_run_full_fields(self, client, mock_collector):
        m = _make_run_metrics(
            "full-run",
            per_stage_durations={"s1": 2.0, "s2": 3.0},
            quality_distribution={"excellent": 5, "good": 3, "fair": 1, "poor": 0},
        )
        mock_collector.get_run.return_value = m

        resp = client.get("/api/metrics/full-run")
        data = resp.json()
        assert data["per_stage_durations"] == {"s1": 2.0, "s2": 3.0}
        assert data["quality_distribution"]["excellent"] == 5
        assert data["cache_hit_rate"] == 0.4
