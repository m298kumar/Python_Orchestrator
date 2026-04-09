"""
Component Resolver
==================
Resolves a specific screen/service name from LLM output, ChromaDB vocab,
configurable suffix map, or constructed fallback.

4-tier priority:
  1. LLM returned a specific, non-generic name → keep it
  2. ChromaDB domain_vocab lookup → dynamic, domain-agnostic
  3. Configurable suffix map keyword match → generic fallback
  4. Construct from category/title → last resort
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from stlc_platform.agents.requirements_agent.constants import (
    DEFAULT_COMPONENT_SUFFIX_MAP,
    DEFAULT_GENERIC_APP_NAMES,
)


class ComponentResolver:
    """Resolves component names for test cases.

    Args:
        suffix_map: Keyword → screen name mapping. Defaults to built-in map.
        generic_names: Set of names considered too generic. Defaults to built-in set.
        vector_store: Optional ChromaDB vector store for domain_vocab lookup.
    """

    def __init__(
        self,
        suffix_map: Optional[Dict[str, str]] = None,
        generic_names: Optional[Set[str]] = None,
        vector_store: Any = None,
    ):
        self._suffix_map = suffix_map or dict(DEFAULT_COMPONENT_SUFFIX_MAP)
        self._generic_names = generic_names or set(DEFAULT_GENERIC_APP_NAMES)
        self._vector_store = vector_store

    def _is_specific_llm_name(self, raw_clean: str) -> bool:
        """Check if the LLM-returned name is specific enough to keep as-is."""
        if not raw_clean or len(raw_clean) <= 15:
            return False
        lower = raw_clean.lower()
        if "specific screen" in lower or "not a generic" in lower:
            return False
        return not any(g in lower for g in self._generic_names)

    def resolve(
        self,
        raw: str,
        category: str,
        req_title: str = "",
        ac_text: str = "",
    ) -> str:
        """Resolve a component name using the 4-tier priority system.

        Args:
            raw: The raw component name from LLM output.
            category: Requirement category.
            req_title: Requirement title.
            ac_text: Target acceptance criterion text.

        Returns:
            A resolved component name string.
        """
        # 1. LLM returned something specific — keep it
        raw_clean = raw.strip()
        if self._is_specific_llm_name(raw_clean):
            return raw_clean

        # 2. ChromaDB domain_vocab lookup
        if self._vector_store is not None:
            try:
                result = self._vector_store.lookup_component(category, req_title, ac_text)
                if result:
                    return str(result)
            except (AttributeError, RuntimeError, OSError):
                pass  # graceful degradation

        # 3. Suffix map keyword match
        match = self._match_suffix_map(category, req_title)
        if match:
            return match

        # 4. Construct from category or title
        return self._construct_fallback(category, req_title)

    def _match_suffix_map(self, category: str, req_title: str) -> str:
        """Try to match a component name from the suffix map."""
        for source in [category, req_title]:
            s = source.strip().lower()
            for key, val in self._suffix_map.items():
                if key in s:
                    prefix = " ".join(w.capitalize() for w in source.strip().split())
                    if len(prefix) > len(key) + 3:
                        return f"{prefix} Screen"
                    return val
        return ""

    @staticmethod
    def _construct_fallback(category: str, req_title: str) -> str:
        """Construct a component name from category or title as last resort."""
        if category.strip():
            return f"{' '.join(w.capitalize() for w in category.strip().split())} Screen"
        if req_title.strip():
            return f"{req_title[:40].strip()} Screen"
        return "Application Screen"
