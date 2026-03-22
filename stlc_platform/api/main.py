"""
STLC Automation Platform — FastAPI Application
===============================================
Main entry point for the API server. Includes all routers, CORS middleware,
WebSocket endpoint for real-time pipeline progress, and health check.

Usage:
    uvicorn stlc_platform.api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from stlc_platform.api.deps import get_agent_registry, get_ws_manager
from stlc_platform.api.schemas import HealthResponse

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
    pipeline,
    requirements,
    test_cases,
)

logger = logging.getLogger(__name__)


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

app = FastAPI(
    title="STLC Automation Platform API",
    description="AI-powered Software Testing Life Cycle automation platform",
    version="0.5.0",
    lifespan=lifespan,
)

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
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────

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

@app.websocket("/ws/pipeline/{run_id}")
async def websocket_pipeline(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time pipeline run updates."""
    ws_mgr = get_ws_manager()
    await ws_mgr.connect(websocket, run_id)
    try:
        while True:
            # Keep connection alive; clients send pings, we ignore data
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect(websocket, run_id)
