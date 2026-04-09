"""
BDD Routes
==========
List and download generated BDD feature files and scaffolded projects.

After a pipeline run completes, the background task runner calls
``load_feature_files_from_run()`` to feed generated artifacts into the
shared FeatureFileStore.  A ``run_id`` query parameter also allows
loading artifacts from any completed run on disk.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from stlc_platform.api.deps import FeatureFileStore, get_ff_store, get_output_dir
from stlc_platform.api.schemas import FeatureFileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bdd", tags=["bdd"])

# Guard so _load_all_runs only scans disk once per server lifetime.
_all_runs_loaded: bool = False
_load_all_lock = threading.Lock()


# ── Population helpers ─────────────────────────────────────────────────────


def populate_feature_files(
    feature_files: List[Dict[str, Any]],
    store: Optional[FeatureFileStore] = None,
    run_id: str = "",
) -> int:
    """Populate the store from a list of feature-file dicts, tagging each with run_id.

    Called by the background task runner after a pipeline completes.
    Returns the number of feature files loaded.
    """
    global _all_runs_loaded
    store = store or get_ff_store()
    # Derive scenario_count from content if not present
    for f in feature_files:
        if "scenario_count" not in f and f.get("content"):
            f["scenario_count"] = len(
                re.findall(
                    r"^\s*Scenario(?:\s+Outline)?:",
                    f["content"],
                    re.MULTILINE,
                )
            )
    count = store.populate(feature_files, run_id=run_id)
    # New run added directly — let next request re-scan for any other new runs
    _all_runs_loaded = False
    logger.info("Populated %d feature files into API store (run=%s)", count, run_id or "unknown")
    return count


def load_feature_files_from_run(
    run_id: str,
    store: Optional[FeatureFileStore] = None,
) -> int:
    """Load feature files from a completed pipeline run's disk artifacts."""
    output_dir = get_output_dir()
    stage_file = output_dir / ".stlc_runs" / run_id / "generate_bdd_code.json"
    if not stage_file.exists():
        return 0
    try:
        data = json.loads(stage_file.read_text(encoding="utf-8"))
        features = data.get("artifacts", {}).get("feature_files", [])
        return populate_feature_files(features, store=store, run_id=run_id)
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.exception("Failed to load feature files from run %s: %s", run_id, exc)
        return 0


def _load_all_runs(store: FeatureFileStore) -> None:
    """Load feature files from ALL completed runs into the consolidated store.

    Only scans disk once per server lifetime (guarded by _all_runs_loaded flag).
    The flag is reset by populate_feature_files() when a new run is added directly.
    """
    global _all_runs_loaded
    if _all_runs_loaded:
        return
    with _load_all_lock:
        if _all_runs_loaded:  # double-check under lock
            return
        output_dir = get_output_dir()
        runs_dir = output_dir / ".stlc_runs"
        if runs_dir.exists():
            candidates = sorted(
                runs_dir.glob("*/generate_bdd_code.json"),
                key=lambda p: p.stat().st_mtime,
            )
            loaded_runs = {v.get("run_id") for v in store.get_all().values() if v.get("run_id")}
            for candidate in candidates:
                rid = candidate.parent.name
                if rid not in loaded_runs:
                    count = load_feature_files_from_run(rid, store=store)
                    if count:
                        logger.info("Auto-loaded %d feature files from run '%s'", count, rid)
        _all_runs_loaded = True


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/features", response_model=list[FeatureFileResponse])
def list_features(
    run_id: Optional[str] = Query(None, description="Load from a specific pipeline run"),
    limit: int = Query(default=100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> list[FeatureFileResponse]:
    """List generated feature files (without content)."""
    store = get_ff_store()
    if run_id:
        if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", run_id):
            raise HTTPException(status_code=400, detail="Invalid run_id format")
        load_feature_files_from_run(run_id, store=store)
    else:
        _load_all_runs(store)

    # When run_id is given, filter to only that run's feature files
    source = store.get_by_run(run_id) if run_id else store.get_all()

    results: List[FeatureFileResponse] = []
    for f in source.values():
        results.append(
            FeatureFileResponse(
                filename=f.get("filename", ""),
                req_id=f.get("req_id", ""),
                scenario_count=f.get("scenario_count", 0),
                tags=f.get("tags", []),
                content="",  # Omit content in list view
                run_id=f.get("run_id") or None,
            )
        )
    return results[offset : offset + limit]


@router.get("/features/{filename}", response_model=FeatureFileResponse)
def get_feature(filename: str) -> FeatureFileResponse:
    """Get a feature file with its content."""
    store = get_ff_store()
    f = store.get(filename)
    if f is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature file '{filename}' not found",
        )
    return FeatureFileResponse(
        filename=f.get("filename", ""),
        req_id=f.get("req_id", ""),
        scenario_count=f.get("scenario_count", 0),
        tags=f.get("tags", []),
        content=f.get("content", ""),
        run_id=f.get("run_id") or None,
    )


@router.get("/project/download")
def download_project() -> StreamingResponse:
    """Download the scaffolded BDD project as a ZIP file."""
    output_dir = get_output_dir()
    bdd_dir = output_dir / "bdd"
    store = get_ff_store()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if bdd_dir.exists():
            for path in bdd_dir.rglob("*"):
                if path.is_file():
                    arcname = str(path.relative_to(bdd_dir))
                    zf.write(path, arcname)

        # Also include in-memory feature files
        for fname, data in store.get_all().items():
            content = data.get("content", "")
            if content:
                zf.writestr(f"features/{fname}", content)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=bdd_project.zip"},
    )
