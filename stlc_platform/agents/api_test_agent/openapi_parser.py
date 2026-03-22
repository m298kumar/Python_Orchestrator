"""
OpenAPI / Swagger Spec Parser
=============================
Parses OpenAPI 3.x and Swagger 2.0 specification files (JSON or YAML)
into an APIModelArtifact for downstream test generation.

Supports:
  - OpenAPI 3.0 / 3.1 (detected by "openapi" key)
  - Swagger 2.0 (detected by "swagger" key)
  - Internal $ref resolution (#/components/schemas/... and #/definitions/...)

Extension points:
  - format_hint parameter for future HAR / GraphQL / gRPC parsers
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact


# HTTP methods we care about
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class OpenAPIParser:
    """Parse an OpenAPI or Swagger spec into an APIModelArtifact."""

    def parse(
        self,
        spec: Union[str, dict],
        format_hint: str = "",
    ) -> APIModelArtifact:
        """
        Parse a spec into an APIModelArtifact.

        Args:
            spec: JSON/YAML string or already-parsed dict.
            format_hint: Optional hint ("openapi_3.0", "swagger_2.0").
                         Auto-detected if empty.

        Returns:
            APIModelArtifact with discovered endpoints.

        Raises:
            ValueError: If the spec format cannot be detected.
        """
        if isinstance(spec, str):
            spec = self._load_spec_string(spec)

        version = format_hint or self._detect_format(spec)

        if version.startswith("openapi"):
            return self._parse_openapi_3(spec)
        elif version.startswith("swagger"):
            return self._parse_swagger_2(spec)
        else:
            raise ValueError(
                f"Unknown spec format: {version}. "
                "Expected 'openapi' or 'swagger' key in spec."
            )

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def _load_spec_string(self, raw: str) -> dict:
        """Parse a JSON or YAML string into a dict."""
        # Try JSON first (faster, more common for API specs)
        try:
            return dict(json.loads(raw))
        except json.JSONDecodeError:
            pass

        # Fall back to YAML
        try:
            import yaml
            return dict(yaml.safe_load(raw))
        except Exception:
            raise ValueError("Spec is not valid JSON or YAML.")

    def _detect_format(self, spec: dict) -> str:
        """Detect whether a spec is OpenAPI 3.x or Swagger 2.0."""
        if "openapi" in spec:
            return "openapi_3.0"
        elif "swagger" in spec:
            return "swagger_2.0"
        else:
            return "unknown"

    # ------------------------------------------------------------------
    # OpenAPI 3.x parsing
    # ------------------------------------------------------------------

    def _parse_openapi_3(self, spec: dict) -> APIModelArtifact:
        """Parse an OpenAPI 3.x spec."""
        info = spec.get("info", {})
        servers = spec.get("servers", [])
        base_url = servers[0]["url"] if servers else ""

        # Global security schemes
        global_security = spec.get("security", [])
        global_auth = self._detect_auth_from_security(
            global_security, spec, version=3
        )

        endpoints: List[APIEndpointArtifact] = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            # Path-level parameters (shared across methods)
            path_level_params = path_item.get("parameters", [])

            for method in _HTTP_METHODS:
                operation = path_item.get(method)
                if operation is None:
                    continue

                endpoint = self._extract_endpoint(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    root=spec,
                    version=3,
                    path_level_params=path_level_params,
                    global_auth=global_auth,
                )
                endpoints.append(endpoint)

        return APIModelArtifact(
            endpoints=endpoints,
            base_url=base_url,
            auth_type=global_auth[1] if global_auth[0] else "",
            spec_format="openapi_3.0",
            spec_title=info.get("title", ""),
        )

    # ------------------------------------------------------------------
    # Swagger 2.0 parsing
    # ------------------------------------------------------------------

    def _parse_swagger_2(self, spec: dict) -> APIModelArtifact:
        """Parse a Swagger 2.0 spec."""
        info = spec.get("info", {})
        host = spec.get("host", "")
        base_path = spec.get("basePath", "")
        schemes = spec.get("schemes", ["https"])
        base_url = f"{schemes[0]}://{host}{base_path}" if host else ""

        # Global security
        global_security = spec.get("security", [])
        global_auth = self._detect_auth_from_security(
            global_security, spec, version=2
        )

        endpoints: List[APIEndpointArtifact] = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            path_level_params = path_item.get("parameters", [])

            for method in _HTTP_METHODS:
                operation = path_item.get(method)
                if operation is None:
                    continue

                endpoint = self._extract_endpoint(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    root=spec,
                    version=2,
                    path_level_params=path_level_params,
                    global_auth=global_auth,
                )
                endpoints.append(endpoint)

        return APIModelArtifact(
            endpoints=endpoints,
            base_url=base_url,
            auth_type=global_auth[1] if global_auth[0] else "",
            spec_format="swagger_2.0",
            spec_title=info.get("title", ""),
        )

    # ------------------------------------------------------------------
    # Shared endpoint extraction
    # ------------------------------------------------------------------

    def _extract_endpoint(
        self,
        path: str,
        method: str,
        operation: dict,
        root: dict,
        version: int,
        path_level_params: List[dict],
        global_auth: Tuple[bool, str],
    ) -> APIEndpointArtifact:
        """Extract a single endpoint from an operation dict."""
        # Merge path-level and operation-level parameters
        op_params = operation.get("parameters", [])
        all_params = self._merge_params(path_level_params, op_params)

        # Detect auth for this operation
        op_security = operation.get("security")
        if op_security is not None:
            # Explicit security override (even [] means "no auth")
            if len(op_security) == 0:
                auth_required = False
                auth_type = ""
            else:
                auth_required, auth_type = self._detect_auth_from_security(
                    op_security, root, version
                )
        else:
            # Inherit global security
            auth_required, auth_type = global_auth

        return APIEndpointArtifact(
            path=path,
            method=method,
            path_params=self._extract_path_params(all_params),
            query_params=self._extract_query_params(all_params),
            request_body_schema=self._extract_request_body(
                operation, root, version, all_params
            ),
            response_schema=self._extract_response_schema(
                operation.get("responses", {}), root, version
            ),
            auth_required=auth_required,
            auth_type=auth_type,
            operation_id=operation.get("operationId", ""),
            summary=operation.get("summary", ""),
            tags=operation.get("tags", []),
            status_codes=self._extract_status_codes(
                operation.get("responses", {})
            ),
            examples=self._extract_examples(operation, version),
        )

    # ------------------------------------------------------------------
    # Parameter extraction
    # ------------------------------------------------------------------

    def _merge_params(
        self, path_params: List[dict], op_params: List[dict]
    ) -> List[dict]:
        """Merge path-level and operation-level params (op overrides path)."""
        merged: Dict[tuple, dict] = {}
        for p in path_params:
            key = (p.get("name", ""), p.get("in", ""))
            merged[key] = p
        for p in op_params:
            key = (p.get("name", ""), p.get("in", ""))
            merged[key] = p
        return list(merged.values())

    def _extract_path_params(self, params: List[dict]) -> List[Dict[str, str]]:
        """Extract path parameters."""
        result = []
        for p in params:
            if p.get("in") == "path":
                schema = p.get("schema", {})
                result.append({
                    "name": p.get("name", ""),
                    "type": schema.get("type", p.get("type", "string")),
                })
        return result

    def _extract_query_params(self, params: List[dict]) -> List[Dict[str, str]]:
        """Extract query parameters."""
        result = []
        for p in params:
            if p.get("in") == "query":
                schema = p.get("schema", {})
                result.append({
                    "name": p.get("name", ""),
                    "type": schema.get("type", p.get("type", "string")),
                    "required": str(p.get("required", False)).lower(),
                })
        return result

    # ------------------------------------------------------------------
    # Request body extraction
    # ------------------------------------------------------------------

    def _extract_request_body(
        self,
        operation: dict,
        root: dict,
        version: int,
        params: List[dict],
    ) -> Optional[Dict[str, Any]]:
        """Extract request body schema."""
        if version == 3:
            rb = operation.get("requestBody", {})
            content = rb.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema")
            if schema:
                return dict(self._resolve_ref(schema, root))
            return None
        else:
            # Swagger 2.0: body parameter
            for p in params:
                if p.get("in") == "body":
                    schema = p.get("schema")
                    if schema:
                        return dict(self._resolve_ref(schema, root))
            return None

    # ------------------------------------------------------------------
    # Response schema extraction
    # ------------------------------------------------------------------

    def _extract_response_schema(
        self,
        responses: dict,
        root: dict,
        version: int,
    ) -> Optional[Dict[str, Any]]:
        """Extract the success response schema (200 or 201)."""
        for code in ["200", "201"]:
            resp = responses.get(code, {})
            if version == 3:
                content = resp.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema")
                if schema:
                    return dict(self._resolve_ref(schema, root))
            else:
                schema = resp.get("schema")
                if schema:
                    return dict(self._resolve_ref(schema, root))
        return None

    def _extract_status_codes(self, responses: dict) -> List[int]:
        """Extract all documented status codes as integers."""
        codes = []
        for code_str in responses:
            try:
                codes.append(int(code_str))
            except (ValueError, TypeError):
                continue
        return sorted(codes)

    # ------------------------------------------------------------------
    # Auth detection
    # ------------------------------------------------------------------

    def _detect_auth_from_security(
        self, security: List[dict], root: dict, version: int
    ) -> Tuple[bool, str]:
        """Detect auth type from a security requirement list."""
        if not security:
            return (False, "")

        # Get the first security scheme name
        first_scheme = security[0]
        if not first_scheme:
            return (False, "")

        scheme_name = list(first_scheme.keys())[0]

        if version == 3:
            schemes = root.get("components", {}).get("securitySchemes", {})
        else:
            schemes = root.get("securityDefinitions", {})

        scheme_def = schemes.get(scheme_name, {})
        scheme_type = scheme_def.get("type", "")
        scheme_scheme = scheme_def.get("scheme", "")

        if scheme_type == "http" and scheme_scheme == "bearer":
            return (True, "bearer")
        elif scheme_type == "apiKey":
            return (True, "api_key")
        elif scheme_type == "oauth2":
            return (True, "oauth2")
        else:
            return (True, scheme_type or "unknown")

    # ------------------------------------------------------------------
    # Examples extraction
    # ------------------------------------------------------------------

    def _extract_examples(self, operation: dict, version: int) -> Dict[str, Any]:
        """Extract example request/response from the operation."""
        examples: Dict[str, Any] = {}

        if version == 3:
            rb = operation.get("requestBody", {})
            content = rb.get("content", {})
            json_content = content.get("application/json", {})
            if "example" in json_content:
                examples["request"] = json_content["example"]
        # Swagger 2.0 examples are less standardized, skip for now

        return examples

    # ------------------------------------------------------------------
    # $ref resolution
    # ------------------------------------------------------------------

    def _resolve_ref(self, schema: Any, root: dict) -> Any:
        """
        Resolve a $ref pointer if present. Returns the resolved schema.

        Only handles internal references (#/...). External refs are
        returned as-is with a warning marker.
        """
        if not isinstance(schema, dict):
            return schema

        ref = schema.get("$ref")
        if ref is None:
            # Recursively resolve nested schemas (items, properties, etc.)
            resolved = {}
            for key, value in schema.items():
                if key == "properties" and isinstance(value, dict):
                    resolved[key] = {
                        k: self._resolve_ref(v, root)
                        for k, v in value.items()
                    }
                elif key == "items" and isinstance(value, dict):
                    resolved[key] = self._resolve_ref(value, root)
                else:
                    resolved[key] = value
            return resolved

        if not ref.startswith("#/"):
            # External ref — return marker
            return {"$ref": ref, "_external": True}

        # Walk the JSON pointer
        parts = ref.lstrip("#/").split("/")
        current = root
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # Missing ref — return as-is
                return {"$ref": ref, "_unresolved": True}

        # Resolve the target (it might itself contain refs)
        return self._resolve_ref(current, root)
