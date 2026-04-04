"""Tests for file upload/download routes."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from stlc_platform.api.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestUpload:
    """File upload endpoint tests."""

    def test_upload_valid_json(self, tmp_path):
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.post(
                "/api/files/upload",
                files={"file": ("test.json", BytesIO(b'{"key": "val"}'), "application/json")},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "test.json"
        assert data["size_bytes"] > 0

    def test_upload_rejected_extension(self, tmp_path):
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.post(
                "/api/files/upload",
                files={"file": ("evil.exe", BytesIO(b"binary"), "application/octet-stream")},
            )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]

    def test_upload_path_traversal_rejected(self, tmp_path):
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.post(
                "/api/files/upload",
                files={"file": ("../etc/passwd.json", BytesIO(b"{}"), "application/json")},
            )
        assert resp.status_code == 400
        assert "Invalid filename" in resp.json()["detail"]


class TestDownload:
    """File download endpoint tests."""

    def test_download_existing_file(self, tmp_path):
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        (uploads / "report.json").write_text('{"ok": true}')

        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.get("/api/files/download/report.json")
        assert resp.status_code == 200

    def test_download_missing_file(self, tmp_path):
        (tmp_path / "uploads").mkdir()
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.get("/api/files/download/nonexistent.json")
        assert resp.status_code == 404

    def test_download_path_traversal_rejected(self, tmp_path):
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.get("/api/files/download/..\\secret.json")
        assert resp.status_code == 400

    def test_download_glob_metacharacters_rejected(self, tmp_path):
        with patch("stlc_platform.api.routes.files.get_output_dir", return_value=tmp_path):
            resp = client.get("/api/files/download/*.json")
        assert resp.status_code == 400
        assert "Invalid filename" in resp.json()["detail"]
