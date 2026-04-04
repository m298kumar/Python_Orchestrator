"""
Tests for /api/pipeline/* endpoints.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api.deps import RunManager
from stlc_platform.api.main import app


@pytest.fixture()
def run_manager(tmp_path):
    """A fresh RunManager for each test."""
    return RunManager(persist_dir=tmp_path)


@pytest.fixture()
def client(run_manager):
    """TestClient that patches get_run_manager at the route-module level."""
    # The pipeline route calls get_run_manager() imported into its own namespace,
    # but it imports it from deps each call, so patching deps is sufficient.
    with patch("stlc_platform.api.deps._run_manager", run_manager):
        yield TestClient(app, raise_server_exceptions=False)


class TestPipelineRun:
    """POST /api/pipeline/run triggers a pipeline."""

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_returns_201_with_run_id(self, mock_submit, client: TestClient):
        resp = client.post("/api/pipeline/run", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)
        assert len(data["run_id"]) > 0

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_accepts_pipeline_path(self, mock_submit, client: TestClient):
        resp = client.post("/api/pipeline/run", json={
            "pipeline_path": "config/pipelines/api_test_only.yaml",
        })
        assert resp.status_code == 201

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_accepts_config_overrides(self, mock_submit, client: TestClient):
        resp = client.post("/api/pipeline/run", json={
            "config": {"project": {"domain": "ecommerce"}},
        })
        assert resp.status_code == 201

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_accepts_profile(self, mock_submit, client: TestClient):
        resp = client.post("/api/pipeline/run", json={
            "profile": "smoke",
        })
        assert resp.status_code == 201

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_response_has_status_pending(self, mock_submit, client: TestClient):
        resp = client.post("/api/pipeline/run", json={})
        data = resp.json()
        assert data["status"] == "pending"

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_run_calls_submit(self, mock_submit, client: TestClient):
        client.post("/api/pipeline/run", json={})
        assert mock_submit.called


class TestPipelineListRuns:
    """GET /api/pipeline/runs lists all runs."""

    def test_list_runs_returns_200(self, client: TestClient):
        resp = client.get("/api/pipeline/runs")
        assert resp.status_code == 200

    def test_list_runs_returns_list(self, client: TestClient):
        data = client.get("/api/pipeline/runs").json()
        assert isinstance(data, list)

    def test_list_runs_empty_initially(self, client: TestClient):
        data = client.get("/api/pipeline/runs").json()
        assert len(data) == 0

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_list_runs_includes_created_run(self, mock_submit, client: TestClient):
        client.post("/api/pipeline/run", json={})
        data = client.get("/api/pipeline/runs").json()
        assert len(data) == 1

    @patch("stlc_platform.api.routes.pipeline.submit_pipeline_run")
    def test_list_runs_has_summary_fields(self, mock_submit, client: TestClient):
        client.post("/api/pipeline/run", json={})
        runs = client.get("/api/pipeline/runs").json()
        run = runs[0]
        assert "run_id" in run
        assert "status" in run
        assert "started_at" in run
        assert "pipeline_name" in run
        assert "stages_completed_count" in run


class TestPipelineRunStatus:
    """GET /api/pipeline/runs/{run_id} returns status of a single run."""

    def test_unknown_run_returns_404(self, client: TestClient):
        resp = client.get("/api/pipeline/runs/nonexistent")
        assert resp.status_code == 404

    def test_known_run_returns_200(self, client: TestClient, run_manager: RunManager):
        rid = run_manager.create_run("test_pipeline")
        resp = client.get(f"/api/pipeline/runs/{rid}")
        assert resp.status_code == 200

    def test_known_run_has_status_fields(self, client: TestClient, run_manager: RunManager):
        rid = run_manager.create_run("test_pipeline")
        data = client.get(f"/api/pipeline/runs/{rid}").json()
        assert data["run_id"] == rid
        assert data["pipeline_name"] == "test_pipeline"
        assert data["status"] == "pending"
        assert "started_at" in data
        assert "stages_completed" in data
        assert "stages_failed" in data

    def test_completed_run_has_duration(self, client: TestClient, run_manager: RunManager):
        rid = run_manager.create_run("test_pipeline")
        run_manager.set_completed(rid, 1.234)
        data = client.get(f"/api/pipeline/runs/{rid}").json()
        assert data["status"] == "completed"
        assert data["total_duration_seconds"] == 1.234

    def test_failed_run_has_error_message(self, client: TestClient, run_manager: RunManager):
        rid = run_manager.create_run("test_pipeline")
        run_manager.set_failed(rid, "stage X blew up", 0.5)
        data = client.get(f"/api/pipeline/runs/{rid}").json()
        assert data["status"] == "failed"
        assert "stage X blew up" in data["error_message"]
