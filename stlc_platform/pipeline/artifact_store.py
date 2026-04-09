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
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ArtifactStore:
    """In-memory artifact store with optional disk persistence."""

    def __init__(self, run_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
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
        """Store stage output artifacts (thread-safe)."""
        with self._lock:
            self._artifacts[stage_id] = artifacts
            self._metadata[stage_id] = metadata or {}
            if stage_id not in self._completed_order:
                self._completed_order.append(stage_id)

    def get(self, stage_id: str, key: str) -> Any:
        """Get a specific artifact by stage_id and key (thread-safe)."""
        with self._lock:
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
        """Get all artifacts for a stage (thread-safe)."""
        with self._lock:
            if stage_id not in self._artifacts:
                raise KeyError(f"No artifacts for stage '{stage_id}'.")
            return self._artifacts[stage_id]

    def has_stage(self, stage_id: str) -> bool:
        """Check if a stage has completed artifacts (thread-safe)."""
        with self._lock:
            return stage_id in self._artifacts

    @property
    def completed_stages(self) -> List[str]:
        """Return completed stage IDs in order (thread-safe)."""
        with self._lock:
            return list(self._completed_order)

    def persist_to_disk(self) -> None:
        """Flush all in-memory artifacts to run_dir as JSON (thread-safe)."""
        if self._run_dir is None:
            return

        # Snapshot data under lock to avoid races with concurrent store() calls
        with self._lock:
            order_snapshot = list(self._completed_order)
            serialized: Dict[str, Dict[str, Any]] = {}
            for stage_id in order_snapshot:
                serialized[stage_id] = {
                    "artifacts": self._serialize_artifacts(self._artifacts[stage_id]),
                    "metadata": dict(self._metadata.get(stage_id, {})),
                }

        # Write to disk outside the lock (I/O can be slow)
        self._run_dir.mkdir(parents=True, exist_ok=True)

        manifest: Dict[str, Any] = {
            "completed_order": order_snapshot,
            "stages": {},
        }

        for stage_id in order_snapshot:
            stage_file = self._run_dir / f"{stage_id}.json"
            stage_file.write_text(
                json.dumps(serialized[stage_id], indent=2, default=str),
                encoding="utf-8",
            )
            manifest["stages"][stage_id] = str(stage_file.name)

        manifest_file = self._run_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Export human-readable files (.feature, .csv)
        self._export_files()

    def _export_files(self) -> None:
        """Export human-readable files from artifacts (feature files, CSV)."""
        if self._run_dir is None:
            return
        logger = logging.getLogger(__name__)

        self._export_feature_files(logger)
        self._export_test_cases_csv(logger)

    def _export_feature_files(self, logger) -> None:
        features = self._artifacts.get("generate_bdd_code", {}).get("feature_files", [])
        if not features:
            return
        features_dir = self._run_dir / "features"
        features_dir.mkdir(exist_ok=True)
        for i, feat in enumerate(features):
            filename, content = self._extract_feature_content(feat, i)
            if content:
                (features_dir / filename).write_text(content, encoding="utf-8")
        logger.info("Exported %d .feature files to %s", len(features), features_dir)

    def _extract_feature_content(self, feat, index: int) -> tuple[str, str]:
        if isinstance(feat, BaseModel):
            feat = feat.model_dump()
        if isinstance(feat, dict):
            return feat.get("filename", f"feature_{index}.feature"), feat.get("content", "")
        if isinstance(feat, str):
            return f"feature_{index}.feature", feat
        return "", ""

    def _export_test_cases_csv(self, logger) -> None:
        test_cases = self._artifacts.get("parse_requirements", {}).get("test_cases", [])
        if not test_cases:
            return
        csv_path = self._run_dir / "test_cases.csv"
        fieldnames = [
            "tc_id",
            "req_id",
            "title",
            "description",
            "test_type",
            "priority",
            "category",
            "component",
            "preconditions",
            "steps",
            "expected_outcome",
            "given",
            "when",
            "then",
            "tags",
            "test_level",
            "estimated_duration",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for tc in test_cases:
                if isinstance(tc, BaseModel):
                    tc = tc.model_dump()
                row = dict(tc)
                row["steps"] = self._flatten_steps(row.get("steps", []))
                tags = row.get("tags", [])
                if isinstance(tags, list):
                    row["tags"] = ", ".join(str(t) for t in tags)
                writer.writerow(row)
        logger.info("Exported %d test cases to %s", len(test_cases), csv_path)

    @staticmethod
    def _flatten_steps(steps) -> str:
        if not isinstance(steps, list):
            return str(steps)
        step_lines = []
        for i, s in enumerate(steps, 1):
            act = s.get("action", "") if isinstance(s, dict) else str(s)
            exp = s.get("expected_result", "") if isinstance(s, dict) else ""
            step_lines.append(f"{i}. {act} -> {exp}")
        return "\n".join(step_lines)

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
                result[key] = [v.model_dump() if isinstance(v, BaseModel) else v for v in value]
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
            $stage_id.artifact_key   -> store.get(stage_id, artifact_key); raises KeyError if missing
            $?stage_id.artifact_key  -> returns None if stage was skipped/missing (optional input)
            $config.dotted.path      -> nested config lookup
            $runtime.llm_client      -> auto-create LLM client from config
            literal_value            -> pass through
        """
        if not isinstance(ref, str) or not ref.startswith("$"):
            return ref

        ref_body = ref[1:]  # strip leading $

        # Optional reference: $?stage_id.artifact_key → None if stage missing
        optional = ref_body.startswith("?")
        if optional:
            ref_body = ref_body[1:]

        if ref_body.startswith("config."):
            return self._resolve_config_ref(ref_body[len("config."):], optional)

        if ref_body.startswith("runtime."):
            return self._resolve_runtime(ref_body[len("runtime."):])

        return self._resolve_stage_ref(ref, ref_body, optional)

    def _resolve_config_ref(self, config_path: str, optional: bool) -> Any:
        """Resolve a $[?]config.dotted.path reference."""
        if optional:
            try:
                return self._resolve_config_path(config_path)
            except KeyError:
                return None
        return self._resolve_config_path(config_path)

    def _resolve_stage_ref(self, original_ref: str, ref_body: str, optional: bool) -> Any:
        """Resolve a $[?]stage_id.artifact_key reference."""
        parts = ref_body.split(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid reference '{original_ref}'. Expected '$stage_id.key' or '$config.path'."
            )
        stage_id, artifact_key = parts
        if optional:
            try:
                return self._store.get(stage_id, artifact_key)
            except KeyError:
                return None
        return self._store.get(stage_id, artifact_key)

    def _resolve_runtime(self, key: str) -> Any:
        """Resolve runtime references like llm_client, feedback_store."""
        if key == "llm_client":
            return self._create_llm_client()
        if key == "feedback_store":
            return self._create_feedback_store()
        raise KeyError(f"Unknown runtime key: '{key}'")

    def _create_feedback_store(self) -> Any:
        """Create a FeedbackStore, optionally with ChromaDB semantic search."""
        from pathlib import Path

        from stlc_platform.pipeline.feedback_store import FeedbackStore

        # Try to create with ChromaDB for semantic search
        chroma_store = None
        try:
            from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

            chroma_cfg = self._config.get("chromadb", {})
            if chroma_cfg:
                chroma_store = RequirementsVectorStore(chromadb_config=chroma_cfg)
        except (ImportError, OSError, ValueError) as exc:
            logging.getLogger(__name__).debug(
                "ChromaDB unavailable, using JSON-only feedback: %s", exc
            )

        return FeedbackStore(
            persist_path=Path("./feedback"),
            chroma_store=chroma_store,
        )

    def _create_llm_client(self) -> Any:
        """Create an LLM client based on config settings."""
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
            import os

            from stlc_platform.core.llm.openai_client import OpenAIClient

            return OpenAIClient(
                model=model or "gpt-4o-mini",
                api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            )
        elif provider == "anthropic":
            import os

            from stlc_platform.core.llm.anthropic_client import AnthropicClient

            return AnthropicClient(
                model=model or "claude-sonnet-4-20250514",
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
            )
        else:
            raise ValueError(
                f"Unsupported LLM provider: '{provider}'. Supported: ollama, openai, anthropic"
            )

    def _resolve_config_path(self, dotted_path: str) -> Any:
        """Resolve a dotted config path like 'llm.model'."""
        parts = dotted_path.split(".")
        current: Any = self._config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise KeyError(f"Config path '{dotted_path}' not found (failed at '{part}').")
        return current
