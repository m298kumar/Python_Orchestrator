"""
Requirements Routes
===================
Upload, list, and manage requirements.

Supported upload formats: JSON, YAML, CSV, Excel (.xlsx), TXT, PDF, DOCX, Markdown.
"""

from __future__ import annotations

import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from stlc_platform.api.schemas import RequirementResponse, RequirementUpdate

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

# In-memory requirements store: req_id -> dict
_requirements: Dict[str, Dict[str, Any]] = {}
_requirement_history: Dict[str, List[Dict[str, Any]]] = {}
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
        from stlc_platform.core.config_loader import _find_project_root, _load_yaml
        from stlc_platform.core.specifications import SpecificationLoader

        raw_config = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
        spec_loader = SpecificationLoader(raw_config)
        requirement_spec = spec_loader.load("requirements")
        violations = {
            req.req_id: spec_loader.validate_requirement(req)
            for req in parsed
            if spec_loader.validate_requirement(req)
        }
        if violations:
            raise HTTPException(
                status_code=422,
                detail={"message": "Requirements violate the approved specification", "errors": violations},
            )
    except ImportError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Missing dependency for .{ext} files: {e}",
        )
    except HTTPException:
        raise
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
            item["specification_versions"] = {
                requirement_spec.specification_id: requirement_spec.version
            }
            previous = _requirements.get(req_id)
            if previous:
                _requirement_history.setdefault(req_id, []).append(dict(previous))
            item["revision_number"] = int((previous or {}).get("revision_number", 0)) + 1
            item["revised_at"] = datetime.now(timezone.utc).isoformat()
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


@router.get("/{req_id}/history")
def get_requirement_history(req_id: str) -> Dict[str, Any]:
    """Return every retained revision, including the current requirement."""
    with _req_lock:
        current = _requirements.get(req_id)
        history = list(_requirement_history.get(req_id, []))
    if current is None:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    return {"req_id": req_id, "revisions": [*history, dict(current)]}


@router.put("/{req_id}", response_model=RequirementResponse)
def update_requirement(req_id: str, update: RequirementUpdate) -> RequirementResponse:
    """Update editable fields of a requirement."""
    with _req_lock:
        if req_id not in _requirements:
            raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")

        existing = _requirements[req_id]
        _requirement_history.setdefault(req_id, []).append(dict(existing))
        changes = update.model_dump(exclude_unset=True)
        existing.update(changes)
        existing["revision_number"] = int(existing.get("revision_number", 1)) + 1
        existing["revised_at"] = datetime.now(timezone.utc).isoformat()
        _requirements[req_id] = existing
    return _dict_to_response(existing)
