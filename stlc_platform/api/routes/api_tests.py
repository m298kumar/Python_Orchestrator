"""
API Test Routes
===============
List and inspect generated API test files.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from stlc_platform.api.schemas import APITestFileResponse

router = APIRouter(prefix="/api/api-tests", tags=["api-tests"])

# In-memory store: filename -> dict
_api_test_files: Dict[str, Dict[str, Any]] = {}


@router.get("/", response_model=list[APITestFileResponse])
def list_api_tests() -> list[APITestFileResponse]:
    """List generated API test files (without content)."""
    results: List[APITestFileResponse] = []
    for f in _api_test_files.values():
        results.append(
            APITestFileResponse(
                filename=f.get("filename", ""),
                framework=f.get("framework", ""),
                language=f.get("language", ""),
                endpoint_path=f.get("endpoint_path", ""),
                test_count=f.get("test_count", 0),
                test_level=f.get("test_level", "api"),
                content="",  # Omit content in list view
            )
        )
    return results


@router.get("/{filename}", response_model=APITestFileResponse)
def get_api_test(filename: str) -> APITestFileResponse:
    """Get an API test file with its content."""
    if filename not in _api_test_files:
        raise HTTPException(
            status_code=404, detail=f"API test file '{filename}' not found"
        )
    f = _api_test_files[filename]
    return APITestFileResponse(
        filename=f.get("filename", ""),
        framework=f.get("framework", ""),
        language=f.get("language", ""),
        endpoint_path=f.get("endpoint_path", ""),
        test_count=f.get("test_count", 0),
        test_level=f.get("test_level", "api"),
        content=f.get("content", ""),
    )
