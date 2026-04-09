"""
Domain Detector
================
Infers a plain-English domain label from requirement metadata using
configurable keyword maps. No hardcoded domain references — all keywords
are loaded from configuration or passed explicitly.

Replaces the legacy `_infer_domain()` function from test_generator.py
with a fully configurable, testable class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# Default domain keywords — extracted from legacy _infer_domain() and made configurable.
_DEFAULT_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "financial services": [
        "cheque",
        "banking",
        "deposit",
        "rcd",
        "micr",
        "clearing",
        "transaction",
        "account",
        "ledger",
        "transfer",
        "payment",
    ],
    "healthcare": [
        "patient",
        "clinical",
        "ehr",
        "prescription",
        "pharmacy",
        "diagnosis",
        "medical",
        "health",
        "hospital",
        "appointment",
    ],
    "retail e-commerce": [
        "product",
        "cart",
        "checkout",
        "inventory",
        "catalogue",
        "order",
        "shipping",
        "storefront",
        "wishlist",
        "coupon",
    ],
    "insurance": [
        "policy",
        "claim",
        "premium",
        "underwriting",
        "insur",
        "coverage",
        "deductible",
        "adjuster",
        "beneficiary",
    ],
    "education": [
        "student",
        "course",
        "enrol",
        "grade",
        "curriculum",
        "lms",
        "assignment",
        "syllabus",
        "semester",
        "faculty",
    ],
    "IT service management": [
        "ticket",
        "incident",
        "asset",
        "sla",
        "helpdesk",
        "itil",
        "change request",
        "service desk",
        "escalation",
    ],
}


@dataclass
class DomainDetector:
    """
    Detects application domain from requirement category/title text.

    Uses a configurable keyword map (domain → keywords list). Matches are
    scored by keyword hit count; the domain with the most hits wins.

    Usage:
        detector = DomainDetector()
        domain = detector.detect(requirements)  # → "healthcare"

        # With custom keywords:
        detector = DomainDetector(domain_keywords={
            "logistics": ["shipment", "warehouse", "freight", "tracking"],
        })
    """

    domain_keywords: Dict[str, List[str]] = field(
        default_factory=lambda: dict(_DEFAULT_DOMAIN_KEYWORDS)
    )

    def detect(self, requirements: Sequence[Any]) -> str:
        """
        Infer domain label from a list of requirement objects.

        Extracts category and title text from each requirement, then scores
        each configured domain by keyword match count.

        Args:
            requirements: Sequence of objects with optional `category` and `title` attrs.

        Returns:
            Detected domain label (e.g., "healthcare"), or the first category/title
            as a fallback, or empty string if no requirements provided.
        """
        if not requirements:
            return ""

        combined = self._extract_text(requirements)
        if not combined.strip():
            return ""

        return self._match_domain(combined, requirements)

    def detect_from_text(self, text: str) -> str:
        """
        Detect domain from arbitrary text (e.g., concatenated requirement descriptions).

        Args:
            text: Free-form text to scan for domain keywords.

        Returns:
            Best-matching domain label, or empty string if no match.
        """
        if not text.strip():
            return ""

        best_domain = ""
        best_score = 0

        lower = text.lower()
        for domain, keywords in self.domain_keywords.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_domain = domain

        return best_domain

    def add_domain(self, domain: str, keywords: List[str]) -> None:
        """
        Register a new domain (or extend an existing one) with keywords.

        Args:
            domain: Domain label (e.g., "logistics").
            keywords: List of keyword strings to associate.
        """
        if domain in self.domain_keywords:
            existing = set(self.domain_keywords[domain])
            existing.update(keywords)
            self.domain_keywords[domain] = sorted(existing)
        else:
            self.domain_keywords[domain] = list(keywords)

    @classmethod
    def from_config(cls, config_dict: Optional[Dict[str, List[str]]] = None) -> "DomainDetector":
        """
        Create a DomainDetector from a YAML config dictionary.

        Args:
            config_dict: Mapping of domain name → keyword list. If None, uses defaults.

        Returns:
            Configured DomainDetector instance.
        """
        if config_dict is None:
            return cls()
        return cls(domain_keywords=dict(config_dict))

    # -- Private helpers -------------------------------------------------------

    def _extract_text(self, requirements: Sequence[Any]) -> str:
        """Extract category and title text from requirements into a single string."""
        parts: List[str] = []
        for req in requirements:
            if hasattr(req, "category") and req.category:
                parts.append(req.category.lower())
            if hasattr(req, "title") and req.title:
                parts.append(req.title.lower())
        return " ".join(parts)

    def _match_domain(self, combined: str, requirements: Sequence[Any]) -> str:
        """Score each domain by keyword hits, return best match or fallback."""
        best_domain = ""
        best_score = 0

        for domain, keywords in self.domain_keywords.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > best_score:
                best_score = score
                best_domain = domain

        if best_domain:
            return best_domain

        # Fallback: use first category or title as the domain label
        for req in requirements:
            if hasattr(req, "category") and req.category:
                return str(req.category).title()
            if hasattr(req, "title") and req.title:
                return str(req.title).title()

        return ""
