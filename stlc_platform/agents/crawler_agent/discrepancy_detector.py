"""
Discrepancy Detector
====================
Compares a SiteModelArtifact against a list of RequirementArtifacts to find
gaps between what the requirements specify and what the crawled site contains.

Uses keyword/regex matching (no LLM). Detection strategies are isolated in
private methods so an LLM-based strategy can be added later without changing
the public interface.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Set

import yaml

from stlc_platform.core.contracts import (
    DiscrepancyArtifact,
    DiscrepancyReportArtifact,
    RequirementArtifact,
    SiteModelArtifact,
)


def _resolve_flags(flag_str):
    """Convert a flag string to re flags value."""
    if flag_str == "IGNORECASE":
        return re.IGNORECASE
    return 0


def _compile_page_keywords(config):
    """Compile page keywords from config into a regex pattern."""
    page_keywords_list = config.get(
        "page_keywords",
        [
            "page",
            "screen",
            "view",
            "dashboard",
            "form",
            "panel",
            "dialog",
            "modal",
            "popup",
            "window",
            "tab",
        ],
    )
    pattern = r"\b(" + "|".join(page_keywords_list) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def _compile_element_patterns(config):
    """Compile element patterns from config into a list of (type, regex) tuples."""
    patterns = []
    for elem_type, items in config.get("element_patterns", {}).items():
        for pc in items:
            pattern_str = pc.get("pattern", "")
            if pattern_str:
                flags = _resolve_flags(pc.get("flags", "IGNORECASE"))
                patterns.append((elem_type, re.compile(pattern_str, flags)))
    return patterns


def _compile_field_patterns(config):
    """Compile field patterns from config into a single regex."""
    parts = []
    for pc in config.get("field_patterns", []):
        pattern_str = pc.get("pattern", "")
        if pattern_str:
            parts.append(pattern_str)
    fallback = r"username|password|email|phone|address|city|zip|card.?number|expiry|cvv|first.?name|last.?name|name|search|date|amount"
    combined = "|".join(parts) if parts else fallback
    return re.compile(rf"\b({combined})\s*(?:field|input|textbox|box)?\b", re.IGNORECASE)


def _load_heuristics_config():
    """Load heuristics configuration from YAML file."""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "config", "heuristics.yaml"
    )
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        return {
            "page_keywords": _compile_page_keywords(config),
            "element_patterns": _compile_element_patterns(config),
            "field_pattern": _compile_field_patterns(config),
        }
    except Exception as e:
        # Fallback to hardcoded values if config loading fails
        print(f"Warning: Failed to load heuristics config: {e}. Using fallback values.")
        page_keywords = re.compile(
            r"\b(page|screen|view|dashboard|form|panel|dialog|modal|popup|window|tab)\b",
            re.IGNORECASE,
        )
        element_patterns = [
            ("button", re.compile(r"\b(\w[\w\s]{0,30})\s+button\b", re.IGNORECASE)),
            ("button", re.compile(r"\bbutton\s+([\w\s]{1,30})\b", re.IGNORECASE)),
            ("link", re.compile(r"\b(\w[\w\s]{0,30})\s+link\b", re.IGNORECASE)),
            ("link", re.compile(r"\blink\s+(?:to\s+)?([\w\s]{1,30})\b", re.IGNORECASE)),
            (
                "input",
                re.compile(
                    r"\b(\w[\w\s]{0,30})\s+(?:input|field|textbox|text\s*box)\b", re.IGNORECASE
                ),
            ),
            ("input", re.compile(r"\b(?:input|field|textbox)\s+([\w\s]{1,30})\b", re.IGNORECASE)),
            (
                "select",
                re.compile(
                    r"\b(\w[\w\s]{0,30})\s+(?:dropdown|select|combo\s*box)\b", re.IGNORECASE
                ),
            ),
            ("checkbox", re.compile(r"\b(\w[\w\s]{0,30})\s+checkbox\b", re.IGNORECASE)),
            ("radio", re.compile(r"\b(\w[\w\s]{0,30})\s+radio\b", re.IGNORECASE)),
        ]
        field_patterns = re.compile(
            r"\b(username|password|email|phone|address|city|zip|card.?number|"
            r"expiry|cvv|first.?name|last.?name|name|search|date|amount)\s*"
            r"(?:field|input|textbox|box)?\b",
            re.IGNORECASE,
        )
        return {
            "page_keywords": page_keywords,
            "element_patterns": element_patterns,
            "field_pattern": field_patterns,
        }


# Load heuristics configuration
_HEURISTICS_CONFIG = _load_heuristics_config()
_PAGE_KEYWORDS = _HEURISTICS_CONFIG["page_keywords"]
_ELEMENT_PATTERNS = _HEURISTICS_CONFIG["element_patterns"]
_FIELD_PATTERN = _HEURISTICS_CONFIG["field_pattern"]


class DiscrepancyDetector:
    """Compare a site model against requirements to find gaps."""

    def detect(
        self,
        site_model: SiteModelArtifact,
        requirements: List[RequirementArtifact],
    ) -> DiscrepancyReportArtifact:
        """
        Run all detection strategies and produce an aggregated report.

        Args:
            site_model: The crawled site structure.
            requirements: List of requirement artifacts to validate against.

        Returns:
            A DiscrepancyReportArtifact with items, counts, and gate decision.
        """
        items: List[DiscrepancyArtifact] = []

        items.extend(self._detect_missing_elements(site_model, requirements))
        items.extend(self._detect_missing_form_fields(site_model, requirements))

        # Compute summary
        show_stoppers = sum(1 for i in items if i.severity == "show_stopper")
        warnings = sum(1 for i in items if i.severity == "warning")
        infos = sum(1 for i in items if i.severity == "info")
        gate = self._compute_gate_decision(items)

        total = len(items)
        summary_parts = []
        if total == 0:
            summary_parts.append("No discrepancies found.")
        else:
            summary_parts.append(f"{total} discrepancy(ies) found.")
            if show_stoppers:
                summary_parts.append(f"{show_stoppers} show-stopper(s).")
            if warnings:
                summary_parts.append(f"{warnings} warning(s).")

        return DiscrepancyReportArtifact(
            summary=" ".join(summary_parts),
            total_requirements=len(requirements),
            total_discrepancies=total,
            show_stoppers=show_stoppers,
            warnings=warnings,
            infos=infos,
            items=items,
            gate_decision=gate,
        )

    # ------------------------------------------------------------------
    # Detection strategies
    # ------------------------------------------------------------------

    def _detect_missing_elements(
        self,
        site_model: SiteModelArtifact,
        requirements: List[RequirementArtifact],
    ) -> List[DiscrepancyArtifact]:
        """
        Check if elements referenced in acceptance criteria exist in the site model.

        Scans AC text for patterns like "Submit button", "email input", etc.
        """
        results: List[DiscrepancyArtifact] = []

        # Build a lookup of all elements by type and text (lowercased)
        all_elements: Dict[str, Set[str]] = {}
        for page in site_model.pages:
            for elem in page.elements:
                etype = elem.element_type.lower()
                if etype not in all_elements:
                    all_elements[etype] = set()
                all_elements[etype].add(elem.text.lower().strip())
                all_elements[etype].add(elem.name.lower().strip())

        for req in requirements:
            ac_text = " ".join(req.acceptance_criteria) + " " + req.description
            for elem_type, pattern in _ELEMENT_PATTERNS:
                for match in pattern.finditer(ac_text):
                    name = match.group(1).strip().lower()
                    if not name or len(name) < 2:
                        continue

                    # Check if any element of this type matches the name
                    # Match bidirectionally: name in element OR element in name
                    type_elements = all_elements.get(elem_type, set())
                    found = any(
                        (name in e or e in name)
                        for e in type_elements
                        if e  # skip empty strings
                    )

                    if not found:
                        severity = self._classify_severity(req)
                        results.append(
                            DiscrepancyArtifact(
                                discrepancy_type="missing_element",
                                requirement_id=req.req_id,
                                expected=f"{name} {elem_type}",
                                actual=f"No matching {elem_type} found in site model",
                                severity=severity,
                                details=(
                                    f"Requirement '{req.title}' references a "
                                    f"'{name}' {elem_type} but it was not found "
                                    f"in any crawled page."
                                ),
                            )
                        )

        return results

    def _detect_missing_form_fields(
        self,
        site_model: SiteModelArtifact,
        requirements: List[RequirementArtifact],
    ) -> List[DiscrepancyArtifact]:
        """
        Check if form fields referenced in requirements exist in crawled forms.
        """
        results: List[DiscrepancyArtifact] = []

        # Build a set of all form field names across all pages
        all_field_names: Set[str] = set()
        for page in site_model.pages:
            for form in page.forms:
                for field in form.get("fields", []):
                    fname = field.get("name", "").lower().strip()
                    if fname:
                        all_field_names.add(fname)

        for req in requirements:
            ac_text = " ".join(req.acceptance_criteria) + " " + req.description
            for match in _FIELD_PATTERN.finditer(ac_text):
                field_name = match.group(1).strip().lower()
                if not field_name or len(field_name) < 2:
                    continue

                # Normalize common patterns: "card number" -> "card_number"
                field_name_normalized = field_name.replace(" ", "_").replace("-", "_")

                # Check if any form field matches
                found = any(
                    field_name in fn or field_name_normalized in fn or fn in field_name
                    for fn in all_field_names
                )

                if not found:
                    severity = self._classify_severity(req, default="warning")
                    results.append(
                        DiscrepancyArtifact(
                            discrepancy_type="missing_form_field",
                            requirement_id=req.req_id,
                            expected=f"Form field '{field_name}'",
                            actual="No matching form field found in any form",
                            severity=severity,
                            details=(
                                f"Requirement '{req.title}' references a "
                                f"'{field_name}' field but it was not found "
                                f"in any crawled form."
                            ),
                        )
                    )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _classify_severity(
        self,
        requirement: RequirementArtifact,
        default: str = "warning",
    ) -> str:
        """Map requirement priority to discrepancy severity."""
        priority = requirement.priority.lower()
        if priority in ("critical",):
            return "show_stopper"
        elif priority in ("high",):
            return "warning"
        elif priority in ("medium", "low"):
            return "info"
        return default

    def _compute_gate_decision(self, items: List[DiscrepancyArtifact]) -> str:
        """
        Determine the pipeline gate decision based on discrepancy severities.

        - block: any show_stopper exists
        - proceed_with_warnings: warnings exist but no show_stoppers
        - proceed: clean report
        """
        has_show_stopper = any(i.severity == "show_stopper" for i in items)
        has_warning = any(i.severity == "warning" for i in items)

        if has_show_stopper:
            return "block"
        elif has_warning:
            return "proceed_with_warnings"
        return "proceed"
