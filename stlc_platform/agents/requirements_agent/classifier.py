"""
AC Type Classifier
==================
Classifies acceptance criteria into configurable types using a two-tier approach:
  1. Fast path: keyword matching against configurable keyword lists
  2. LLM path: fallback when fast path confidence is low

AC types are loaded from config (stlc_config.yaml → test_generation.ac_types)
or fall back to built-in defaults extracted from the legacy classifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ACTypeConfig:
    """Configuration for a single AC type."""

    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    priority: int = 0  # Lower = checked first


@dataclass
class ClassificationResult:
    """Result of classifying an acceptance criterion."""

    ac_type: str
    confidence: float  # 1.0 for keyword match, 0.0-1.0 for LLM
    method: str  # "keyword" or "llm"


def default_ac_types() -> List[ACTypeConfig]:
    """Return the 6 built-in AC types with their generic keyword lists.

    These are extracted from the legacy _classify_ac() function and are
    intentionally domain-agnostic — they work across banking, healthcare,
    retail, insurance, education, and IT service management.
    """
    return [
        ACTypeConfig(
            name="security",
            description="Authentication, encryption, session control, MFA",
            keywords=[
                "biometric", "otp", "certificate pinning", "screenshot",
                "screen recording", "rooted", "jailbreak", "session timeout",
                "session hard", "encrypt", "hash", "auth token",
                "re-authenticate", "re-verify", "ssl", "tls", "certificate",
                "pinning", "security feature", "multi-factor", "mfa", "2fa",
                "two-factor", "access token", "tamper", "intrusion",
                "anomaly detection", "fraud detection",
            ],
            priority=0,
        ),
        ACTypeConfig(
            name="timing",
            description="Time limits, deadlines, performance thresholds, SLAs",
            keywords=[
                "within ", "seconds", "minutes", "hours", "days", "timeout",
                "t+1", "t+2", "t+3", "millisecond", "latency", "cutoff",
                "business hours", "sla", "response time", "no longer than",
                "at most",
            ],
            priority=1,
        ),
        ACTypeConfig(
            name="eligibility",
            description="Rules about who/what qualifies, access gating",
            keywords=[
                "eligible", "ineligible", "eligibility", "enrolled", "enroll",
                "not allowed", "not permitted", "access denied", "unauthorised",
                "unauthorized", "restricted to", "only allowed",
                "must be a member", "membership required", "tier ",
                " tier", "subscription", "licence required",
                "license required", "only users", "only customers",
                "only agents", "only staff", "only admin", "must present",
                "must provide valid", "requires role", "must have role",
                "must hold", "requires permission", "requires a valid",
            ],
            priority=2,
        ),
        ACTypeConfig(
            name="data_valid",
            description="Validation rules on fields/submitted values",
            keywords=[
                "validated", "validation", "format validated", "digits",
                "numeric", "date picker", "future dates", "minimum",
                "exactly", "> 100", "< 40%", "< 75%", ">85%", ">95%",
                "confidence score", "dpi", "characters", "contrast ratio",
                "blur", "inline error", "must not exceed", "must be between",
                "required format", "allowed values", "cannot be empty",
                "max length", "min length", "alphanumeric", "maximum",
                "field is required", "mandatory field",
            ],
            priority=3,
        ),
        ACTypeConfig(
            name="ui_behaviour",
            description="User interface interactions and visual feedback",
            keywords=[
                "shown", "displayed", "visible", "appears", "prompt", "button",
                "overlay", "badge", "spinner", "indicator", "launches",
                "screen", "message", "notification", "banner", "toast",
                "alert", "highlight", "colour", "color", "icon", "label",
                "shows", "listed", "accessible", "pre-populated", "paginated",
                "sorted", "search by", "deep link", "toggle", "thumbnail",
                "pinch-to-zoom", "colour-coded", "landscape", "overlay guide",
                "sequential flow", "auto-capture", "brightness",
                "focus quality",
            ],
            priority=4,
        ),
        ACTypeConfig(
            name="general",
            description="General acceptance criteria (fallback)",
            keywords=[],
            priority=99,
        ),
    ]


class ACClassifier:
    """Classifies acceptance criteria into configurable types.

    Two-tier classification:
      1. Fast keyword matching against configured type keyword lists
      2. Optional LLM fallback when keyword confidence is low

    Args:
        ac_types: List of ACTypeConfig objects. Defaults to built-in types.
        llm_confidence_threshold: Minimum confidence for keyword path to
            be accepted without LLM fallback. Default 0.5.
    """

    def __init__(
        self,
        ac_types: Optional[List[ACTypeConfig]] = None,
        llm_confidence_threshold: float = 0.5,
    ):
        self._types = ac_types or default_ac_types()
        # Sort by priority (lower first)
        self._types = sorted(self._types, key=lambda t: t.priority)
        self._llm_threshold = llm_confidence_threshold

    @property
    def ac_types(self) -> List[ACTypeConfig]:
        """Return configured AC types."""
        return list(self._types)

    @property
    def type_names(self) -> List[str]:
        """Return list of configured type names."""
        return [t.name for t in self._types]

    def classify(self, ac_text: str) -> ClassificationResult:
        """Classify an AC using keyword matching (fast path).

        Args:
            ac_text: The acceptance criterion text.

        Returns:
            ClassificationResult with type, confidence, and method.
        """
        a = ac_text.lower()

        for ac_type in self._types:
            if not ac_type.keywords:
                continue
            if any(k in a for k in ac_type.keywords):
                return ClassificationResult(
                    ac_type=ac_type.name,
                    confidence=1.0,
                    method="keyword",
                )

        # No keyword match — return general with low confidence
        return ClassificationResult(
            ac_type="general",
            confidence=0.3,
            method="keyword",
        )

    def classify_with_llm(
        self,
        ac_text: str,
        llm_client: Any,
    ) -> ClassificationResult:
        """Classify an AC using LLM when keyword confidence is low.

        Args:
            ac_text: The acceptance criterion text.
            llm_client: A BaseLLMClient instance.

        Returns:
            ClassificationResult from LLM classification.
        """
        type_descriptions = "\n".join(
            f"  - {t.name}: {t.description}"
            for t in self._types
            if t.name != "general"
        )

        prompt = (
            f"Classify the following acceptance criterion into exactly one type.\n\n"
            f"Types:\n{type_descriptions}\n"
            f"  - general: Anything that doesn't fit the above categories\n\n"
            f"Acceptance Criterion: {ac_text}\n\n"
            f"Reply with ONLY the type name (e.g., 'security', 'timing', etc.):"
        )

        try:
            response = llm_client.generate(prompt=prompt, temperature=0.1)
            response = response.strip().lower().replace('"', '').replace("'", "")

            # Validate response is a known type
            known_types = {t.name for t in self._types}
            if response in known_types:
                return ClassificationResult(
                    ac_type=response,
                    confidence=0.8,
                    method="llm",
                )
        except Exception:
            pass

        # LLM failed or returned unknown type — fall back to general
        return ClassificationResult(
            ac_type="general",
            confidence=0.3,
            method="llm",
        )

    def classify_smart(
        self,
        ac_text: str,
        llm_client: Optional[Any] = None,
    ) -> ClassificationResult:
        """Two-tier classification: keyword first, LLM if confidence is low.

        Args:
            ac_text: The acceptance criterion text.
            llm_client: Optional BaseLLMClient. If None, only keyword path is used.

        Returns:
            ClassificationResult from the best available method.
        """
        result = self.classify(ac_text)

        if result.confidence >= self._llm_threshold:
            return result

        if llm_client is not None:
            return self.classify_with_llm(ac_text, llm_client)

        return result

    @classmethod
    def from_config(cls, config_list: List[Dict[str, Any]]) -> "ACClassifier":
        """Create an ACClassifier from config dict list.

        Expected format (from stlc_config.yaml):
            ac_types:
              - name: security
                description: "Authentication, encryption, session control"
                keywords: [biometric, otp, encrypt, ...]
              - name: custom_type
                description: "My custom AC type"
                keywords: [keyword1, keyword2]

        Args:
            config_list: List of dicts with name, description, keywords.

        Returns:
            Configured ACClassifier.
        """
        types = []
        for i, item in enumerate(config_list):
            types.append(ACTypeConfig(
                name=item["name"],
                description=item.get("description", ""),
                keywords=item.get("keywords", []),
                priority=i,
            ))
        return cls(ac_types=types)
