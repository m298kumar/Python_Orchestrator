"""
Tests for Phase D4: Domain vocabulary enrichment from generated test cases.

Covers:
  - _extract_vocab extraction from components, tags, and quoted step strings
  - Filtering of generic/short terms
  - add_vocab in ChromaDB store (mocked collection)
  - End-to-end enrichment flow in generate_for_all
"""

from __future__ import annotations

from unittest.mock import MagicMock

from stlc_platform.core.contracts import TestCaseArtifact, TestStepArtifact  # noqa: I001

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tc(**overrides) -> TestCaseArtifact:
    """Build a minimal TestCaseArtifact with sensible defaults."""
    defaults = {
        "tc_id": "TC-0001",
        "req_id": "REQ-001",
        "title": "Test title",
        "description": "desc",
        "preconditions": "none",
        "test_type": "positive",
        "priority": "Medium",
        "steps": [],
        "expected_outcome": "pass",
        "tags": [],
        "category": "functional",
        "component": "",
    }
    defaults.update(overrides)
    return TestCaseArtifact(**defaults)


def _make_generator(vector_store=None):
    """Create a TestCaseGenerator with a stubbed LLM."""
    from stlc_platform.agents.requirements_agent.generator import TestCaseGenerator

    llm = MagicMock()
    return TestCaseGenerator(llm_client=llm, vector_store=vector_store)


# ---------------------------------------------------------------------------
# _extract_vocab tests
# ---------------------------------------------------------------------------


class TestExtractVocabFromComponents:
    def test_extracts_non_generic_component(self):
        gen = _make_generator()
        tcs = [_make_tc(component="Login Screen")]
        result = gen._extract_vocab(tcs)
        assert "Login Screen" in result

    def test_skips_generic_component(self):
        gen = _make_generator()
        tcs = [_make_tc(component="general")]
        result = gen._extract_vocab(tcs)
        assert result == []

    def test_skips_unknown_component(self):
        gen = _make_generator()
        tcs = [_make_tc(component="unknown")]
        result = gen._extract_vocab(tcs)
        assert result == []

    def test_skips_empty_component(self):
        gen = _make_generator()
        tcs = [_make_tc(component="")]
        result = gen._extract_vocab(tcs)
        assert result == []


class TestExtractVocabFromTags:
    def test_extracts_domain_tags(self):
        gen = _make_generator()
        tcs = [_make_tc(tags=["checkout-flow", "payment", "edge_case"])]
        result = gen._extract_vocab(tcs)
        assert "checkout-flow" in result
        # "payment" has 7 chars and is not generic, so it should be included
        assert "payment" in result

    def test_skips_generic_tags(self):
        gen = _make_generator()
        tcs = [_make_tc(tags=["positive", "negative", "edge_case", "general", "synthesised"])]
        result = gen._extract_vocab(tcs)
        assert result == []

    def test_skips_short_tags(self):
        gen = _make_generator()
        tcs = [_make_tc(tags=["ui", "db", "api"])]
        result = gen._extract_vocab(tcs)
        assert result == []


class TestExtractVocabFromQuotedStrings:
    def test_extracts_quoted_strings_from_steps(self):
        gen = _make_generator()
        steps = [
            TestStepArtifact(
                action='Click the "Submit Order" button',
                expected_result="Order submitted",
            ),
            TestStepArtifact(
                action='Enter "admin@test.com" in the email field',
                expected_result="Email accepted",
            ),
        ]
        tcs = [_make_tc(steps=steps)]
        result = gen._extract_vocab(tcs)
        assert "Submit Order" in result
        assert "admin@test.com" in result

    def test_skips_short_quoted_strings(self):
        gen = _make_generator()
        steps = [
            TestStepArtifact(action='Type "ok"', expected_result="done"),
        ]
        tcs = [_make_tc(steps=steps)]
        result = gen._extract_vocab(tcs)
        assert "ok" not in result

    def test_handles_dict_steps(self):
        """Steps passed as dicts (legacy format) should also work."""
        gen = _make_generator()
        # Manually override steps with dicts to test the fallback path
        tc_dict_steps = _make_tc(
            steps=[
                TestStepArtifact(
                    action='Navigate to "Dashboard Page"',
                    expected_result="Page loads",
                ),
            ]
        )
        result = gen._extract_vocab([tc_dict_steps])
        assert "Dashboard Page" in result


class TestExtractVocabSkipsGenericTerms:
    def test_deduplicates_across_tcs(self):
        gen = _make_generator()
        tcs = [
            _make_tc(component="Login Screen", tags=["login-flow"]),
            _make_tc(component="Login Screen", tags=["login-flow", "authentication"]),
        ]
        result = gen._extract_vocab(tcs)
        assert result.count("Login Screen") == 1
        assert result.count("login-flow") == 1

    def test_caps_at_50_terms(self):
        gen = _make_generator()
        tcs = [_make_tc(tags=[f"domain-term-{i:03d}" for i in range(60)])]
        result = gen._extract_vocab(tcs)
        assert len(result) <= 50


# ---------------------------------------------------------------------------
# add_vocab tests (ChromaDB collection mocked)
# ---------------------------------------------------------------------------


class TestAddVocabToChroma:
    def test_add_vocab_upserts_terms(self):
        from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

        store = RequirementsVectorStore.__new__(RequirementsVectorStore)
        store._ready = True
        store._coll_vocab = MagicMock()

        count = store.add_vocab(["Login Screen", "Checkout Flow"], domain="ecommerce")

        assert count == 2
        store._coll_vocab.upsert.assert_called_once()
        call_kwargs = store._coll_vocab.upsert.call_args
        ids = (
            call_kwargs.kwargs.get("ids") or call_kwargs[1].get("ids") or call_kwargs[0][0]
            if call_kwargs[0]
            else None
        )
        # Verify IDs are deterministic based on term text
        assert "vocab_auto_login_screen" in (ids or call_kwargs.kwargs.get("ids", []))
        assert "vocab_auto_checkout_flow" in (ids or call_kwargs.kwargs.get("ids", []))

    def test_add_vocab_empty_list_returns_zero(self):
        from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

        store = RequirementsVectorStore.__new__(RequirementsVectorStore)
        store._ready = True
        store._coll_vocab = MagicMock()

        count = store.add_vocab([])
        assert count == 0
        store._coll_vocab.upsert.assert_not_called()

    def test_add_vocab_skips_blank_terms(self):
        from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

        store = RequirementsVectorStore.__new__(RequirementsVectorStore)
        store._ready = True
        store._coll_vocab = MagicMock()

        count = store.add_vocab(["  ", "", "Valid Term"])
        assert count == 1

    def test_add_vocab_metadata_has_source_field(self):
        from stlc_platform.core.storage.chroma_store import RequirementsVectorStore

        store = RequirementsVectorStore.__new__(RequirementsVectorStore)
        store._ready = True
        store._coll_vocab = MagicMock()

        store.add_vocab(["Dashboard"], domain="retail")
        call_kwargs = store._coll_vocab.upsert.call_args
        metas = call_kwargs.kwargs.get("metadatas") or call_kwargs[1].get("metadatas")
        assert metas[0]["source"] == "auto_extracted"
        assert metas[0]["domain"] == "retail"
        assert metas[0]["vocab_type"] == "auto_term"


# ---------------------------------------------------------------------------
# End-to-end enrichment test (vector_store mocked)
# ---------------------------------------------------------------------------


class TestVocabEnrichmentEndToEnd:
    def test_generate_for_all_calls_add_vocab(self):
        """After generation + dedup, generate_for_all should call add_vocab."""
        gen = _make_generator(vector_store=MagicMock())
        gen.vector_store.add_vocab = MagicMock(return_value=3)
        gen.vector_store.extract_and_store_vocab = MagicMock()
        gen.vector_store.add_requirements = MagicMock()
        gen.vector_store.get_context_for_requirement = MagicMock(return_value="")
        gen.vector_store.retrieve_examples = MagicMock(return_value=[])

        # Patch generate_for_requirement to return controlled TCs
        tc = _make_tc(component="Shopping Cart", tags=["cart-management"])
        gen.generate_for_requirement = MagicMock(return_value=[tc])

        # Create a minimal requirement
        req = MagicMock()
        req.req_id = "REQ-001"
        req.title = "Add to cart"
        req.description = "User adds item to cart"
        req.acceptance_criteria = ["Item appears in cart"]
        req.category = "functional"
        req.priority = "High"

        gen.generate_for_all([req])

        gen.vector_store.add_requirements.assert_called_once_with([req])
        gen.vector_store.add_vocab.assert_called_once()
        terms_arg = gen.vector_store.add_vocab.call_args[0][0]
        assert "Shopping Cart" in terms_arg
        assert "cart-management" in terms_arg

    def test_generate_for_all_handles_add_vocab_error(self):
        """add_vocab errors should not break generation."""
        gen = _make_generator(vector_store=MagicMock())
        gen.vector_store.add_vocab = MagicMock(side_effect=RuntimeError("DB down"))
        gen.vector_store.extract_and_store_vocab = MagicMock()
        gen.vector_store.add_requirements = MagicMock(side_effect=RuntimeError("DB down"))
        gen.vector_store.get_context_for_requirement = MagicMock(return_value="")
        gen.vector_store.retrieve_examples = MagicMock(return_value=[])

        tc = _make_tc(component="Login Screen")
        gen.generate_for_requirement = MagicMock(return_value=[tc])

        req = MagicMock()
        req.req_id = "REQ-002"
        req.title = "Login"
        req.description = "User logs in"
        req.acceptance_criteria = ["User sees dashboard"]
        req.category = "auth"
        req.priority = "High"

        # Should not raise
        result = gen.generate_for_all([req])
        assert len(result) == 1

    def test_no_enrichment_without_vector_store(self):
        """When vector_store is None, enrichment is skipped gracefully."""
        gen = _make_generator(vector_store=None)

        tc = _make_tc(component="Profile Page")
        gen.generate_for_requirement = MagicMock(return_value=[tc])

        req = MagicMock()
        req.req_id = "REQ-003"
        req.title = "View profile"
        req.description = "User views profile"
        req.acceptance_criteria = ["Profile shown"]
        req.category = "user"
        req.priority = "Medium"

        # Should not raise
        result = gen.generate_for_all([req])
        assert len(result) == 1
