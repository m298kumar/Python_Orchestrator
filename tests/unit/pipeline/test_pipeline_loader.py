"""Unit tests for the Pipeline Loader."""

from __future__ import annotations

import pytest

from stlc_platform.pipeline.pipeline_loader import (
    load_pipeline,
    load_pipeline_from_dict,
)


class TestLoadFromDict:
    def test_load_valid_pipeline(self):
        data = {
            "pipeline": "test_pipeline",
            "stages": [
                {"id": "s1", "agent": "agent_a", "output": ["result"]},
                {
                    "id": "s2",
                    "agent": "agent_b",
                    "depends_on": ["s1"],
                    "input": {"data": "$s1.result"},
                },
            ],
        }
        dag = load_pipeline_from_dict(data)
        assert dag.pipeline_name == "test_pipeline"
        assert dag.stage_ids == ["s1", "s2"]

    def test_config_refs_preserved(self):
        data = {
            "pipeline": "p",
            "stages": [
                {
                    "id": "s1",
                    "agent": "a",
                    "input": {"url": "$config.app_url"},
                },
            ],
        }
        dag = load_pipeline_from_dict(data)
        stage = dag.get_stage("s1")
        assert stage.input_map["url"] == "$config.app_url"

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="missing required 'id'"):
            load_pipeline_from_dict({
                "stages": [{"agent": "a"}],
            })

    def test_missing_agent_raises(self):
        with pytest.raises(ValueError, match="missing required 'agent'"):
            load_pipeline_from_dict({
                "stages": [{"id": "s1"}],
            })

    def test_empty_stages_raises(self):
        with pytest.raises(ValueError, match="at least one stage"):
            load_pipeline_from_dict({"stages": []})


class TestLoadFromFile:
    def test_load_full_stlc_yaml(self):
        dag = load_pipeline("config/pipelines/full_stlc.yaml")
        assert dag.pipeline_name == "full_stlc"
        assert len(dag.stage_ids) >= 3

    def test_load_api_test_only_yaml(self):
        dag = load_pipeline("config/pipelines/api_test_only.yaml")
        assert dag.pipeline_name == "api_test_only"
        assert len(dag.stage_ids) == 1

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_pipeline("nonexistent.yaml")
