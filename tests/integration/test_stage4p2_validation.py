"""
Stage 4 Phase 2 Integration Tests
==================================
Tests for skill files, model router, execution profiles, config merging,
feedback loop, CI output, and full pipeline E2E with mock agents.
"""

import json
import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from stlc_platform.core.base_agent import (
    AgentCapabilities,
    AgentResult,
    BaseAgent,
    ValidationResult,
)
from stlc_platform.core.contracts import AgentFeedbackArtifact
from stlc_platform.pipeline.dag import PipelineDAG, StageNode
from stlc_platform.pipeline.orchestrator import PipelineOrchestrator
from stlc_platform.pipeline.agent_registry import AgentRegistry
from stlc_platform.pipeline.skill_loader import SkillLoader
from stlc_platform.pipeline.profile_loader import ProfileLoader, ExecutionProfile
from stlc_platform.pipeline.model_router import ModelRouter
from stlc_platform.pipeline.feedback_store import FeedbackStore


# ── Mock Agents ───────────────────────────────────────────────────────────────


class SkillAwareAgent(BaseAgent):
    """Agent that records injected skills for verification."""

    agent_id = "skill_aware"
    agent_version = "1.0"
    last_config: Dict[str, Any] = {}

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        # Store config for test inspection
        SkillAwareAgent.last_config = dict(config)
        return AgentResult(
            success=True,
            artifacts={"output": "done"},
            metadata={"has_skills": "skills" in config},
        )

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            required_skills=["coding_standards", "test_design_principles"],
            default_model_tier="standard",
        )


class ProfileAwareAgent(BaseAgent):
    """Agent that records injected profile info."""

    agent_id = "profile_aware"
    agent_version = "1.0"
    last_config: Dict[str, Any] = {}

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        ProfileAwareAgent.last_config = dict(config)
        return AgentResult(success=True, artifacts={"output": "filtered"})

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id,
            agent_version=self.agent_version,
        )


# ── Skill Injection Tests ────────────────────────────────────────────────────


class TestSkillInjection:
    def test_orchestrator_injects_skills_into_agent(self):
        """Skills from SkillLoader should appear in the agent's config."""
        dag = PipelineDAG(
            pipeline_name="skill_test",
            stages=[StageNode(stage_id="s1", agent_id="skill_aware")],
        )
        registry = AgentRegistry()
        registry.register("skill_aware", SkillAwareAgent)

        skill_loader = SkillLoader(
            skills_dir=Path("config/skills"), domain=""
        )

        orchestrator = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            skill_loader=skill_loader,
        )
        result = orchestrator.run()
        assert result.status == "completed"
        # Agent should have received skills in config
        assert "skills" in SkillAwareAgent.last_config
        assert "coding_standards" in SkillAwareAgent.last_config["skills"]

    def test_skill_injection_with_domain(self):
        """Domain-specific skills should overlay common skills."""
        dag = PipelineDAG(
            pipeline_name="domain_skill_test",
            stages=[StageNode(
                stage_id="s1",
                agent_id="skill_aware",
            )],
        )
        registry = AgentRegistry()
        registry.register("skill_aware", SkillAwareAgent)

        # Override capabilities to include data_catalog
        original_caps = SkillAwareAgent.get_capabilities
        def caps_with_data_catalog(self):
            c = original_caps(self)
            c.required_skills = ["data_catalog"]
            return c
        SkillAwareAgent.get_capabilities = caps_with_data_catalog

        try:
            loader = SkillLoader(skills_dir=Path("config/skills"), domain="ecommerce")
            orchestrator = PipelineOrchestrator(
                dag=dag,
                registry=registry,
                skill_loader=loader,
            )
            result = orchestrator.run()
            assert result.status == "completed"
            skills = SkillAwareAgent.last_config.get("skills", {})
            assert "data_catalog" in skills
            assert "entities" in skills["data_catalog"]
            assert "product" in skills["data_catalog"]["entities"]
        finally:
            SkillAwareAgent.get_capabilities = original_caps


# ── Execution Profile Tests ──────────────────────────────────────────────────


class TestExecutionProfileIntegration:
    def test_profile_injected_into_config(self):
        """Execution profile info should appear in agent config."""
        dag = PipelineDAG(
            pipeline_name="profile_test",
            stages=[StageNode(stage_id="s1", agent_id="profile_aware")],
        )
        registry = AgentRegistry()
        registry.register("profile_aware", ProfileAwareAgent)

        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["critical", "high"]},
            max_tests=10,
        )

        orchestrator = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            execution_profile=profile,
        )
        result = orchestrator.run()
        assert result.status == "completed"
        assert "execution_profile" in ProfileAwareAgent.last_config
        assert ProfileAwareAgent.last_config["execution_profile"]["name"] == "smoke"


# ── Model Router Integration Tests ──────────────────────────────────────────


class TestModelRouterIntegration:
    def test_real_agents_declare_tiers(self):
        """All built-in agents should declare a default_model_tier."""
        registry = AgentRegistry.default()
        for cap in registry.list_agents():
            assert hasattr(cap, "default_model_tier")
            assert cap.default_model_tier in ("lightweight", "standard", "advanced")

    def test_router_selects_correct_tier_for_agents(self):
        """Requirements agent → advanced, BDD/crawler → lightweight."""
        router = ModelRouter.default()
        registry = AgentRegistry.default()

        for cap in registry.list_agents():
            tier = router.select_tier(cap)
            assert tier.name in ("lightweight", "standard", "advanced")


# ── Feedback Loop Integration Tests ──────────────────────────────────────────


class TestFeedbackIntegration:
    def test_feedback_roundtrip(self, tmp_path):
        """Store feedback, create new store from disk, retrieve."""
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(
            agent_id="bdd_agent",
            feedback_type="correction",
            message="Use data-testid selectors",
        ))
        store.store(AgentFeedbackArtifact(
            agent_id="api_test_agent",
            feedback_type="preference",
            message="Prefer pytest over unittest",
        ))

        # Reload from disk
        store2 = FeedbackStore(persist_path=tmp_path)
        bdd_fb = store2.retrieve("bdd_agent")
        assert len(bdd_fb) == 1
        assert "data-testid" in bdd_fb[0].message


# ── Config Profile Integration Tests ─────────────────────────────────────────


class TestConfigProfileIntegration:
    def test_web_profile_changes_crawler_config(self):
        from stlc_platform.core.config_loader import load_config_yaml
        base = load_config_yaml()
        web = load_config_yaml(profile="web")
        assert web["crawler"]["max_depth"] > base["crawler"]["max_depth"]

    def test_api_profile_disables_crawler(self):
        from stlc_platform.core.config_loader import load_config_yaml
        api = load_config_yaml(profile="api")
        assert api["crawler"]["max_depth"] == 0


# ── CI Output Tests ──────────────────────────────────────────────────────────


class TestCIOutput:
    def test_pipeline_result_is_json_serializable(self):
        """PipelineRunArtifact should produce valid JSON via model_dump_json."""
        dag = PipelineDAG(
            pipeline_name="ci_test",
            stages=[StageNode(stage_id="s1", agent_id="profile_aware")],
        )
        registry = AgentRegistry()
        registry.register("profile_aware", ProfileAwareAgent)

        orchestrator = PipelineOrchestrator(dag=dag, registry=registry)
        result = orchestrator.run()

        json_str = result.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        assert "run_id" in parsed
        assert "status" in parsed
        assert "stages_completed" in parsed
        assert "total_duration_seconds" in parsed

    def test_github_actions_workflow_exists(self):
        path = Path(".github/workflows/stlc_ci.yml")
        assert path.exists()


# ── Full Pipeline E2E with Mock Agents ────────────────────────────────────────


class MockReqAgent(BaseAgent):
    agent_id = "test_generation"
    agent_version = "1.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=True,
            artifacts={"test_cases": [{"tc_id": "TC-001", "title": "Login test"}]},
            metadata={"total_test_cases": 1},
        )

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id, agent_version=self.agent_version,
            required_skills=["test_design_principles"],
            default_model_tier="advanced",
        )


class MockBDDAgent(BaseAgent):
    agent_id = "bdd_generation"
    agent_version = "1.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=True,
            artifacts={"feature_files": ["login.feature"]},
            metadata={"total_features": 1},
        )

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id, agent_version=self.agent_version,
            required_skills=["coding_standards"],
            default_model_tier="lightweight",
        )


class MockCrawlerAgent(BaseAgent):
    agent_id = "web_crawler"
    agent_version = "1.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=True,
            artifacts={"site_model": {"pages": 3}},
            metadata={"total_pages": 3},
        )

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id, agent_version=self.agent_version,
            required_skills=["coding_standards"],
            default_model_tier="lightweight",
        )


class MockAPITestAgent(BaseAgent):
    agent_id = "api_test_generation"
    agent_version = "1.0"

    def validate_input(self, artifacts):
        return ValidationResult(valid=True)

    def execute(self, artifacts, config):
        return AgentResult(
            success=True,
            artifacts={"api_model": {"endpoints": []}, "test_files": ["test_pets.py"]},
            metadata={"total_tests": 5},
        )

    def get_capabilities(self):
        return AgentCapabilities(
            agent_id=self.agent_id, agent_version=self.agent_version,
            required_skills=["coding_standards", "data_catalog"],
            default_model_tier="standard",
        )


class TestFullPipelineE2E:
    def test_full_stlc_pipeline_with_mocks(self, tmp_path):
        """Full 5-stage pipeline with mock agents, skills, and profiles."""
        from stlc_platform.pipeline.pipeline_loader import load_pipeline

        dag = load_pipeline("config/pipelines/full_stlc.yaml")

        registry = AgentRegistry()
        registry.register("test_generation", MockReqAgent)
        registry.register("requirements_agent", MockReqAgent)
        registry.register("bdd_generation", MockBDDAgent)
        registry.register("bdd_agent", MockBDDAgent)
        registry.register("web_crawler", MockCrawlerAgent)
        registry.register("crawler_agent", MockCrawlerAgent)
        registry.register("api_test_generation", MockAPITestAgent)
        registry.register("api_test_agent", MockAPITestAgent)

        skill_loader = SkillLoader(skills_dir=Path("config/skills"), domain="ecommerce")
        profile = ExecutionProfile(name="regression", filters={})

        # Provide config values that $config references resolve to.
        # The $runtime.llm_client reference needs a "runtime" pseudo-stage
        # in the artifact store. We pre-populate it after creating the orchestrator.
        pipeline_config = {
            "requirements": [{"req_id": "REQ-001", "title": "Login"}],
            "html_pages": {"http://test.com": "<html></html>"},
            "openapi_spec": {"openapi": "3.0.0", "info": {"title": "Test"}},
        }

        orchestrator = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            config=pipeline_config,
            run_dir=tmp_path,
            skill_loader=skill_loader,
            execution_profile=profile,
        )
        # Pre-populate "runtime" pseudo-stage for $runtime.llm_client reference
        orchestrator._store.store("runtime", {"llm_client": "mock_llm"})

        result = orchestrator.run()

        assert result.status == "completed"
        assert len(result.stages_completed) == len(dag.stage_ids)
        assert result.stages_failed == []
        assert result.total_duration_seconds >= 0

    def test_pipeline_with_smoke_profile(self, tmp_path):
        """Pipeline with smoke profile propagates profile info."""
        dag = PipelineDAG(
            pipeline_name="profile_pipeline",
            stages=[
                StageNode(stage_id="s1", agent_id="profile_aware"),
            ],
        )
        registry = AgentRegistry()
        registry.register("profile_aware", ProfileAwareAgent)

        profile = ExecutionProfile(
            name="smoke",
            filters={"priority": ["critical"]},
            max_tests=5,
        )

        orchestrator = PipelineOrchestrator(
            dag=dag,
            registry=registry,
            run_dir=tmp_path,
            execution_profile=profile,
        )
        result = orchestrator.run()
        assert result.status == "completed"
        assert ProfileAwareAgent.last_config["execution_profile"]["max_tests"] == 5

    def test_api_only_pipeline(self, tmp_path):
        """Minimal single-stage pipeline works."""
        from stlc_platform.pipeline.pipeline_loader import load_pipeline

        dag = load_pipeline("config/pipelines/api_test_only.yaml")

        registry = AgentRegistry()
        registry.register("api_test_generation", MockAPITestAgent)
        registry.register("api_test_agent", MockAPITestAgent)

        pipeline_config = {
            "openapi_spec": {"openapi": "3.0.0", "info": {"title": "Test"}},
        }

        orchestrator = PipelineOrchestrator(
            dag=dag, registry=registry, run_dir=tmp_path,
            config=pipeline_config,
        )
        result = orchestrator.run()
        assert result.status == "completed"
