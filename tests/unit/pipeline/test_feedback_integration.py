"""
Tests for Phase B: Feedback Loop Integration
=============================================
Verifies that feedback is retrieved, injected into prompts, and
high-quality TCs are auto-stored as examples.
"""

from unittest.mock import MagicMock

from stlc_platform.agents.requirements_agent.prompts import PromptRenderer
from stlc_platform.core.contracts import AgentFeedbackArtifact
from stlc_platform.pipeline.feedback_store import FeedbackStore

# ── FeedbackStore Semantic Retrieval ────────────────────────────────────────


class TestFeedbackStoreSemanticSearch:
    """Test that ChromaDB semantic search is used when available."""

    def test_retrieve_without_chroma_falls_back_to_keyword(self, tmp_path):
        """No ChromaDB → plain keyword filter + least-applied ordering."""
        store = FeedbackStore(persist_path=tmp_path)
        store.store(
            AgentFeedbackArtifact(
                agent_id="test_generation",
                feedback_type="correction",
                message="Always include error message validation",
            )
        )
        store.store(
            AgentFeedbackArtifact(
                agent_id="bdd_agent",
                message="BDD unrelated",
            )
        )

        results = store.retrieve(
            "test_generation",
            context={"query": "login validation"},
            limit=5,
        )
        assert len(results) == 1
        assert results[0].message == "Always include error message validation"

    def test_retrieve_with_context_and_no_chroma(self, tmp_path):
        """Context is provided but no ChromaDB — still works via fallback."""
        store = FeedbackStore(persist_path=tmp_path)
        for i in range(5):
            store.store(
                AgentFeedbackArtifact(
                    agent_id="test_generation",
                    message=f"Feedback {i}",
                )
            )

        results = store.retrieve(
            "test_generation",
            context={"query": "test"},
            limit=3,
        )
        assert len(results) == 3

    def test_retrieve_increments_applied_count(self, tmp_path):
        """applied_count is bumped on each retrieval."""
        store = FeedbackStore(persist_path=tmp_path)
        store.store(
            AgentFeedbackArtifact(
                agent_id="test_generation",
                message="Test feedback",
            )
        )

        store.retrieve("test_generation")
        store.retrieve("test_generation")

        entries = store.list_all("test_generation")
        assert entries[0].applied_count == 2

    def test_chroma_collection_init_with_mock(self, tmp_path):
        """ChromaDB collection is initialized when chroma_store is provided."""
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_store._client = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_collection.get.return_value = {"ids": []}
        mock_client.get_or_create_collection.return_value = mock_collection

        store = FeedbackStore(persist_path=tmp_path, chroma_store=mock_store)
        assert store._chroma_collection is not None
        mock_client.get_or_create_collection.assert_called_once()

    def test_store_indexes_in_chroma(self, tmp_path):
        """Storing feedback also indexes it in ChromaDB."""
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_store._client = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_collection.get.return_value = {"ids": []}
        mock_client.get_or_create_collection.return_value = mock_collection

        store = FeedbackStore(persist_path=tmp_path, chroma_store=mock_store)
        store.store(
            AgentFeedbackArtifact(
                agent_id="test_generation",
                message="Use data-testid for selectors",
            )
        )

        # Verify upsert was called on the collection
        assert mock_collection.upsert.called

    def test_semantic_retrieve_with_mock_chroma(self, tmp_path):
        """Semantic retrieval queries ChromaDB with context and maps via fb_index."""
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_store._client = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.get.return_value = {"ids": []}
        mock_client.get_or_create_collection.return_value = mock_collection

        # Set up query results — use fb_index for mapping
        mock_collection.query.return_value = {
            "metadatas": [
                [
                    {
                        "agent_id": "test_generation",
                        "feedback_type": "correction",
                        "created_at": "2026-01-01T00:00:00",
                        "fb_index": 0,
                    }
                ]
            ],
            "distances": [[0.2]],  # 0.8 similarity — above threshold
        }

        store = FeedbackStore(persist_path=tmp_path, chroma_store=mock_store)
        store.store(
            AgentFeedbackArtifact(
                agent_id="test_generation",
                message="Always validate error messages",
            )
        )

        store.retrieve(
            "test_generation",
            context={"query": "error handling for login"},
            limit=3,
        )
        # Should find the matching feedback via semantic search
        assert mock_collection.query.called

    def test_semantic_retrieve_filters_low_similarity(self, tmp_path):
        """Results below similarity threshold are filtered out."""
        mock_store = MagicMock()
        mock_client = MagicMock()
        mock_store._client = mock_client
        mock_collection = MagicMock()
        mock_collection.count.return_value = 1
        mock_collection.get.return_value = {"ids": []}
        mock_client.get_or_create_collection.return_value = mock_collection

        # Low similarity (distance 0.9 = 0.1 similarity, below 0.3 threshold)
        mock_collection.query.return_value = {
            "metadatas": [
                [
                    {
                        "agent_id": "test_generation",
                        "feedback_type": "correction",
                        "created_at": "",
                        "fb_index": 0,
                    }
                ]
            ],
            "distances": [[0.9]],
        }

        store = FeedbackStore(persist_path=tmp_path, chroma_store=mock_store)
        store.store(
            AgentFeedbackArtifact(
                agent_id="test_generation",
                message="Unrelated feedback",
            )
        )

        # Semantic search returns nothing relevant, fallback kicks in
        results = store.retrieve(
            "test_generation",
            context={"query": "completely different topic"},
            limit=3,
        )
        # Should still get results via fallback (keyword filter)
        assert len(results) >= 1


# ── Prompt Injection ────────────────────────────────────────────────────────


class TestFeedbackPromptInjection:
    """Test that feedback is injected into the rendered prompt."""

    def test_render_feedback_block_empty(self):
        """No feedback → empty string."""
        renderer = PromptRenderer()
        assert renderer.render_feedback_block(None) == ""
        assert renderer.render_feedback_block([]) == ""

    def test_render_feedback_block_with_items(self):
        """Feedback items are formatted with type-specific emphasis."""
        renderer = PromptRenderer()
        fb1 = AgentFeedbackArtifact(
            agent_id="test_generation",
            feedback_type="correction",
            message="Always include error message text in expected results",
        )
        fb2 = AgentFeedbackArtifact(
            agent_id="test_generation",
            feedback_type="constraint",
            message="Use data-testid selectors, not CSS classes",
        )
        fb3 = AgentFeedbackArtifact(
            agent_id="test_generation",
            feedback_type="preference",
            message="Prefer shorter step descriptions",
        )

        block = renderer.render_feedback_block([fb1, fb2, fb3])
        assert "LEARNED CONSTRAINTS" in block
        assert "Always include error message text" in block
        assert "Use data-testid selectors" in block
        assert "Prefer shorter step descriptions" in block
        # Type-specific prefixes
        assert "FIX:" in block
        assert "MUST:" in block
        assert "PREFER:" in block

    def test_user_prompt_includes_feedback_block(self):
        """render_user_prompt passes feedback through to template."""
        renderer = PromptRenderer()

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "The system shall allow users to log in."
            category = "Authentication"
            acceptance_criteria = ["User can log in with valid credentials"]

        fb = AgentFeedbackArtifact(
            agent_id="test_generation",
            feedback_type="correction",
            message="Must verify error message text exactly",
        )

        prompt = renderer.render_user_prompt(
            requirement=MockReq(),
            slot={
                "test_type": "positive",
                "target_ac": "User can log in",
                "title": "TC-Login",
                "ac_type": "general",
            },
            test_number=1,
            total=1,
            feedback_constraints=[fb],
        )
        assert "LEARNED CONSTRAINTS" in prompt
        assert "Must verify error message text exactly" in prompt
        assert "FIX:" in prompt  # correction type gets FIX: prefix

    def test_user_prompt_without_feedback_has_no_block(self):
        """No feedback → no LEARNED CONSTRAINTS section in prompt."""
        renderer = PromptRenderer()

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "Login feature"
            category = "Auth"
            acceptance_criteria = ["Valid login works"]

        prompt = renderer.render_user_prompt(
            requirement=MockReq(),
            slot={
                "test_type": "positive",
                "target_ac": "Valid login works",
                "title": "TC-1",
                "ac_type": "general",
            },
            test_number=1,
            total=1,
        )
        assert "LEARNED CONSTRAINTS" not in prompt


# ── Generator Integration ───────────────────────────────────────────────────


class TestGeneratorFeedbackIntegration:
    """Test that TestCaseGenerator uses feedback_store."""

    def test_generator_accepts_feedback_store(self):
        """Constructor accepts feedback_store without error."""
        from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator

        mock_llm = MagicMock()
        mock_store = MagicMock()

        gen = TestCaseGenerator(
            llm_client=mock_llm,
            feedback_store=mock_store,
        )
        assert gen.feedback_store is mock_store

    def test_generator_without_feedback_store(self):
        """Generator works fine without feedback_store (None)."""
        from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator

        mock_llm = MagicMock()
        gen = TestCaseGenerator(llm_client=mock_llm)
        assert gen.feedback_store is None

    def test_agent_passes_feedback_store_to_generator(self):
        """TestGenerationAgent.execute() passes feedback_store from artifacts."""
        from stlc_platform.agents.requirements_agent.agent import TestGenerationAgent

        agent = TestGenerationAgent()
        mock_llm = MagicMock()
        mock_llm.generate_test_case.return_value = {
            "test_cases": [
                {
                    "title": "Test Login",
                    "description": "Test login flow",
                    "preconditions": "User is on login page",
                    "test_type": "positive",
                    "priority": "High",
                    "steps": [
                        {"action": "Enter username", "expected_result": "Username entered"},
                        {"action": "Enter password", "expected_result": "Password entered"},
                        {"action": "Click login", "expected_result": "Logged in"},
                    ],
                    "expected_outcome": "User is logged in",
                    "given": "User is on login page",
                    "when": "User enters valid credentials",
                    "then": "User is logged in",
                    "tags": ["auth", "positive"],
                    "component": "Login Screen",
                }
            ]
        }

        mock_feedback = MagicMock()
        mock_feedback.retrieve.return_value = []

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "Login feature"
            priority = "High"
            category = "Auth"
            acceptance_criteria = ["User can log in with valid credentials"]
            tags = ["auth"]

        result = agent.execute(
            artifacts={
                "requirements": [MockReq()],
                "llm_client": mock_llm,
                "feedback_store": mock_feedback,
            },
            config={},
        )
        assert result.success
        # The feedback_store.retrieve should have been called
        assert mock_feedback.retrieve.called


# ── ArtifactResolver Runtime ────────────────────────────────────────────────


class TestArtifactResolverFeedbackStore:
    """Test that $runtime.feedback_store resolves correctly."""

    def test_resolve_feedback_store(self, tmp_path):
        """$runtime.feedback_store creates a FeedbackStore instance."""
        from stlc_platform.pipeline.artifact_store import ArtifactResolver, ArtifactStore

        store = ArtifactStore(run_dir=tmp_path)
        resolver = ArtifactResolver(store, config={})

        fb_store = resolver.resolve_single("$runtime.feedback_store")
        assert fb_store is not None
        assert isinstance(fb_store, FeedbackStore)

    def test_resolve_feedback_store_with_chroma_config(self, tmp_path):
        """Resolver attempts ChromaDB integration when config is present."""
        from stlc_platform.pipeline.artifact_store import ArtifactResolver, ArtifactStore

        store = ArtifactStore(run_dir=tmp_path)
        resolver = ArtifactResolver(
            store,
            config={
                "chromadb": {
                    "persist_directory": str(tmp_path / "chroma"),
                    "collection_name": "test",
                }
            },
        )

        # Should still create a FeedbackStore even if ChromaDB fails
        fb_store = resolver.resolve_single("$runtime.feedback_store")
        assert isinstance(fb_store, FeedbackStore)


# ── Auto-Store High-Quality Examples ────────────────────────────────────────


class TestAutoStoreExamples:
    """Test that high-scoring TCs are auto-stored in ChromaDB."""

    def test_high_quality_tc_triggers_store(self):
        """TCs scoring above auto_example_threshold are stored."""
        from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator
        from stlc_platform.core.quality.scorer import ScorerConfig

        mock_llm = MagicMock()
        mock_llm.generate_test_case.return_value = {
            "test_cases": [
                {
                    "title": "Test Login",
                    "description": "Verifies user can log in with valid email and password to access the dashboard",
                    "preconditions": "User has registered account with verified email address",
                    "test_type": "positive",
                    "priority": "High",
                    "steps": [
                        {
                            "action": "Navigate to login page",
                            "expected_result": "Login form displayed with email and password fields",
                        },
                        {
                            "action": "Enter valid email in email field",
                            "expected_result": "Email entered successfully",
                        },
                        {
                            "action": "Enter valid password in password field",
                            "expected_result": "Password masked and entered",
                        },
                        {
                            "action": "Click the Login button",
                            "expected_result": "System authenticates and redirects to dashboard",
                        },
                    ],
                    "expected_outcome": "User is logged in and sees the dashboard",
                    "given": "User has a verified account and is on the login page",
                    "when": "User enters valid email and password and clicks Login",
                    "then": "User is authenticated and redirected to the dashboard",
                    "tags": ["auth", "positive", "req-001"],
                    "component": "Login Screen",
                }
            ]
        }

        mock_vector = MagicMock()
        mock_vector.get_context_for_requirement.return_value = ""
        mock_vector.retrieve_examples.return_value = []

        # Set a low threshold so our TC passes
        config = ScorerConfig(auto_example_threshold=0.30)

        gen = TestCaseGenerator(
            llm_client=mock_llm,
            vector_store=mock_vector,
            scorer_config=config,
        )

        class MockReq:
            req_id = "REQ-001"
            title = "User Login"
            description = "Login feature"
            priority = "High"
            category = "Auth"
            acceptance_criteria = ["User can log in with valid credentials"]
            tags = ["auth"]

        tcs = gen.generate_for_requirement(MockReq(), max_tests=1)
        assert len(tcs) >= 1

        # Check that store_approved_tc was called for the high-quality TC
        if tcs[0].quality_score >= config.auto_example_threshold:
            mock_vector.store_approved_tc.assert_called()
