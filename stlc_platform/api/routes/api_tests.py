"""
API Test Routes
===============
List and inspect generated API test files.

After a pipeline run completes, the background task runner calls
``load_api_tests_from_run()`` to feed generated artifacts into the
shared store so that the API Tests page shows output immediately.
A ``run_id`` query parameter allows filtering to a specific run.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from stlc_platform.api.deps import get_output_dir
from stlc_platform.api.schemas import APITestFileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/api-tests", tags=["api-tests"])

_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# In-memory store: filename -> dict (tagged with run_id)
_api_test_files: Dict[str, Dict[str, Any]] = {}
_api_tests_lock = threading.Lock()
_run_order: List[str] = []

# Guard so _load_all_runs only scans disk once per server lifetime.
_all_runs_loaded: bool = False
_load_all_lock = threading.Lock()


# ── Population helpers ──────────────────────────────────────────────────────


def populate_api_tests(
    test_files: List[Dict[str, Any]],
    run_id: str = "",
) -> int:
    """Merge API test files into the store, tagging each with run_id."""
    global _all_runs_loaded
    count = 0
    with _api_tests_lock:
        for f in test_files:
            filename = f.get("filename", "")
            if filename:
                entry = dict(f)
                if run_id:
                    entry["run_id"] = run_id
                _api_test_files[filename] = entry
                count += 1
        if run_id and run_id not in _run_order:
            _run_order.append(run_id)
    # New run added directly — let next request re-scan for any other new runs
    _all_runs_loaded = False
    logger.info("Populated %d API test files into store (run=%s)", count, run_id or "unknown")
    return count


def clear_run(run_id: str) -> None:
    """Remove all API test files for a specific run from the in-memory store."""
    with _api_tests_lock:
        to_remove = [k for k, v in _api_test_files.items() if v.get("run_id") == run_id]
        for k in to_remove:
            del _api_test_files[k]
        if run_id in _run_order:
            _run_order.remove(run_id)


def load_api_tests_from_run(run_id: str) -> int:
    """Load API test files from a completed pipeline run's disk artifacts.

    Tries generate_api_tests stage first, then discover_apis.
    """
    output_dir = get_output_dir()
    run_dir = output_dir / ".stlc_runs" / run_id

    for stage in ("generate_api_tests", "discover_apis"):
        stage_file = run_dir / f"{stage}.json"
        if not stage_file.exists():
            continue
        try:
            data = json.loads(stage_file.read_text(encoding="utf-8"))
            files = data.get("artifacts", {}).get("test_files", [])
            if files:
                return populate_api_tests(files, run_id=run_id)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.exception("Failed to load API tests from %s/%s: %s", run_id, stage, exc)
    return 0


def _collect_run_candidates(runs_dir: Any) -> List[Any]:
    """Return sorted candidate stage files for all runs, preferring generate_api_tests."""
    primary = list(runs_dir.glob("*/generate_api_tests.json"))
    fallback = [
        p
        for p in runs_dir.glob("*/discover_apis.json")
        if not (p.parent / "generate_api_tests.json").exists()
    ]
    return sorted(primary + fallback, key=lambda p: p.stat().st_mtime)


def _load_all_runs() -> None:
    """Load API test files from ALL completed runs into the consolidated store.

    Only scans disk once per server lifetime (guarded by _all_runs_loaded flag).
    The flag is reset by populate_api_tests() when a new run is added directly.
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
            candidates = _collect_run_candidates(runs_dir)
            with _api_tests_lock:
                loaded_runs = {v.get("run_id") for v in _api_test_files.values() if v.get("run_id")}
            for candidate in candidates:
                rid = candidate.parent.name
                if rid not in loaded_runs:
                    count = load_api_tests_from_run(rid)
                    if count:
                        logger.info("Auto-loaded %d API test files from run '%s'", count, rid)
        _all_runs_loaded = True


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/", response_model=list[APITestFileResponse])
def list_api_tests(
    run_id: Optional[str] = Query(None, description="Filter to a specific pipeline run"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[APITestFileResponse]:
    """List generated API test files (without content)."""
    if run_id:
        if not _RUN_ID_PATTERN.match(run_id):
            raise HTTPException(status_code=400, detail="Invalid run_id format")
        load_api_tests_from_run(run_id)
    else:
        _load_all_runs()

    with _api_tests_lock:
        source = (
            {k: v for k, v in _api_test_files.items() if v.get("run_id") == run_id}
            if run_id
            else dict(_api_test_files)
        )

    results: List[APITestFileResponse] = []
    for f in source.values():
        results.append(
            APITestFileResponse(
                filename=f.get("filename", ""),
                framework=f.get("framework", ""),
                language=f.get("language", ""),
                endpoint_path=f.get("endpoint_path", ""),
                test_count=f.get("test_count", 0),
                test_level=f.get("test_level", "api"),
                content="",  # Omit content in list view
                run_id=f.get("run_id") or None,
            )
        )
    return results[offset : offset + limit]


@router.get("/{filename}", response_model=APITestFileResponse)
def get_api_test(filename: str) -> APITestFileResponse:
    """Get an API test file with its content."""
    with _api_tests_lock:
        f = _api_test_files.get(filename)
    if f is None:
        raise HTTPException(status_code=404, detail=f"API test file '{filename}' not found")
    return APITestFileResponse(
        filename=f.get("filename", ""),
        framework=f.get("framework", ""),
        language=f.get("language", ""),
        endpoint_path=f.get("endpoint_path", ""),
        test_count=f.get("test_count", 0),
        test_level=f.get("test_level", "api"),
        content=f.get("content", ""),
        run_id=f.get("run_id") or None,
    )
