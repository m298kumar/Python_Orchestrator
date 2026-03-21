"""
Pipeline Loader
===============
Load pipeline definitions from YAML files into PipelineDAG objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from stlc_platform.pipeline.dag import PipelineDAG, StageNode


def load_pipeline(path: Union[str, Path]) -> PipelineDAG:
    """Load a pipeline YAML file and return a PipelineDAG."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return load_pipeline_from_dict(data)


def load_pipeline_from_dict(data: Dict[str, Any]) -> PipelineDAG:
    """Build a PipelineDAG from a parsed YAML dict."""
    pipeline_name = data.get("pipeline", "unnamed")
    raw_stages: List[Dict[str, Any]] = data.get("stages", [])

    if not raw_stages:
        raise ValueError("Pipeline definition must have at least one stage.")

    stages: List[StageNode] = []
    for raw in raw_stages:
        if "id" not in raw:
            raise ValueError(
                f"Stage missing required 'id' field: {raw}"
            )
        if "agent" not in raw:
            raise ValueError(
                f"Stage '{raw['id']}' missing required 'agent' field."
            )

        stages.append(
            StageNode(
                stage_id=raw["id"],
                agent_id=raw["agent"],
                depends_on=raw.get("depends_on", []),
                input_map=raw.get("input", {}),
                output_keys=raw.get("output", []),
                config_overrides=raw.get("config", {}),
                retry_count=raw.get("retry_count", 0),
                optional=raw.get("optional", False),
            )
        )

    return PipelineDAG(stages=stages, pipeline_name=pipeline_name)
