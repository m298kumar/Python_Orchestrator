"""
Test Case Generator
===================
Core engine that generates test cases from requirements using an LLM.
All dependencies are injected — no hardcoded domain terms, no global state.

Migrated from legacy test_generator.py (lines 1403-1640) into a clean,
testable class with full dependency injection.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from rich.console import Console

from stlc_platform.agents.requirements_agent.classifier import ACClassifier
from stlc_platform.agents.requirements_agent.component_resolver import ComponentResolver
from stlc_platform.agents.requirements_agent.constants import ac_to_title
from stlc_platform.agents.requirements_agent.domain_detector import DomainDetector
from stlc_platform.agents.requirements_agent.prompts import PromptRenderer
from stlc_platform.agents.requirements_agent.sanitiser import TestCaseSanitiser
from stlc_platform.agents.requirements_agent.synthesiser import (
    clean_duration,
    extract_steps,
    make_description,
    make_gwt,
    make_preconditions,
    synthesise_steps,
)
from stlc_platform.agents.requirements_agent.tech_stack import TechStackContext
from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact
from stlc_platform.core.quality.scorer import QualityReport, ScorerConfig, TestCaseScorer

logger = logging.getLogger(__name__)
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
        scorer: Optional[TestCaseScorer] = None,
        scorer_config: Optional[ScorerConfig] = None,
        feedback_store: Any = None,
    ):
        self.llm = llm_client
        self.prompt_renderer = prompt_renderer or PromptRenderer()
        self.classifier = classifier or ACClassifier()
        self.sanitiser = sanitiser or TestCaseSanitiser()
        self.component_resolver = component_resolver or ComponentResolver(vector_store=vector_store)
        self.domain_detector = domain_detector or DomainDetector()
        self.tech_stack = tech_stack or TechStackContext()
        self.vector_store = vector_store
        self._domain = domain
        self._tc_counter = 0
        self.scorer = scorer or TestCaseScorer(config=scorer_config)
        self.feedback_store = feedback_store

    def generate_for_requirement(
        self,
        requirement: Any,
        max_tests: int = 6,
        include_negative: bool = True,
        include_edge: bool = True,
        tc_format: str = "gherkin",
    ) -> List[TestCaseArtifact]:
        system_prompt = self._build_system_prompt()
        context = self._fetch_context(requirement)
        feedback_constraints = self._fetch_feedback(requirement)
        slots = self._build_slot_plan(
            requirement=requirement,
            max_tc=max_tests,
            include_negative=include_negative,
            include_edge=include_edge,
        )
        max_prompt_tokens = self._calc_max_prompt_tokens()

        results: List[TestCaseArtifact] = []
        max_regen = self.scorer.config.max_regeneration_attempts

        for i, slot in enumerate(slots):
            best_tc, best_report = self._generate_single_test_case(
                requirement,
                slot,
                system_prompt,
                context,
                feedback_constraints,
                max_prompt_tokens,
                max_regen,
                results,
            )
            results.append(best_tc)
            self._maybe_store_example(best_tc, slot, results)

        return results

    def _build_system_prompt(self) -> str:
        tech_stack_dict = {"platform": self.tech_stack.platform} if self.tech_stack else {}
        return self.prompt_renderer.render_system_prompt(
            domain=self._domain,
            tech_stack=tech_stack_dict,
        )

    def _fetch_context(self, requirement: Any) -> str:
        if not self.vector_store:
            return ""
        try:
            return self.vector_store.get_context_for_requirement(requirement)
        except (AttributeError, RuntimeError, OSError):
            return ""

    def _fetch_feedback(self, requirement: Any) -> list:
        if not self.feedback_store:
            return []
        try:
            return self.feedback_store.retrieve(
                agent_id="test_generation",
                context={
                    "requirement": requirement,
                    "query": getattr(requirement, "title", ""),
                },
                limit=3,
            )
        except (AttributeError, RuntimeError, OSError):
            return []

    def _calc_max_prompt_tokens(self) -> int:
        try:
            _num_predict = getattr(self.llm, "num_predict", None) or getattr(
                self.llm, "max_tokens", None
            )
            _num_predict = int(_num_predict) if _num_predict is not None else 3200
            _num_ctx = getattr(self.llm, "num_ctx", None)
            _num_ctx = int(_num_ctx) if _num_ctx is not None else 8192
            return max((_num_ctx - _num_predict) * 6 // 10, 1024)
        except (TypeError, ValueError):
            return 3000

    def _retrieve_few_shot_examples(self, slot: Dict[str, str]) -> list:
        if not self.vector_store:
            return []
        try:
            return self.vector_store.retrieve_examples(
                ac_text=slot["target_ac"],
                ac_type=slot.get("ac_type", "general"),
                test_type=slot["test_type"],
                n=2,
            )
        except (AttributeError, RuntimeError, OSError):
            return []

    def _generate_single_test_case(
        self,
        requirement: Any,
        slot: Dict[str, str],
        system_prompt: str,
        context: str,
        feedback_constraints: list,
        max_prompt_tokens: int,
        max_regen: int,
        existing_tcs: List[TestCaseArtifact],
    ) -> tuple[TestCaseArtifact, QualityReport]:
        examples = self._retrieve_few_shot_examples(slot)
        prompt = self.prompt_renderer.render_user_prompt(
            requirement=requirement,
            slot=slot,
            test_number=len(existing_tcs) + 1,
            total=len(self._build_slot_plan(requirement, 6, True, True)),
            context=context,
            tc_format="gherkin",
            examples=examples,
            feedback_constraints=feedback_constraints,
            max_prompt_tokens=max_prompt_tokens,
        )

        best_tc, best_report = self._run_generation_attempts(
            requirement,
            slot,
            system_prompt,
            prompt,
            max_regen,
            existing_tcs,
        )

        if best_tc is None or best_report is None:
            best_tc = self._synthesise_tc(requirement, slot)
            best_tc = self.sanitiser.sanitise(tc=best_tc, slot=slot, requirement=requirement)
            best_report = self.scorer.score(
                tc=best_tc,
                slot=slot,
                requirement=requirement,
                existing_tcs=existing_tcs,
            )

        best_tc = best_tc.model_copy(
            update={
                "quality_score": best_report.overall_score,
                "quality_issues": best_report.issues,
            }
        )
        return best_tc, best_report

    def _run_generation_attempts(
        self,
        requirement: Any,
        slot: Dict[str, str],
        system_prompt: str,
        base_prompt: str,
        max_regen: int,
        existing_tcs: List[TestCaseArtifact],
    ) -> tuple[Optional[TestCaseArtifact], Optional[QualityReport]]:
        best_tc: Optional[TestCaseArtifact] = None
        best_report: Optional[QualityReport] = None

        for attempt in range(1, 2 + max_regen):
            current_prompt = self._build_prompt_with_feedback(
                base_prompt,
                attempt,
                best_report,
            )
            tc = self._call_llm_and_parse(
                current_prompt,
                system_prompt,
                slot,
                requirement,
                attempt,
            )
            if not tc:
                continue

            tc = self.sanitiser.sanitise(tc=tc, slot=slot, requirement=requirement)
            report = self.scorer.score(
                tc=tc,
                slot=slot,
                requirement=requirement,
                existing_tcs=existing_tcs,
            )

            if best_tc is None or report.overall_score > (
                best_report.overall_score if best_report else -1
            ):
                best_tc = tc
                best_report = report

            if report.suggestion == "accept":
                break
            if attempt == 1 and report.suggestion == "fallback":
                break
            if attempt > 1:
                console.print(
                    f"    [yellow]  regen {attempt - 1}: "
                    f"score {report.overall_score:.2f} ({report.suggestion})[/yellow]"
                )

        return best_tc, best_report

    def _build_prompt_with_feedback(
        self,
        base_prompt: str,
        attempt: int,
        best_report: Optional[QualityReport],
    ) -> str:
        if attempt <= 1 or not best_report or not best_report.issues:
            return base_prompt
        hint = "\n\nIMPORTANT — fix these issues from previous attempt:\n"
        for issue in best_report.issues[:5]:
            hint += f"  - {issue}\n"
        return base_prompt + hint

    def _call_llm_and_parse(
        self,
        prompt: str,
        system_prompt: str,
        slot: Dict[str, str],
        requirement: Any,
        attempt: int,
    ) -> Optional[TestCaseArtifact]:
        try:
            raw = self.llm.generate_test_case(
                prompt=prompt,
                system_prompt=system_prompt,
                slot=slot,
                requirement=requirement,
            )
            return self._parse(raw, requirement, slot)
        except Exception as e:
            console.print(f"    [yellow]  attempt {attempt} error: {e}[/yellow]")
            return None

    def _maybe_store_example(
        self,
        tc: TestCaseArtifact,
        slot: Dict[str, str],
        results: List[TestCaseArtifact],
    ) -> None:
        auto_threshold = self.scorer.config.auto_example_threshold
        report = self.scorer.score(tc=tc, slot=slot, requirement=None, existing_tcs=results)
        if report.overall_score < auto_threshold or not self.vector_store:
            return
        if not hasattr(self.vector_store, "store_approved_tc"):
            return
        try:
            self.vector_store.store_approved_tc(
                tc_dict=tc.model_dump(),
                ac_type=slot.get("ac_type", "general"),
                test_type=slot["test_type"],
                domain=self._domain or "",
            )
        except (AttributeError, RuntimeError, OSError):
            pass

    def _deduplicate_tcs(self, all_tc: List[TestCaseArtifact]) -> List[TestCaseArtifact]:
        """Cross-requirement deduplication of generated test cases."""
        import logging as _logging

        from stlc_platform.core.quality.deduplicator import TestCaseDeduplicator

        _dedup_logger = _logging.getLogger(__name__)
        deduplicator = TestCaseDeduplicator(threshold=0.85)
        dedup_result = deduplicator.deduplicate(all_tc)
        if dedup_result.removed:
            _dedup_logger.info("Deduplication removed %d duplicate TCs", len(dedup_result.removed))
            console.print(
                f"  [yellow]Dedup removed {len(dedup_result.removed)} near-duplicate TC(s)[/yellow]"
            )
        return dedup_result.kept

    def _enrich_vocab(self, all_tc: List[TestCaseArtifact]) -> None:
        """Enrich domain vocabulary from generated test cases."""
        if not self.vector_store:
            return
        try:
            vocab_terms = self._extract_vocab(all_tc)
            if vocab_terms:
                added = self.vector_store.add_vocab(vocab_terms, domain=self._domain or "")
                if added:
                    logger.info("Enriched domain vocabulary with %d new terms", added)
        except Exception as e:
            logger.debug("Vocab enrichment skipped: %s", e)

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

        # Phase D: Cross-requirement deduplication
        all_tc = self._deduplicate_tcs(all_tc)

        # Phase D4: Domain vocabulary enrichment from generated test cases
        self._enrich_vocab(all_tc)

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
            slots.append(
                {
                    "test_type": test_type,
                    "target_ac": target_ac,
                    "title": title,
                    "ac_type": ac_type,
                }
            )

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
                    expected_result=s.expected_result
                    if hasattr(s, "expected_result")
                    else s["expected_result"],  # type: ignore[index]
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

    def _synthesise_tc(self, requirement: Any, slot: Dict[str, str]) -> TestCaseArtifact:
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
                expected_result=s.expected_result
                if hasattr(s, "expected_result")
                else s["expected_result"],  # type: ignore[index]
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

    # -- Vocabulary extraction -------------------------------------------------

    _GENERIC_TAGS = frozenset({"positive", "negative", "edge_case", "general", "synthesised"})

    def _extract_vocab(self, test_cases: List[TestCaseArtifact]) -> List[str]:
        """Extract component names and UI element names from generated test cases."""
        terms: set[str] = set()
        for tc in test_cases:
            # Extract component field
            comp = getattr(tc, "component", "")
            if comp and comp.lower() not in ("general", "unknown", ""):
                terms.add(comp)

            # Extract tags that look like domain terms
            for tag in getattr(tc, "tags", []):
                if len(tag) > 3 and tag not in self._GENERIC_TAGS:
                    terms.add(tag)

            # Extract quoted strings from step actions (likely UI elements/features)
            for step in getattr(tc, "steps", []):
                action = (
                    getattr(step, "action", "")
                    if hasattr(step, "action")
                    else (step.get("action", "") if isinstance(step, dict) else "")
                )
                quoted = re.findall(r'"([^"]+)"', action)
                terms.update(q for q in quoted if len(q) > 2)

        return list(terms)[:50]  # Cap at 50 terms per batch
