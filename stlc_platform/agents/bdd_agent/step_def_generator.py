"""
Step Definition Generator
=========================
Generates step definition skeleton code for Python (Behave, Pytest-BDD),
Java (Cucumber), and JavaScript (Cucumber.js) from parameterized step
patterns using Jinja2 templates.

Supports optional CSS selector injection from a crawler site model:
when a ``selector_map`` is provided, the generator post-processes the
rendered code and replaces ``TODO: implement this step`` placeholders
with concrete selector hints wherever a fuzzy match is found.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from stlc_platform.agents.bdd_agent.step_parser import ParameterizedStep
from stlc_platform.core.contracts import (
    FeatureFileArtifact,
    StepDefinitionArtifact,
)

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
        "cucumber_java": "java",
        "cucumberjs": "javascript",
    }

    _TEMPLATE_MAP: ClassVar[Dict[str, str]] = {
        "behave": "behave_steps.py.j2",
        "pytest_bdd": "pytest_bdd_steps.py.j2",
        "cucumber_java": "cucumber_java.java.j2",
        "cucumberjs": "cucumberjs_steps.js.j2",
    }

    _FILENAME_MAP: ClassVar[Dict[str, str]] = {
        "behave": "steps.py",
        "pytest_bdd": "test_steps.py",
        "cucumber_java": "StepDefinitions.java",
        "cucumberjs": "steps.js",
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
        selector_map: Optional[Dict[str, str]] = None,
    ) -> List[StepDefinitionArtifact]:
        """
        Generate step definition files from parameterized steps.

        Args:
            steps: Parameterized steps extracted from feature files.
            features: Feature file artifacts (needed for pytest_bdd scenario refs).
            selector_map: Optional mapping of element name (lowercased) to CSS
                selector string, built from the crawler's site model.

        Returns one StepDefinitionArtifact per output file.
        """
        if self.framework == "behave":
            artifacts = self._generate_behave(steps)
        elif self.framework == "pytest_bdd":
            artifacts = self._generate_pytest_bdd(steps, features or [])
        elif self.framework in ("cucumber_java", "cucumberjs"):
            artifacts = self._generate_generic(steps)
        else:
            raise ValueError(f"Unknown framework: {self.framework}")

        # Post-process: inject real CSS selectors into TODO placeholders
        if selector_map:
            artifacts = self._inject_selectors(artifacts, selector_map)

        return artifacts

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

    def _generate_generic(
        self, steps: List[ParameterizedStep]
    ) -> List[StepDefinitionArtifact]:
        """Generate step definitions for Java Cucumber or Cucumber.js."""
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

        # Java/JS templates need {param} → {string} for Cucumber expressions
        # and also pass param names list for method/function signatures
        for step_list in (given_steps, when_steps, then_steps):
            for step in step_list:
                # Convert Python-style {param} to Cucumber expression {string}
                param_names = []
                if step["has_params"]:
                    import re as _re
                    params_found = _re.findall(r"\{([^}]+)\}", step["pattern"])
                    param_names = params_found
                    # Replace {paramN} with {string} for Cucumber expression
                    step["cucumber_pattern"] = _re.sub(
                        r"\{[^}]+\}", "{string}", step["pattern"]
                    )
                else:
                    step["cucumber_pattern"] = step["pattern"]
                step["param_names"] = param_names

        template_name = self._TEMPLATE_MAP[self.framework]
        template = self._env.get_template(template_name)
        content = template.render(
            automation_lib=self.automation_lib,
            given_steps=given_steps,
            when_steps=when_steps,
            then_steps=then_steps,
        )

        total = len(given_steps) + len(when_steps) + len(then_steps)
        filename = self._FILENAME_MAP[self.framework]

        return [
            StepDefinitionArtifact(
                language=self.SUPPORTED_FRAMEWORKS[self.framework],
                framework=self.framework,
                filename=filename,
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

    # -- Selector injection helpers --

    # Regex that matches the TODO placeholder line in generated step bodies.
    # Captures the leading whitespace so the replacement keeps indentation.
    _TODO_LINE_RE = re.compile(
        r'^(?P<indent>\s*)raise NotImplementedError\("TODO: implement this step"\)',
        re.MULTILINE,
    )

    # Pattern to capture the step-decorator line immediately before a function
    # definition so we can extract the step text for selector matching.
    _STEP_DECORATOR_RE = re.compile(
        r"@(?:given|when|then)\(\s*(?:parsers\.parse\()?\s*['\"](.+?)['\"]\s*\)?\s*\)",
    )

    def _inject_selectors(
        self,
        artifacts: List[StepDefinitionArtifact],
        selector_map: Dict[str, str],
    ) -> List[StepDefinitionArtifact]:
        """
        Post-process generated step definition code: replace TODO
        placeholders with CSS selector hints where a match is found
        in *selector_map*.

        Returns a new list of artifacts with updated content.
        """
        result = []
        for artifact in artifacts:
            new_content = self._replace_todos_with_selectors(
                artifact.content, selector_map
            )
            result.append(
                StepDefinitionArtifact(
                    language=artifact.language,
                    framework=artifact.framework,
                    filename=artifact.filename,
                    content=new_content,
                    step_count=artifact.step_count,
                )
            )
        return result

    def _replace_todos_with_selectors(
        self,
        content: str,
        selector_map: Dict[str, str],
    ) -> str:
        """
        Walk through *content* line-by-line.  For each TODO placeholder,
        look back to find the step decorator text, extract meaningful
        words, and try to fuzzy-match against *selector_map*.
        """
        lines = content.split("\n")
        out: List[str] = []

        for i, line in enumerate(lines):
            m = self._TODO_LINE_RE.match(line)
            if not m:
                out.append(line)
                continue

            indent = m.group("indent")

            # Walk backwards to find the decorator text
            step_text = self._find_step_text(lines, i)
            if step_text:
                selector = self._fuzzy_match_selector(step_text, selector_map)
            else:
                selector = None

            if selector:
                # Replace the TODO with a selector comment + the original raise
                out.append(
                    f'{indent}# Selector: "{selector}"'
                )
                out.append(line)
            else:
                out.append(line)

        return "\n".join(out)

    @staticmethod
    def _find_step_text(lines: List[str], todo_index: int) -> str:
        """
        Search backwards from *todo_index* to find the nearest step
        decorator line and return the step pattern text.
        """
        for j in range(todo_index - 1, max(todo_index - 6, -1), -1):
            dm = StepDefinitionGenerator._STEP_DECORATOR_RE.search(lines[j])
            if dm:
                return dm.group(1)
        return ""

    @staticmethod
    def _fuzzy_match_selector(
        element_name: str,
        selector_map: Dict[str, str],
    ) -> Optional[str]:
        """
        Try to match *element_name* (step text) against keys in
        *selector_map*.

        Strategy (first match wins):
          1. Exact match (lowercased).
          2. Substring containment (either direction).
          3. Word overlap (>50 % of words in common).

        Returns the CSS selector string or ``None``.
        """
        if not selector_map or not element_name:
            return None

        name_lower = element_name.lower().strip()

        # 1. Exact match
        if name_lower in selector_map:
            return selector_map[name_lower]

        # 2. Substring containment
        for key, selector in selector_map.items():
            if name_lower in key or key in name_lower:
                return selector

        # 3. Word overlap (>50 %)
        name_words = set(re.findall(r"[a-z]+", name_lower))
        if not name_words:
            return None

        best_selector: Optional[str] = None
        best_ratio = 0.0
        for key, selector in selector_map.items():
            key_words = set(re.findall(r"[a-z]+", key))
            if not key_words:
                continue
            overlap = len(name_words & key_words)
            ratio = overlap / max(len(name_words), len(key_words))
            if ratio > 0.5 and ratio > best_ratio:
                best_ratio = ratio
                best_selector = selector

        return best_selector
