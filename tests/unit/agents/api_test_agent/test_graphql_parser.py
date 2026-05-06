"""Tests for GraphQL schema parser."""

import json
from pathlib import Path

import pytest
from stlc_platform.agents.api_test_agent.graphql_parser import GraphQLParser
from stlc_platform.core.contracts import APIModelArtifact


@pytest.fixture
def gql_parser():
    return GraphQLParser()


@pytest.fixture
def introspection_schema():
    path = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "graphql_schema.json"
    return json.loads(path.read_text())


@pytest.fixture
def sample_sdl():
    return """
    type Query {
        user(id: ID!): User
        users(limit: Int, offset: Int): [User]
        product(id: ID!): Product
    }

    type Mutation {
        createUser(name: String!, email: String!): User
        deleteUser(id: ID!): Boolean
    }

    type User {
        id: ID
        name: String
        email: String
    }

    type Product {
        id: ID
        name: String
        price: Float
    }
    """


class TestIntrospectionParsing:
    def test_parses_introspection_json(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        assert isinstance(result, APIModelArtifact)
        assert result.spec_format == "graphql"

    def test_parses_json_string(self, gql_parser, introspection_schema):
        result = gql_parser.parse(json.dumps(introspection_schema))
        assert isinstance(result, APIModelArtifact)

    def test_discovers_queries(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        tags = [tag for ep in result.endpoints for tag in ep.tags]
        assert "query" in tags

    def test_discovers_mutations(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        tags = [tag for ep in result.endpoints for tag in ep.tags]
        assert "mutation" in tags

    def test_total_operations(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        # 3 queries + 2 mutations = 5 endpoints
        assert len(result.endpoints) == 5

    def test_all_endpoints_are_post(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        assert all(ep.method == "POST" for ep in result.endpoints)

    def test_all_endpoints_have_graphql_path(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        assert all(ep.path == "/graphql" for ep in result.endpoints)

    def test_user_query_has_id_arg(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        user_query = next(
            (ep for ep in result.endpoints if "user" in ep.tags and "query" in ep.tags),
            None,
        )
        assert user_query is not None
        param_names = [p["name"] for p in user_query.query_params]
        assert "id" in param_names

    def test_create_user_mutation_has_args(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        create = next((ep for ep in result.endpoints if "createUser" in ep.tags), None)
        assert create is not None
        param_names = [p["name"] for p in create.query_params]
        assert "name" in param_names
        assert "email" in param_names

    def test_request_body_has_query_field(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema)
        for ep in result.endpoints:
            assert "query" in ep.request_body_schema


class TestSDLParsing:
    def test_parses_sdl(self, gql_parser, sample_sdl):
        result = gql_parser.parse_sdl(sample_sdl)
        assert isinstance(result, APIModelArtifact)
        assert result.spec_format == "graphql_sdl"

    def test_discovers_sdl_queries(self, gql_parser, sample_sdl):
        result = gql_parser.parse_sdl(sample_sdl)
        query_eps = [ep for ep in result.endpoints if "query" in ep.tags]
        assert len(query_eps) == 3  # user, users, product

    def test_discovers_sdl_mutations(self, gql_parser, sample_sdl):
        result = gql_parser.parse_sdl(sample_sdl)
        mutation_eps = [ep for ep in result.endpoints if "mutation" in ep.tags]
        assert len(mutation_eps) == 2  # createUser, deleteUser

    def test_sdl_total_operations(self, gql_parser, sample_sdl):
        result = gql_parser.parse_sdl(sample_sdl)
        assert len(result.endpoints) == 5


class TestGraphQLEdgeCases:
    def test_invalid_json_raises(self, gql_parser):
        with pytest.raises(ValueError, match="Invalid GraphQL"):
            gql_parser.parse("not json")

    def test_missing_schema_raises(self, gql_parser):
        with pytest.raises(ValueError, match="__schema"):
            gql_parser.parse({"data": {}})

    def test_direct_schema_format(self, gql_parser):
        """Test parsing when __schema is at top level (no data wrapper)."""
        schema = {
            "__schema": {
                "queryType": {"name": "Query"},
                "types": [
                    {
                        "name": "Query",
                        "fields": [
                            {
                                "name": "hello",
                                "args": [],
                                "type": {"kind": "SCALAR", "name": "String"},
                            }
                        ],
                    }
                ],
            }
        }
        result = gql_parser.parse(schema)
        assert len(result.endpoints) == 1

    def test_no_mutations_is_valid(self, gql_parser):
        schema = {
            "__schema": {
                "queryType": {"name": "Query"},
                "mutationType": None,
                "types": [
                    {
                        "name": "Query",
                        "fields": [
                            {
                                "name": "ping",
                                "args": [],
                                "type": {"kind": "SCALAR", "name": "String"},
                            }
                        ],
                    }
                ],
            }
        }
        result = gql_parser.parse(schema)
        assert len(result.endpoints) == 1

    def test_custom_endpoint_url(self, gql_parser, introspection_schema):
        result = gql_parser.parse(introspection_schema, endpoint_url="/api/graphql")
        assert all(ep.path == "/api/graphql" for ep in result.endpoints)

    def test_preserves_example_request(self, gql_parser, introspection_schema):
        """Bug fix: example_request was silently dropped before contract v1.2."""
        result = gql_parser.parse(introspection_schema)
        for ep in result.endpoints:
            assert ep.example_request is not None
            assert "query" in ep.example_request

    def test_preserves_example_response(self, gql_parser, introspection_schema):
        """Bug fix: example_response was silently dropped before contract v1.2."""
        result = gql_parser.parse(introspection_schema)
        for ep in result.endpoints:
            assert ep.example_response is not None

    def test_sdl_preserves_examples(self, gql_parser, sample_sdl):
        """SDL-parsed endpoints should also have example request/response."""
        result = gql_parser.parse_sdl(sample_sdl)
        for ep in result.endpoints:
            assert ep.example_request is not None
            assert ep.example_response is not None
