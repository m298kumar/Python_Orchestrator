"""
Artifact Store
==============
In-memory + on-disk artifact persistence for pipeline runs.
Includes ArtifactResolver for resolving $stage.key and $config.key references.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ArtifactStore:
    """In-memory artifact store with optional disk persistence."""

    def __init__(self, run_dir: Optional[Path] = None) -> None:
        self._artifacts: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._run_dir = run_dir
        self._completed_order: List[str] = []

    def store(
        self,
        stage_id: str,
        artifacts: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store stage output artifacts."""
        self._artifacts[stage_id] = artifacts
        self._metadata[stage_id] = metadata or {}
        if stage_id not in self._completed_order:
            self._completed_order.append(stage_id)

    def get(self, stage_id: str, key: str) -> Any:
        """Get a specific artifact by stage_id and key."""
        if stage_id not in self._artifacts:
            raise KeyError(f"No artifacts for stage '{stage_id}'.")
        stage_artifacts = self._artifacts[stage_id]
        if key not in stage_artifacts:
            raise KeyError(
                f"Artifact '{key}' not found in stage '{stage_id}'. "
                f"Available: {list(stage_artifacts.keys())}"
            )
        return stage_artifacts[key]

    def get_all(self, stage_id: str) -> Dict[str, Any]:
        """Get all artifacts for a stage."""
        if stage_id not in self._artifacts:
            raise KeyError(f"No artifacts for stage '{stage_id}'.")
        return self._artifacts[stage_id]

    def has_stage(self, stage_id: str) -> bool:
        """Check if a stage has completed artifacts."""
        return stage_id in self._artifacts

    @property
    def completed_stages(self) -> List[str]:
        """Return completed stage IDs in order."""
        return list(self._completed_order)

    def persist_to_disk(self) -> None:
        """Flush all in-memory artifacts to run_dir as JSON."""
        if self._run_dir is None:
            return
        self._run_dir.mkdir(parents=True, exist_ok=True)

        manifest: Dict[str, Any] = {
            "completed_order": self._completed_order,
            "stages": {},
        }

        for stage_id in self._completed_order:
            stage_data = self._serialize_artifacts(self._artifacts[stage_id])
            stage_meta = self._metadata.get(stage_id, {})
            stage_file = self._run_dir / f"{stage_id}.json"
            stage_file.write_text(
                json.dumps(
                    {"artifacts": stage_data, "metadata": stage_meta},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
            manifest["stages"][stage_id] = str(stage_file.name)

        manifest_file = self._run_dir / "manifest.json"
        manifest_file.write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        # Export human-readable files (.feature, .csv)
        self._export_files()

    def _export_files(self) -> None:
        """Export human-readable files from artifacts (feature files, CSV)."""
        if self._run_dir is None:
            return
        logger = logging.getLogger(__name__)

        # Export .feature files from BDD stage
        for stage_id in ("generate_bdd_code",):
            if stage_id not in self._artifacts:
                continue
            features = self._artifacts[stage_id].get("feature_files", [])
            if not features:
                continue
            features_dir = self._run_dir / "features"
            features_dir.mkdir(exist_ok=True)
            for i, feat in enumerate(features):
                if isinstance(feat, BaseModel):
                    feat = feat.model_dump()
                if isinstance(feat, dict):
                    filename = feat.get("filename", f"feature_{i}.feature")
                    content = feat.get("content", "")
                elif isinstance(feat, str):
                    # Already serialized as plain string content
                    filename = f"feature_{i}.feature"
                    content = feat
                else:
                    continue
                if content:
                    (features_dir / filename).write_text(content, encoding="utf-8")
            logger.info("Exported %d .feature files to %s", len(features), features_dir)

        # Export test_cases.csv from requirements stage
        for stage_id in ("parse_requirements",):
            if stage_id not in self._artifacts:
                continue
            test_cases = self._artifacts[stage_id].get("test_cases", [])
            if not test_cases:
                continue
            csv_path = self._run_dir / "test_cases.csv"
            fieldnames = [
                "tc_id", "req_id", "title", "description", "test_type",
                "priority", "category", "component", "preconditions",
                "steps", "expected_outcome", "given", "when", "then",
                "tags", "test_level", "estimated_duration",
            ]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for tc in test_cases:
                    if isinstance(tc, BaseModel):
                        tc = tc.model_dump()
                    row = dict(tc)
                    # Flatten steps to readable text
                    steps = row.get("steps", [])
                    if isinstance(steps, list):
                        step_lines = []
                        for i, s in enumerate(steps, 1):
                            act = s.get("action", "") if isinstance(s, dict) else str(s)
                            exp = s.get("expected_result", "") if isinstance(s, dict) else ""
                            step_lines.append(f"{i}. {act} -> {exp}")
                        row["steps"] = "\n".join(step_lines)
                    # Flatten tags
                    tags = row.get("tags", [])
                    if isinstance(tags, list):
                        row["tags"] = ", ".join(str(t) for t in tags)
                    writer.writerow(row)
            logger.info("Exported %d test cases to %s", len(test_cases), csv_path)

    def load_from_disk(self, up_to_stage: Optional[str] = None) -> List[str]:
        """Load persisted artifacts from disk. Returns list of loaded stage_ids."""
        if self._run_dir is None:
            return []

        manifest_file = self._run_dir / "manifest.json"
        if not manifest_file.exists():
            return []

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        loaded: List[str] = []

        for stage_id in manifest.get("completed_order", []):
            stage_file = self._run_dir / manifest["stages"][stage_id]
            if stage_file.exists():
                data = json.loads(stage_file.read_text(encoding="utf-8"))
                self._artifacts[stage_id] = data.get("artifacts", {})
                self._metadata[stage_id] = data.get("metadata", {})
                if stage_id not in self._completed_order:
                    self._completed_order.append(stage_id)
                loaded.append(stage_id)

            if up_to_stage and stage_id == up_to_stage:
                break

        return loaded

    @staticmethod
    def _serialize_artifacts(artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize artifacts, handling Pydantic models."""
        result: Dict[str, Any] = {}
        for key, value in artifacts.items():
            if isinstance(value, BaseModel):
                result[key] = value.model_dump()
            elif isinstance(value, list):
                result[key] = [
                    v.model_dump() if isinstance(v, BaseModel) else v
                    for v in value
                ]
            else:
                try:
                    json.dumps(value, default=str)
                    result[key] = value
                except (TypeError, ValueError):
                    result[key] = str(value)
        return result


class ArtifactResolver:
    """Resolves $stage.output and $config.key references in input maps."""

    def __init__(self, store: ArtifactStore, config: Dict[str, Any]) -> None:
        self._store = store
        self._config = config

    def resolve(self, input_map: Dict[str, str]) -> Dict[str, Any]:
        """Resolve all references in an input_map to actual values."""
        resolved: Dict[str, Any] = {}
        for key, ref in input_map.items():
            resolved[key] = self.resolve_single(ref)
        return resolved

    def resolve_single(self, ref: str) -> Any:
        """Resolve a single reference string.

        Patterns:
            $stage_id.artifact_key  -> store.get(stage_id, artifact_key)
            $config.dotted.path     -> nested config lookup
            $runtime.llm_client     -> auto-create LLM client from config
            literal_value           -> pass through
        """
        if not isinstance(ref, str) or not ref.startswith("$"):
            return ref

        ref_body = ref[1:]  # strip leading $

        if ref_body.startswith("config."):
            config_path = ref_body[len("config."):]
            return self._resolve_config_path(config_path)

        if ref_body.startswith("runtime."):
            runtime_key = ref_body[len("runtime."):]
            return self._resolve_runtime(runtime_key)

        # $stage_id.artifact_key
        parts = ref_body.split(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid reference '{ref}'. Expected '$stage_id.key' or '$config.path'."
            )
        stage_id, artifact_key = parts
        return self._store.get(stage_id, artifact_key)

    def _resolve_runtime(self, key: str) -> Any:
        """Resolve runtime references like llm_client."""
        if key == "llm_client":
            return self._create_llm_client()
        raise KeyError(f"Unknown runtime key: '{key}'")

    def _create_llm_client(self) -> Any:
        """Create an LLM client based on config settings."""
        from stlc_platform.core.llm.base_client import BaseLLMClient

        llm_cfg = self._config.get("llm", {})
        provider = llm_cfg.get("provider", "ollama")
        model = llm_cfg.get("model", "")
        api_key = llm_cfg.get("api_key", "")
        base_url = llm_cfg.get("base_url", "")

        if provider == "ollama":
            from stlc_platform.core.llm.ollama_client import OllamaClient
            return OllamaClient(
                model=model or "qwen2.5:7b-instruct",
                base_url=base_url or "http://localhost:11434",
            )
        elif provider == "openai":
            from stlc_platform.core.llm.openai_client import OpenAIClient
            import os
            return OpenAIClient(
                model=model or "gpt-4o-mini",
                api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            )
        elif provider == "anthropic":
            from stlc_platform.core.llm.anthropic_client import AnthropicClient
            import os
            return AnthropicClient(
                model=model or "claude-sonnet-4-20250514",
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{provider}'. "
                "Supported: ollama, openai, anthropic"
            )

    def _resolve_config_path(self, dotted_path: str) -> Any:
        """Resolve a dotted config path like 'llm.model'."""
        parts = dotted_path.split(".")
        current: Any = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise KeyError(
                    f"Config path '{dotted_path}' not found "
                    f"(failed at '{part}')."
                )
        return current
