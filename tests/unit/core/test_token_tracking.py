"""Unit tests for token tracking in BaseLLMClient."""

from __future__ import annotations

from typing import Optional

from stlc_platform.core.llm.base_client import BaseLLMClient, TokenUsage

# ── Concrete stub for testing base class behaviour ──────────────────────────


class StubLLMClient(BaseLLMClient):
    """Minimal concrete implementation for testing token tracking."""

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_schema: Optional[dict] = None,
    ) -> str:
        # Simulate recording tokens on each call
        self._record_tokens(input_tokens=10, output_tokens=20)
        return '{"title": "stub"}'

    def check_connection(self) -> bool:
        return True

    def list_models(self) -> list:
        return ["stub-model"]


# ── TokenUsage dataclass ────────────────────────────────────────────────────


class TestTokenUsage:
    def test_defaults(self):
        t = TokenUsage()
        assert t.input_tokens == 0
        assert t.output_tokens == 0
        assert t.total_tokens == 0

    def test_total_tokens(self):
        t = TokenUsage(input_tokens=100, output_tokens=50)
        assert t.total_tokens == 150

    def test_total_zero_when_empty(self):
        t = TokenUsage(input_tokens=0, output_tokens=0)
        assert t.total_tokens == 0


# ── _record_tokens ──────────────────────────────────────────────────────────


class TestRecordTokens:
    def test_single_record(self):
        client = StubLLMClient()
        client._record_tokens(input_tokens=50, output_tokens=100)
        assert client.last_token_usage().input_tokens == 50
        assert client.last_token_usage().output_tokens == 100
        assert client.accumulated_tokens.input_tokens == 50
        assert client.accumulated_tokens.output_tokens == 100

    def test_multiple_records_accumulate(self):
        client = StubLLMClient()
        client._record_tokens(input_tokens=10, output_tokens=20)
        client._record_tokens(input_tokens=30, output_tokens=40)
        # last_token_usage reflects only the latest call
        assert client.last_token_usage().input_tokens == 30
        assert client.last_token_usage().output_tokens == 40
        # accumulated_tokens sums all calls
        assert client.accumulated_tokens.input_tokens == 40
        assert client.accumulated_tokens.output_tokens == 60
        assert client.accumulated_tokens.total_tokens == 100

    def test_record_via_generate(self):
        client = StubLLMClient()
        client.generate("test prompt")
        client.generate("another prompt")
        # StubLLMClient records 10 input + 20 output per call
        assert client.accumulated_tokens.input_tokens == 20
        assert client.accumulated_tokens.output_tokens == 40
        assert client.accumulated_tokens.total_tokens == 60


# ── accumulated_tokens property ─────────────────────────────────────────────


class TestAccumulatedTokens:
    def test_initial_state_is_zero(self):
        client = StubLLMClient()
        assert client.accumulated_tokens.total_tokens == 0

    def test_property_returns_running_total(self):
        client = StubLLMClient()
        for _ in range(5):
            client._record_tokens(input_tokens=100, output_tokens=200)
        assert client.accumulated_tokens.input_tokens == 500
        assert client.accumulated_tokens.output_tokens == 1000


# ── reset_token_counts ──────────────────────────────────────────────────────


class TestResetTokenCounts:
    def test_reset_clears_accumulated(self):
        client = StubLLMClient()
        client._record_tokens(input_tokens=100, output_tokens=200)
        assert client.accumulated_tokens.total_tokens == 300
        client.reset_token_counts()
        assert client.accumulated_tokens.total_tokens == 0
        assert client.accumulated_tokens.input_tokens == 0
        assert client.accumulated_tokens.output_tokens == 0

    def test_reset_then_new_records(self):
        client = StubLLMClient()
        client._record_tokens(input_tokens=50, output_tokens=50)
        client.reset_token_counts()
        client._record_tokens(input_tokens=10, output_tokens=10)
        assert client.accumulated_tokens.total_tokens == 20

    def test_last_usage_unaffected_by_reset(self):
        client = StubLLMClient()
        client._record_tokens(input_tokens=99, output_tokens=1)
        client.reset_token_counts()
        # last_token_usage is independent of accumulated reset
        assert client.last_token_usage().input_tokens == 99
