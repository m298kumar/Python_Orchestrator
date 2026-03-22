"""
Crawler Routes
==============
View site model and crawled pages from the Crawler agent.
"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException

from stlc_platform.api.schemas import PageSummary, SiteModelResponse

router = APIRouter(prefix="/api/crawler", tags=["crawler"])

# In-memory stores populated by pipeline runs
_site_model: Dict[str, Any] = {}
_crawled_pages: Dict[str, Dict[str, Any]] = {}  # url -> page data


@router.get("/site-model", response_model=SiteModelResponse)
def get_site_model() -> SiteModelResponse:
    """Get the current site model."""
    if not _site_model:
        return SiteModelResponse(
            base_url="",
            total_pages=0,
            total_elements=0,
            total_forms=0,
            navigation_graph={},
            crawl_timestamp="",
        )
    return SiteModelResponse(
        base_url=_site_model.get("base_url", ""),
        total_pages=_site_model.get("total_pages", 0),
        total_elements=_site_model.get("total_elements", 0),
        total_forms=_site_model.get("total_forms", 0),
        navigation_graph=_site_model.get("navigation_graph", {}),
        crawl_timestamp=_site_model.get("crawl_timestamp", ""),
    )


@router.get("/pages", response_model=list[PageSummary])
def list_pages() -> list[PageSummary]:
    """List all crawled pages."""
    results: List[PageSummary] = []
    for page in _crawled_pages.values():
        results.append(
            PageSummary(
                url=page.get("url", ""),
                title=page.get("title", ""),
                element_count=page.get("element_count", 0),
                form_count=page.get("form_count", 0),
                link_count=page.get("link_count", 0),
            )
        )
    return results


@router.get("/pages/{url_encoded:path}", response_model=PageSummary)
def get_page(url_encoded: str) -> PageSummary:
    """Get details for a specific crawled page by URL."""
    url = unquote(url_encoded)

    # Try exact match first, then decoded match
    page = _crawled_pages.get(url) or _crawled_pages.get(url_encoded)
    if page is None:
        raise HTTPException(status_code=404, detail=f"Page '{url}' not found")

    return PageSummary(
        url=page.get("url", ""),
        title=page.get("title", ""),
        element_count=page.get("element_count", 0),
        form_count=page.get("form_count", 0),
        link_count=page.get("link_count", 0),
    )
