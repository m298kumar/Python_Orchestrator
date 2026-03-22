"""
Tests for CRUD Sequence Test Generation
========================================
Validates that the APITestGenerator correctly detects CRUD resource groups
and generates integration-level sequence tests.
"""


from stlc_platform.agents.api_test_agent.test_generator import APITestGenerator
from stlc_platform.core.contracts import APIEndpointArtifact, APIModelArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_endpoint(path: str, method: str, **kwargs) -> APIEndpointArtifact:
    """Shortcut to build an APIEndpointArtifact."""
    return APIEndpointArtifact(path=path, method=method, **kwargs)


def _petstore_model() -> APIModelArtifact:
    """Return a minimal petstore-style API model with full CRUD on /pets."""
    return APIModelArtifact(
        base_url="https://api.example.com",
        auth_type="bearer",
        endpoints=[
            _make_endpoint(
                "/pets",
                "POST",
                request_body_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["name"],
                },
            ),
            _make_endpoint("/pets", "GET"),
            _make_endpoint(
                "/pets/{petId}",
                "GET",
                path_params=[{"name": "petId", "type": "integer"}],
            ),
            _make_endpoint(
                "/pets/{petId}",
                "PUT",
                path_params=[{"name": "petId", "type": "integer"}],
                request_body_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
            ),
            _make_endpoint(
                "/pets/{petId}",
                "DELETE",
                path_params=[{"name": "petId", "type": "integer"}],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: _detect_crud_groups
# ---------------------------------------------------------------------------


class TestDetectCrudGroups:
    """Tests for _detect_crud_groups()."""

    def test_finds_full_crud_group(self):
        """A base path with POST + GET + PUT + DELETE is detected."""
        gen = APITestGenerator(framework="pytest_requests")
        model = _petstore_model()

        groups = gen._detect_crud_groups(model)

        assert len(groups) == 1
        group = groups[0]
        assert group["base_path"] == "/pets"
        assert group["resource_name"] == "pets"
        assert "POST" in group["endpoints"]
        assert "GET" in group["endpoints"]
        assert "PUT" in group["endpoints"]
        assert "DELETE" in group["endpoints"]

    def test_no_group_without_post(self):
        """Endpoints without POST should not form a CRUD group."""
        gen = APITestGenerator(framework="pytest_requests")
        model = APIModelArtifact(
            base_url="https://api.example.com",
            endpoints=[
                _make_endpoint("/items", "GET"),
                _make_endpoint("/items/{id}", "PUT"),
                _make_endpoint("/items/{id}", "DELETE"),
            ],
        )

        groups = gen._detect_crud_groups(model)
        assert len(groups) == 0

    def test_no_group_without_delete(self):
        """Endpoints without DELETE should not form a CRUD group."""
        gen = APITestGenerator(framework="pytest_requests")
        model = APIModelArtifact(
            base_url="https://api.example.com",
            endpoints=[
                _make_endpoint("/items", "POST"),
                _make_endpoint("/items", "GET"),
                _make_endpoint("/items/{id}", "PUT"),
            ],
        )

        groups = gen._detect_crud_groups(model)
        assert len(groups) == 0

    def test_patch_counts_as_update(self):
        """PATCH should satisfy the update requirement for CRUD groups."""
        gen = APITestGenerator(framework="pytest_requests")
        model = APIModelArtifact(
            base_url="https://api.example.com",
            endpoints=[
                _make_endpoint("/widgets", "POST"),
                _make_endpoint("/widgets", "GET"),
                _make_endpoint("/widgets/{widgetId}", "PATCH"),
                _make_endpoint("/widgets/{widgetId}", "DELETE"),
            ],
        )

        groups = gen._detect_crud_groups(model)
        assert len(groups) == 1
        assert groups[0]["resource_name"] == "widgets"

    def test_multiple_resource_groups(self):
        """Multiple independent CRUD groups are detected."""
        gen = APITestGenerator(framework="pytest_requests")
        model = APIModelArtifact(
            base_url="https://api.example.com",
            endpoints=[
                # Group 1: /pets
                _make_endpoint("/pets", "POST"),
                _make_endpoint("/pets", "GET"),
                _make_endpoint("/pets/{petId}", "PUT"),
                _make_endpoint("/pets/{petId}", "DELETE"),
                # Group 2: /orders
                _make_endpoint("/orders", "POST"),
                _make_endpoint("/orders", "GET"),
                _make_endpoint("/orders/{orderId}", "PUT"),
                _make_endpoint("/orders/{orderId}", "DELETE"),
            ],
        )

        groups = gen._detect_crud_groups(model)
        names = {g["resource_name"] for g in groups}
        assert len(groups) == 2
        assert names == {"pets", "orders"}


# ---------------------------------------------------------------------------
# Tests: CRUD test generation
# ---------------------------------------------------------------------------


class TestCrudSequenceGeneration:
    """Tests for CRUD sequence test case generation."""

    def test_crud_test_has_integration_level(self):
        """Generated CRUD tests are integration-level."""
        gen = APITestGenerator(framework="pytest_requests")
        model = _petstore_model()

        groups = gen._detect_crud_groups(model)
        tests = gen._crud_sequence_tests_for_group(groups[0], model)

        assert len(tests) == 1
        assert tests[0]["test_type"] == "crud_sequence"
        assert tests[0]["test_level"] == "integration"

    def test_crud_test_contains_required_keys(self):
        """CRUD test dict has all keys needed by the template."""
        gen = APITestGenerator(framework="pytest_requests")
        model = _petstore_model()

        groups = gen._detect_crud_groups(model)
        tests = gen._crud_sequence_tests_for_group(groups[0], model)
        test = tests[0]

        required_keys = {
            "func_name", "description", "test_type", "test_level",
            "failure_type", "create_payload", "update_payload",
            "base_path", "resource_name", "post_path", "get_path",
            "put_path", "delete_path", "update_method", "auth_required",
        }
        assert required_keys.issubset(test.keys())

    def test_generate_includes_crud_artifacts(self):
        """generate() produces CRUD artifacts alongside per-endpoint ones."""
        gen = APITestGenerator(framework="pytest_requests")
        model = _petstore_model()

        artifacts = gen.generate(model)

        crud_artifacts = [a for a in artifacts if a.test_type == "crud_sequence"]
        assert len(crud_artifacts) == 1
        assert crud_artifacts[0].test_level == "integration"
        assert "crud" in crud_artifacts[0].tags
        assert crud_artifacts[0].filename == "test_crud_sequence_pets.py"

    def test_generate_no_crud_without_full_group(self):
        """generate() produces no CRUD artifacts when CRUD group is incomplete."""
        gen = APITestGenerator(framework="pytest_requests")
        model = APIModelArtifact(
            base_url="https://api.example.com",
            endpoints=[
                _make_endpoint("/items", "GET"),
                _make_endpoint("/items", "POST"),
                # Missing PUT and DELETE
            ],
        )

        artifacts = gen.generate(model)
        crud_artifacts = [a for a in artifacts if a.test_type == "crud_sequence"]
        assert len(crud_artifacts) == 0

    def test_crud_artifact_content_contains_sequence_steps(self):
        """The rendered CRUD test content includes all five sequence steps."""
        gen = APITestGenerator(framework="pytest_requests")
        model = _petstore_model()

        artifacts = gen.generate(model)
        crud_artifact = next(
            a for a in artifacts if a.test_type == "crud_sequence"
        )
        content = crud_artifact.content

        # All five steps should be present in the rendered template
        assert "POST" in content or "post" in content
        assert "GET" in content or "get" in content
        assert "PUT" in content or "put" in content
        assert "DELETE" in content or "delete" in content
        assert "404" in content
