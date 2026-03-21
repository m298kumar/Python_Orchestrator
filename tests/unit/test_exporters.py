"""Unit tests for CSV, Zephyr Scale, and JSON Report exporters."""

import csv
import json
import os
from unittest.mock import patch

import pytest

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.exporters.exporters import (
    CSVExporter,
    JSONReportExporter,
    ZephyrScaleExporter,
)


@pytest.fixture
def sample_test_cases():
    return [
        TestCaseArtifact(
            tc_id="TC-001",
            req_id="REQ-001",
            title="Verify login with valid credentials",
            description="Test that a user can log in with correct username and password",
            preconditions="User account exists",
            test_type="positive",
            priority="High",
            category="Security",
            component="Login Screen",
            expected_outcome="User is redirected to dashboard",
            given="User is on login page",
            when="User enters valid credentials and clicks Login",
            then="User sees the dashboard",
            tags=["login", "smoke"],
            estimated_duration="3",
            steps=[
                TestStepArtifact(action="Navigate to login page", expected_result="Login page loads"),
                TestStepArtifact(action="Enter username 'admin'", expected_result="Field populated"),
                TestStepArtifact(action="Click Login button", expected_result="Dashboard appears"),
            ],
        ),
        TestCaseArtifact(
            tc_id="TC-002",
            req_id="REQ-001",
            title="Verify login with invalid password",
            description="Test login fails with wrong password",
            preconditions="User account exists",
            test_type="negative",
            priority="Medium",
            category="Security",
            component="Login Screen",
            expected_outcome="Error message displayed",
            given="User is on login page",
            when="User enters invalid password",
            then="Error message is shown",
            tags=["login", "security"],
            estimated_duration="2",
            steps=[
                TestStepArtifact(action="Enter wrong password", expected_result="Error shown"),
            ],
        ),
    ]


@pytest.fixture
def mock_output_dir(tmp_path):
    """Patch config.output.output_dir to use a temp directory."""
    with patch("stlc_platform.exporters.exporters.config") as mock_cfg:
        mock_cfg.output.output_dir = str(tmp_path)
        mock_cfg.output.csv_filename = "test_cases.csv"
        mock_cfg.output.zephyr_filename = "zephyr_export.csv"
        mock_cfg.output.report_filename = "report.json"
        mock_cfg.zephyr.default_labels = "automated,regression"
        mock_cfg.zephyr.folder_prefix = "/Tests"
        mock_cfg.zephyr.default_status = "Draft"
        mock_cfg.zephyr.default_component = "General"
        mock_cfg.ollama.model = "test-model"
        yield tmp_path


class TestCSVExporter:
    def test_creates_csv_file(self, sample_test_cases, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export(sample_test_cases)
        assert os.path.exists(path)
        assert path.endswith(".csv")

    def test_csv_has_correct_headers(self, sample_test_cases, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "TC ID" in reader.fieldnames
            assert "Title" in reader.fieldnames
            assert "Given" in reader.fieldnames
            assert "Steps" in reader.fieldnames

    def test_csv_has_correct_row_count(self, sample_test_cases, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2

    def test_csv_contains_step_data(self, sample_test_cases, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first_row = next(reader)
        assert "Navigate to login page" in first_row["Steps"]
        assert "Login page loads" in first_row["Steps"]

    def test_csv_custom_filename(self, sample_test_cases, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export(sample_test_cases, filename="custom.csv")
        assert path.endswith("custom.csv")

    def test_csv_empty_test_cases(self, mock_output_dir):
        exporter = CSVExporter()
        path = exporter.export([])
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 0

    def test_format_steps_no_steps(self, mock_output_dir):
        exporter = CSVExporter()
        tc = TestCaseArtifact(
            tc_id="TC-X", req_id="REQ-X", title="No steps",
            description="d", preconditions="p", test_type="positive",
            priority="High",
        )
        assert exporter._format_steps(tc) == ""


class TestZephyrScaleExporter:
    def test_creates_zephyr_csv(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        assert os.path.exists(path)

    def test_zephyr_has_correct_headers(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert "Name" in reader.fieldnames
            assert "Folder" in reader.fieldnames
            assert "Requirement" in reader.fieldnames

    def test_zephyr_priority_mapping(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows[0]["Priority"] == "High"
        assert rows[1]["Priority"] == "Normal"

    def test_zephyr_folder_structure(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(reader)
        assert first["Folder"] == "/Tests/REQ-001"

    def test_zephyr_labels_include_tags(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(reader)
        assert "login" in first["Labels"]
        assert "smoke" in first["Labels"]

    def test_zephyr_gwt_in_plain_text(self, sample_test_cases, mock_output_dir):
        exporter = ZephyrScaleExporter()
        path = exporter.export(sample_test_cases)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            first = next(reader)
        plain = first["Test Script (Plain Text)"]
        assert "Given" in plain
        assert "When" in plain
        assert "Then" in plain


class TestJSONReportExporter:
    def test_creates_json_file(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        assert os.path.exists(path)
        assert path.endswith(".json")

    def test_json_has_summary(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report["summary"]["total_test_cases"] == 2
        assert report["summary"]["total_requirements"] == 1
        assert report["summary"]["avg_tests_per_requirement"] == 2.0

    def test_json_breakdown_by_type(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report["breakdown_by_type"]["positive"] == 1
        assert report["breakdown_by_type"]["negative"] == 1

    def test_json_breakdown_by_priority(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report["breakdown_by_priority"]["High"] == 1
        assert report["breakdown_by_priority"]["Medium"] == 1

    def test_json_test_case_entries(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert len(report["test_cases"]) == 2
        assert report["test_cases"][0]["tc_id"] == "TC-001"
        assert report["test_cases"][0]["steps_count"] == 3

    def test_json_model_used(self, sample_test_cases, mock_output_dir):
        exporter = JSONReportExporter()
        path = exporter.export(sample_test_cases, requirements_count=1)
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report["model_used"] == "test-model"
