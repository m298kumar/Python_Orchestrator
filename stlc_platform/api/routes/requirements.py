"""
Requirements Routes
===================
Upload, list, and manage requirements.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, UploadFile, File

from stlc_platform.api.schemas import RequirementResponse, RequirementUpdate

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

# In-memory requirements store: req_id -> dict
_requirements: Dict[str, Dict[str, Any]] = {}


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
    """Upload a requirements file (JSON or YAML)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("json", "yaml", "yml"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Use .json or .yaml",
        )

    content = await file.read()
    try:
        if ext == "json":
            data = json.loads(content)
        else:
            import yaml
            data = yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")

    # Accept either a list of dicts or a dict with a "requirements" key
    if isinstance(data, dict) and "requirements" in data:
        items = data["requirements"]
    elif isinstance(data, list):
        items = data
    else:
        raise HTTPException(
            status_code=400,
            detail="File must contain a list of requirements or a dict with a 'requirements' key",
        )

    results: List[RequirementResponse] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        req_id = item.get("req_id", f"REQ-{len(_requirements) + i + 1:04d}")
        item["req_id"] = req_id
        _requirements[req_id] = item
        results.append(_dict_to_response(item))

    return results


@router.get("/", response_model=list[RequirementResponse])
def list_requirements() -> list[RequirementResponse]:
    """List all current requirements."""
    return [_dict_to_response(r) for r in _requirements.values()]


@router.get("/{req_id}", response_model=RequirementResponse)
def get_requirement(req_id: str) -> RequirementResponse:
    """Get a single requirement by ID."""
    if req_id not in _requirements:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    return _dict_to_response(_requirements[req_id])


@router.put("/{req_id}", response_model=RequirementResponse)
def update_requirement(req_id: str, update: RequirementUpdate) -> RequirementResponse:
    """Update editable fields of a requirement."""
    if req_id not in _requirements:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")

    existing = _requirements[req_id]
    changes = update.model_dump(exclude_unset=True)
    existing.update(changes)
    _requirements[req_id] = existing
    return _dict_to_response(existing)
