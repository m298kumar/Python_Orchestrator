"""
Tests for /api/artifacts/* endpoints.

The artifacts route uses RunManager for state and produces ZIP downloads.
We reset the RunManager between tests to ensure isolation.
"""

import zipfile
import io

import pytest
from fastapi.testclient import TestClient

from stlc_platform.api.main import app
from stlc_platform.api import deps as deps_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_run_manager(tmp_path):
    """Reset the RunManager singleton and output dir between tests."""
    old_mgr = deps_module._run_manager
    old_dir = deps_module._output_dir
    deps_module._run_manager = deps_module.RunManager()
    deps_module._output_dir = tmp_path
    yield
    deps_module._run_manager = old_mgr
    deps_module._output_dir = old_dir


@pytest.fixture()
def client():
    return TestClient(app)


def _seed_run(run_id: str = "test-run", pipeline: str = "full_stlc", artifacts=None):
    """Create a run in the RunManager and optionally attach artifacts."""
    mgr = deps_module.get_run_manager()
    mgr.create_run(pipeline, run_id=run_id)
    if artifacts:
        mgr.store_artifacts(run_id, artifacts)
    return run_id


# ---------------------------------------------------------------------------
# GET /api/artifacts/{run_id}/download — non-existent run
# ---------------------------------------------------------------------------

class TestDownloadArtifactsNotFound:
    """GET /api/artifacts/{run_id}/download returns 404 for unknown runs."""

    def test_nonexistent_run_returns_404(self, client: TestClient):
        resp = client.get("/api/artifacts/nonexistent/download")
        assert resp.status_code == 404

    def test_404_includes_detail(self, client: TestClient):
        resp = client.get("/api/artifacts/no-such-run/download")
        body = resp.json()
        assert "not found" in body["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/artifacts/{run_id}/download — valid run
# ---------------------------------------------------------------------------

class TestDownloadArtifactsValid:
    """GET /api/artifacts/{run_id}/download returns a ZIP for existing runs."""

    def test_valid_run_returns_200(self, client: TestClient):
        _seed_run("run-1")
        resp = client.get("/api/artifacts/run-1/download")
        assert resp.status_code == 200

    def test_response_content_type_is_zip(self, client: TestClient):
        _seed_run("run-2")
        resp = client.get("/api/artifacts/run-2/download")
        assert "application/zip" in resp.headers.get("content-type", "")

    def test_content_disposition_header(self, client: TestClient):
        _seed_run("run-3")
        resp = client.get("/api/artifacts/run-3/download")
        disposition = resp.headers.get("content-disposition", "")
        assert "run_run-3_artifacts.zip" in disposition

    def test_zip_contains_artifacts_json(self, client: TestClient):
        _seed_run("run-4", artifacts={"requirements": {"count": 5}})
        resp = client.get("/api/artifacts/run-4/download")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert "artifacts.json" in zf.namelist()

    def test_empty_run_produces_valid_zip(self, client: TestClient):
        _seed_run("run-5")
        resp = client.get("/api/artifacts/run-5/download")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        # Empty run with no artifacts dict entries -> empty zip
        assert isinstance(zf.namelist(), list)

    def test_zip_includes_on_disk_files(self, client: TestClient, tmp_path):
        """When the run directory has files on disk, they appear in the ZIP."""
        _seed_run("run-6")
        run_dir = tmp_path / ".stlc_runs" / "run-6"
        run_dir.mkdir(parents=True)
        (run_dir / "output.json").write_text('{"result": true}')

        resp = client.get("/api/artifacts/run-6/download")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert "output.json" in zf.namelist()
