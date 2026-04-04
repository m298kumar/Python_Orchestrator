"""
Artifact Routes
===============
Download pipeline run artifacts as ZIP archives.
"""

from __future__ import annotations

import io
import re
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from stlc_platform.api.deps import get_output_dir, get_run_manager

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@router.get("/{run_id}/download")
def download_artifacts(run_id: str) -> StreamingResponse:
    """Download all artifacts for a pipeline run as a ZIP file."""
    if not _RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    mgr = get_run_manager()
    run = mgr.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    output_dir = get_output_dir()
    run_dir = output_dir / ".stlc_runs" / run_id

    buf = io.BytesIO()
    file_count = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if run_dir.exists():
            for path in run_dir.rglob("*"):
                if path.is_file():
                    arcname = str(path.relative_to(run_dir))
                    zf.write(path, arcname)
                    file_count += 1

        # Include any in-memory artifacts as JSON
        artifacts = run.get("artifacts", {})
        if artifacts:
            import json
            zf.writestr(
                "artifacts.json",
                json.dumps(artifacts, indent=2, default=str),
            )
            file_count += 1

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=run_{run_id}_artifacts.zip"
        },
    )
