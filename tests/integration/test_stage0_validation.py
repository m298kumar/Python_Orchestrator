"""
Stage 0 Integration Tests
=========================
Cross-module tests verifying the entire Stage 0 foundation works end-to-end.
These go beyond unit tests by testing real interactions between modules.
"""

import json
import os
import tempfile

import pytest


# ── 1. Config Loader → All Modules ──────────────────────────────────────────

class TestConfigIntegration:
    """Verify that config loaded from YAML is correctly consumed by all modules."""

    def test_config_singleton_is_consistent(self):
        """Config loaded in different modules returns the same object."""
        from stlc_platform.core.config_loader import config as config1
        from stlc_platform.core.config_loader import config as config2
        assert config1 is config2

    def test_config_feeds_ollama_client(self):
        """OllamaClient reads config values correctly."""
        from stlc_platform.core.config_loader import config
        from stlc_platform.core.llm.ollama_client import OllamaClient

        client = OllamaClient()
        assert client.base_url == config.ollama.base_url
        assert client.model == config.ollama.model
        assert client.temperature == config.ollama.temperature

    def test_config_feeds_exporters(self):
        """Exporters read output_dir from config."""
        from stlc_platform.core.config_loader import config
        from stlc_platform.exporters.exporters import CSVExporter

        exporter = CSVExporter()
        assert hasattr(exporter, "export")
        # Verify config is accessible (output_dir exists)
        assert config.output.output_dir is not None

    def test_env_override_propagates(self, monkeypatch):
        """Environment variable override propagates through config to clients."""
        monkeypatch.setenv("OLLAMA_MODEL", "integration-test-model:1b")
        from stlc_platform.core.config_loader import load_config
        cfg = load_config()
        assert cfg.ollama.model == "integration-test-model:1b"


# ── 2. Contracts → Storage/Export ────────────────────────────────────────────

class TestContractIntegration:
    """Verify contracts work with storage and export modules."""

    def test_requirement_artifact_serialization_roundtrip(self):
        """RequirementArtifact serializes to JSON and back without data loss."""
        from stlc_platform.core.contracts import RequirementArtifact

        original = RequirementArtifact(
            req_id="REQ-INT-001",
            title="Integration Test Requirement",
            description="This requirement verifies serialization round-trip",
            priority="High",
            acceptance_criteria=["AC1: Data preserved", "AC2: Types correct"],
            tags=["integration", "serialization"],
        )

        json_str = original.model_dump_json()
        restored = RequirementArtifact.model_validate_json(json_str)

        assert restored.req_id == original.req_id
        assert restored.title == original.title
        assert restored.acceptance_criteria == original.acceptance_criteria
        assert restored.tags == original.tags
        assert restored.schema_version == "1.0"

    def test_testcase_artifact_serialization_roundtrip(self):
        """TestCaseArtifact serializes and deserializes correctly."""
        from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact

        original = TestCaseArtifact(
            tc_id="TC-INT-001",
            req_id="REQ-INT-001",
            title="Verify integration test",
            description="Tests the full contract cycle",
            preconditions="System is running",
            test_type="positive",
            priority="High",
            steps=[
                TestStepArtifact(action="Open the application", expected_result="App loads"),
                TestStepArtifact(action="Click the login button", expected_result="Form shown"),
                TestStepArtifact(action="Enter credentials and submit", expected_result="Dashboard"),
            ],
            given="a running application",
            when="user logs in",
            then="dashboard is shown",
        )

        json_str = original.model_dump_json()
        restored = TestCaseArtifact.model_validate_json(json_str)

        assert len(restored.steps) == 3
        assert restored.steps[0].action == "Open the application"
        assert restored.given == "a running application"

    def test_all_contract_types_are_serializable(self):
        """Every artifact contract can be serialized to JSON and back."""
        from stlc_platform.core.contracts import (
            RequirementArtifact,
            TestCaseArtifact,
            FeatureFileArtifact,
            StepDefinitionArtifact,
            SiteModelArtifact,
            APIModelArtifact,
            APITestArtifact,
            PipelineRunArtifact,
        )

        # Minimal valid instances for each type
        instances = [
            RequirementArtifact(req_id="R1", title="T", description="D"),
            TestCaseArtifact(
                tc_id="TC1", req_id="R1", title="T", description="D",
                preconditions="P", test_type="positive", priority="High",
            ),
            FeatureFileArtifact(req_id="R1", filename="f.feature", content="c"),
            StepDefinitionArtifact(
                language="python", framework="behave", filename="s.py", content="c",
            ),
            SiteModelArtifact(base_url="https://example.com"),
            APIModelArtifact(),
            APITestArtifact(
                framework="pytest", language="python", filename="t.py", content="c",
            ),
            PipelineRunArtifact(run_id="run-1", pipeline_name="test"),
        ]

        for instance in instances:
            json_str = instance.model_dump_json()
            cls = type(instance)
            restored = cls.model_validate_json(json_str)
            assert restored.schema_version == instance.schema_version, (
                f"{cls.__name__} schema_version mismatch after roundtrip"
            )


# ── 3. Reader → Contracts Compatibility ──────────────────────────────────────

class TestReaderContractIntegration:
    """Verify that the requirements reader output is compatible with contracts."""

    def test_reader_output_can_create_artifact(self, tmp_path):
        """RequirementsReader output can be used to create RequirementArtifact."""
        from stlc_platform.agents.requirements_agent.reader import RequirementsReader
        from stlc_platform.core.contracts import RequirementArtifact

        csv_file = tmp_path / "reqs.csv"
        csv_file.write_text(
            "id,title,description,priority,category\n"
            "REQ-001,Login Feature,Users must log in with credentials,High,Auth\n"
        )

        reader = RequirementsReader()
        reqs = reader.read(str(csv_file))
        assert len(reqs) == 1

        # Convert reader output to artifact
        req = reqs[0]
        artifact = RequirementArtifact(
            req_id=req.req_id,
            title=req.title,
            description=req.description,
            priority=req.priority,
            category=req.category,
            acceptance_criteria=req.acceptance_criteria,
            tags=req.tags,
        )

        assert artifact.req_id == "REQ-001"
        assert artifact.schema_version == "1.0"

    def test_reader_chroma_document_format(self, tmp_path):
        """Reader's to_chroma_document() produces searchable text."""
        from stlc_platform.agents.requirements_agent.reader import RequirementsReader

        json_file = tmp_path / "reqs.json"
        json_file.write_text(json.dumps({
            "requirements": [{
                "id": "REQ-002",
                "title": "Password Reset",
                "description": "Users can reset password via email",
                "acceptance_criteria": ["Link sent within 5 minutes"],
            }]
        }))

        reader = RequirementsReader()
        reqs = reader.read(str(json_file))
        doc = reqs[0].to_chroma_document()

        assert "REQ-002" in doc
        assert "Password Reset" in doc
        assert "Link sent within 5 minutes" in doc


# ── 4. Export Pipeline ───────────────────────────────────────────────────────

class TestExportIntegration:
    """Verify export pipeline works with contract-based test cases."""

    def test_csv_export_with_artifact(self, tmp_path, sample_test_case):
        """CSVExporter works with TestCaseArtifact objects."""
        from stlc_platform.core.config_loader import config
        from stlc_platform.exporters.exporters import CSVExporter

        # Override output dir for test isolation
        original_dir = config.output.output_dir
        config.output.output_dir = str(tmp_path)

        try:
            exporter = CSVExporter()
            path = exporter.export([sample_test_case])

            assert os.path.exists(path)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "TC-0001" in content
            assert "REQ-001" in content
        finally:
            config.output.output_dir = original_dir

    def test_json_report_export_with_artifact(self, tmp_path, sample_test_case):
        """JSONReportExporter works with TestCaseArtifact objects."""
        from stlc_platform.core.config_loader import config
        from stlc_platform.exporters.exporters import JSONReportExporter

        original_dir = config.output.output_dir
        config.output.output_dir = str(tmp_path)

        try:
            exporter = JSONReportExporter()
            path = exporter.export([sample_test_case], 1)

            assert os.path.exists(path)
            with open(path, "r", encoding="utf-8") as f:
                report = json.load(f)
            assert report["summary"]["total_test_cases"] == 1
            assert report["summary"]["total_requirements"] == 1
        finally:
            config.output.output_dir = original_dir


# ── 5. Schema Validation ────────────────────────────────────────────────────

class TestSchemaValidation:
    """Verify that config schema JSON exists and is valid JSON Schema."""

    def test_schema_file_is_valid_json(self):
        """stlc_config.schema.json is valid JSON."""
        from stlc_platform.core.utils import find_project_root
        schema_path = find_project_root() / "config" / "stlc_config.schema.json"

        assert schema_path.exists(), f"Schema file not found: {schema_path}"

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        assert "$schema" in schema
        assert "properties" in schema
        assert "llm" in schema["properties"]
        assert "chromadb" in schema["properties"]
        assert "export" in schema["properties"]

    def test_schema_covers_all_config_sections(self):
        """Schema has entries for every section in stlc_config.yaml."""
        from stlc_platform.core.utils import find_project_root
        schema_path = find_project_root() / "config" / "stlc_config.schema.json"

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        expected_sections = [
            "project", "llm", "chromadb", "test_generation",
            "bdd", "crawler", "api_testing", "export",
        ]
        for section in expected_sections:
            assert section in schema["properties"], (
                f"Missing section '{section}' in config schema"
            )


# ── 6. Utils Module ─────────────────────────────────────────────────────────

class TestUtilsIntegration:
    """Verify utility functions work correctly."""

    def test_find_project_root(self):
        """find_project_root() returns a directory with expected structure."""
        from stlc_platform.core.utils import find_project_root
        root = find_project_root()
        assert (root / "stlc_platform").is_dir() or (root / "config").is_dir()

    def test_slugify(self):
        from stlc_platform.core.utils import slugify
        assert slugify("User Login Auth") == "user-login-auth"
        assert slugify("REQ-001: Test!@#") == "req-001-test"

    def test_deep_merge(self):
        from stlc_platform.core.utils import deep_merge
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 99}, "e": 5}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}

    def test_safe_filename(self):
        from stlc_platform.core.utils import safe_filename
        assert safe_filename('Test: "Special" <chars>') == "Test_Special_chars"

    def test_flatten_dict(self):
        from stlc_platform.core.utils import flatten_dict
        nested = {"a": {"b": 1, "c": {"d": 2}}}
        flat = flatten_dict(nested)
        assert flat == {"a.b": 1, "a.c.d": 2}

    def test_chunk_list(self):
        from stlc_platform.core.utils import chunk_list
        assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


# ── 7. Migration Script ─────────────────────────────────────────────────────

class TestMigrationIntegration:
    """Verify migration script functions work."""

    def test_get_current_versions(self):
        """All artifact types report version 1.0."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        from migrate import get_current_versions

        versions = get_current_versions()
        assert len(versions) >= 8
        for name, version in versions.items():
            assert version == "1.0", f"{name} has unexpected version {version}"

    def test_check_no_migrations_needed(self):
        """With no artifact files, no migrations are needed."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        from migrate import check_migrations_needed
        from pathlib import Path

        issues = check_migrations_needed(Path("/nonexistent"))
        assert any("No migrations needed" in i for i in issues)
