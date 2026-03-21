"""Tests for Project Scaffolder."""

import pytest
from pathlib import Path

from stlc_platform.core.contracts import (
    FeatureFileArtifact,
    StepDefinitionArtifact,
)
from stlc_platform.agents.bdd_agent.pom_generator import PageObjectStub
from stlc_platform.agents.bdd_agent.scaffolder import (
    ProjectScaffolder,
    ScaffoldedProject,
)


@pytest.fixture
def features():
    return [
        FeatureFileArtifact(
            req_id="REQ-001",
            filename="login.feature",
            content="Feature: Login\n  Scenario: Valid login\n    Given user on login\n    When enters credentials\n    Then dashboard shown",
            scenario_count=1,
        ),
        FeatureFileArtifact(
            req_id="REQ-002",
            filename="search.feature",
            content="Feature: Search\n  Scenario: Search products\n    Given user on dashboard\n    When searches for laptop\n    Then results displayed",
            scenario_count=1,
        ),
    ]


@pytest.fixture
def step_defs():
    return [
        StepDefinitionArtifact(
            language="python",
            framework="behave",
            filename="steps.py",
            content="from behave import given, when, then\n\n@given('user on login')\ndef step_user_login(context):\n    pass\n",
            step_count=3,
        ),
    ]


@pytest.fixture
def pom_stubs():
    return [
        PageObjectStub(
            page_name="Login Page",
            class_name="LoginPage",
            filename="login_page.py",
            language="python",
            content="class LoginPage:\n    pass\n",
            locator_count=2,
            action_count=1,
        ),
    ]


class TestBehaveScaffold:
    def test_creates_project(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert isinstance(project, ScaffoldedProject)
        assert project.project_name == "my_tests"
        assert project.framework == "behave"
        assert project.language == "python"

    def test_has_feature_files(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "features/login.feature" in project.files
        assert "features/search.feature" in project.files

    def test_has_step_definitions(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "features/steps/steps.py" in project.files

    def test_has_behave_ini(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "behave.ini" in project.files
        assert "[behave]" in project.files["behave.ini"]

    def test_has_requirements_txt(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "requirements.txt" in project.files
        assert "behave" in project.files["requirements.txt"]

    def test_has_environment_py(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "features/environment.py" in project.files
        assert "before_all" in project.files["features/environment.py"]

    def test_has_readme(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert "README.md" in project.files
        assert "behave" in project.files["README.md"]

    def test_includes_pom_stubs(self, features, step_defs, pom_stubs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold(
            "my_tests", features, step_defs, pom_stubs=pom_stubs
        )
        assert "pages/login_page.py" in project.files
        assert "pages/__init__.py" in project.files

    def test_file_count_accurate(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("my_tests", features, step_defs)
        assert project.file_count == len(project.files)


class TestPytestBDDScaffold:
    def test_creates_project(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="pytest_bdd")
        project = scaffolder.scaffold("pytest_tests", features, step_defs)
        assert project.framework == "pytest_bdd"
        assert project.language == "python"

    def test_has_pytest_ini(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="pytest_bdd")
        project = scaffolder.scaffold("pytest_tests", features, step_defs)
        assert "pytest.ini" in project.files
        assert "[pytest]" in project.files["pytest.ini"]

    def test_has_conftest(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="pytest_bdd")
        project = scaffolder.scaffold("pytest_tests", features, step_defs)
        assert "tests/conftest.py" in project.files
        assert "base_url" in project.files["tests/conftest.py"]

    def test_step_defs_in_tests_dir(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="pytest_bdd")
        project = scaffolder.scaffold("pytest_tests", features, step_defs)
        assert "tests/steps.py" in project.files


class TestCucumberJavaScaffold:
    def test_creates_project(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumber_java")
        project = scaffolder.scaffold("java_tests", features, step_defs)
        assert project.framework == "cucumber_java"
        assert project.language == "java"

    def test_has_pom_xml(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumber_java")
        project = scaffolder.scaffold("java_tests", features, step_defs)
        assert "pom.xml" in project.files
        content = project.files["pom.xml"]
        assert "cucumber-java" in content
        assert "junit-jupiter" in content

    def test_has_runner_class(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumber_java")
        project = scaffolder.scaffold("java_tests", features, step_defs)
        runner_path = "src/test/java/runners/RunCucumberTest.java"
        assert runner_path in project.files
        assert "@Suite" in project.files[runner_path]

    def test_features_in_resources(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumber_java")
        project = scaffolder.scaffold("java_tests", features, step_defs)
        assert "src/test/resources/features/login.feature" in project.files

    def test_steps_in_java_dir(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumber_java")
        project = scaffolder.scaffold("java_tests", features, step_defs)
        assert "src/test/java/steps/steps.py" in project.files


class TestCucumberJSScaffold:
    def test_creates_project(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumberjs")
        project = scaffolder.scaffold("js_tests", features, step_defs)
        assert project.framework == "cucumberjs"
        assert project.language == "javascript"

    def test_has_package_json(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumberjs")
        project = scaffolder.scaffold("js_tests", features, step_defs)
        assert "package.json" in project.files
        content = project.files["package.json"]
        assert "@cucumber/cucumber" in content

    def test_has_cucumber_config(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumberjs")
        project = scaffolder.scaffold("js_tests", features, step_defs)
        assert "cucumber.js" in project.files

    def test_steps_in_step_definitions_dir(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="cucumberjs")
        project = scaffolder.scaffold("js_tests", features, step_defs)
        assert "step_definitions/steps.py" in project.files


class TestWriteToDisk:
    def test_writes_project_to_disk(self, features, step_defs, tmp_path):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold("disk_test", features, step_defs)
        project_root = project.write_to_disk(tmp_path)
        assert project_root.exists()
        assert (project_root / "features" / "login.feature").exists()
        assert (project_root / "behave.ini").exists()
        assert (project_root / "README.md").exists()


class TestEdgeCases:
    def test_unsupported_framework_raises(self):
        with pytest.raises(ValueError, match="Unsupported framework"):
            ProjectScaffolder(framework="rspec")

    def test_custom_base_url(self, features, step_defs):
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold(
            "my_tests", features, step_defs,
            base_url="https://app.example.com"
        )
        env_content = project.files["features/environment.py"]
        assert "https://app.example.com" in env_content
