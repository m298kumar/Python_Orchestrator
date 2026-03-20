"""
Tech Stack Context
==================
Platform-specific verb mapping and test type modifiers for prompt generation.

Provides context-aware language substitution so prompts read naturally for
web ("click"), mobile ("tap"), API ("send request"), and desktop ("click")
platforms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# Default verb mappings per platform
_DEFAULT_PLATFORM_VERBS: Dict[str, Dict[str, str]] = {
    "web": {
        "click": "click",
        "navigate": "navigate to",
        "page_loads": "page loads",
        "input": "enter",
        "submit": "submit",
        "select": "select",
        "view": "view",
        "screen": "page",
    },
    "mobile": {
        "click": "tap",
        "navigate": "navigate to",
        "page_loads": "screen appears",
        "input": "enter",
        "submit": "submit",
        "select": "select",
        "view": "view",
        "screen": "screen",
    },
    "api": {
        "click": "send request",
        "navigate": "call endpoint",
        "page_loads": "response is received",
        "input": "set parameter",
        "submit": "send",
        "select": "specify",
        "view": "inspect response",
        "screen": "endpoint",
    },
    "desktop": {
        "click": "click",
        "navigate": "open",
        "page_loads": "window loads",
        "input": "enter",
        "submit": "submit",
        "select": "select",
        "view": "view",
        "screen": "window",
    },
}

# Platform-specific test modifiers (hints appended to prompts)
_DEFAULT_PLATFORM_MODIFIERS: Dict[str, Dict[str, str]] = {
    "web": {
        "positive": "Verify the feature works correctly in the browser.",
        "negative": "Test invalid inputs and error handling in the UI.",
        "edge_case": "Test boundary conditions, timeouts, and concurrent sessions.",
    },
    "mobile": {
        "positive": "Verify the feature works correctly on mobile devices.",
        "negative": "Test invalid inputs and error states on the device.",
        "edge_case": "Test offline mode, low memory, orientation changes, and interruptions.",
    },
    "api": {
        "positive": "Verify the endpoint returns correct responses for valid requests.",
        "negative": "Test invalid payloads, missing fields, and authentication failures.",
        "edge_case": "Test rate limiting, large payloads, concurrent requests, and timeout handling.",
    },
    "desktop": {
        "positive": "Verify the feature works correctly in the desktop application.",
        "negative": "Test invalid inputs and error handling in the application.",
        "edge_case": "Test system resource limits, multi-monitor, and OS-specific behaviors.",
    },
}


@dataclass
class TechStackContext:
    """
    Provides platform-aware verb substitution and test modifiers.

    Usage:
        ctx = TechStackContext.from_config({"platform": "mobile"})
        verb = ctx.get_verb("click")  # → "tap"
        modifier = ctx.get_test_modifier("edge_case")  # → mobile edge hint
    """

    platform: str = "web"
    frontend: str = ""
    backend: str = "rest"
    database: str = ""
    auth: str = ""
    platform_verbs: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: dict(_DEFAULT_PLATFORM_VERBS)
    )
    platform_modifiers: Dict[str, Dict[str, str]] = field(
        default_factory=lambda: dict(_DEFAULT_PLATFORM_MODIFIERS)
    )

    def get_verb(self, action: str) -> str:
        """
        Get the platform-appropriate verb for a generic action.

        Args:
            action: Generic action name (e.g., "click", "navigate", "page_loads").

        Returns:
            Platform-specific verb string. Falls back to the action name itself.
        """
        verbs = self.platform_verbs.get(self.platform, {})
        return verbs.get(action, action)

    def get_all_verbs(self) -> Dict[str, str]:
        """Return all verb mappings for the current platform."""
        return dict(self.platform_verbs.get(self.platform, {}))

    def get_test_modifier(self, test_type: str) -> str:
        """
        Get platform-specific test modifier text.

        Args:
            test_type: One of "positive", "negative", "edge_case".

        Returns:
            Modifier text string. Empty string if not found.
        """
        modifiers = self.platform_modifiers.get(self.platform, {})
        return modifiers.get(test_type, "")

    def get_platform_summary(self) -> str:
        """
        Produce a one-line summary of the tech stack for prompt injection.

        Returns:
            e.g. "web application (React frontend, REST backend, JWT auth)"
        """
        parts = [f"{self.platform} application"]
        details = []
        if self.frontend:
            details.append(f"{self.frontend} frontend")
        if self.backend:
            details.append(f"{self.backend.upper()} backend")
        if self.database:
            details.append(f"{self.database} database")
        if self.auth:
            details.append(f"{self.auth.upper()} auth")
        if details:
            parts.append(f"({', '.join(details)})")
        return " ".join(parts)

    @classmethod
    def from_config(
        cls,
        tech_stack: Optional[Dict[str, Any]] = None,
        platform_verbs: Optional[Dict[str, Dict[str, str]]] = None,
        platform_modifiers: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> "TechStackContext":
        """
        Create a TechStackContext from a config dictionary.

        Args:
            tech_stack: Dict with keys like "platform", "frontend", "backend", etc.
            platform_verbs: Optional override for verb mappings.
            platform_modifiers: Optional override for test modifiers.

        Returns:
            Configured TechStackContext instance.
        """
        ts = tech_stack or {}
        verbs = platform_verbs or dict(_DEFAULT_PLATFORM_VERBS)
        modifiers = platform_modifiers or dict(_DEFAULT_PLATFORM_MODIFIERS)

        return cls(
            platform=ts.get("platform", "web"),
            frontend=ts.get("frontend", ""),
            backend=ts.get("backend", "rest"),
            database=ts.get("database", ""),
            auth=ts.get("auth", ""),
            platform_verbs=verbs,
            platform_modifiers=modifiers,
        )
