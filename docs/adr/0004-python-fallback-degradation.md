# ADR 0004 — Dual-implementation Python fallbacks for graceful degradation

**Status:** Inferred — Requires Human Confirmation

## Context
The pipeline should keep clearing declarations even if the Rust binary is missing, crashes, or trips the circuit breaker.

## Decision
Reimplement parse and compliance in pure Python (`fallback_parser.py`, `fallback_compliance.py`) that mirror the Rust output shape, and switch to them automatically on Rust failure.

## Evidence from the project
- `orchestrator.py:131-208` (`run_engine_or_fallback_parse/check`); `test_dropout.py:660-745` (cascading-failure tests pass).

## Alternatives
- No fallback (halt on Rust failure).
- Ship the Rust binary redundantly / vendor it (availability without duplication).

## Pros
- High availability; no single point of failure for the core path; well-tested fallback modules.

## Cons / Risks
- **Two sources of truth** for compliance semantics → confirmed divergences (risk scores, cert-matching, `approve_with_conditions`, count semantics — GAP-DRIFT-001). A declaration can be judged differently depending on which engine ran, with **no equivalence test**.
- Doubles maintenance surface for every rule change.

## Revisit conditions
Either (a) add a golden-vector equivalence test suite that both engines must pass, or (b) eliminate duplication (e.g., ship/vendor the Rust binary reliably and treat its absence as a hard, alerted failure). Constitution P14 requires equivalence.
