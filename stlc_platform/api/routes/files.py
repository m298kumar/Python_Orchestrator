"""
File Routes
===========
Generic file upload and download for requirements, OpenAPI specs, HAR files, etc.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from stlc_platform.api.deps import get_output_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

# Track uploaded files: filename -> metadata
_uploaded_files: Dict[str, Dict[str, Any]] = {}

ALLOWED_EXTENSIONS = {"json", "yaml", "yml", "har", "feature", "txt", "csv"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", status_code=201)
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a file (requirements, OpenAPI spec, HAR file, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Reject path traversal attempts
    from pathlib import PurePosixPath
    safe_name = PurePosixPath(file.filename).name
    if safe_name != file.filename or ".." in file.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '.{ext}' not allowed. "
                f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    output_dir = get_output_dir()
    uploads_dir = output_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    dest = uploads_dir / file.filename
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    dest.write_bytes(content)

    file_size = len(content)
    _uploaded_files[file.filename] = {
        "filename": file.filename,
        "path": str(dest),
        "size_bytes": file_size,
        "content_type": file.content_type or "",
    }

    logger.info("File uploaded: %s (%d bytes)", file.filename, file_size)
    return {
        "filename": file.filename,
        "size_bytes": file_size,
        "message": "File uploaded successfully",
    }


@router.get("/download/{filename}")
def download_file(filename: str) -> FileResponse:
    """Download a generated or uploaded file."""
    from pathlib import PurePosixPath

    # Reject path traversal and glob metacharacter attempts
    safe_name = PurePosixPath(filename).name
    if safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if any(c in filename for c in ("*", "?", "[", "]")):
        raise HTTPException(status_code=400, detail="Invalid filename")

    output_dir = get_output_dir()

    # Check uploads directory first
    uploads_path = output_dir / "uploads" / filename
    if uploads_path.exists() and uploads_path.resolve().is_relative_to(output_dir.resolve()):
        return FileResponse(
            path=str(uploads_path),
            filename=filename,
            media_type="application/octet-stream",
        )

    # Search recursively in output directory, ensuring result stays within output_dir
    for path in output_dir.rglob(filename):
        if path.is_file() and path.resolve().is_relative_to(output_dir.resolve()):
            return FileResponse(
                path=str(path),
                filename=filename,
                media_type="application/octet-stream",
            )

    raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
