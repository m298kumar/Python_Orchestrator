"""
Artifact Contracts
==================
Pydantic models defining the data schemas that flow between agents.
Every contract is versioned. Consumers validate on load.

Versioning rules:
  - Patch (1.0 -> 1.1): add optional fields only (backward compatible)
  - Minor (1.x -> 2.0): change required fields (requires migration)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Stage 1: Requirements & Test Cases ───────────────────────────────────────


class RequirementArtifact(BaseModel):
    """Output of requirements parsing — one per requirement."""

    schema_version: str = "1.0"
    req_id: str
    title: str
    description: str
    priority: str = "Medium"
    category: str = "Functional"
    acceptance_criteria: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    raw_text: str = ""

    def to_chroma_document(self) -> str:
        parts = [
            f"Requirement ID: {self.req_id}",
            f"Title: {self.title}",
            f"Description: {self.description}",
            f"Priority: {self.priority}",
            f"Category: {self.category}",
        ]
        if self.acceptance_criteria:
            parts.append("Acceptance Criteria:")
            for ac in self.acceptance_criteria:
                parts.append(f"  - {ac}")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "category": self.category,
            "acceptance_criteria": self.acceptance_criteria,
            "tags": self.tags,
        }


class TestStepArtifact(BaseModel):
    """A single test step within a test case."""

    action: str
    expected_result: str


class TestCaseArtifact(BaseModel):
    """Output of test case generation — one per test case."""

    schema_version: str = "1.0"
    tc_id: str
    req_id: str
    title: str
    description: str
    preconditions: str
    test_type: str
    priority: str
    steps: List[TestStepArtifact] = Field(default_factory=list)
    expected_outcome: str = ""
    tags: List[str] = Field(default_factory=list)
    category: str = ""
    component: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    estimated_duration: str = "5"


# ── Stage 2: BDD Code Generation ────────────────────────────────────────────


class FeatureFileArtifact(BaseModel):
    """Output of BDD feature file generation."""

    schema_version: str = "1.0"
    req_id: str
    filename: str
    content: str
    scenario_count: int = 0
    tags: List[str] = Field(default_factory=list)


class StepDefinitionArtifact(BaseModel):
    """Output of step definition skeleton generation."""

    schema_version: str = "1.0"
    language: str
    framework: str
    filename: str
    content: str
    step_count: int = 0


# ── Stage 3: Crawler & API ──────────────────────────────────────────────────


class PageElementArtifact(BaseModel):
    """A single element discovered on a crawled page."""

    element_type: str  # input, button, link, form, etc.
    name: str = ""
    selector: str = ""
    text: str = ""
    attributes: Dict[str, str] = Field(default_factory=dict)


class CrawledPageArtifact(BaseModel):
    """A single page discovered by the web crawler."""

    url: str
    title: str = ""
    elements: List[PageElementArtifact] = Field(default_factory=list)
    forms: List[Dict[str, Any]] = Field(default_factory=list)
    api_calls: List[Dict[str, Any]] = Field(default_factory=list)


class DiscrepancyArtifact(BaseModel):
    """A single discrepancy between requirements and the site model."""

    schema_version: str = "1.0"
    discrepancy_type: str  # missing_element | missing_page | missing_form_field
    requirement_id: str
    expected: str
    actual: str
    severity: str = "warning"  # show_stopper | warning | info
    page_url: str = ""
    details: str = ""


class DiscrepancyReportArtifact(BaseModel):
    """Aggregated report of all discrepancies found."""

    schema_version: str = "1.0"
    summary: str = ""
    total_requirements: int = 0
    total_discrepancies: int = 0
    show_stoppers: int = 0
    warnings: int = 0
    infos: int = 0
    items: List[DiscrepancyArtifact] = Field(default_factory=list)
    gate_decision: str = "proceed"  # proceed | proceed_with_warnings | block


class SiteModelArtifact(BaseModel):
    """Output of web crawler — full site structure."""

    schema_version: str = "1.1"
    base_url: str
    pages: List[CrawledPageArtifact] = Field(default_factory=list)
    navigation_graph: Dict[str, List[str]] = Field(default_factory=dict)
    crawl_timestamp: str = ""
    discrepancies: Optional[DiscrepancyReportArtifact] = None


class APIEndpointArtifact(BaseModel):
    """A single API endpoint discovered or parsed."""

    path: str
    method: str
    path_params: List[Dict[str, str]] = Field(default_factory=list)
    query_params: List[Dict[str, str]] = Field(default_factory=list)
    request_body_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    auth_required: bool = False
    auth_type: str = ""


class APIModelArtifact(BaseModel):
    """Output of API discovery — all endpoints."""

    schema_version: str = "1.0"
    endpoints: List[APIEndpointArtifact] = Field(default_factory=list)
    base_url: str = ""
    auth_type: str = ""


class APITestArtifact(BaseModel):
    """Output of API test generation."""

    schema_version: str = "1.0"
    framework: str
    language: str
    filename: str
    content: str
    endpoint_path: str = ""
    test_count: int = 0


# ── Stage 4: Pipeline ───────────────────────────────────────────────────────


class PipelineRunArtifact(BaseModel):
    """Metadata about a pipeline execution."""

    schema_version: str = "1.0"
    run_id: str
    pipeline_name: str
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"  # pending, running, completed, failed
    stages_completed: List[str] = Field(default_factory=list)
    stages_failed: List[str] = Field(default_factory=list)
    artifacts: Dict[str, str] = Field(default_factory=dict)  # stage_id -> artifact path
    error_message: str = ""
