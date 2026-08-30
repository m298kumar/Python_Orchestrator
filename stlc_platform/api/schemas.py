"""
API Request/Response Schemas
============================
Pydantic models for FastAPI request/response validation.
These wrap the internal artifact contracts for API serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

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
    status: Literal["pending", "running", "completed", "failed"]
    started_at: str
    completed_at: Optional[str] = None
    stages_completed: List[str] = Field(default_factory=list)
    stages_failed: List[str] = Field(default_factory=list)
    stages_skipped: List[str] = Field(default_factory=list)
    current_stage: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    archived: bool = False
    archived_at: Optional[str] = None


class PipelineRunSummary(BaseModel):
    """Brief summary for listing runs."""

    run_id: str
    pipeline_name: str
    status: str
    started_at: str
    stages_completed_count: int = 0
    total_duration_seconds: Optional[float] = None
    archived: bool = False
    archived_at: Optional[str] = None


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


class TestStepResponse(BaseModel):
    """A single test step."""

    action: str = ""
    expected_result: str = ""


class TestCaseResponse(BaseModel):
    """A single test case."""

    tc_id: str
    req_id: str
    title: str
    description: str = ""
    preconditions: str = ""
    test_type: str = ""
    priority: str = ""
    category: str = ""
    component: str = ""
    steps: List[TestStepResponse] = Field(default_factory=list)
    given: str = ""
    when: str = ""
    then: str = ""
    expected_outcome: str = ""
    tags: List[str] = Field(default_factory=list)
    status: str = "generated"  # generated, approved, rejected
    test_level: str = ""
    quality_score: float = 0.0
    quality_issues: List[str] = Field(default_factory=list)
    quality_validated: bool = True
    run_id: Optional[str] = None
    rag_example_id: Optional[str] = None
    review_id: Optional[int] = None
    reviewer: str = ""
    review_reason: str = ""
    reviewed_at: str = ""


class TestCaseUpdate(BaseModel):
    """Editable fields of a test case."""

    title: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[TestStepResponse]] = None
    expected_outcome: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None


class TestCaseAction(BaseModel):
    """Approve/reject a test case."""

    reason: Optional[str] = None
    reviewer: Optional[str] = None


class TestCaseRef(BaseModel):
    """Unambiguous test-case identity across pipeline runs."""

    tc_id: str
    run_id: str


class BulkTestCaseAction(BaseModel):
    """Bulk approve/reject test cases."""

    items: List[TestCaseRef] = Field(..., min_length=1, max_length=500)
    reason: Optional[str] = None
    reviewer: Optional[str] = None


# ── BDD ──────────────────────────────────────────────────────────────────────


class FeatureFileResponse(BaseModel):
    """A generated feature file."""

    filename: str
    req_id: str
    scenario_count: int
    tags: List[str] = Field(default_factory=list)
    content: str = ""
    run_id: Optional[str] = None


# ── Crawler ──────────────────────────────────────────────────────────────────


class SiteModelResponse(BaseModel):
    """Site model summary."""

    base_url: str
    total_pages: int
    total_elements: int
    total_forms: int
    navigation_graph: Dict[str, List[str]] = Field(default_factory=dict)
    crawl_timestamp: str = ""
    run_id: Optional[str] = None


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
    run_id: Optional[str] = None


# ── Feedback ─────────────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    """Submit feedback for an agent."""

    agent_id: str
    feedback_type: Literal["correction", "preference", "constraint"] = Field(
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
    specifications: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    crawler: Dict[str, Any] = Field(default_factory=dict)
    api_testing: Dict[str, Any] = Field(default_factory=dict)
    test_generation: Dict[str, Any] = Field(default_factory=dict)
    bdd: Dict[str, Any] = Field(default_factory=dict)
    quality_gate: Dict[str, Any] = Field(default_factory=dict)
    coverage: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    chromadb: Dict[str, Any] = Field(default_factory=dict)
    export: Dict[str, Any] = Field(default_factory=dict)
    circuit_breaker: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    review: Dict[str, Any] = Field(default_factory=dict)


class ConfigUpdate(BaseModel):
    """Config fields to update.

    Supports two formats:
    1. Dot-notation via ``updates``: {"updates": {"llm.model": "gpt-4o"}}
    2. Structured sections: {"llm": {"model": "gpt-4o"}, "project": {"name": "X"}}

    Both can be combined; ``updates`` is applied first, then sections are deep-merged.
    """

    updates: Optional[Dict[str, Any]] = None
    project: Optional[Dict[str, Any]] = None
    specifications: Optional[Dict[str, Any]] = None
    llm: Optional[Dict[str, Any]] = None
    crawler: Optional[Dict[str, Any]] = None
    api_testing: Optional[Dict[str, Any]] = None
    test_generation: Optional[Dict[str, Any]] = None
    bdd: Optional[Dict[str, Any]] = None
    quality_gate: Optional[Dict[str, Any]] = None
    coverage: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    chromadb: Optional[Dict[str, Any]] = None
    export: Optional[Dict[str, Any]] = None
    circuit_breaker: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    review: Optional[Dict[str, Any]] = None


class LLMTestRequest(BaseModel):
    """Request to test an LLM provider connection."""

    provider: str  # ollama | openai | anthropic | azure
    model: str = ""
    base_url: str = ""
    api_key: str = ""


class LLMTestResponse(BaseModel):
    """Result of an LLM provider connection test."""

    success: bool
    message: str
    models: list[str] = []


# ── WebSocket Messages ──────────────────────────────────────────────────────


class WSMessage(BaseModel):
    """WebSocket message from server to client."""

    event: str  # stage_start, stage_complete, stage_error, pipeline_complete
    run_id: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Generic ──────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    stage: int
    agents_registered: int


# ── Metrics ─────────────────────────────────────────────────────────────────


class MetricsResponse(BaseModel):
    """Metrics for a single pipeline run."""

    run_id: str
    timestamp: str
    pipeline_name: str = ""
    total_test_cases: int = 0
    avg_quality_score: float = 0.0
    quality_distribution: Dict[str, int] = Field(default_factory=dict)
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    llm_provider: str = ""
    llm_model: str = ""
    cache_hit_rate: float = 0.0
    generation_time_seconds: float = 0.0
    per_stage_durations: Dict[str, float] = Field(default_factory=dict)
    per_ac_type_scores: Dict[str, float] = Field(default_factory=dict)
    coverage_pct: float = 0.0
    stages_completed: int = 0
    stages_failed: int = 0
    stages_skipped: int = 0


class MetricsTrendResponse(BaseModel):
    """Aggregated quality and cost trends."""

    run_count: int
    avg_quality_score: float
    avg_generation_time: float
    total_tokens: int
    total_cost_usd: float
    quality_trend: List[Dict[str, Any]] = Field(default_factory=list)
    degradation_warning: Optional[str] = None


class MetricsComparisonResponse(BaseModel):
    """Side-by-side comparison of two pipeline runs."""

    run_a: MetricsResponse
    run_b: MetricsResponse
    deltas: Dict[str, float] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: str
