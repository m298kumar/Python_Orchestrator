"""
GraphQL Schema Parser
=====================
Discovers GraphQL API endpoints by parsing introspection query results
or SDL (Schema Definition Language) strings into APIModelArtifact.

Supports:
  - Introspection JSON result (standard __schema response)
  - SDL string parsing (type Query { ... })
  - Generates one APIEndpointArtifact per query/mutation field

Usage:
    parser = GraphQLParser()
    model = parser.parse(introspection_json)
    # or
    model = parser.parse_sdl(sdl_string)
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union

from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact


class GraphQLParser:
    """
    Parse GraphQL schemas into APIModelArtifact.

    Each query/mutation field becomes an APIEndpointArtifact with:
      - path: /graphql (single endpoint)
      - method: POST
      - operation_name in tags
      - Args mapped to request_body_schema
      - Return type mapped to response_schema
    """

    def parse(
        self,
        introspection: Union[str, dict],
        endpoint_url: str = "/graphql",
    ) -> APIModelArtifact:
        """
        Parse a GraphQL introspection result into an APIModelArtifact.

        Args:
            introspection: JSON string or dict of introspection result.
                          Expected format: {"data": {"__schema": {...}}}
                          or just {"__schema": {...}}.
            endpoint_url: The GraphQL endpoint URL (default: /graphql).

        Returns:
            APIModelArtifact with query/mutation endpoints.

        Raises:
            ValueError: If the introspection format is invalid.
        """
        if isinstance(introspection, str):
            try:
                introspection = json.loads(introspection)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid GraphQL introspection JSON: {e}")

        assert isinstance(introspection, dict), "Introspection must be a dict"

        # Extract __schema from different wrapper formats
        schema = self._extract_schema(introspection)

        endpoints: List[APIEndpointArtifact] = []

        # Parse Query type
        query_type_name = schema.get("queryType", {}).get("name", "Query")
        query_type = self._find_type(schema, query_type_name)
        if query_type:
            for field in query_type.get("fields", []):
                ep = self._field_to_endpoint(
                    field, "query", endpoint_url, schema
                )
                endpoints.append(ep)

        # Parse Mutation type
        mutation_type_name = (schema.get("mutationType") or {}).get("name", "Mutation")
        mutation_type = self._find_type(schema, mutation_type_name)
        if mutation_type:
            for field in mutation_type.get("fields", []):
                ep = self._field_to_endpoint(
                    field, "mutation", endpoint_url, schema
                )
                endpoints.append(ep)

        return APIModelArtifact(
            endpoints=endpoints,
            base_url=endpoint_url,
            auth_type="bearer",
            spec_format="graphql",
        )

    def parse_sdl(
        self,
        sdl: str,
        endpoint_url: str = "/graphql",
    ) -> APIModelArtifact:
        """
        Parse a GraphQL SDL (Schema Definition Language) string.

        This is a simplified parser that extracts query/mutation fields
        from SDL type definitions.

        Args:
            sdl: GraphQL schema in SDL format.
            endpoint_url: The GraphQL endpoint URL.

        Returns:
            APIModelArtifact with discovered operations.
        """
        endpoints: List[APIEndpointArtifact] = []

        # Extract type Query { ... } blocks
        for operation_type in ("Query", "Mutation"):
            pattern = rf"type\s+{operation_type}\s*\{{([^}}]+)\}}"
            match = re.search(pattern, sdl, re.DOTALL)
            if match:
                block = match.group(1)
                fields = self._parse_sdl_fields(block)
                op = "query" if operation_type == "Query" else "mutation"
                for field_name, args, return_type in fields:
                    ep = self._sdl_field_to_endpoint(
                        field_name, args, return_type, op, endpoint_url
                    )
                    endpoints.append(ep)

        return APIModelArtifact(
            endpoints=endpoints,
            base_url=endpoint_url,
            auth_type="bearer",
            spec_format="graphql_sdl",
        )

    def _extract_schema(self, data: dict) -> dict:
        """Extract __schema from various wrapper formats."""
        if "__schema" in data:
            return dict(data["__schema"])
        if "data" in data and "__schema" in data.get("data", {}):
            return dict(data["data"]["__schema"])
        raise ValueError(
            "Invalid introspection result: expected '__schema' key."
        )

    def _find_type(self, schema: dict, type_name: str) -> Optional[dict]:
        """Find a type definition by name in the schema."""
        for t in schema.get("types", []):
            if t.get("name") == type_name:
                return dict(t)
        return None

    def _field_to_endpoint(
        self,
        field: dict,
        operation: str,
        endpoint_url: str,
        schema: dict,
    ) -> APIEndpointArtifact:
        """Convert a GraphQL field to an APIEndpointArtifact."""
        field_name = field.get("name", "unknown")

        # Extract arguments as query params
        args = field.get("args", [])
        query_params = []
        request_body: Dict[str, Any] = {
            "query": f"{operation} {{ {field_name} }}",
            "variables": {},
        }

        for arg in args:
            arg_name = arg.get("name", "")
            arg_type = self._resolve_type(arg.get("type", {}))
            is_required = self._is_non_null(arg.get("type", {}))

            query_params.append({
                "name": arg_name,
                "type": arg_type,
                "required": str(is_required).lower(),
            })
            request_body["variables"][arg_name] = f"<{arg_type}>"

        # Extract return type
        return_type = self._resolve_type(field.get("type", {}))
        response_schema = {
            "data": {field_name: f"<{return_type}>"},
        }

        return APIEndpointArtifact(
            path=endpoint_url,
            method="POST",
            path_params=[],
            query_params=query_params,
            request_body_schema=request_body,
            response_schema=response_schema,
            auth_required=True,
            auth_type="bearer",
            example_request=request_body,
            example_response=response_schema,
            status_codes=[200],
            tags=[operation, field_name],
        )

    def _resolve_type(self, type_obj: dict) -> str:
        """Resolve a GraphQL type to a string representation."""
        kind = type_obj.get("kind", "")
        name = type_obj.get("name", "")

        if kind == "NON_NULL":
            inner = self._resolve_type(type_obj.get("ofType", {}))
            return f"{inner}!"
        elif kind == "LIST":
            inner = self._resolve_type(type_obj.get("ofType", {}))
            return f"[{inner}]"
        elif name:
            return str(name)
        return "Unknown"

    def _is_non_null(self, type_obj: dict) -> bool:
        """Check if a type is non-nullable."""
        return type_obj.get("kind") == "NON_NULL"

    def _parse_sdl_fields(self, block: str) -> List[tuple]:
        """Parse field definitions from an SDL type block."""
        fields = []
        # Match: fieldName(args): ReturnType
        pattern = r"(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(\S+)"
        for match in re.finditer(pattern, block):
            field_name = match.group(1)
            args_str = match.group(2) or ""
            return_type = match.group(3)

            # Parse args
            args = []
            if args_str:
                for arg_match in re.finditer(r"(\w+)\s*:\s*(\S+)", args_str):
                    args.append({
                        "name": arg_match.group(1),
                        "type": arg_match.group(2),
                    })

            fields.append((field_name, args, return_type))
        return fields

    def _sdl_field_to_endpoint(
        self,
        field_name: str,
        args: List[Dict[str, str]],
        return_type: str,
        operation: str,
        endpoint_url: str,
    ) -> APIEndpointArtifact:
        """Convert an SDL field to an APIEndpointArtifact."""
        query_params = [
            {"name": a["name"], "type": a["type"]}
            for a in args
        ]

        request_body = {
            "query": f"{operation} {{ {field_name} }}",
            "variables": {a["name"]: f"<{a['type']}>" for a in args},
        }

        return APIEndpointArtifact(
            path=endpoint_url,
            method="POST",
            path_params=[],
            query_params=query_params,
            request_body_schema=request_body,
            response_schema={"data": {field_name: f"<{return_type}>"}},
            auth_required=True,
            auth_type="bearer",
            example_request=request_body,
            example_response={"data": {field_name: f"<{return_type}>"}},
            status_codes=[200],
            tags=[operation, field_name],
        )
