"""
HAR File Parser
===============
Parses HTTP Archive (HAR) files into APIModelArtifact for downstream
API test generation.

HAR files are JSON exports from browser DevTools or proxy tools (Fiddler,
Charles, mitmproxy) containing captured HTTP request/response pairs.

Supports:
  - HAR 1.2 format (standard)
  - Filtering by MIME type (JSON/XML API calls only)
  - Deduplication of endpoints (same method + path pattern)
  - Path parameter extraction (numeric IDs → {id})
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, parse_qs

from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact


# MIME types that indicate API calls
_API_MIME_TYPES = {
    "application/json",
    "application/xml",
    "text/xml",
    "application/x-www-form-urlencoded",
}

# Static asset extensions to exclude
_STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map", ".html", ".htm",
}

# HTTP methods to include
_API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


class HARParser:
    """
    Parse HAR (HTTP Archive) files into APIModelArtifact.

    Usage:
        parser = HARParser()
        model = parser.parse(har_json_string)
        # or
        model = parser.parse(har_dict)
    """

    def parse(
        self,
        har: Union[str, dict],
        base_url_filter: str = "",
    ) -> APIModelArtifact:
        """
        Parse a HAR file into an APIModelArtifact.

        Args:
            har: HAR JSON string or already-parsed dict.
            base_url_filter: Optional base URL to filter entries
                            (only include requests matching this origin).

        Returns:
            APIModelArtifact with discovered endpoints.

        Raises:
            ValueError: If the HAR format is invalid.
        """
        if isinstance(har, str):
            try:
                har = json.loads(har)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid HAR JSON: {e}")

        if not isinstance(har, dict) or "log" not in har:
            raise ValueError(
                "Invalid HAR format: expected object with 'log' key."
            )

        log = har["log"]
        entries = log.get("entries", [])

        if not entries:
            return APIModelArtifact(
                endpoints=[],
                base_url=base_url_filter,
                auth_type="unknown",
                spec_format="har",
            )

        # Filter and extract API entries
        api_entries = self._filter_api_entries(entries, base_url_filter)

        # Deduplicate endpoints (same method + parameterized path)
        endpoints = self._build_endpoints(api_entries, base_url_filter)

        # Infer base URL if not provided
        base_url = base_url_filter
        if not base_url and api_entries:
            base_url = self._infer_base_url(api_entries)

        # Detect auth type from headers
        auth_type = self._detect_auth_type(api_entries)

        return APIModelArtifact(
            endpoints=endpoints,
            base_url=base_url,
            auth_type=auth_type,
            spec_format="har",
        )

    def _filter_api_entries(
        self,
        entries: List[Dict[str, Any]],
        base_url_filter: str,
    ) -> List[Dict[str, Any]]:
        """Filter HAR entries to API-relevant requests only."""
        api_entries = []

        for entry in entries:
            request = entry.get("request", {})
            response = entry.get("response", {})

            method = request.get("method", "").upper()
            url = request.get("url", "")

            # Skip non-API methods
            if method not in _API_METHODS:
                continue

            # Skip static assets
            parsed = urlparse(url)
            path = parsed.path.lower()
            if any(path.endswith(ext) for ext in _STATIC_EXTENSIONS):
                continue

            # Apply base URL filter
            if base_url_filter:
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if not origin.startswith(base_url_filter.rstrip("/")):
                    continue

            # Check MIME type (request or response)
            resp_content = response.get("content", {})
            resp_mime = resp_content.get("mimeType", "")
            req_mime = self._get_request_content_type(request)

            is_api = (
                any(m in resp_mime for m in _API_MIME_TYPES)
                or any(m in req_mime for m in _API_MIME_TYPES)
                or "/api/" in url
                or "/graphql" in url
            )

            if is_api:
                api_entries.append(entry)

        return api_entries

    def _build_endpoints(
        self,
        entries: List[Dict[str, Any]],
        base_url: str,
    ) -> List[APIEndpointArtifact]:
        """Build deduplicated API endpoints from HAR entries."""
        seen_signatures: Dict[str, APIEndpointArtifact] = {}

        for entry in entries:
            request = entry.get("request", {})
            response = entry.get("response", {})

            method = request.get("method", "").upper()
            url = request.get("url", "")
            parsed = urlparse(url)

            # Parameterize path (replace numeric IDs with {id})
            path = self._parameterize_path(parsed.path)

            # Build signature for dedup
            sig = f"{method} {path}"
            if sig in seen_signatures:
                continue

            # Extract query params
            query_params = []
            for name, values in parse_qs(parsed.query).items():
                query_params.append({
                    "name": name,
                    "type": "string",
                    "example": values[0] if values else "",
                })

            # Extract path params
            path_params = []
            for match in re.finditer(r"\{(\w+)\}", path):
                path_params.append({
                    "name": match.group(1),
                    "type": "string",
                })

            # Extract request body schema (basic)
            request_body = self._extract_request_body(request)

            # Extract response schema (basic)
            response_body = self._extract_response_body(response)

            # Detect auth requirement
            auth_required = self._has_auth_header(request)

            status = response.get("status", 200)

            endpoint = APIEndpointArtifact(
                path=path,
                method=method,
                path_params=path_params,
                query_params=query_params,
                request_body_schema=request_body,
                response_schema=response_body,
                auth_required=auth_required,
                auth_type="bearer" if auth_required else "none",
                example_request=request_body,
                example_response=response_body,
                status_codes=[status],
                tags=[],
            )
            seen_signatures[sig] = endpoint

        return list(seen_signatures.values())

    def _parameterize_path(self, path: str) -> str:
        """Replace numeric path segments with parameter placeholders."""
        parts = path.strip("/").split("/")
        result = []
        for part in parts:
            if re.match(r"^\d+$", part):
                result.append("{id}")
            elif re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", part, re.IGNORECASE):
                result.append("{uuid}")
            else:
                result.append(part)
        return "/" + "/".join(result) if result else "/"

    def _extract_request_body(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract and parse request body."""
        post_data = request.get("postData", {})
        text = post_data.get("text", "")
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return {"items": parsed}
            return dict(parsed)
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}

    def _extract_response_body(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract and parse response body."""
        content = response.get("content", {})
        text = content.get("text", "")
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return {"items": parsed}
            return dict(parsed)
        except (json.JSONDecodeError, TypeError):
            return None

    def _has_auth_header(self, request: Dict[str, Any]) -> bool:
        """Check if request has an authorization header."""
        headers = request.get("headers", [])
        for header in headers:
            name = header.get("name", "").lower()
            if name in ("authorization", "x-api-key", "x-auth-token"):
                return True
        return False

    def _get_request_content_type(self, request: Dict[str, Any]) -> str:
        """Get Content-Type from request headers."""
        headers = request.get("headers", [])
        for header in headers:
            if header.get("name", "").lower() == "content-type":
                return str(header.get("value", ""))
        return ""

    def _detect_auth_type(self, entries: List[Dict[str, Any]]) -> str:
        """Detect the predominant auth type from HAR entries."""
        for entry in entries:
            request = entry.get("request", {})
            headers = request.get("headers", [])
            for header in headers:
                name = header.get("name", "").lower()
                value = header.get("value", "").lower()
                if name == "authorization":
                    if "bearer" in value:
                        return "bearer"
                    elif "basic" in value:
                        return "basic"
                if name == "x-api-key":
                    return "api_key"
        return "none"

    def _infer_base_url(self, entries: List[Dict[str, Any]]) -> str:
        """Infer base URL from the most common origin in entries."""
        origins: Dict[str, int] = {}
        for entry in entries:
            url = entry.get("request", {}).get("url", "")
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            origins[origin] = origins.get(origin, 0) + 1

        if origins:
            return max(origins, key=lambda k: origins[k])
        return ""
