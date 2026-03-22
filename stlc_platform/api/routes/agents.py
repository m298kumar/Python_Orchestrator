"""
Agent Routes
============
List and inspect registered STLC agents.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from stlc_platform.api.deps import get_agent_registry
from stlc_platform.api.schemas import AgentInfo

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/", response_model=list[AgentInfo])
def list_agents() -> list[AgentInfo]:
    """List all registered agents with their capabilities."""
    registry = get_agent_registry()
    result = []
    for cap in registry.list_agents():
        result.append(
            AgentInfo(
                agent_id=cap.agent_id,
                agent_version=cap.agent_version,
                description=cap.description,
                input_types=cap.input_types,
                output_types=cap.output_types,
                required_skills=cap.required_skills,
                default_model_tier=cap.default_model_tier,
            )
        )
    return result


@router.get("/{agent_id}", response_model=AgentInfo)
def get_agent(agent_id: str) -> AgentInfo:
    """Get capabilities of a specific agent."""
    registry = get_agent_registry()
    if not registry.has(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    agent = registry.get(agent_id)
    cap = agent.get_capabilities()
    return AgentInfo(
        agent_id=cap.agent_id,
        agent_version=cap.agent_version,
        description=cap.description,
        input_types=cap.input_types,
        output_types=cap.output_types,
        required_skills=cap.required_skills,
        default_model_tier=cap.default_model_tier,
    )
