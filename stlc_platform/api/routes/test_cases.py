"""
Test Case Routes
================
List, inspect, edit, approve, and reject generated test cases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from stlc_platform.api.schemas import TestCaseAction, TestCaseResponse, TestCaseUpdate

router = APIRouter(prefix="/api/test-cases", tags=["test-cases"])

# In-memory test case store: tc_id -> dict
_test_cases: Dict[str, Dict[str, Any]] = {}


def _dict_to_response(d: Dict[str, Any]) -> TestCaseResponse:
    return TestCaseResponse(
        tc_id=d.get("tc_id", ""),
        req_id=d.get("req_id", ""),
        title=d.get("title", ""),
        description=d.get("description", ""),
        test_type=d.get("test_type", ""),
        priority=d.get("priority", ""),
        category=d.get("category", ""),
        component=d.get("component", ""),
        given=d.get("given", ""),
        when=d.get("when", ""),
        then=d.get("then", ""),
        expected_outcome=d.get("expected_outcome", ""),
        tags=d.get("tags", []),
        status=d.get("status", "generated"),
    )


@router.get("/", response_model=list[TestCaseResponse])
def list_test_cases(
    req_id: Optional[str] = Query(None, description="Filter by requirement ID"),
    test_type: Optional[str] = Query(None, description="Filter by test type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status: Optional[str] = Query(None, description="Filter by status"),
) -> list[TestCaseResponse]:
    """List test cases with optional filters."""
    results: List[TestCaseResponse] = []
    for tc in _test_cases.values():
        if req_id and tc.get("req_id") != req_id:
            continue
        if test_type and tc.get("test_type") != test_type:
            continue
        if priority and tc.get("priority") != priority:
            continue
        if status and tc.get("status") != status:
            continue
        results.append(_dict_to_response(tc))
    return results


@router.get("/{tc_id}", response_model=TestCaseResponse)
def get_test_case(tc_id: str) -> TestCaseResponse:
    """Get a single test case by ID."""
    if tc_id not in _test_cases:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")
    return _dict_to_response(_test_cases[tc_id])


@router.put("/{tc_id}", response_model=TestCaseResponse)
def update_test_case(tc_id: str, update: TestCaseUpdate) -> TestCaseResponse:
    """Edit a test case."""
    if tc_id not in _test_cases:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")

    existing = _test_cases[tc_id]
    changes = update.model_dump(exclude_unset=True)
    existing.update(changes)
    _test_cases[tc_id] = existing
    return _dict_to_response(existing)


@router.post("/{tc_id}/approve", response_model=TestCaseResponse)
def approve_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as approved."""
    if tc_id not in _test_cases:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")

    _test_cases[tc_id]["status"] = "approved"
    if action and action.reason:
        _test_cases[tc_id]["approval_reason"] = action.reason
    return _dict_to_response(_test_cases[tc_id])


@router.post("/{tc_id}/reject", response_model=TestCaseResponse)
def reject_test_case(tc_id: str, action: TestCaseAction | None = None) -> TestCaseResponse:
    """Mark a test case as rejected."""
    if tc_id not in _test_cases:
        raise HTTPException(status_code=404, detail=f"Test case '{tc_id}' not found")

    _test_cases[tc_id]["status"] = "rejected"
    if action and action.reason:
        _test_cases[tc_id]["rejection_reason"] = action.reason
    return _dict_to_response(_test_cases[tc_id])
