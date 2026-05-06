"""
Crawler Routes
==============
View site model and crawled pages from the Crawler agent.

Supports multiple pipeline runs: each crawl result is stored and served
per run_id.  The ``run_id`` query parameter selects a specific run;
omitting it returns the most recent run's data.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query

from stlc_platform.api.deps import get_output_dir
from stlc_platform.api.schemas import PageSummary, SiteModelResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crawler", tags=["crawler"])

# ── Multi-run in-memory stores ──────────────────────────────────────────────
# run_id → site model dict
_site_models: Dict[str, Dict[str, Any]] = {}
# run_id → {url → page dict}
_crawled_pages: Dict[str, Dict[str, Dict[str, Any]]] = {}
# Ordered list of run_ids (oldest → newest insertion order)
_run_order: List[str] = []
_crawler_lock = threading.Lock()


# ── Population helpers ──────────────────────────────────────────────────────


def populate_crawler(site_model: Dict[str, Any], pages: List[Dict[str, Any]], run_id: str) -> None:
    """Store a site model and its pages tagged with run_id."""
    with _crawler_lock:
        _site_models[run_id] = {**site_model, "run_id": run_id}
        _crawled_pages[run_id] = {}
        for page in pages:
            url = page.get("url", "")
            if url:
                _crawled_pages[run_id][url] = {**page, "run_id": run_id}
        if run_id not in _run_order:
            _run_order.append(run_id)
    logger.info("Populated crawler data for run '%s': %d pages", run_id, len(pages))


def clear_run(run_id: str) -> None:
    """Remove all crawler data for a specific run from the in-memory store."""
    with _crawler_lock:
        _site_models.pop(run_id, None)
        _crawled_pages.pop(run_id, None)
        if run_id in _run_order:
            _run_order.remove(run_id)


def load_crawler_from_run(run_id: str) -> bool:
    """Load crawler artifacts from a completed pipeline run's disk artifacts.

    Reads ``crawl_application.json`` from the run directory, extracts the
    site_model artifact, and populates the in-memory store.
    Returns True if data was loaded, False if the stage file doesn't exist.
    """
    output_dir = get_output_dir()
    stage_file = output_dir / ".stlc_runs" / run_id / "crawl_application.json"
    if not stage_file.exists():
        return False
    try:
        data = json.loads(stage_file.read_text(encoding="utf-8"))
        artifacts = data.get("artifacts", {})
        site_model = artifacts.get("site_model")
        if not site_model:
            return False

        # Extract pages from site_model.pages list
        pages: List[Dict[str, Any]] = []
        for page in site_model.get("pages", []):
            elements = page.get("elements", [])
            forms = page.get("forms", [])
            # Build the PageSummary-compatible dict
            pages.append(
                {
                    "url": page.get("url", ""),
                    "title": page.get("title", ""),
                    "element_count": len(elements),
                    "form_count": len(forms),
                    "link_count": len([e for e in elements if e.get("element_type") == "link"]),
                }
            )

        # Don't populate a run with zero pages — it would show up in the
        # Crawler page run selector with no content, creating a misleading
        # "No site model for this run" empty state.
        if not pages:
            logger.info(
                "Skipping crawler population for run '%s': site model has no pages", run_id
            )
            return False

        summary = {
            "base_url": site_model.get("base_url", ""),
            "total_pages": len(pages),
            "total_elements": sum(p["element_count"] for p in pages),
            "total_forms": sum(p["form_count"] for p in pages),
            "navigation_graph": site_model.get("navigation_graph", {}),
            "crawl_timestamp": site_model.get("crawl_timestamp", ""),
        }
        populate_crawler(summary, pages, run_id)
        return True
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.exception("Failed to load crawler data from run %s: %s", run_id, exc)
        return False


def _load_all_runs() -> None:
    """Scan disk for all crawl_application.json files not yet loaded."""
    output_dir = get_output_dir()
    runs_dir = output_dir / ".stlc_runs"
    if not runs_dir.exists():
        return
    candidates = sorted(
        runs_dir.glob("*/crawl_application.json"),
        key=lambda p: p.stat().st_mtime,
    )
    with _crawler_lock:
        loaded = set(_run_order)
    for candidate in candidates:
        rid = candidate.parent.name
        if rid not in loaded:
            if load_crawler_from_run(rid):
                logger.info("Auto-loaded crawler data from run '%s'", rid)


def _latest_run_id() -> Optional[str]:
    with _crawler_lock:
        return _run_order[-1] if _run_order else None


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/runs", response_model=List[str])
def list_crawler_runs() -> List[str]:
    """List all run_ids that have crawler data (newest first)."""
    _load_all_runs()
    with _crawler_lock:
        return list(reversed(_run_order))


@router.get("/site-model", response_model=SiteModelResponse)
def get_site_model(
    run_id: Optional[str] = Query(None, description="Pipeline run ID; omit for latest"),
) -> SiteModelResponse:
    """Get the site model summary for a specific run (or the latest run)."""
    _load_all_runs()

    if run_id:
        with _crawler_lock:
            model = dict(_site_models.get(run_id, {}))
        if not model:
            raise HTTPException(status_code=404, detail=f"No crawler data for run '{run_id}'")
    else:
        rid = _latest_run_id()
        with _crawler_lock:
            model = dict(_site_models.get(rid, {})) if rid else {}

    if not model:
        return SiteModelResponse(
            base_url="",
            total_pages=0,
            total_elements=0,
            total_forms=0,
            navigation_graph={},
            crawl_timestamp="",
        )

    return SiteModelResponse(
        base_url=model.get("base_url", ""),
        total_pages=model.get("total_pages", 0),
        total_elements=model.get("total_elements", 0),
        total_forms=model.get("total_forms", 0),
        navigation_graph=model.get("navigation_graph", {}),
        crawl_timestamp=model.get("crawl_timestamp", ""),
        run_id=model.get("run_id") or None,
    )


@router.get("/pages", response_model=list[PageSummary])
def list_pages(
    run_id: Optional[str] = Query(None, description="Pipeline run ID; omit for latest"),
) -> list[PageSummary]:
    """List all crawled pages for a specific run (or the latest run)."""
    _load_all_runs()

    if run_id:
        with _crawler_lock:
            pages_dict = dict(_crawled_pages.get(run_id, {}))
    else:
        rid = _latest_run_id()
        with _crawler_lock:
            pages_dict = dict(_crawled_pages.get(rid, {})) if rid else {}

    results: List[PageSummary] = []
    for page in pages_dict.values():
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
def get_page(
    url_encoded: str,
    run_id: Optional[str] = Query(None),
) -> PageSummary:
    """Get details for a specific crawled page by URL."""
    url = unquote(url_encoded)

    if run_id:
        with _crawler_lock:
            pages_dict = _crawled_pages.get(run_id, {})
            page = pages_dict.get(url) or pages_dict.get(url_encoded)
    else:
        rid = _latest_run_id()
        with _crawler_lock:
            pages_dict = _crawled_pages.get(rid, {}) if rid else {}
            page = pages_dict.get(url) or pages_dict.get(url_encoded)

    if page is None:
        raise HTTPException(status_code=404, detail=f"Page '{url}' not found")

    return PageSummary(
        url=page.get("url", ""),
        title=page.get("title", ""),
        element_count=page.get("element_count", 0),
        form_count=page.get("form_count", 0),
        link_count=page.get("link_count", 0),
    )
