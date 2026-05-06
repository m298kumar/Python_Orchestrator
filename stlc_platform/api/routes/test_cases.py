"""
Test Case Routes
================
List, inspect, edit, approve, and reject generated test cases.

After a pipeline run completes, the background task runner calls
``load_test_cases_from_run()`` to feed generated artifacts into the
shared TestCaseStore so they are immediately visible in the frontend.
A ``run_id`` query parameter also allows loading artifacts from any
completed run on disk.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

# Import our logging configuration
from stlc_platform.core.logging_config import get_logger

_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

from stlc_platform.api.deps import TestCaseStore, get_output_dir, get_tc_store
from stlc_platform.api.schemas import (
    BulkTestCaseAction,
    TestCaseAction,
    TestCaseResponse,
    TestCaseUpdate,
    TestStepResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/test-cases", tags=["test-cases"])

# Guard so _load_all_runs only scans disk once per server lifetime.
# Reset to False when a new run is populated so the next request picks it up.
_all_runs_loaded: bool = False
_load_all_lock = threading.Lock()


# ── Population helpers ─────────────────────────────────────────────────────


def populate_test_cases(
    test_cases: List[Dict[str, Any]],
    store: Optional[TestCaseStore] = None,
    run_id: str = "",
) -> int:
    """Populate the store from a list of test-case dicts, tagging each with run_id.

    Called by the background task runner after a pipeline completes.
    Returns the number of test cases loaded.
    """
    global _all_runs_loaded
    store = store or get_tc_store()
    count = store.populate(test_cases, run_id=run_id)
    # A new run was just added directly — allow _load_all_runs to pick up any
    # other runs it may have missed on the next request.
    _all_runs_loaded = False
    logger.info("Populated %d test cases into API store (run=%s)", count, run_id or "unknown")
    return count


def load_test_cases_from_run(
    run_id: str,
    store: Optional[TestCaseStore] = None,
) -> int:
    """Load test cases from a completed pipeline run's disk artifacts.

    Tries enriched test cases first (enrich_test_cases stage), then falls back
    to the raw parse_requirements output. Tags each test case with run_id.
    """
    output_dir = get_output_dir()
    run_dir = output_dir / ".stlc_runs" / run_id

    # Prefer enriched test cases; fall back to raw parse_requirements output
    for stage in ("enrich_test_cases", "parse_requirements"):
        stage_file = run_dir / f"{stage}.json"
        if not stage_file.exists():
            continue
        try:
            data = json.loads(stage_file.read_text(encoding="utf-8"))
            tcs = data.get("artifacts", {}).get("test_cases", [])
            if tcs:
                return populate_test_cases(tcs, store=store, run_id=run_id)
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.exception("Failed to load test cases from %s/%s: %s", run_id, stage, exc)
    return 0


def _load_all_runs(store: TestCaseStore) -> None:
    """Load test cases from ALL completed runs on disk into the consolidated store.

    Only scans disk once per server lifetime (guarded by _all_runs_loaded flag).
    The flag is reset by populate_test_cases() when a new run is added directly,
    so the next request picks up any runs that arrived after the last scan.
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
                runs_dir.glob("*/parse_requirements.json"),
                key=lambda p: p.stat().st_mtime,
            )
            loaded_runs = {v.get("run_id") for v in store.get_all().values() if v.get("run_id")}
            for candidate in candidates:
                rid = candidate.parent.name
                if rid not in loaded_runs:
                    count = load_test_cases_from_run(rid, store=store)
                    if count:
                        logger.info("Auto-loaded %d test cases from run '%s'", count, rid)
        _all_runs_loaded = True


# ── Response helpers ───────────────────────────────────────────────────────


def _dict_to_response(d: Dict[str, Any]) -> TestCaseResponse:
    raw_steps = d.get("steps", [])
    steps = [
        TestStepResponse(
            action=s.get("action", "") if isinstance(s, dict) else "",
            expected_result=s.get("expected_result", "") if isinstance(s, dict) else "",
        )
        for s in raw_steps
    ]
    return TestCaseResponse(
        tc_id=d.get("tc_id", ""),
        req_id=d.get("req_id", ""),
        title=d.get("title", ""),
        description=d.get("description", ""),
        preconditions=d.get("preconditions", ""),
        test_type=d.get("test_type", ""),
        priority=d.get("priority", ""),
        category=d.get("category", ""),
        component=d.get("component", ""),
        steps=steps,
        given=d.get("given", ""),
        when=d.get("when", ""),
        then=d.get("then", ""),
        expected_outcome=d.get("expected_outcome", ""),
        tags=d.get("tags", []),
        status=d.get("status", "generated"),
        test_level=d.get("test_level", ""),
        quality_score=float(d.get("quality_score", 0.0)),
        run_id=d.get("run_id") or None,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────


def _matches_filters(
    tc: Dict[str, Any],
    req_id: Optional[str],
    test_type: Optional[str],
    priority: Optional[str],
    status: Optional[str],
) -> bool:
    """Return True if a test case dict passes all active filters."""
    if req_id and tc.get("req_id") != req_id:
        return False
    if test_type and tc.get("test_type") != test_type:
        return False
    if priority and tc.get("priority") != priority:
        return False
    if status and tc.get("status") != status:
        return False
    return True


def _load_store_for_run(run_id: Optional[str], store: TestCaseStore) -> None:
    """Ensure the store is populated for the given run_id (or all runs)."""
    if run_id:
        if not _RUN_ID_PATTERN.match(run_id):
            raise HTTPException(status_code=400, detail="Invalid run_id format")
        load_test_cases_from_run(run_id, store=store)
    else:
        _load_all_runs(store)


@router.get("/", response_model=list[TestCaseResponse])
def list_test_cases(
    req_id: Optional[str] = Query(None, description="Filter by requirement ID"),
    test_type: Optional[str] = Query(None, description="Filter by test type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status: Optional[str] = Query(None, description="Filter by status"),
    run_id: Optional[str] = Query(None, description="Load from a specific pipeline run"),
    limit: int = Query(default=100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> list[TestCaseResponse]:
    """List test cases with optional filters and pagination."""
    store = get_tc_store()
    _load_store_for_run(run_id, store)

    source = store.get_by_run(run_id) if run_id else store.get_all()
    results = [
        _dict_to_response(tc)
        for tc in source.values()
        if _matches_filters(tc, req_id, test_type, priority, status)
    ]
    return results[offset : offset + limit]


@router.get("/{tc_id}", response_model=TestCaseResponse)
def get_test_case(tc_id: str) -> TestCaseResponse:
    """Get a single test case by ID."""
    store = get_tc_store()
    tc = store.get(tc_id)
    if tc is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(tc)


@router.put("/{tc_id}", response_model=TestCaseResponse)
def update_test_case(tc_id: str, update: TestCaseUpdate) -> TestCaseResponse:
    """Edit a test case."""
    store = get_tc_store()
    changes = update.model_dump(exclude_unset=True)
    updated = store.update(tc_id, changes)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(updated)


@router.post("/{tc_id}/approve", response_model=TestCaseResponse)
def approve_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as approved."""
    store = get_tc_store()
    changes: Dict[str, Any] = {"status": "approved"}
    if action and action.reason:
        changes["approval_reason"] = action.reason
    updated = store.update(tc_id, changes)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(updated)


@router.post("/{tc_id}/reject", response_model=TestCaseResponse)
def reject_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as rejected."""
    store = get_tc_store()
    changes: Dict[str, Any] = {"status": "rejected"}
    if action and action.reason:
        changes["rejection_reason"] = action.reason
    updated = store.update(tc_id, changes)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(updated)


# ── Bulk operations ───────────────────────────────────────────────────────


@router.post("/bulk/approve")
def bulk_approve(action: BulkTestCaseAction) -> Dict[str, Any]:
    """Approve multiple test cases at once."""
    store = get_tc_store()
    updated_ids: List[str] = []
    not_found: List[str] = []
    for tc_id in action.tc_ids:
        changes: Dict[str, Any] = {"status": "approved"}
        if action.reason:
            changes["approval_reason"] = action.reason
        result = store.update(tc_id, changes)
        if result is None:
            not_found.append(tc_id)
        else:
            updated_ids.append(tc_id)
    return {"updated": updated_ids, "not_found": not_found}


@router.post("/bulk/reject")
def bulk_reject(action: BulkTestCaseAction) -> Dict[str, Any]:
    """Reject multiple test cases at once."""
    store = get_tc_store()
    updated_ids: List[str] = []
    not_found: List[str] = []
    for tc_id in action.tc_ids:
        changes: Dict[str, Any] = {"status": "rejected"}
        if action.reason:
            changes["rejection_reason"] = action.reason
        result = store.update(tc_id, changes)
        if result is None:
            not_found.append(tc_id)
        else:
            updated_ids.append(tc_id)
    return {"updated": updated_ids, "not_found": not_found}
