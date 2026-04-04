"""
Feedback Routes
===============
Submit and list agent feedback entries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

from stlc_platform.api.schemas import FeedbackRequest, FeedbackResponse
from stlc_platform.core.contracts import AgentFeedbackArtifact
from stlc_platform.pipeline.feedback_store import FeedbackStore

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# Shared feedback store instance
_feedback_store: Optional[FeedbackStore] = None


def _get_feedback_store() -> FeedbackStore:
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore()
    return _feedback_store


@router.post("/", response_model=FeedbackResponse, status_code=201)
def submit_feedback(req: FeedbackRequest) -> FeedbackResponse:
    """Submit feedback for an agent."""
    store = _get_feedback_store()

    artifact = AgentFeedbackArtifact(
        agent_id=req.agent_id,
        feedback_type=req.feedback_type,
        message=req.message,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.store(artifact)
    logger.info("Feedback submitted for agent '%s': %s", req.agent_id, req.feedback_type)

    return FeedbackResponse(
        agent_id=artifact.agent_id,
        feedback_type=artifact.feedback_type,
        message=artifact.message,
        applied_count=artifact.applied_count,
        created_at=artifact.created_at,
    )


@router.get("/", response_model=list[FeedbackResponse])
def list_feedback(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    limit: int = Query(default=100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
) -> list[FeedbackResponse]:
    """List feedback entries, optionally filtered by agent ID."""
    store = _get_feedback_store()
    items = store.list_all(agent_id=agent_id)

    results: List[FeedbackResponse] = []
    for f in items:
        results.append(
            FeedbackResponse(
                agent_id=f.agent_id,
                feedback_type=f.feedback_type,
                message=f.message,
                applied_count=f.applied_count,
                created_at=f.created_at,
            )
        )
    return results[offset : offset + limit]
