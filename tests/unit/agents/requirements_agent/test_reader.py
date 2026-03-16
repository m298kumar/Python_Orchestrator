"""
Tests for the requirements reader.
"""

import json
import os
import tempfile

import pytest

from stlc_platform.agents.requirements_agent.reader import (
    Requirement,
    RequirementsReader,
)


class TestRequirement:
    def test_to_dict(self):
        r = Requirement(
            req_id="REQ-001",
            title="Test",
            description="Desc",
            acceptance_criteria=["AC1"],
        )
        d = r.to_dict()
        assert d["req_id"] == "REQ-001"
        assert d["acceptance_criteria"] == ["AC1"]

    def test_to_chroma_document(self):
        r = Requirement(
            req_id="REQ-001",
            title="Test",
            description="Desc",
            acceptance_criteria=["AC1"],
        )
        doc = r.to_chroma_document()
        assert "REQ-001" in doc
        assert "AC1" in doc


class TestRequirementsReader:
    def test_read_txt(self, tmp_path):
        txt_file = tmp_path / "reqs.txt"
        txt_file.write_text(
            "REQ-001 User Login\nUsers must log in with valid credentials\n"
            "---\n"
            "REQ-002 Password Reset\nUsers can reset their password via email\n"
        )
        reader = RequirementsReader()
        reqs = reader.read(str(txt_file))
        assert len(reqs) >= 1

    def test_read_csv(self, tmp_path):
        csv_file = tmp_path / "reqs.csv"
        csv_file.write_text(
            "id,title,description,priority,category,acceptance_criteria\n"
            "REQ-001,Login,Users must log in,High,Auth,AC1;AC2\n"
            "REQ-002,Reset,Users can reset password,Medium,Auth,AC3\n"
        )
        reader = RequirementsReader()
        reqs = reader.read(str(csv_file))
        assert len(reqs) == 2
        assert reqs[0].req_id == "REQ-001"
        assert reqs[0].acceptance_criteria == ["AC1", "AC2"]

    def test_read_json(self, tmp_path):
        json_file = tmp_path / "reqs.json"
        data = {
            "requirements": [
                {
                    "id": "REQ-001",
                    "title": "Login",
                    "description": "Users must log in",
                    "acceptance_criteria": ["AC1"],
                }
            ]
        }
        json_file.write_text(json.dumps(data))
        reader = RequirementsReader()
        reqs = reader.read(str(json_file))
        assert len(reqs) == 1
        assert reqs[0].acceptance_criteria == ["AC1"]

    def test_file_not_found(self):
        reader = RequirementsReader()
        with pytest.raises(FileNotFoundError):
            reader.read("/nonexistent/file.csv")

    def test_unsupported_format(self, tmp_path):
        bad_file = tmp_path / "reqs.xyz"
        bad_file.write_text("data")
        reader = RequirementsReader()
        with pytest.raises(ValueError, match="Unsupported format"):
            reader.read(str(bad_file))
