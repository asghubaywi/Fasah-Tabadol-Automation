# ADR 0005 — Circuit breaker + checkpoint/resume for resilience

**Status:** Inferred — Requires Human Confirmation

## Context
Repeated Rust invocation failures shouldn't hammer a broken dependency, and a crash mid-batch shouldn't reprocess or lose files.

## Decision
Wrap engine calls in a thread-safe circuit breaker (CLOSED/OPEN/HALF_OPEN) and persist per-file progress in an atomic checkpoint so restarts resume cleanly.

## Evidence from the project
- `circuit_breaker.py:53-199`; `checkpoint.py:45-208`; orchestrator wiring `orchestrator.py:75-79,454-506`.
- Tests: `TestCircuitBreaker`, `TestCheckpoint`, `TestCheckpointResume` (pass).

## Alternatives
- Naive retry loops; external supervisor (systemd restart) only.

## Pros
- Fast-fail during outages; deterministic resume; both well-tested.

## Cons / Risks
- Breaker + degradation state is **in-memory only** — lost on restart and invisible cross-process (health CLI can't see it).
- Checkpoint and the SHA-256 idempotency ledger track **overlapping** state via two mechanisms; they can disagree.
- Recovery timeout (120s default) is untuned against real engine behavior.

## Revisit conditions
Consolidate idempotency-vs-checkpoint, and persist/aggregate breaker + degradation state if cross-process observability becomes needed.
