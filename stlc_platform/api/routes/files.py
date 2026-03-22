"""
File Routes
===========
Generic file upload and download for requirements, OpenAPI specs, HAR files, etc.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from stlc_platform.api.deps import get_output_dir

router = APIRouter(prefix="/api/files", tags=["files"])

# Track uploaded files: filename -> metadata
_uploaded_files: Dict[str, Dict[str, Any]] = {}

ALLOWED_EXTENSIONS = {"json", "yaml", "yml", "har", "feature", "txt", "csv"}


@router.post("/upload", status_code=201)
async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a file (requirements, OpenAPI spec, HAR file, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    output_dir = get_output_dir()
    uploads_dir = output_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    dest = uploads_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    file_size = len(content)
    _uploaded_files[file.filename] = {
        "filename": file.filename,
        "path": str(dest),
        "size_bytes": file_size,
        "content_type": file.content_type or "",
    }

    return {
        "filename": file.filename,
        "size_bytes": file_size,
        "message": "File uploaded successfully",
    }


@router.get("/download/{filename}")
def download_file(filename: str) -> FileResponse:
    """Download a generated or uploaded file."""
    output_dir = get_output_dir()

    # Check uploads directory first
    uploads_path = output_dir / "uploads" / filename
    if uploads_path.exists():
        return FileResponse(
            path=str(uploads_path),
            filename=filename,
            media_type="application/octet-stream",
        )

    # Search recursively in output directory
    for path in output_dir.rglob(filename):
        if path.is_file():
            return FileResponse(
                path=str(path),
                filename=filename,
                media_type="application/octet-stream",
            )

    raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
