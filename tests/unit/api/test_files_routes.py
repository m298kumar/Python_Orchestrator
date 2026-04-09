"""
Tests for /api/files/* endpoints.

The files route handles upload/download with allowed-extension enforcement.
We reset the module-level state and use a temp output dir between tests.
"""

import pytest
from fastapi.testclient import TestClient
from stlc_platform.api import deps as deps_module
from stlc_platform.api.main import app
from stlc_platform.api.routes import files as files_module

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(tmp_path):
    """Reset uploaded-files registry and output dir between tests."""
    old_dir = deps_module._output_dir
    deps_module._output_dir = tmp_path
    files_module._uploaded_files.clear()
    yield
    files_module._uploaded_files.clear()
    deps_module._output_dir = old_dir


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/files/upload — valid file
# ---------------------------------------------------------------------------


class TestUploadFile:
    """POST /api/files/upload accepts files with allowed extensions."""

    def test_upload_json_returns_201(self, client: TestClient):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("spec.json", b'{"openapi":"3.0.0"}', "application/json")},
        )
        assert resp.status_code == 201

    def test_upload_returns_filename(self, client: TestClient):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("reqs.yaml", b"key: value", "application/x-yaml")},
        )
        body = resp.json()
        assert body["filename"] == "reqs.yaml"

    def test_upload_returns_size(self, client: TestClient):
        content = b"hello world"
        resp = client.post(
            "/api/files/upload",
            files={"file": ("data.txt", content, "text/plain")},
        )
        body = resp.json()
        assert body["size_bytes"] == len(content)

    def test_upload_writes_to_disk(self, client: TestClient, tmp_path):
        client.post(
            "/api/files/upload",
            files={"file": ("test.csv", b"a,b,c", "text/csv")},
        )
        uploaded = tmp_path / "uploads" / "test.csv"
        assert uploaded.exists()
        assert uploaded.read_bytes() == b"a,b,c"


# ---------------------------------------------------------------------------
# POST /api/files/upload — no file / bad input
# ---------------------------------------------------------------------------


class TestUploadFileErrors:
    """POST /api/files/upload rejects missing or disallowed files."""

    def test_no_file_returns_422(self, client: TestClient):
        resp = client.post("/api/files/upload")
        assert resp.status_code == 422

    def test_disallowed_extension_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_disallowed_extension_error_detail(self, client: TestClient):
        resp = client.post(
            "/api/files/upload",
            files={"file": ("image.png", b"\x89PNG", "image/png")},
        )
        body = resp.json()
        assert "not allowed" in body["detail"].lower()

    def test_all_allowed_extensions_accepted(self, client: TestClient):
        """Verify each allowed extension is accepted."""
        for ext in files_module.ALLOWED_EXTENSIONS:
            resp = client.post(
                "/api/files/upload",
                files={"file": (f"file.{ext}", b"data", "application/octet-stream")},
            )
            assert resp.status_code == 201, f"Extension '.{ext}' should be allowed"


# ---------------------------------------------------------------------------
# GET /api/files/download/{filename} — not found
# ---------------------------------------------------------------------------


class TestDownloadFileNotFound:
    """GET /api/files/download/{filename} returns 404 for missing files."""

    def test_nonexistent_file_returns_404(self, client: TestClient):
        resp = client.get("/api/files/download/no_such_file.json")
        assert resp.status_code == 404

    def test_404_includes_detail(self, client: TestClient):
        resp = client.get("/api/files/download/missing.yaml")
        body = resp.json()
        assert "not found" in body["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/files/download/{filename} — valid file
# ---------------------------------------------------------------------------


class TestDownloadFileValid:
    """GET /api/files/download/{filename} returns uploaded files."""

    def test_download_uploaded_file(self, client: TestClient):
        client.post(
            "/api/files/upload",
            files={"file": ("spec.json", b'{"key":"val"}', "application/json")},
        )
        resp = client.get("/api/files/download/spec.json")
        assert resp.status_code == 200

    def test_download_content_matches(self, client: TestClient):
        content = b"feature: login"
        client.post(
            "/api/files/upload",
            files={"file": ("login.feature", content, "text/plain")},
        )
        resp = client.get("/api/files/download/login.feature")
        assert resp.content == content

    def test_download_content_type(self, client: TestClient):
        client.post(
            "/api/files/upload",
            files={"file": ("data.txt", b"hello", "text/plain")},
        )
        resp = client.get("/api/files/download/data.txt")
        assert "octet-stream" in resp.headers.get("content-type", "")
