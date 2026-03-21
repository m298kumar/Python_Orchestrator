"""
Project Scaffolder
==================
Assembles generated BDD artifacts (feature files, step definitions, POM stubs)
into a complete, runnable project directory with dependency files, runner
configuration, and a README.

Supports:
  - Python Behave
  - Python Pytest-BDD
  - Java Cucumber
  - JavaScript Cucumber.js
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from stlc_platform.core.contracts import (
    FeatureFileArtifact,
    StepDefinitionArtifact,
)
from stlc_platform.agents.bdd_agent.pom_generator import PageObjectStub


@dataclass
class ScaffoldedProject:
    """Result of project scaffolding."""

    project_name: str
    root_dir: str
    files: Dict[str, str] = field(default_factory=dict)  # relative path -> content
    framework: str = ""
    language: str = ""
    file_count: int = 0

    def write_to_disk(self, base_dir: Path) -> Path:
        """Write all project files to disk under base_dir/project_name."""
        project_root = base_dir / self.project_name
        for rel_path, content in self.files.items():
            file_path = project_root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        return project_root


# -- Framework-specific project templates --

_BEHAVE_INI = """\
[behave]
paths = features
format = pretty
color = true
"""

_BEHAVE_REQUIREMENTS = """\
behave>=1.2.6
# Uncomment the automation library you need:
# playwright>=1.40.0
# selenium>=4.15.0
"""

_PYTEST_BDD_REQUIREMENTS = """\
pytest>=8.0.0
pytest-bdd>=7.0.0
# Uncomment the automation library you need:
# playwright>=1.40.0
# selenium>=4.15.0
"""

_PYTEST_INI = """\
[pytest]
bdd_features_base_dir = features/
markers =
    bdd: BDD scenario tests
"""

_CUCUMBER_JAVA_POM = """\
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.stlc.tests</groupId>
    <artifactId>{project_name}</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <cucumber.version>7.15.0</cucumber.version>
        <junit.version>5.10.1</junit.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.cucumber</groupId>
            <artifactId>cucumber-java</artifactId>
            <version>${{cucumber.version}}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.cucumber</groupId>
            <artifactId>cucumber-junit-platform-engine</artifactId>
            <version>${{cucumber.version}}</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${{junit.version}}</version>
            <scope>test</scope>
        </dependency>
        <!-- Uncomment for Selenium -->
        <!--
        <dependency>
            <groupId>org.seleniumhq.selenium</groupId>
            <artifactId>selenium-java</artifactId>
            <version>4.15.0</version>
        </dependency>
        -->
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.3</version>
            </plugin>
        </plugins>
    </build>
</project>
"""

_CUCUMBER_JAVA_RUNNER = """\
package runners;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

import static io.cucumber.junit.platform.engine.Constants.*;

@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "steps")
@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME, value = "pretty")
public class RunCucumberTest {
}
"""

_CUCUMBERJS_PACKAGE_JSON = """\
{{
  "name": "{project_name}",
  "version": "1.0.0",
  "description": "Auto-generated BDD test project",
  "scripts": {{
    "test": "npx cucumber-js"
  }},
  "devDependencies": {{
    "@cucumber/cucumber": "^10.3.0"
  }}
}}
"""

_CUCUMBERJS_CONFIG = """\
module.exports = {
    default: {
        paths: ['features/**/*.feature'],
        require: ['step_definitions/**/*.js'],
        format: ['progress-bar', 'html:reports/cucumber-report.html'],
        publishQuiet: true,
    },
};
"""


class ProjectScaffolder:
    """
    Assembles BDD artifacts into a complete runnable project directory.

    Usage:
        scaffolder = ProjectScaffolder(framework="behave")
        project = scaffolder.scaffold(
            project_name="my_bdd_tests",
            features=feature_artifacts,
            step_defs=step_def_artifacts,
            pom_stubs=pom_stubs,         # optional
        )
        # Write to disk
        project.write_to_disk(Path("./output"))
    """

    _FRAMEWORK_CONFIGS = {
        "behave": {
            "language": "python",
            "features_dir": "features",
            "steps_dir": "features/steps",
            "pages_dir": "pages",
        },
        "pytest_bdd": {
            "language": "python",
            "features_dir": "features",
            "steps_dir": "tests",
            "pages_dir": "pages",
        },
        "cucumber_java": {
            "language": "java",
            "features_dir": "src/test/resources/features",
            "steps_dir": "src/test/java/steps",
            "pages_dir": "src/test/java/pages",
        },
        "cucumberjs": {
            "language": "javascript",
            "features_dir": "features",
            "steps_dir": "step_definitions",
            "pages_dir": "pages",
        },
    }

    def __init__(self, framework: str = "behave"):
        if framework not in self._FRAMEWORK_CONFIGS:
            raise ValueError(
                f"Unsupported framework: '{framework}'. "
                f"Supported: {list(self._FRAMEWORK_CONFIGS.keys())}"
            )
        self.framework = framework
        self._config = self._FRAMEWORK_CONFIGS[framework]

    def scaffold(
        self,
        project_name: str,
        features: List[FeatureFileArtifact],
        step_defs: List[StepDefinitionArtifact],
        pom_stubs: Optional[List[PageObjectStub]] = None,
        base_url: str = "http://localhost:8080",
    ) -> ScaffoldedProject:
        """
        Assemble all artifacts into a project structure.

        Returns a ScaffoldedProject with all files as a dict.
        """
        files: Dict[str, str] = {}

        # 1. Feature files
        features_dir = self._config["features_dir"]
        for ff in features:
            path = f"{features_dir}/{ff.filename}"
            files[path] = ff.content

        # 2. Step definitions
        steps_dir = self._config["steps_dir"]
        for sd in step_defs:
            path = f"{steps_dir}/{sd.filename}"
            files[path] = sd.content

        # 3. POM stubs (if provided)
        if pom_stubs:
            pages_dir = self._config["pages_dir"]
            for pom in pom_stubs:
                path = f"{pages_dir}/{pom.filename}"
                files[path] = pom.content
            # Add __init__.py for Python pages package
            if self._config["language"] == "python":
                files[f"{pages_dir}/__init__.py"] = (
                    '"""Page Object Models — auto-generated."""\n'
                )

        # 4. Framework-specific config & deps
        framework_files = self._generate_framework_files(
            project_name, base_url
        )
        files.update(framework_files)

        # 5. README
        files["README.md"] = self._generate_readme(
            project_name, features, step_defs, pom_stubs
        )

        return ScaffoldedProject(
            project_name=project_name,
            root_dir=project_name,
            files=files,
            framework=self.framework,
            language=self._config["language"],
            file_count=len(files),
        )

    def _generate_framework_files(
        self, project_name: str, base_url: str
    ) -> Dict[str, str]:
        """Generate framework-specific configuration and dependency files."""
        files: Dict[str, str] = {}

        if self.framework == "behave":
            files["behave.ini"] = _BEHAVE_INI
            files["requirements.txt"] = _BEHAVE_REQUIREMENTS
            files["features/__init__.py"] = ""
            files["features/steps/__init__.py"] = ""
            files["features/environment.py"] = self._behave_env(base_url)

        elif self.framework == "pytest_bdd":
            files["pytest.ini"] = _PYTEST_INI
            files["requirements.txt"] = _PYTEST_BDD_REQUIREMENTS
            files["tests/__init__.py"] = ""
            files["tests/conftest.py"] = self._pytest_conftest(base_url)

        elif self.framework == "cucumber_java":
            files["pom.xml"] = _CUCUMBER_JAVA_POM.format(
                project_name=project_name
            )
            files["src/test/java/runners/RunCucumberTest.java"] = (
                _CUCUMBER_JAVA_RUNNER
            )

        elif self.framework == "cucumberjs":
            files["package.json"] = _CUCUMBERJS_PACKAGE_JSON.format(
                project_name=project_name
            )
            files["cucumber.js"] = _CUCUMBERJS_CONFIG

        return files

    def _behave_env(self, base_url: str) -> str:
        """Generate Behave environment.py."""
        return f'''\
"""
Behave environment hooks.
Auto-generated by STLC Platform.
"""

BASE_URL = "{base_url}"


def before_all(context):
    """Set up test environment."""
    context.base_url = BASE_URL
    # TODO: Initialize browser driver here
    # from playwright.sync_api import sync_playwright
    # context.playwright = sync_playwright().start()
    # context.browser = context.playwright.chromium.launch(headless=True)
    # context.page = context.browser.new_page()


def after_all(context):
    """Tear down test environment."""
    # TODO: Close browser driver here
    # context.browser.close()
    # context.playwright.stop()
    pass


def before_scenario(context, scenario):
    """Set up before each scenario."""
    pass


def after_scenario(context, scenario):
    """Clean up after each scenario."""
    pass
'''

    def _pytest_conftest(self, base_url: str) -> str:
        """Generate Pytest-BDD conftest.py."""
        return f'''\
"""
Pytest-BDD conftest.
Auto-generated by STLC Platform.
"""

import pytest


BASE_URL = "{base_url}"


@pytest.fixture
def base_url():
    """Base URL for the application under test."""
    return BASE_URL


@pytest.fixture
def browser_page():
    """Browser page fixture -- uncomment when implementing."""
    # from playwright.sync_api import sync_playwright
    # pw = sync_playwright().start()
    # browser = pw.chromium.launch(headless=True)
    # page = browser.new_page()
    # yield page
    # browser.close()
    # pw.stop()
    yield None
'''

    def _generate_readme(
        self,
        project_name: str,
        features: List[FeatureFileArtifact],
        step_defs: List[StepDefinitionArtifact],
        pom_stubs: Optional[List[PageObjectStub]] = None,
    ) -> str:
        """Generate a README with setup and run instructions."""
        lines = [
            f"# {project_name}",
            "",
            "Auto-generated BDD test project by STLC Platform.",
            "",
            "## Contents",
            "",
            f"- **{len(features)}** feature file(s)",
            f"- **{len(step_defs)}** step definition file(s)",
        ]
        if pom_stubs:
            lines.append(f"- **{len(pom_stubs)}** page object model(s)")

        lines.extend(["", "## Setup & Run", ""])

        if self.framework == "behave":
            lines.extend([
                "```bash",
                "pip install -r requirements.txt",
                "behave",
                "```",
            ])
        elif self.framework == "pytest_bdd":
            lines.extend([
                "```bash",
                "pip install -r requirements.txt",
                "pytest tests/",
                "```",
            ])
        elif self.framework == "cucumber_java":
            lines.extend([
                "```bash",
                "mvn clean test",
                "```",
            ])
        elif self.framework == "cucumberjs":
            lines.extend([
                "```bash",
                "npm install",
                "npm test",
                "```",
            ])

        lines.extend([
            "",
            "## TODO",
            "",
            "1. Replace `TODO` selectors in page objects with real locators",
            "2. Implement step definition bodies (currently raise NotImplementedError)",
            "3. Configure browser/driver settings in environment setup",
            "4. Set the correct base URL (currently placeholder)",
            "",
            "---",
            "*Generated by STLC Automation Platform*",
            "",
        ])
        return "\n".join(lines)
