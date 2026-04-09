"""
Requirements Routes
===================
Upload, list, and manage requirements.

Supported upload formats: JSON, YAML, CSV, Excel (.xlsx), TXT, PDF, DOCX, Markdown.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from stlc_platform.api.schemas import RequirementResponse, RequirementUpdate

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

# In-memory requirements store: req_id -> dict
_requirements: Dict[str, Dict[str, Any]] = {}
_req_lock = threading.Lock()

_SUPPORTED_EXTENSIONS = {"json", "yaml", "yml", "csv", "xlsx", "txt", "pdf", "docx", "md"}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _dict_to_response(d: Dict[str, Any]) -> RequirementResponse:
    return RequirementResponse(
        req_id=d.get("req_id", ""),
        title=d.get("title", ""),
        description=d.get("description", ""),
        priority=d.get("priority", "Medium"),
        category=d.get("category", "Functional"),
        acceptance_criteria=d.get("acceptance_criteria", []),
        tags=d.get("tags", []),
    )


@router.post("/upload", response_model=list[RequirementResponse], status_code=201)
async def upload_requirements(file: UploadFile = File(...)) -> list[RequirementResponse]:
    """Upload a requirements file (JSON, YAML, CSV, Excel, TXT, PDF, DOCX, Markdown)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '.{ext}'. "
                f"Supported: {', '.join(sorted('.' + e for e in _SUPPORTED_EXTENSIONS))}"
            ),
        )

    # Save to a temp file so RequirementsReader can parse it
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")
    suffix = "." + ext
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        from stlc_platform.agents.requirements_agent.reader import RequirementsReader

        reader = RequirementsReader()
        parsed = reader.read(tmp_path)
    except ImportError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing dependency for .{ext} files: {e}",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    results: List[RequirementResponse] = []
    with _req_lock:
        for i, req in enumerate(parsed):
            item = req.to_dict()
            req_id = item.get("req_id") or f"REQ-{len(_requirements) + i + 1:04d}"
            item["req_id"] = req_id
            _requirements[req_id] = item
            results.append(_dict_to_response(item))

    return results


@router.get("/", response_model=list[RequirementResponse])
def list_requirements(
    limit: int = Query(default=100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> list[RequirementResponse]:
    """List all current requirements with pagination."""
    with _req_lock:
        all_items = [_dict_to_response(r) for r in _requirements.values()]
    return all_items[offset : offset + limit]


@router.get("/{req_id}", response_model=RequirementResponse)
def get_requirement(req_id: str) -> RequirementResponse:
    """Get a single requirement by ID."""
    with _req_lock:
        item = _requirements.get(req_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    return _dict_to_response(item)


@router.put("/{req_id}", response_model=RequirementResponse)
def update_requirement(req_id: str, update: RequirementUpdate) -> RequirementResponse:
    """Update editable fields of a requirement."""
    with _req_lock:
        if req_id not in _requirements:
            raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")

        existing = _requirements[req_id]
        changes = update.model_dump(exclude_unset=True)
        existing.update(changes)
        _requirements[req_id] = existing
    return _dict_to_response(existing)
