"""Unit tests for the STLC CLI entry point.

Tests Click commands using CliRunner with mocked dependencies.
"""


import pytest
from click.testing import CliRunner

from stlc_platform.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestMainGroup:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "STLC Automation Platform" in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "stlc" in result.output


class TestRunCommand:
    def test_run_without_args_fails(self, runner):
        result = runner.invoke(main, ["run"])
        assert result.exit_code != 0
        assert "Specify --pipeline or --agent" in result.output

    def test_run_agent_not_found(self, runner):
        result = runner.invoke(main, ["run", "--agent", "nonexistent_agent"])
        assert result.exit_code != 0
        assert "Error" in result.output

    def test_run_agent_missing_input_file(self, runner, tmp_path):
        result = runner.invoke(main, [
            "run", "--agent", "bdd_agent",
            "--input", str(tmp_path / "no_such_file.json"),
        ])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_run_pipeline_not_found(self, runner):
        result = runner.invoke(main, [
            "run", "--pipeline", "no_such_pipeline.yaml",
        ])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestValidateCommand:
    def test_validate_help(self, runner):
        result = runner.invoke(main, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--stage" in result.output


class TestAgentsCommand:
    def test_agents_list(self, runner):
        result = runner.invoke(main, ["agents", "list"])
        assert result.exit_code == 0
        assert "agents registered" in result.output
        # Should show all 4 built-in agents
        assert "requirements_agent" in result.output or "test_generation" in result.output

    def test_agents_list_has_table_header(self, runner):
        result = runner.invoke(main, ["agents", "list"])
        assert "ID" in result.output
        assert "Version" in result.output


class TestFeedbackCommand:
    def test_feedback_add(self, runner, tmp_path):
        result = runner.invoke(main, [
            "feedback", "add",
            "--agent", "bdd_agent",
            "--type", "correction",
            "--message", "Use page objects for all selectors",
            "--output", str(tmp_path / "feedback"),
        ])
        assert result.exit_code == 0
        assert "Feedback stored" in result.output

    def test_feedback_list_empty(self, runner, tmp_path):
        result = runner.invoke(main, [
            "feedback", "list",
            "--output", str(tmp_path / "feedback"),
        ])
        assert result.exit_code == 0
        assert "No feedback entries found" in result.output

    def test_feedback_add_then_list(self, runner, tmp_path):
        fb_dir = str(tmp_path / "feedback")
        # Add
        runner.invoke(main, [
            "feedback", "add",
            "--agent", "bdd_agent",
            "--type", "preference",
            "--message", "Prefer Playwright over Selenium",
            "--output", fb_dir,
        ])
        # List
        result = runner.invoke(main, [
            "feedback", "list",
            "--agent", "bdd_agent",
            "--output", fb_dir,
        ])
        assert result.exit_code == 0
        assert "Playwright" in result.output

    def test_feedback_invalid_type(self, runner, tmp_path):
        result = runner.invoke(main, [
            "feedback", "add",
            "--agent", "bdd_agent",
            "--type", "invalid_type",
            "--message", "test",
            "--output", str(tmp_path / "feedback"),
        ])
        assert result.exit_code != 0
