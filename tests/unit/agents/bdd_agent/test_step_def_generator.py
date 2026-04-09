"""Tests for StepDefinitionGenerator."""

import ast

import pytest
from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator
from stlc_platform.agents.bdd_agent.step_parser import ParameterizedStep
from stlc_platform.core.contracts import FeatureFileArtifact


@pytest.fixture
def behave_gen():
    return StepDefinitionGenerator(framework="behave")


@pytest.fixture
def pytest_bdd_gen():
    return StepDefinitionGenerator(framework="pytest_bdd")


def _make_steps() -> list:
    return [
        ParameterizedStep(keyword="given", pattern="A user on the page", params=[]),
        ParameterizedStep(keyword="when", pattern="The user clicks the button", params=[]),
        ParameterizedStep(keyword="then", pattern="The result is displayed", params=[]),
    ]


def _make_param_steps() -> list:
    return [
        ParameterizedStep(
            keyword="when",
            pattern="The user enters {value} in {field}",
            params=["value", "field"],
        ),
    ]


class TestBehaveGeneration:
    def test_generates_step_definitions(self, behave_gen):
        result = behave_gen.generate(_make_steps())
        assert len(result) == 1
        assert result[0].framework == "behave"
        assert result[0].language == "python"
        assert result[0].step_count == 3

    def test_content_has_decorators(self, behave_gen):
        result = behave_gen.generate(_make_steps())
        content = result[0].content
        assert "@given(" in content
        assert "@when(" in content
        assert "@then(" in content

    def test_content_has_not_implemented(self, behave_gen):
        result = behave_gen.generate(_make_steps())
        assert "NotImplementedError" in result[0].content

    def test_content_is_valid_python(self, behave_gen):
        result = behave_gen.generate(_make_steps())
        # Should parse without SyntaxError
        ast.parse(result[0].content)

    def test_parameterized_steps_have_args(self, behave_gen):
        result = behave_gen.generate(_make_param_steps())
        content = result[0].content
        assert "value" in content
        assert "field" in content

    def test_playwright_import_comment(self, behave_gen):
        result = behave_gen.generate(_make_steps())
        assert "playwright" in result[0].content.lower()

    def test_selenium_import_when_configured(self):
        gen = StepDefinitionGenerator(framework="behave", automation_lib="selenium")
        result = gen.generate(_make_steps())
        assert "selenium" in result[0].content.lower()


class TestPytestBddGeneration:
    def test_generates_step_definitions(self, pytest_bdd_gen):
        features = [
            FeatureFileArtifact(
                req_id="REQ-001", filename="test.feature", content="", scenario_count=1
            )
        ]
        result = pytest_bdd_gen.generate(_make_steps(), features)
        assert len(result) == 1
        assert result[0].framework == "pytest_bdd"
        assert result[0].filename == "test_steps.py"

    def test_content_has_parsers_for_params(self, pytest_bdd_gen):
        result = pytest_bdd_gen.generate(_make_param_steps())
        content = result[0].content
        assert "parsers.parse" in content

    def test_content_is_valid_python(self, pytest_bdd_gen):
        result = pytest_bdd_gen.generate(_make_steps())
        ast.parse(result[0].content)


class TestFunctionNaming:
    def test_valid_python_identifiers(self, behave_gen):
        steps = [
            ParameterizedStep(
                keyword="given",
                pattern="A user with a valid email address",
                params=[],
            ),
        ]
        result = behave_gen.generate(steps)
        content = result[0].content
        # Should be valid Python
        tree = ast.parse(content)
        func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        for name in func_names:
            assert name.isidentifier(), f"'{name}' is not a valid identifier"

    def test_duplicate_names_get_suffix(self, behave_gen):
        steps = [
            ParameterizedStep(keyword="given", pattern="A user", params=[]),
            ParameterizedStep(keyword="when", pattern="A user", params=[]),
        ]
        result = behave_gen.generate(steps)
        content = result[0].content
        tree = ast.parse(content)
        func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        # All names should be unique
        assert len(func_names) == len(set(func_names))


class TestUnsupportedFramework:
    def test_raises_for_unknown_framework(self):
        with pytest.raises(ValueError, match="Unsupported framework"):
            StepDefinitionGenerator(framework="rspec")
