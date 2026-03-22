"""
BDD Routes
==========
List and download generated BDD feature files and scaffolded projects.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from stlc_platform.api.deps import get_output_dir
from stlc_platform.api.schemas import FeatureFileResponse

router = APIRouter(prefix="/api/bdd", tags=["bdd"])

# In-memory feature file store: filename -> dict
_feature_files: Dict[str, Dict[str, Any]] = {}


@router.get("/features", response_model=list[FeatureFileResponse])
def list_features() -> list[FeatureFileResponse]:
    """List generated feature files (without content)."""
    results: List[FeatureFileResponse] = []
    for f in _feature_files.values():
        results.append(
            FeatureFileResponse(
                filename=f.get("filename", ""),
                req_id=f.get("req_id", ""),
                scenario_count=f.get("scenario_count", 0),
                tags=f.get("tags", []),
                content="",  # Omit content in list view
            )
        )
    return results


@router.get("/features/{filename}", response_model=FeatureFileResponse)
def get_feature(filename: str) -> FeatureFileResponse:
    """Get a feature file with its content."""
    if filename not in _feature_files:
        raise HTTPException(
            status_code=404, detail=f"Feature file '{filename}' not found"
        )
    f = _feature_files[filename]
    return FeatureFileResponse(
        filename=f.get("filename", ""),
        req_id=f.get("req_id", ""),
        scenario_count=f.get("scenario_count", 0),
        tags=f.get("tags", []),
        content=f.get("content", ""),
    )


@router.get("/project/download")
def download_project() -> StreamingResponse:
    """Download the scaffolded BDD project as a ZIP file."""
    output_dir = get_output_dir()
    bdd_dir = output_dir / "bdd"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if bdd_dir.exists():
            for path in bdd_dir.rglob("*"):
                if path.is_file():
                    arcname = str(path.relative_to(bdd_dir))
                    zf.write(path, arcname)

        # Also include in-memory feature files
        for fname, data in _feature_files.items():
            content = data.get("content", "")
            if content:
                zf.writestr(f"features/{fname}", content)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=bdd_project.zip"},
    )
