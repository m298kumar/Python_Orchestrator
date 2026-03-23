"""
Test Case Generator
===================
Core engine that generates test cases from requirements using an LLM.
All dependencies are injected — no hardcoded domain terms, no global state.

Migrated from legacy test_generator.py (lines 1403-1640) into a clean,
testable class with full dependency injection.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from rich.console import Console

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact

from stlc_platform.agents.requirements_agent.classifier import ACClassifier
from stlc_platform.agents.requirements_agent.constants import ac_to_title
from stlc_platform.agents.requirements_agent.sanitiser import TestCaseSanitiser
from stlc_platform.agents.requirements_agent.synthesiser import (
    clean_duration,
    extract_steps,
    make_description,
    make_gwt,
    make_preconditions,
    synthesise_steps,
)
from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver
from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector
from stlc_platform.agents.requirements_agent.prompts import PromptRenderer
from stlc_platform.agents.requirements_agent.tech_stack import TechStackContext

console = Console()


class TestCaseGenerator:
    """
    Generates test cases for requirements using an LLM with prompt templates.

    All components are injected via constructor:
      - llm_client: BaseLLMClient for LLM calls
      - prompt_renderer: PromptRenderer for Jinja2 templates
      - classifier: ACClassifier for AC type classification
      - sanitiser: TestCaseSanitiser for output cleanup
      - component_resolver: ComponentResolver for screen name resolution
      - domain_detector: DomainDetector for domain inference
      - tech_stack: TechStackContext for platform verb mapping
      - vector_store: optional ChromaDB store for context & few-shot retrieval
    """

    def __init__(
        self,
        llm_client: Any,
        prompt_renderer: Optional[PromptRenderer] = None,
        classifier: Optional[ACClassifier] = None,
        sanitiser: Optional[TestCaseSanitiser] = None,
        component_resolver: Optional[ComponentResolver] = None,
        domain_detector: Optional[DomainDetector] = None,
        tech_stack: Optional[TechStackContext] = None,
        vector_store: Any = None,
        domain: str = "",
    ):
        self.llm = llm_client
        self.prompt_renderer = prompt_renderer or PromptRenderer()
        self.classifier = classifier or ACClassifier()
        self.sanitiser = sanitiser or TestCaseSanitiser()
        self.component_resolver = component_resolver or ComponentResolver(
            vector_store=vector_store
        )
        self.domain_detector = domain_detector or DomainDetector()
        self.tech_stack = tech_stack or TechStackContext()
        self.vector_store = vector_store
        self._domain = domain
        self._tc_counter = 0

    def generate_for_requirement(
        self,
        requirement: Any,
        max_tests: int = 6,
        include_negative: bool = True,
        include_edge: bool = True,
        tc_format: str = "gherkin",
    ) -> List[TestCaseArtifact]:
        """
        Generate test cases for a single requirement.

        Args:
            requirement: Object with req_id, title, description, acceptance_criteria, category.
            max_tests: Maximum number of test cases to generate.
            include_negative: Include negative/error handling test cases.
            include_edge: Include edge case/boundary test cases.
            tc_format: "gherkin" or "standard".

        Returns:
            List of TestCaseArtifact instances.
        """
        tech_stack_dict = {"platform": self.tech_stack.platform} if self.tech_stack else {}
        system_prompt = self.prompt_renderer.render_system_prompt(
            domain=self._domain,
            tech_stack=tech_stack_dict,
        )

        context = ""
        if self.vector_store:
            try:
                context = self.vector_store.get_context_for_requirement(requirement)
            except Exception:
                pass

        slots = self._build_slot_plan(
            requirement=requirement,
            max_tc=max_tests,
            include_negative=include_negative,
            include_edge=include_edge,
        )

        results: List[TestCaseArtifact] = []

        for i, slot in enumerate(slots):
            ac_type_label = slot.get("ac_type", "general")
            test_type = slot["test_type"]
            ac_text = slot["target_ac"]

            # Retrieve few-shot examples from ChromaDB
            examples: list = []
            if self.vector_store:
                try:
                    examples = self.vector_store.retrieve_examples(
                        ac_text=ac_text,
                        ac_type=ac_type_label,
                        test_type=test_type,
                        n=2,
                    )
                except Exception:
                    pass

            prompt = self.prompt_renderer.render_user_prompt(
                requirement=requirement,
                slot=slot,
                test_number=i + 1,
                total=max_tests,
                context=context,
                tc_format=tc_format,
                examples=examples,
            )

            tc = None
            for attempt in range(1, 3):
                try:
                    raw = self.llm.generate_test_case(
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    tc = self._parse(raw, requirement, slot)
                except Exception as e:
                    console.print(f"    [yellow]  attempt {attempt} error: {e}[/yellow]")
                if tc:
                    break

            if not tc:
                tc = self._synthesise_tc(requirement, slot)

            # Sanitise
            tc = self.sanitiser.sanitise(
                tc=tc,
                slot=slot,
                requirement=requirement,
            )

            results.append(tc)

        return results

    def generate_for_all(
        self,
        requirements: List[Any],
        max_tests: int = 6,
        include_negative: bool = True,
        include_edge: bool = True,
        tc_format: str = "gherkin",
    ) -> List[TestCaseArtifact]:
        """
        Generate test cases for all requirements.

        Detects domain from the requirement set if not already set,
        extracts vocabulary for component resolution, then generates
        test cases for each requirement.

        Args:
            requirements: List of requirement objects.
            max_tests: Max test cases per requirement.
            include_negative: Include negative tests.
            include_edge: Include edge case tests.
            tc_format: "gherkin" or "standard".

        Returns:
            List of all TestCaseArtifact instances.
        """
        if not self._domain:
            self._domain = self.domain_detector.detect(requirements)

        if self._domain:
            console.print(f"[cyan]Domain detected: [bold]{self._domain}[/bold][/cyan]")

        # Extract vocab for component resolution
        if self.vector_store:
            try:
                self.vector_store.extract_and_store_vocab(requirements)
            except Exception as e:
                console.print(f"[yellow]Vocab extraction skipped: {e}[/yellow]")

        all_tc: List[TestCaseArtifact] = []
        for req in requirements:
            try:
                # Ensure full AC coverage: at least one TC per acceptance criterion
                acs = getattr(req, "acceptance_criteria", None) or []
                ac_count = len(acs) if isinstance(acs, list) else 0
                effective_max = max(max_tests, ac_count) if ac_count > 0 else max_tests

                tcs = self.generate_for_requirement(
                    requirement=req,
                    max_tests=effective_max,
                    include_negative=include_negative,
                    include_edge=include_edge,
                    tc_format=tc_format,
                )
                all_tc.extend(tcs)
                console.print(f"  [green]OK {req.req_id}[/green]: {len(tcs)} test case(s)")
            except Exception as e:
                console.print(f"  [red]ERR {req.req_id}: {e}[/red]")

        console.print(
            f"\n[bold green]{len(all_tc)} test cases "
            f"from {len(requirements)} requirements[/bold green]"
        )
        return all_tc

    # -- Slot planning ---------------------------------------------------------

    def _build_slot_plan(
        self,
        requirement: Any,
        max_tc: int,
        include_negative: bool,
        include_edge: bool,
    ) -> List[Dict[str, str]]:
        """
        Build a plan of test case slots — which AC to test, with which test type.

        Uses round-robin pattern cycling through positive/negative/edge_case
        across the requirement's acceptance criteria.
        """
        if include_negative and include_edge:
            pattern = ["positive", "negative", "edge_case"]
        elif include_negative:
            pattern = ["positive", "negative"]
        elif include_edge:
            pattern = ["positive", "edge_case"]
        else:
            pattern = ["positive"]

        acs = requirement.acceptance_criteria or [requirement.description[:120]]
        slots: List[Dict[str, str]] = []
        seen_titles: set = set()

        for i in range(max_tc):
            test_type = pattern[i % len(pattern)]
            target_ac = acs[i % len(acs)]
            ac_type = self.classifier.classify(target_ac).ac_type
            title = ac_to_title(target_ac, test_type)

            original = title
            suffix = 2
            while title.lower() in seen_titles:
                title = f"{original} ({suffix})"
                suffix += 1

            seen_titles.add(title.lower())
            slots.append({
                "test_type": test_type,
                "target_ac": target_ac,
                "title": title,
                "ac_type": ac_type,
            })

        return slots

    # -- Parsing ---------------------------------------------------------------

    def _parse(
        self, raw: Any, requirement: Any, slot: Dict[str, str]
    ) -> Optional[TestCaseArtifact]:
        """Parse raw LLM JSON output into a TestCaseArtifact."""
        if not raw or (isinstance(raw, dict) and "raw_response" in raw):
            return None

        if isinstance(raw, dict):
            if "test_cases" in raw and isinstance(raw["test_cases"], list) and raw["test_cases"]:
                item = raw["test_cases"][0]
            elif "title" in raw:
                item = raw
            else:
                return None
        else:
            return None

        if not isinstance(item, dict):
            return None

        self._tc_counter += 1
        ac_type = slot.get("ac_type", self.classifier.classify(slot["target_ac"]).ac_type)

        steps = extract_steps(
            raw_steps=item.get("steps", []),
            ac=slot["target_ac"],
            test_type=slot["test_type"],
            req_title=requirement.title,
            ac_type=ac_type,
        )

        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,;\s]+", tags) if t.strip()]
        tags = [t for t in tags if len(t) > 1]
        if not tags:
            req_tag = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())
            cat = getattr(requirement, "category", "general") or "general"
            tags = [cat.lower().replace(" ", "-"), slot["test_type"], req_tag]

        return TestCaseArtifact(
            tc_id=f"TC-{self._tc_counter:04d}",
            req_id=requirement.req_id,
            title=slot["title"],
            description=item.get("description", "").strip(),
            preconditions=item.get("preconditions", "").strip(),
            test_type=slot["test_type"],
            priority=getattr(requirement, "priority", "Medium"),
            steps=[
                TestStepArtifact(
                    action=s.action if hasattr(s, "action") else s["action"],  # type: ignore[index]
                    expected_result=s.expected_result if hasattr(s, "expected_result") else s["expected_result"],  # type: ignore[index]
                )
                for s in steps
            ],
            expected_outcome=item.get("expected_outcome", "").strip(),
            tags=tags,
            category=getattr(requirement, "category", ""),
            component=item.get("component", "").strip(),
            given=item.get("given", "").strip(),
            when=item.get("when", "").strip(),
            then=item.get("then", "").strip(),
            estimated_duration=clean_duration(item.get("estimated_duration", "5")),
        )

    # -- Synthesis fallback ----------------------------------------------------

    def _synthesise_tc(
        self, requirement: Any, slot: Dict[str, str]
    ) -> TestCaseArtifact:
        """Create a deterministic fallback test case when LLM fails."""
        self._tc_counter += 1
        ac = slot["target_ac"]
        tt = slot["test_type"]
        ac_type = slot.get("ac_type", self.classifier.classify(ac).ac_type)
        g, w, t = make_gwt(ac, tt, requirement.title)
        req_tag = re.sub(r"[^a-z0-9-]", "-", requirement.req_id.lower())
        cat = getattr(requirement, "category", "general") or "general"

        component = self.component_resolver.resolve(
            raw="",
            category=cat,
            req_title=requirement.title,
            ac_text=ac,
        )

        synth_steps = synthesise_steps(ac, tt, requirement.title, ac_type)
        pydantic_steps = [
            TestStepArtifact(
                action=s.action if hasattr(s, "action") else s["action"],  # type: ignore[index]
                expected_result=s.expected_result if hasattr(s, "expected_result") else s["expected_result"],  # type: ignore[index]
            )
            for s in synth_steps
        ]

        return TestCaseArtifact(
            tc_id=f"TC-{self._tc_counter:04d}",
            req_id=requirement.req_id,
            title=slot["title"],
            description=make_description(ac, tt),
            preconditions=make_preconditions(ac, tt, cat, requirement.title),
            test_type=tt,
            priority=getattr(requirement, "priority", "Medium"),
            steps=pydantic_steps,
            expected_outcome=ac,
            tags=[cat.lower().replace(" ", "-"), tt, req_tag, "synthesised"],
            category=cat,
            component=component,
            given=g,
            when=w,
            then=t,
        )
