"""
Circuit Breaker
===============
Prevents repeated retries of the same failing operation. After N consecutive
failures of the same type for a stage, the circuit "opens" and further
retries are skipped with a diagnostic message.

States:
  - CLOSED: Normal operation, failures are counted
  - OPEN: Stage has failed too many times, skip retries
  - HALF_OPEN: After reset_timeout, allow one probe attempt
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """State of a stage circuit."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class StageCircuit:
    """Circuit state for a single pipeline stage."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_type: str = ""
    last_failure_time: float = 0.0
    failure_history: List[str] = field(default_factory=list)


class CircuitBreaker:
    """
    Circuit breaker for pipeline stage retries.

    After *threshold* consecutive failures for a stage, the circuit opens and
    ``is_open()`` returns True until *reset_timeout* seconds have elapsed
    (at which point it transitions to HALF_OPEN and allows one probe attempt).

    Args:
        threshold: Number of consecutive failures before opening circuit.
        reset_timeout: Seconds after which an open circuit transitions to half-open.
    """

    def __init__(self, threshold: int = 3, reset_timeout: float = 60.0):
        self._threshold = max(1, threshold)
        self._reset_timeout = max(0.0, reset_timeout)
        self._lock = threading.Lock()
        self._circuits: Dict[str, StageCircuit] = {}

    # ── Public API ─────────────────────────────────────────────────────

    def record_failure(self, stage_id: str, failure_type: str = "") -> bool:
        """Record a failure for a stage (thread-safe).

        Returns True if the circuit has just opened (caller should stop retrying).
        """
        with self._lock:
            circuit = self._get_or_create(stage_id)
            circuit.failure_count += 1
            circuit.last_failure_type = failure_type
            circuit.last_failure_time = time.monotonic()
            circuit.failure_history.append(failure_type)

            # Cap history to last 10 entries
            if len(circuit.failure_history) > 10:
                circuit.failure_history = circuit.failure_history[-10:]

            if circuit.failure_count >= self._threshold:
                circuit.state = CircuitState.OPEN
                logger.warning(
                    "Circuit OPEN for '%s' after %d failures (last: %s)",
                    stage_id,
                    circuit.failure_count,
                    failure_type,
                )
                return True
            return False

    def record_success(self, stage_id: str) -> None:
        """Record a success — resets the circuit to closed (thread-safe)."""
        with self._lock:
            circuit = self._get_or_create(stage_id)
            circuit.state = CircuitState.CLOSED
            circuit.failure_count = 0
            circuit.last_failure_type = ""
            circuit.last_failure_time = 0.0
            circuit.failure_history.clear()

    def is_open(self, stage_id: str) -> bool:
        """Check if the circuit is open (thread-safe).

        Also handles the HALF_OPEN transition after *reset_timeout*.
        """
        with self._lock:
            circuit = self._circuits.get(stage_id)
            if circuit is None:
                return False

            if circuit.state == CircuitState.OPEN:
                elapsed = time.monotonic() - circuit.last_failure_time
                if elapsed >= self._reset_timeout:
                    circuit.state = CircuitState.HALF_OPEN
                    logger.info("Circuit HALF-OPEN for '%s' (%.1fs elapsed)", stage_id, elapsed)
                    return False
                return True

            return False

    def reset(self, stage_id: str) -> None:
        """Manually reset a circuit to closed (thread-safe)."""
        with self._lock:
            if stage_id in self._circuits:
                self._circuits[stage_id] = StageCircuit()

    def get_diagnostic(self, stage_id: str) -> Optional[str]:
        """Get a human-readable diagnostic for an open/half-open circuit (thread-safe)."""
        with self._lock:
            circuit = self._circuits.get(stage_id)
            if circuit is None or circuit.state == CircuitState.CLOSED:
                return None

            history = list(circuit.failure_history)
            fail_count = circuit.failure_count
            state_val = circuit.state.value

        if history:
            counts = Counter(history)
            most_common_type, most_common_count = counts.most_common(1)[0]
            return (
                f"Stage '{stage_id}' circuit {state_val}: "
                f"{fail_count} failures. "
                f"Most common: {most_common_type} ({most_common_count}x)"
            )
        return f"Stage '{stage_id}' circuit {state_val}: {fail_count} failures"

    @property
    def all_circuits(self) -> Dict[str, StageCircuit]:
        """Return all circuit states (for observability, thread-safe)."""
        with self._lock:
            return dict(self._circuits)

    def get_metrics(self) -> Dict[str, Any]:
        """Return observability metrics for all circuits (thread-safe).

        Returns a dict with:
          - total_circuits: number of tracked stages
          - open_count: circuits currently open
          - half_open_count: circuits in half-open state
          - total_failures: sum of failure counts across all stages
          - stages: per-stage detail (state, failure_count, last_failure_type)
        """
        with self._lock:
            open_count = 0
            half_open_count = 0
            total_failures = 0
            stages: Dict[str, Dict[str, Any]] = {}

            for stage_id, circuit in self._circuits.items():
                if circuit.state == CircuitState.OPEN:
                    open_count += 1
                elif circuit.state == CircuitState.HALF_OPEN:
                    half_open_count += 1
                total_failures += circuit.failure_count

                top_types: Dict[str, int] = {}
                for ft in circuit.failure_history:
                    top_types[ft] = top_types.get(ft, 0) + 1

                stages[stage_id] = {
                    "state": circuit.state.value,
                    "failure_count": circuit.failure_count,
                    "last_failure_type": circuit.last_failure_type,
                    "failure_type_counts": top_types,
                }

            return {
                "total_circuits": len(self._circuits),
                "open_count": open_count,
                "half_open_count": half_open_count,
                "total_failures": total_failures,
                "stages": stages,
            }

    # ── Internal ───────────────────────────────────────────────────────

    def _get_or_create(self, stage_id: str) -> StageCircuit:
        if stage_id not in self._circuits:
            self._circuits[stage_id] = StageCircuit()
        return self._circuits[stage_id]
