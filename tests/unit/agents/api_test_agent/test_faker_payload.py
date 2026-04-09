"""
Tests for Smart Payload Generation (Faker-style Heuristics)
============================================================
Validates that _smart_field_value() and _make_example_payload() produce
realistic test data based on field name patterns.
"""

from stlc_platform.agents.api_test_agent.test_generator import APITestGenerator
from stlc_platform.core.contracts import APIEndpointArtifact


class TestSmartFieldValue:
    """Tests for the static _smart_field_value() method."""

    # -- String fields: email ------------------------------------------------

    def test_email_field(self):
        val = APITestGenerator._smart_field_value("email", "string", {})
        assert "@" in val
        assert "example.com" in val

    def test_email_address_field(self):
        val = APITestGenerator._smart_field_value("email_address", "string", {})
        assert "@" in val

    # -- String fields: name -------------------------------------------------

    def test_name_field(self):
        val = APITestGenerator._smart_field_value("name", "string", {})
        assert val == "John Doe"

    def test_first_name_field(self):
        val = APITestGenerator._smart_field_value("first_name", "string", {})
        assert val == "Jane"

    def test_last_name_field(self):
        val = APITestGenerator._smart_field_value("last_name", "string", {})
        assert val == "Smith"

    # -- String fields: phone ------------------------------------------------

    def test_phone_field(self):
        val = APITestGenerator._smart_field_value("phone", "string", {})
        assert "555" in val

    def test_mobile_field(self):
        val = APITestGenerator._smart_field_value("mobile_number", "string", {})
        assert "555" in val

    # -- String fields: address ----------------------------------------------

    def test_address_field(self):
        val = APITestGenerator._smart_field_value("address", "string", {})
        assert "Street" in val

    def test_city_field(self):
        val = APITestGenerator._smart_field_value("city", "string", {})
        assert val == "Test City"

    def test_zip_field(self):
        val = APITestGenerator._smart_field_value("zip", "string", {})
        assert val == "12345"

    def test_postal_code_field(self):
        val = APITestGenerator._smart_field_value("postal_code", "string", {})
        assert val == "12345"

    # -- String fields: URL --------------------------------------------------

    def test_url_field(self):
        val = APITestGenerator._smart_field_value("url", "string", {})
        assert val.startswith("https://")

    def test_website_field(self):
        val = APITestGenerator._smart_field_value("website", "string", {})
        assert val.startswith("https://")

    # -- String fields: description ------------------------------------------

    def test_description_field(self):
        val = APITestGenerator._smart_field_value("description", "string", {})
        assert "description" in val.lower()

    # -- String fields: date -------------------------------------------------

    def test_date_field(self):
        val = APITestGenerator._smart_field_value("date", "string", {})
        assert "2024" in val
        assert "T" in val  # ISO format

    def test_created_at_field(self):
        val = APITestGenerator._smart_field_value("created_at", "string", {})
        assert "2024" in val

    # -- String fields: default fallback -------------------------------------

    def test_unknown_string_field(self):
        val = APITestGenerator._smart_field_value("foobar", "string", {})
        assert val == "test_foobar"

    # -- Integer fields ------------------------------------------------------

    def test_age_field(self):
        val = APITestGenerator._smart_field_value("age", "integer", {})
        assert val == 25

    def test_quantity_field(self):
        val = APITestGenerator._smart_field_value("quantity", "integer", {})
        assert val == 5

    def test_count_field(self):
        val = APITestGenerator._smart_field_value("count", "integer", {})
        assert val == 5

    def test_price_integer_field(self):
        val = APITestGenerator._smart_field_value("price", "integer", {})
        assert val == 1999

    def test_id_field(self):
        val = APITestGenerator._smart_field_value("id", "integer", {})
        assert val == 1

    def test_user_id_field(self):
        val = APITestGenerator._smart_field_value("user_id", "integer", {})
        assert val == 1

    def test_unknown_integer_field(self):
        val = APITestGenerator._smart_field_value("widgets", "integer", {})
        assert val == 42

    # -- Number fields -------------------------------------------------------

    def test_price_number_field(self):
        val = APITestGenerator._smart_field_value("price", "number", {})
        assert val == 19.99

    def test_unknown_number_field(self):
        val = APITestGenerator._smart_field_value("ratio", "number", {})
        assert val == 1.0

    # -- Boolean / array / other ---------------------------------------------

    def test_boolean_field(self):
        val = APITestGenerator._smart_field_value("active", "boolean", {})
        assert val is True

    def test_array_field(self):
        val = APITestGenerator._smart_field_value("tags", "array", {})
        assert val == []

    def test_unknown_type_field(self):
        val = APITestGenerator._smart_field_value("data", "object", {})
        assert val == "test_data"


class TestMakeExamplePayload:
    """Tests for _make_example_payload() with smart heuristics."""

    def test_payload_uses_smart_values(self):
        """The generated payload uses heuristic values, not generic ones."""
        gen = APITestGenerator(framework="pytest_requests")
        endpoint = APIEndpointArtifact(
            path="/users",
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "age": {"type": "integer"},
                },
            },
        )

        payload_str = gen._make_example_payload(endpoint)

        assert "John Doe" in payload_str
        assert "test_user@example.com" in payload_str
        assert "25" in payload_str

    def test_payload_falls_back_for_unknown_fields(self):
        """Unknown field names use the test_{field_name} pattern."""
        gen = APITestGenerator(framework="pytest_requests")
        endpoint = APIEndpointArtifact(
            path="/things",
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {
                    "widget_label": {"type": "string"},
                },
            },
        )

        payload_str = gen._make_example_payload(endpoint)
        assert "test_widget_label" in payload_str

    def test_payload_uses_examples_when_available(self):
        """If endpoint.examples['request'] is set, it takes priority."""
        gen = APITestGenerator(framework="pytest_requests")
        endpoint = APIEndpointArtifact(
            path="/things",
            method="POST",
            request_body_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            examples={"request": {"name": "From Example"}},
        )

        payload_str = gen._make_example_payload(endpoint)
        assert "From Example" in payload_str
