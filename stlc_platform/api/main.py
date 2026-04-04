"""
STLC Automation Platform — FastAPI Application
===============================================
Main entry point for the API server. Includes all routers, CORS middleware,
WebSocket endpoint for real-time pipeline progress, and health check.

Usage:
    uvicorn stlc_platform.api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path as _Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from stlc_platform.core.logging_config import get_logger, setup_logging

# Setup logging as early as possible
setup_logging()
logger = get_logger(__name__)

from stlc_platform.api.deps import get_agent_registry, get_ws_manager

# Route modules
from stlc_platform.api.routes import (
    agents,
    api_tests,
    artifacts,
    bdd,
    config,
    crawler,
    feedback,
    files,
    metrics,
    pipeline,
    requirements,
    test_cases,
)
from stlc_platform.api.routes import (
    auth as auth_mod,
)
from stlc_platform.api.schemas import HealthResponse


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler."""
    logger.info("STLC API starting up")
    # Eagerly initialise the agent registry so first request is fast
    try:
        get_agent_registry()
        logger.info("Agent registry initialised")
    except Exception as exc:
        logger.warning("Agent registry init deferred: %s", exc)
    yield
    logger.info("STLC API shutting down")


# ── App ──────────────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="STLC Automation Platform API",
    description="AI-powered Software Testing Life Cycle automation platform",
    version="0.5.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────

_default_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

_extra_origins = os.environ.get("STLC_CORS_ORIGINS", "")
_allowed_origins = _default_origins + [
    o.strip() for o in _extra_origins.split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "Accept"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
# NOTE: Each router already defines its own prefix (e.g. prefix="/api/test-cases"),
# so we do NOT pass prefix= here to avoid double-prefixing.

app.include_router(auth_mod.router)
app.include_router(pipeline.router)
app.include_router(agents.router)
app.include_router(requirements.router)
app.include_router(test_cases.router)
app.include_router(bdd.router)
app.include_router(crawler.router)
app.include_router(api_tests.router)
app.include_router(artifacts.router)
app.include_router(feedback.router)
app.include_router(config.router)
app.include_router(files.router)
app.include_router(metrics.router)


# ── Global Exception Handlers ──────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return consistent JSON for all HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return structured JSON for any unhandled server error."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "status_code": 500},
    )


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Health check endpoint."""
    try:
        registry = get_agent_registry()
        agent_count = len(registry.list_agents())
    except Exception:
        agent_count = 0

    return HealthResponse(
        status="ok",
        version="0.5.0",
        stage=5,
        agents_registered=agent_count,
    )


# ── WebSocket ────────────────────────────────────────────────────────────────

_WS_RUN_ID_RE = __import__("re").compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@app.websocket("/ws/pipeline/{run_id}")
async def websocket_pipeline(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time pipeline run updates."""
    if not _WS_RUN_ID_RE.match(run_id):
        await websocket.close(code=1008, reason="Invalid run_id format")
        return
    ws_mgr = get_ws_manager()
    await ws_mgr.connect(websocket, run_id)
    try:
        while True:
            # Keep connection alive; clients send pings, we ignore data
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect(websocket, run_id)


# ── Static Frontend Serving (Production) ─────────────────────────────

_frontend_dist = _Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
_serve_frontend = os.environ.get("STLC_SERVE_FRONTEND", "auto")

if _serve_frontend == "true" or (
    _serve_frontend == "auto" and _frontend_dist.is_dir()
):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _assets_dir = _frontend_dist / "assets"
    if _assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_assets_dir)),
            name="frontend-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve the SPA frontend; fall back to index.html for client routing."""
        file_path = (_frontend_dist / full_path).resolve()
        dist_resolved = _frontend_dist.resolve()
        if full_path and str(file_path).startswith(str(dist_resolved)) and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))
