"""
Tests for FeedbackStore — agent feedback persistence and retrieval.
"""

from stlc_platform.core.contracts import AgentFeedbackArtifact
from stlc_platform.pipeline.feedback_store import FeedbackStore


class TestFeedbackStoreBasic:
    def test_store_and_retrieve(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        feedback = AgentFeedbackArtifact(
            agent_id="bdd_agent",
            feedback_type="correction",
            message="Don't use hardcoded IDs in step definitions.",
        )
        store.store(feedback)

        results = store.retrieve("bdd_agent")
        assert len(results) == 1
        assert results[0].message == "Don't use hardcoded IDs in step definitions."
        assert results[0].agent_id == "bdd_agent"

    def test_retrieve_filters_by_agent(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="bdd_agent", message="BDD feedback"))
        store.store(AgentFeedbackArtifact(agent_id="api_test_agent", message="API feedback"))

        bdd = store.retrieve("bdd_agent")
        assert len(bdd) == 1
        assert bdd[0].message == "BDD feedback"

        api = store.retrieve("api_test_agent")
        assert len(api) == 1
        assert api[0].message == "API feedback"

    def test_retrieve_respects_limit(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        for i in range(10):
            store.store(AgentFeedbackArtifact(agent_id="test_agent", message=f"Feedback {i}"))

        results = store.retrieve("test_agent", limit=3)
        assert len(results) == 3

    def test_applied_count_incremented(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="test_agent", message="Test"))

        store.retrieve("test_agent")
        store.retrieve("test_agent")

        entries = store.list_all("test_agent")
        assert entries[0].applied_count == 2

    def test_created_at_set_automatically(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="test_agent", message="Test"))
        entries = store.list_all()
        assert entries[0].created_at != ""


class TestFeedbackStorePersistence:
    def test_persists_to_disk_and_reloads(self, tmp_path):
        store1 = FeedbackStore(persist_path=tmp_path)
        store1.store(AgentFeedbackArtifact(agent_id="bdd_agent", message="Persist me"))

        # New store from same path should load existing feedback
        store2 = FeedbackStore(persist_path=tmp_path)
        assert store2.count == 1
        assert store2.list_all()[0].message == "Persist me"

    def test_corrupted_file_handled(self, tmp_path):
        # Write invalid JSON
        (tmp_path / "feedback.json").write_text("not valid json")
        store = FeedbackStore(persist_path=tmp_path)
        assert store.count == 0


class TestFeedbackStoreManagement:
    def test_list_all(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="a", message="1"))
        store.store(AgentFeedbackArtifact(agent_id="b", message="2"))

        assert len(store.list_all()) == 2
        assert len(store.list_all(agent_id="a")) == 1

    def test_clear_by_agent(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="a", message="1"))
        store.store(AgentFeedbackArtifact(agent_id="b", message="2"))

        removed = store.clear(agent_id="a")
        assert removed == 1
        assert store.count == 1
        assert store.list_all()[0].agent_id == "b"

    def test_clear_all(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        store.store(AgentFeedbackArtifact(agent_id="a", message="1"))
        store.store(AgentFeedbackArtifact(agent_id="b", message="2"))

        removed = store.clear()
        assert removed == 2
        assert store.count == 0

    def test_count_property(self, tmp_path):
        store = FeedbackStore(persist_path=tmp_path)
        assert store.count == 0
        store.store(AgentFeedbackArtifact(agent_id="a", message="1"))
        assert store.count == 1


class TestAgentFeedbackArtifact:
    def test_model_validates(self):
        fb = AgentFeedbackArtifact(
            agent_id="test",
            feedback_type="correction",
            message="Use data-testid for selectors",
        )
        assert fb.schema_version == "1.0"
        assert fb.applied_count == 0
        assert fb.context == {}

    def test_model_dump_roundtrip(self):
        fb = AgentFeedbackArtifact(
            agent_id="test",
            feedback_type="preference",
            message="Prefer pytest over unittest",
            context={"framework": "pytest"},
        )
        data = fb.model_dump()
        restored = AgentFeedbackArtifact(**data)
        assert restored.message == fb.message
        assert restored.context == fb.context
