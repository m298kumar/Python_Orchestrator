"""Pipeline orchestration — DAG-based agent execution (Stage 4)."""

from stlc_platform.pipeline.dag import PipelineDAG, StageNode
from stlc_platform.pipeline.orchestrator import PipelineOrchestrator, StageResult
from stlc_platform.pipeline.artifact_store import ArtifactStore, ArtifactResolver
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.pipeline_loader import load_pipeline

__all__ = [
    "PipelineDAG",
    "StageNode",
    "PipelineOrchestrator",
    "StageResult",
    "ArtifactStore",
    "ArtifactResolver",
    "AgentRegistry",
    "load_pipeline",
]
