"""Tests for artifact download routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from stlc_platform.api.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestArtifactDownload:
    """Artifact download endpoint tests."""

    def test_download_invalid_run_id(self):
        resp = client.get("/api/artifacts/run@invalid!chars/download")
        assert resp.status_code == 400

    def test_download_missing_run(self):
        mock_mgr = MagicMock()
        mock_mgr.get_run.return_value = None
        with patch("stlc_platform.api.routes.artifacts.get_run_manager", return_value=mock_mgr):
            resp = client.get("/api/artifacts/run-abc-123/download")
        assert resp.status_code == 404

    def test_download_valid_run(self, tmp_path):
        run_dir = tmp_path / ".stlc_runs" / "run-ok"
        run_dir.mkdir(parents=True)
        (run_dir / "output.json").write_text('{"result": "ok"}')

        mock_mgr = MagicMock()
        mock_mgr.get_run.return_value = {"run_id": "run-ok", "artifacts": {}}

        with (
            patch("stlc_platform.api.routes.artifacts.get_run_manager", return_value=mock_mgr),
            patch("stlc_platform.api.routes.artifacts.get_output_dir", return_value=tmp_path),
        ):
            resp = client.get("/api/artifacts/run-ok/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
