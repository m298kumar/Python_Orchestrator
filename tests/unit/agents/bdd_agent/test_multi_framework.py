"""Tests for Java Cucumber and JavaScript Cucumber.js step definition generation."""

import pytest
from stlc_platform.agents.bdd_agent.step_parser import ParameterizedStep
from stlc_platform.agents.bdd_agent.step_def_generator import StepDefinitionGenerator


@pytest.fixture
def cucumber_java_gen():
    return StepDefinitionGenerator(framework="cucumber_java", language="java")


@pytest.fixture
def cucumberjs_gen():
    return StepDefinitionGenerator(
        framework="cucumberjs", language="javascript"
    )


def _make_steps() -> list:
    return [
        ParameterizedStep(keyword="given", pattern="A user on the page", params=[]),
        ParameterizedStep(keyword="when", pattern="The user clicks login", params=[]),
        ParameterizedStep(keyword="then", pattern="The dashboard is shown", params=[]),
    ]


def _make_param_steps() -> list:
    return [
        ParameterizedStep(
            keyword="when",
            pattern="The user enters {value} in {field}",
            params=["value", "field"],
        ),
    ]


class TestCucumberJavaGeneration:
    def test_generates_java_step_definitions(self, cucumber_java_gen):
        result = cucumber_java_gen.generate(_make_steps())
        assert len(result) == 1
        assert result[0].framework == "cucumber_java"
        assert result[0].language == "java"
        assert result[0].filename == "StepDefinitions.java"
        assert result[0].step_count == 3

    def test_content_has_java_annotations(self, cucumber_java_gen):
        result = cucumber_java_gen.generate(_make_steps())
        content = result[0].content
        assert "@Given(" in content
        assert "@When(" in content
        assert "@Then(" in content
        assert "public void" in content
        assert "PendingException" in content

    def test_content_has_java_imports(self, cucumber_java_gen):
        result = cucumber_java_gen.generate(_make_steps())
        content = result[0].content
        assert "import io.cucumber.java.en.Given;" in content
        assert "import io.cucumber.java.en.When;" in content
        assert "import io.cucumber.java.en.Then;" in content
        assert "package steps;" in content

    def test_parameterized_steps_use_string_type(self, cucumber_java_gen):
        result = cucumber_java_gen.generate(_make_param_steps())
        content = result[0].content
        # Cucumber expressions: {string} instead of {param}
        assert "{string}" in content
        assert "String value" in content or "String param" in content

    def test_automation_lib_selenium_import(self):
        gen = StepDefinitionGenerator(
            framework="cucumber_java",
            language="java",
            automation_lib="selenium",
        )
        result = gen.generate(_make_steps())
        content = result[0].content
        assert "selenium" in content.lower()

    def test_automation_lib_playwright_import(self):
        gen = StepDefinitionGenerator(
            framework="cucumber_java",
            language="java",
            automation_lib="playwright",
        )
        result = gen.generate(_make_steps())
        content = result[0].content
        assert "playwright" in content.lower()


class TestCucumberJSGeneration:
    def test_generates_js_step_definitions(self, cucumberjs_gen):
        result = cucumberjs_gen.generate(_make_steps())
        assert len(result) == 1
        assert result[0].framework == "cucumberjs"
        assert result[0].language == "javascript"
        assert result[0].filename == "steps.js"
        assert result[0].step_count == 3

    def test_content_has_js_functions(self, cucumberjs_gen):
        result = cucumberjs_gen.generate(_make_steps())
        content = result[0].content
        assert "Given(" in content
        assert "When(" in content
        assert "Then(" in content
        assert "async function" in content
        assert "throw new Error" in content

    def test_content_has_js_imports(self, cucumberjs_gen):
        result = cucumberjs_gen.generate(_make_steps())
        content = result[0].content
        assert "require('@cucumber/cucumber')" in content

    def test_parameterized_steps_use_string(self, cucumberjs_gen):
        result = cucumberjs_gen.generate(_make_param_steps())
        content = result[0].content
        assert "{string}" in content

    def test_automation_lib_playwright_import(self):
        gen = StepDefinitionGenerator(
            framework="cucumberjs",
            language="javascript",
            automation_lib="playwright",
        )
        result = gen.generate(_make_steps())
        content = result[0].content
        assert "playwright" in content.lower()


class TestFrameworkRegistry:
    def test_four_frameworks_supported(self):
        assert len(StepDefinitionGenerator.SUPPORTED_FRAMEWORKS) == 4

    def test_behave_is_python(self):
        assert StepDefinitionGenerator.SUPPORTED_FRAMEWORKS["behave"] == "python"

    def test_pytest_bdd_is_python(self):
        assert StepDefinitionGenerator.SUPPORTED_FRAMEWORKS["pytest_bdd"] == "python"

    def test_cucumber_java_is_java(self):
        assert StepDefinitionGenerator.SUPPORTED_FRAMEWORKS["cucumber_java"] == "java"

    def test_cucumberjs_is_javascript(self):
        assert StepDefinitionGenerator.SUPPORTED_FRAMEWORKS["cucumberjs"] == "javascript"

    def test_unsupported_framework_raises(self):
        with pytest.raises(ValueError, match="Unsupported framework"):
            StepDefinitionGenerator(framework="xunit")

    def test_template_map_has_all_frameworks(self):
        for fw in StepDefinitionGenerator.SUPPORTED_FRAMEWORKS:
            assert fw in StepDefinitionGenerator._TEMPLATE_MAP

    def test_filename_map_has_all_frameworks(self):
        for fw in StepDefinitionGenerator.SUPPORTED_FRAMEWORKS:
            assert fw in StepDefinitionGenerator._FILENAME_MAP
