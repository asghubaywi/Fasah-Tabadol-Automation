"""
circuit_breaker.py — Circuit breaker pattern for external service calls.
قاطع الدائرة — نمط للحماية من الإخفاقات المتكررة في الخدمات الخارجية

States:
  CLOSED    — Normal operation; all calls pass through.
  OPEN      — Service is failing; calls rejected immediately (fail-fast).
  HALF_OPEN — Testing recovery; one probe call is allowed through.

Usage:
    breaker = CircuitBreaker("rust_engine", failure_threshold=3)
    try:
        result = breaker.call(run_engine, ["parse", path])
    except CircuitOpenError:
        result = python_fallback(path)
    except RuntimeError:
        result = python_fallback(path)
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, TypeVar

log = logging.getLogger("fasah.circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """
    Raised when a call is attempted while the circuit is OPEN.

    يُطلق عند محاولة استدعاء خدمة وقاطع الدائرة مفتوح.
    """

    def __init__(self, name: str, remaining_secs: float):
        self.name = name
        self.remaining_secs = remaining_secs
        super().__init__(
            f"Circuit '{name}' is OPEN — retry in {remaining_secs:.0f}s"
        )


class CircuitBreaker:
    """
    Thread-safe circuit breaker for protecting external calls.

    قاطع دائرة آمن للخيوط لحماية الاستدعاءات الخارجية.

    Args:
        name:               Human-readable identifier used in log messages.
        failure_threshold:  Consecutive failures before opening the circuit.
        recovery_timeout:   Seconds to wait in OPEN before probing (HALF_OPEN).
        success_threshold:  Consecutive successes in HALF_OPEN to close again.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        success_threshold: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """Current circuit state (thread-safe read)."""
        with self._lock:
            return self._resolved_state()

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    # ── Main entry point ──────────────────────────────────────────────────────

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute *func* through the circuit breaker.

        تنفيذ الدالة من خلال قاطع الدائرة.

        Raises:
            CircuitOpenError: circuit is OPEN — use a fallback.
            Any exception raised by *func* (after recording the failure).
        """
        with self._lock:
            state = self._resolved_state()
            if state == CircuitState.OPEN:
                assert self._opened_at is not None
                remaining = max(
                    0.0, self.recovery_timeout - (time.monotonic() - self._opened_at)
                )
                raise CircuitOpenError(self.name, remaining)

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise  # don't double-count as a failure
        except Exception:
            self._on_failure()
            raise

    # ── State management ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Manually reset circuit to CLOSED. إعادة الضبط اليدوي."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None
        log.info("[CircuitBreaker:%s] Manually reset to CLOSED.", self.name)

    def status(self) -> dict[str, Any]:
        """Return serialisable status dict for health reporting."""
        with self._lock:
            state = self._resolved_state()
            return {
                "name": self.name,
                "state": state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_secs": self.recovery_timeout,
                "opened_at": self._opened_at,
            }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolved_state(self) -> CircuitState:
        """Re-evaluate OPEN → HALF_OPEN transition. Must hold _lock."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout:
                log.info(
                    "[CircuitBreaker:%s] OPEN → HALF_OPEN after %.0fs",
                    self.name, elapsed,
                )
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    log.info(
                        "[CircuitBreaker:%s] HALF_OPEN → CLOSED (recovered).",
                        self.name,
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._opened_at = None
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # reset on any success

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            log.warning(
                "[CircuitBreaker:%s] Failure %d/%d.",
                self.name, self._failure_count, self.failure_threshold,
            )
            if self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if (
                    self._state == CircuitState.HALF_OPEN
                    or self._failure_count >= self.failure_threshold
                ):
                    self._state = CircuitState.OPEN
                    self._opened_at = time.monotonic()
                    log.error(
                        "[CircuitBreaker:%s] Circuit OPENED after %d failure(s) — "
                        "will probe again in %.0fs.",
                        self.name, self._failure_count, self.recovery_timeout,
                    )
