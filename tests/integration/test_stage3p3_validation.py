"""
Stage 3 Phase 3 Integration Tests
===================================
Cross-stage integration (Crawler + API), multi-framework end-to-end,
and test pyramid validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stlc_platform.agents.api_test_agent import APITestAgent, APITestGenerator
from stlc_platform.agents.api_test_agent.openapi_parser import OpenAPIParser
from stlc_platform.agents.api_test_agent.test_generator import SUPPORTED_FRAMEWORKS
from stlc_platform.agents.crawler_agent import CrawlerAgent

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def petstore_v3():
    return _load_fixture("openapi_petstore.json")


@pytest.fixture
def petstore_model(petstore_v3):
    return OpenAPIParser().parse(petstore_v3)


@pytest.fixture
def simple_html():
    return {
        "http://localhost/login": (
            "<html><head><title>Login</title></head>"
            '<body><form><input name="user" type="text">'
            "<button type=\"submit\">Login</button></form></body></html>"
        )
    }


# ── Cross-Stage Integration ─────────────────────────────────────────────────


class TestCrossStageIntegration:
    def test_crawler_and_api_agent_both_succeed(self, simple_html, petstore_v3):
        crawler = CrawlerAgent()
        cr = crawler.execute({"html_pages": simple_html}, {})
        assert cr.success is True

        api_agent = APITestAgent()
        ar = api_agent.execute({"openapi_spec": petstore_v3}, {})
        assert ar.success is True

    def test_combined_artifacts_cover_ui_and_api(self, simple_html, petstore_v3):
        crawler = CrawlerAgent()
        cr = crawler.execute({"html_pages": simple_html}, {})

        api_agent = APITestAgent()
        ar = api_agent.execute({"openapi_spec": petstore_v3}, {})

        # Crawler produces site_model, API agent produces test_files
        assert "site_model" in cr.artifacts
        assert "test_files" in ar.artifacts

    def test_artifact_types_are_distinct(self, simple_html, petstore_v3):
        crawler = CrawlerAgent()
        cr = crawler.execute({"html_pages": simple_html}, {})

        api_agent = APITestAgent()
        ar = api_agent.execute({"openapi_spec": petstore_v3}, {})

        # Site model is a SiteModelArtifact, test files are APITestArtifact
        site_model = cr.artifacts["site_model"]
        test_file = ar.artifacts["test_files"][0]
        assert type(site_model).__name__ == "SiteModelArtifact"
        assert type(test_file).__name__ == "APITestArtifact"

    def test_discrepancy_report_coexists_with_api_tests(self, petstore_v3):
        from stlc_platform.core.contracts import RequirementArtifact

        html = {
            "http://localhost/login": (
                "<html><head><title>Login</title></head>"
                '<body><form><input name="user">'
                "<button>Sign In</button></form></body></html>"
            )
        }
        reqs = [
            RequirementArtifact(
                req_id="REQ-1",
                title="Login",
                description="Login page",
                acceptance_criteria=["User clicks Sign In button"],
                priority="High",
            )
        ]

        crawler = CrawlerAgent()
        cr = crawler.execute({"html_pages": html, "requirements": reqs}, {})
        assert "discrepancy_report" in cr.artifacts

        api_agent = APITestAgent()
        ar = api_agent.execute({"openapi_spec": petstore_v3}, {})
        assert "test_files" in ar.artifacts


# ── Multi-Framework End-to-End ──────────────────────────────────────────────


class TestMultiFrameworkEndToEnd:
    def test_rest_assured_full_pipeline(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute(
            {"openapi_spec": petstore_v3}, {"framework": "rest_assured"}
        )
        assert result.success is True
        assert result.metadata["framework"] == "rest_assured"
        # Heuristic syntax check
        all_content = "\n".join(t.content for t in result.artifacts["test_files"])
        assert "import io.restassured" in all_content
        assert "@Test" in all_content
        assert "given()" in all_content

    def test_karate_full_pipeline(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute(
            {"openapi_spec": petstore_v3}, {"framework": "karate"}
        )
        assert result.success is True
        assert result.metadata["framework"] == "karate"
        # Heuristic syntax check
        all_content = "\n".join(t.content for t in result.artifacts["test_files"])
        assert "Feature:" in all_content
        assert "Scenario:" in all_content
        assert "Given path" in all_content

    def test_all_three_frameworks_from_same_spec(self, petstore_v3):
        for fw in SUPPORTED_FRAMEWORKS:
            agent = APITestAgent()
            result = agent.execute({"openapi_spec": petstore_v3}, {"framework": fw})
            assert result.success is True, f"{fw} failed: {result.errors}"
            assert result.metadata["total_endpoints"] == 8
            assert result.metadata["total_tests"] >= 20


# ── Pyramid Distribution Validation ─────────────────────────────────────────


class TestPyramidDistributionValidation:
    def test_e2e_under_20_percent(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        dist = result.metadata["test_level_distribution"]
        total = sum(dist.values())
        e2e_count = dist.get("e2e", 0)
        assert e2e_count / total < 0.2 if total > 0 else True

    def test_api_level_above_80_percent(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        dist = result.metadata["test_level_distribution"]
        total = sum(dist.values())
        api_count = dist.get("api", 0)
        assert api_count / total > 0.8

    def test_distribution_metadata_present(self, petstore_v3):
        agent = APITestAgent()
        result = agent.execute({"openapi_spec": petstore_v3}, {})
        assert "test_level_distribution" in result.metadata
        dist = result.metadata["test_level_distribution"]
        assert isinstance(dist, dict)
        assert sum(dist.values()) > 0
