"""
Step Definition Generator
=========================
Generates step definition skeleton code for Python Behave and Pytest-BDD
from parameterized step patterns using Jinja2 templates.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from stlc_platform.core.contracts import (
    FeatureFileArtifact,
    StepDefinitionArtifact,
)
from stlc_platform.agents.bdd_agent.step_parser import ParameterizedStep


# -- Paths --
_BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"
_DEFAULT_OVERRIDES = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "config"
    / "prompt_overrides"
    / "bdd"
)


class StepDefinitionGenerator:
    """
    Generates step definition skeleton files from parameterized steps.

    Supports:
      - Python Behave: @given/@when/@then decorators
      - Pytest-BDD: parsers.parse() based step functions
    """

    SUPPORTED_FRAMEWORKS: ClassVar[Dict[str, str]] = {
        "behave": "python",
        "pytest_bdd": "python",
    }

    def __init__(
        self,
        framework: str = "behave",
        language: str = "python",
        automation_lib: str = "playwright",
        template_dir: Optional[Path] = None,
        override_dir: Optional[Path] = None,
    ):
        if framework not in self.SUPPORTED_FRAMEWORKS:
            raise ValueError(
                f"Unsupported framework: '{framework}'. "
                f"Supported: {list(self.SUPPORTED_FRAMEWORKS.keys())}"
            )
        self.framework = framework
        self.language = language
        self.automation_lib = automation_lib

        loaders = []
        override = override_dir or _DEFAULT_OVERRIDES
        if override.is_dir():
            loaders.append(FileSystemLoader(str(override)))
        builtin = template_dir or _BUILTIN_TEMPLATES
        loaders.append(FileSystemLoader(str(builtin)))

        self._env = Environment(
            loader=ChoiceLoader(loaders),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate(
        self,
        steps: List[ParameterizedStep],
        features: Optional[List[FeatureFileArtifact]] = None,
    ) -> List[StepDefinitionArtifact]:
        """
        Generate step definition files from parameterized steps.

        Returns one StepDefinitionArtifact per output file.
        """
        if self.framework == "behave":
            return self._generate_behave(steps)
        elif self.framework == "pytest_bdd":
            return self._generate_pytest_bdd(steps, features or [])
        else:
            raise ValueError(f"Unknown framework: {self.framework}")

    def _generate_behave(
        self, steps: List[ParameterizedStep]
    ) -> List[StepDefinitionArtifact]:
        """Generate Behave step definition file."""
        seen_names: set = set()
        given_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "given"], seen_names
        )
        when_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "when"], seen_names
        )
        then_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "then"], seen_names
        )

        template = self._env.get_template("behave_steps.py.j2")
        content = template.render(
            automation_lib=self.automation_lib,
            given_steps=given_steps,
            when_steps=when_steps,
            then_steps=then_steps,
        )

        total = len(given_steps) + len(when_steps) + len(then_steps)

        return [
            StepDefinitionArtifact(
                language=self.language,
                framework=self.framework,
                filename="steps.py",
                content=content,
                step_count=total,
            )
        ]

    def _generate_pytest_bdd(
        self,
        steps: List[ParameterizedStep],
        features: List[FeatureFileArtifact],
    ) -> List[StepDefinitionArtifact]:
        """Generate Pytest-BDD step definition file."""
        seen_names: set = set()
        given_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "given"], seen_names
        )
        when_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "when"], seen_names
        )
        then_steps = self._prepare_steps(
            [s for s in steps if s.keyword == "then"], seen_names
        )

        # Prepare feature references for @scenario decorators
        feature_refs = []
        for f in features:
            # Use forward slash paths (cross-platform)
            fname = f.filename.replace("\\", "/")
            # Derive a test function name from the filename
            func_name = self._make_function_name(
                f.filename.replace(".feature", ""), prefix="test_"
            )
            feature_refs.append({
                "filename": fname,
                "func_name": func_name,
                "first_scenario": "",  # Pytest-BDD scenario decorator
            })

        template = self._env.get_template("pytest_bdd_steps.py.j2")
        content = template.render(
            automation_lib=self.automation_lib,
            features=feature_refs,
            given_steps=given_steps,
            when_steps=when_steps,
            then_steps=then_steps,
        )

        total = len(given_steps) + len(when_steps) + len(then_steps)

        return [
            StepDefinitionArtifact(
                language=self.language,
                framework=self.framework,
                filename="test_steps.py",
                content=content,
                step_count=total,
            )
        ]

    def _prepare_steps(
        self,
        steps: List[ParameterizedStep],
        seen_names: Optional[set] = None,
    ) -> List[Dict]:
        """
        Prepare steps for template rendering.

        Each step gets:
          - pattern: the step text (with {param} placeholders if parameterized)
          - func_name: a valid Python function name
          - param_signature: ", value, field" for Behave context params
          - param_list: "value, field" for Pytest-BDD function params
          - has_params: bool
        """
        if seen_names is None:
            seen_names = set()
        prepared = []

        for step in steps:
            func_name = self._make_function_name(step.pattern)

            # Deduplicate function names
            original = func_name
            suffix = 2
            while func_name in seen_names:
                func_name = f"{original}_{suffix}"
                suffix += 1
            seen_names.add(func_name)

            param_list = ", ".join(step.params) if step.params else ""
            param_signature = (
                ", " + param_list if param_list else ""
            )

            # Escape single quotes in the pattern for Python string literals
            safe_pattern = step.pattern.replace("'", "\\'")

            prepared.append({
                "pattern": safe_pattern,
                "func_name": func_name,
                "param_signature": param_signature,
                "param_list": param_list,
                "has_params": bool(step.params),
            })

        return prepared

    def _make_function_name(
        self, text: str, prefix: str = "step_"
    ) -> str:
        """
        Generate a valid Python function name from step text.

        "user enters {value} in {field}" -> "step_user_enters_value_in_field"
        """
        # Remove {param} placeholders for the function name
        clean = re.sub(r"\{[^}]+\}", "", text)
        # Slugify
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()
        # Truncate
        if len(slug) > 60:
            slug = slug[:60].rstrip("_")
        # Ensure it starts with a letter
        if slug and slug[0].isdigit():
            slug = f"n{slug}"
        return f"{prefix}{slug}" if slug else f"{prefix}unnamed"
