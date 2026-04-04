"""Tests for the CircuitBreaker."""

from __future__ import annotations

from stlc_platform.pipeline.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:

    def test_initial_state_closed(self):
        breaker = CircuitBreaker(threshold=3)
        assert not breaker.is_open("stage_a")
        assert breaker.get_diagnostic("stage_a") is None

    def test_single_failure_stays_closed(self):
        breaker = CircuitBreaker(threshold=3)
        opened = breaker.record_failure("stage_a", "ValueError")
        assert not opened
        assert not breaker.is_open("stage_a")

    def test_threshold_failures_opens_circuit(self):
        breaker = CircuitBreaker(threshold=3)
        breaker.record_failure("s1", "Err")
        breaker.record_failure("s1", "Err")
        opened = breaker.record_failure("s1", "Err")
        assert opened
        assert breaker.is_open("s1")

    def test_success_resets_circuit(self):
        breaker = CircuitBreaker(threshold=2)
        breaker.record_failure("s1", "Err")
        breaker.record_failure("s1", "Err")
        assert breaker.is_open("s1")

        breaker.record_success("s1")
        assert not breaker.is_open("s1")

    def test_is_open_returns_true_when_open(self):
        breaker = CircuitBreaker(threshold=1, reset_timeout=9999)
        breaker.record_failure("s1", "Err")
        assert breaker.is_open("s1")

    def test_half_open_after_timeout(self):
        breaker = CircuitBreaker(threshold=1, reset_timeout=0.0)
        breaker.record_failure("s1", "Err")
        # With reset_timeout=0, should immediately transition to half-open
        assert not breaker.is_open("s1")
        circuit = breaker.all_circuits["s1"]
        assert circuit.state == CircuitState.HALF_OPEN

    def test_diagnostic_message(self):
        breaker = CircuitBreaker(threshold=2)
        breaker.record_failure("s1", "TimeoutError")
        breaker.record_failure("s1", "TimeoutError")
        diag = breaker.get_diagnostic("s1")
        assert diag is not None
        assert "s1" in diag
        assert "TimeoutError" in diag
        assert "2" in diag

    def test_reset_clears_state(self):
        breaker = CircuitBreaker(threshold=1)
        breaker.record_failure("s1", "Err")
        assert breaker.is_open("s1")
        breaker.reset("s1")
        assert not breaker.is_open("s1")

    def test_failure_history_capped(self):
        breaker = CircuitBreaker(threshold=20)
        for i in range(15):
            breaker.record_failure("s1", f"Err{i}")
        circuit = breaker.all_circuits["s1"]
        assert len(circuit.failure_history) == 10  # capped at 10
