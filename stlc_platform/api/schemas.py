"""
API Request/Response Schemas
============================
Pydantic models for FastAPI request/response validation.
These wrap the internal artifact contracts for API serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    """Request to trigger a pipeline run."""
    pipeline_path: str = Field(
        default="config/pipelines/full_stlc.yaml",
        description="Path to pipeline YAML definition.",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Config overrides for this run.",
    )
    resume_from: Optional[str] = Field(
        default=None,
        description="Stage ID to resume from.",
    )
    max_workers: int = Field(default=4, ge=1, le=16)
    profile: Optional[str] = Field(
        default=None,
        description="Execution profile (smoke, targeted, regression).",
    )


class PipelineRunStatus(BaseModel):
    """Status of a pipeline run."""
    run_id: str
    pipeline_name: str
    status: str  # "running", "completed", "failed"
    started_at: str
    completed_at: Optional[str] = None
    stages_completed: List[str] = Field(default_factory=list)
    stages_failed: List[str] = Field(default_factory=list)
    stages_skipped: List[str] = Field(default_factory=list)
    current_stage: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    error_message: Optional[str] = None


class PipelineRunSummary(BaseModel):
    """Brief summary for listing runs."""
    run_id: str
    pipeline_name: str
    status: str
    started_at: str
    stages_completed_count: int = 0
    total_duration_seconds: Optional[float] = None


# ── Agents ───────────────────────────────────────────────────────────────────

class AgentInfo(BaseModel):
    """Agent capability information."""
    agent_id: str
    agent_version: str
    description: str
    input_types: List[str] = Field(default_factory=list)
    output_types: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    default_model_tier: str = "standard"


# ── Requirements ─────────────────────────────────────────────────────────────

class RequirementResponse(BaseModel):
    """A single requirement."""
    req_id: str
    title: str
    description: str
    priority: str = "Medium"
    category: str = "Functional"
    acceptance_criteria: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class RequirementUpdate(BaseModel):
    """Editable fields of a requirement."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    tags: Optional[List[str]] = None


# ── Test Cases ───────────────────────────────────────────────────────────────

class TestCaseResponse(BaseModel):
    """A single test case."""
    tc_id: str
    req_id: str
    title: str
    description: str = ""
    test_type: str = ""
    priority: str = ""
    category: str = ""
    component: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    expected_outcome: str = ""
    tags: List[str] = Field(default_factory=list)
    status: str = "generated"  # generated, approved, rejected


class TestCaseUpdate(BaseModel):
    """Editable fields of a test case."""
    title: Optional[str] = None
    description: Optional[str] = None
    given: Optional[str] = None
    when: Optional[str] = None
    then: Optional[str] = None
    expected_outcome: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None


class TestCaseAction(BaseModel):
    """Approve/reject a test case."""
    reason: Optional[str] = None


# ── BDD ──────────────────────────────────────────────────────────────────────

class FeatureFileResponse(BaseModel):
    """A generated feature file."""
    filename: str
    req_id: str
    scenario_count: int
    tags: List[str] = Field(default_factory=list)
    content: str = ""


# ── Crawler ──────────────────────────────────────────────────────────────────

class SiteModelResponse(BaseModel):
    """Site model summary."""
    base_url: str
    total_pages: int
    total_elements: int
    total_forms: int
    navigation_graph: Dict[str, List[str]] = Field(default_factory=dict)
    crawl_timestamp: str = ""


class PageSummary(BaseModel):
    """Summary of a crawled page."""
    url: str
    title: str
    element_count: int
    form_count: int
    link_count: int


# ── API Tests ────────────────────────────────────────────────────────────────

class APITestFileResponse(BaseModel):
    """A generated API test file."""
    filename: str
    framework: str
    language: str
    endpoint_path: str = ""
    test_count: int
    test_level: str = "api"
    content: str = ""


# ── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """Submit feedback for an agent."""
    agent_id: str
    feedback_type: str = Field(
        default="correction",
        description="correction, preference, or constraint",
    )
    message: str


class FeedbackResponse(BaseModel):
    """A feedback entry."""
    agent_id: str
    feedback_type: str
    message: str
    applied_count: int = 0
    created_at: str = ""


# ── Config ───────────────────────────────────────────────────────────────────

class ConfigResponse(BaseModel):
    """Current configuration (sanitized)."""
    project: Dict[str, Any] = Field(default_factory=dict)
    ollama: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)


class ConfigUpdate(BaseModel):
    """Config fields to update."""
    updates: Dict[str, Any]


# ── WebSocket Messages ──────────────────────────────────────────────────────

class WSMessage(BaseModel):
    """WebSocket message from server to client."""
    event: str  # stage_start, stage_complete, stage_error, pipeline_complete
    run_id: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Generic ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    stage: int
    agents_registered: int


class ErrorResponse(BaseModel):
    detail: str
