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
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from stlc_platform.api.deps import TestCaseStore, get_output_dir, get_tc_store
from stlc_platform.api.review_store import TestCaseReviewStore
from stlc_platform.api.schemas import (
    BulkTestCaseAction,
    TestCaseAction,
    TestCaseResponse,
    TestCaseUpdate,
    TestStepResponse,
)
from stlc_platform.core.contracts import TestCaseArtifact
from stlc_platform.core.logging_config import get_logger
from stlc_platform.core.quality.scorer import ScorerConfig, TestCaseScorer

_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

logger = get_logger(__name__)

router = APIRouter(prefix="/api/test-cases", tags=["test-cases"])

# Guard so _load_all_runs only scans disk once per server lifetime.
# Reset to False when a new run is populated so the next request picks it up.
_all_runs_loaded: bool = False
_load_all_lock = threading.Lock()
_rag_store = None
_review_store = None


def _get_review_store() -> TestCaseReviewStore:
    global _review_store
    if _review_store is None:
        from stlc_platform.core.config_loader import _find_project_root, _load_yaml

        root = _find_project_root()
        raw = _load_yaml(root / "config" / "stlc_config.yaml")
        configured = (raw.get("review", {}) or {}).get(
            "sqlite_path", "output/review/test_case_reviews.sqlite3"
        )
        path = Path(configured)
        if not path.is_absolute():
            path = root / path
        _review_store = TestCaseReviewStore(path)
    return _review_store


def _quality_threshold() -> float:
    from stlc_platform.core.config_loader import _find_project_root, _load_yaml

    raw = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
    return float((raw.get("quality_gate", {}) or {}).get("accept_threshold", 0.65))


def _get_rag_store():
    """Return the persistent RAG store used only by explicit approval actions."""
    global _rag_store
    if _rag_store is None:
        from stlc_platform.core.config_loader import _find_project_root, _load_yaml, config
        from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

        raw = _load_yaml(_find_project_root() / "config" / "stlc_config.yaml")
        project = raw.get("project", {}) or {}
        project_id = project.get("id") or project.get("name") or "default"
        _rag_store = RequirementsVectorStore(config.chromadb, project_id=project_id)
        _rag_store.initialize()
    return _rag_store


def _promote_approved_tc(tc: Dict[str, Any]) -> str:
    """Apply the approved quality gate, then promote one test case to RAG."""
    threshold = _quality_threshold()
    score = float(tc.get("quality_score", 0.0) or 0.0)
    issues = tc.get("quality_issues", []) or []
    if not tc.get("quality_validated", True) or score < threshold or issues:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Test case is not eligible for RAG promotion: score {score:.2f} "
                f"must be >= {threshold:.2f} and quality_issues must be empty"
            ),
        )
    return _get_rag_store().store_approved_tc(
        tc_dict=tc,
        ac_type=str(tc.get("category") or "general").lower(),
        test_type=str(tc.get("test_type") or "positive"),
        domain=str(tc.get("domain") or ""),
        human_approved=True,
    )


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
        quality_issues=d.get("quality_issues", []) or [],
        quality_validated=bool(d.get("quality_validated", True)),
        run_id=d.get("run_id") or None,
        rag_example_id=d.get("rag_example_id") or None,
        review_id=d.get("review_id"),
        reviewer=d.get("reviewer", ""),
        review_reason=d.get("review_reason", ""),
        reviewed_at=d.get("reviewed_at", ""),
    )


def _with_persisted_review(tc: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(tc)
    review = _get_review_store().latest(str(tc.get("run_id") or "legacy"), str(tc.get("tc_id")))
    if review and review["review_content_hash"] == _get_review_store().content_hash(tc):
        result.update(
            status=review["status"],
            rag_example_id=review["rag_example_id"],
            review_id=review["review_id"],
            reviewer=review["reviewer"],
            review_reason=review["reason"],
            reviewed_at=review["reviewed_at"],
        )
    return result


def _require_tc(store: TestCaseStore, run_id: str, tc_id: str) -> Dict[str, Any]:
    tc = store.get(tc_id, run_id=run_id)
    if tc is None:
        raise HTTPException(
            status_code=404, detail=f"Test case '{tc_id}' not found in run '{run_id}'"
        )
    return tc


def _record_decision(
    store: TestCaseStore,
    run_id: str,
    tc_id: str,
    decision: str,
    action: TestCaseAction | None,
) -> Dict[str, Any]:
    existing = _require_tc(store, run_id, tc_id)
    previous_review = _get_review_store().latest(run_id or "legacy", tc_id)
    if decision == "rejected" and previous_review and previous_review.get("rag_example_id"):
        _get_rag_store().delete_approved_tc(previous_review["rag_example_id"])
    rag_id = _promote_approved_tc(existing) if decision == "approved" else ""
    review = _get_review_store().record(
        existing,
        decision=decision,
        reason=(action.reason if action else None) or "",
        reviewer=(action.reviewer if action else None) or "anonymous",
        rag_example_id=rag_id,
    )
    changes = {
        "status": decision,
        "rag_example_id": rag_id or None,
        "review_id": review["review_id"],
        "reviewer": review["reviewer"],
        "review_reason": review["reason"],
        "reviewed_at": review["reviewed_at"],
    }
    return store.update(tc_id, changes, run_id=run_id) or existing


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
        _dict_to_response(_with_persisted_review(tc))
        for tc in source.values()
        if _matches_filters(tc, req_id, test_type, priority, status)
    ]
    return results[offset : offset + limit]


@router.get("/{tc_id}", response_model=TestCaseResponse)
def get_test_case(tc_id: str, run_id: str = Query("")) -> TestCaseResponse:
    """Get a single test case by ID."""
    store = get_tc_store()
    tc = store.get(tc_id, run_id=run_id)
    if tc is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(_with_persisted_review(tc))


@router.put("/{tc_id}", response_model=TestCaseResponse)
def update_test_case(tc_id: str, update: TestCaseUpdate, run_id: str = Query("")) -> TestCaseResponse:
    """Edit a test case."""
    store = get_tc_store()
    previous_review = _get_review_store().latest(run_id or "legacy", tc_id)
    if previous_review and previous_review.get("rag_example_id"):
        _get_rag_store().delete_approved_tc(previous_review["rag_example_id"])
    changes = update.model_dump(exclude_unset=True)
    changes.update(status="generated", quality_validated=False, rag_example_id=None)
    updated = store.update(tc_id, changes, run_id=run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(updated)


@router.post("/runs/{run_id}/{tc_id}/revalidate", response_model=TestCaseResponse)
def revalidate_test_case(run_id: str, tc_id: str) -> TestCaseResponse:
    """Deterministically re-score a human-edited test case before approval."""
    store = get_tc_store()
    existing = _require_tc(store, run_id, tc_id)
    artifact = TestCaseArtifact(**existing)
    target = artifact.expected_outcome or artifact.description or artifact.title
    requirement = SimpleNamespace(
        title=artifact.title,
        description=artifact.description,
        acceptance_criteria=[target],
    )
    report = TestCaseScorer(ScorerConfig(accept_threshold=_quality_threshold())).score(
        artifact,
        {"target_ac": target, "test_type": artifact.test_type, "ac_type": "general"},
        requirement,
    )
    updated = store.update(
        tc_id,
        {
            "quality_score": report.overall_score,
            "quality_issues": report.issues,
            "quality_validated": True,
            "status": "generated",
        },
        run_id=run_id,
    )
    return _dict_to_response(updated or existing)


@router.post("/runs/{run_id}/{tc_id}/approve", response_model=TestCaseResponse)
def approve_run_test_case(
    run_id: str, tc_id: str, action: TestCaseAction | None = None
) -> TestCaseResponse:
    return _dict_to_response(_record_decision(get_tc_store(), run_id, tc_id, "approved", action))


@router.post("/runs/{run_id}/{tc_id}/reject", response_model=TestCaseResponse)
def reject_run_test_case(
    run_id: str, tc_id: str, action: TestCaseAction | None = None
) -> TestCaseResponse:
    return _dict_to_response(_record_decision(get_tc_store(), run_id, tc_id, "rejected", action))


@router.post("/{tc_id}/approve", response_model=TestCaseResponse)
def approve_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as approved."""
    store = get_tc_store()
    existing = store.get(tc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(
        _record_decision(store, str(existing.get("run_id") or ""), tc_id, "approved", action)
    )


@router.post("/{tc_id}/reject", response_model=TestCaseResponse)
def reject_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as rejected."""
    store = get_tc_store()
    existing = store.get(tc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(
        _record_decision(store, str(existing.get("run_id") or ""), tc_id, "rejected", action)
    )


# ── Bulk operations ───────────────────────────────────────────────────────


@router.post("/review-actions/bulk/approve")
def bulk_approve(action: BulkTestCaseAction) -> Dict[str, Any]:
    """Approve multiple test cases at once."""
    store = get_tc_store()
    results = []
    for item in action.items:
        try:
            result = _record_decision(
                store,
                item.run_id,
                item.tc_id,
                "approved",
                TestCaseAction(reason=action.reason, reviewer=action.reviewer),
            )
            results.append({"tc_id": item.tc_id, "run_id": item.run_id, "success": True,
                            "rag_example_id": result.get("rag_example_id")})
        except HTTPException as exc:
            results.append({"tc_id": item.tc_id, "run_id": item.run_id, "success": False,
                            "error": exc.detail})
    return {"results": results}


@router.post("/review-actions/bulk/reject")
def bulk_reject(action: BulkTestCaseAction) -> Dict[str, Any]:
    """Reject multiple test cases at once."""
    store = get_tc_store()
    results = []
    for item in action.items:
        try:
            _record_decision(
                store,
                item.run_id,
                item.tc_id,
                "rejected",
                TestCaseAction(reason=action.reason, reviewer=action.reviewer),
            )
            results.append({"tc_id": item.tc_id, "run_id": item.run_id, "success": True})
        except HTTPException as exc:
            results.append({"tc_id": item.tc_id, "run_id": item.run_id, "success": False,
                            "error": exc.detail})
    return {"results": results}
