"""
Requirements Routes
===================
Upload, list, and manage requirements.

Supported upload formats: JSON, YAML, CSV, Excel (.xlsx), TXT, PDF, DOCX, Markdown.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, UploadFile, File

from stlc_platform.api.schemas import RequirementResponse, RequirementUpdate

router = APIRouter(prefix="/api/requirements", tags=["requirements"])

# In-memory requirements store: req_id -> dict
_requirements: Dict[str, Dict[str, Any]] = {}

_SUPPORTED_EXTENSIONS = {"json", "yaml", "yml", "csv", "xlsx", "txt", "pdf", "docx", "md"}


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
    content = await file.read()
    suffix = "." + ext
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, mode="wb"
        ) as tmp:
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
        Path(tmp_path).unlink(missing_ok=True)

    results: List[RequirementResponse] = []
    for i, req in enumerate(parsed):
        item = req.to_dict()
        req_id = item.get("req_id") or f"REQ-{len(_requirements) + i + 1:04d}"
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
