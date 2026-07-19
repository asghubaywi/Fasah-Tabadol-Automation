# Domain: Resilience & Degradation / المرونة والتدهور المتحكم به

**Primary code:** `circuit_breaker.py`, `fallback_parser.py`, `fallback_compliance.py`, `checkpoint.py` (pipeline); `degradation.py` (utils); `health_check.py`, `retry.py` (browser)

## Goal / الهدف
Keep the pipeline running (in a documented degraded mode) when the Rust engine, disk, or browser misbehaves — never crash the whole run for a recoverable fault.

## Actors / الأدوار
Orchestrator (uses breaker + fallbacks + checkpoint + degradation); browser worker (uses health monitor + retry).

## Components & rules / المكونات والقواعد
| ID | Component | Behavior | Evidence |
|----|-----------|----------|----------|
| REQ-RESIL-001 | Circuit breaker | CLOSED→OPEN after N failures; OPEN→HALF_OPEN after timeout; HALF_OPEN→CLOSED on success; thread-safe | `circuit_breaker.py:53-199` |
| REQ-RESIL-002 | Fallback parser | Pure-Python CSV/JSON producing engine-shaped output | `fallback_parser.py` |
| REQ-RESIL-003 | Fallback compliance | Pure-Python verdicts mirroring the Rust rules | `fallback_compliance.py` |
| REQ-RESIL-004 | Checkpoint | Atomic tmp→rename JSON; in-flight/complete/failed; resume | `checkpoint.py:45-208` |
| REQ-RESIL-005 | Degradation manager | Process-wide singleton registry of component health + event log | `degradation.py:43-210` |
| REQ-RESIL-006 | Browser health monitor | Consecutive-failure + stuck-task detection; RSS (Linux) | `health_check.py:34-175` |
| REQ-RESIL-007 | Retry helpers | Decorator + imperative exponential backoff | `retry.py:29-141` |

## Use cases
Rust binary missing → fallback parse/check, mark degraded, continue; 3 engine failures → circuit opens → straight to fallback; crash mid-file → resume in-flight; disk write fails → audit buffers (see `domain-audit.md`); browser fails 5× → skip tasks until restart.

## Main / exception / failure scenarios
Breaker `call()` raises `CircuitOpenError` when OPEN (caller falls back); fallbacks always return a result dict; checkpoint corruption → start fresh (`checkpoint.py:70-74`).

## Permissions / State changes / Data
Checkpoint writes `.pipeline_checkpoint.json`; degradation state is **in-memory only** (not persisted → health CLI in a separate process always shows healthy, `health.py:197-205`).

## Integrations
Breaker wraps `run_engine`; fallbacks imported by orchestrator; degradation consulted by health dashboard when in-process.

## Proven behavior / Tests
Extensively tested in `test_dropout.py`: circuit breaker (6), checkpoint (6), degradation (7), health monitor (6), retry (5), cascading failure (4) — all pass **except** the resilient-audit `test_never_raises` (see audit spec).

## Known constraints / القيود
- Fallbacks **diverge** from the Rust engine (see `domain-compliance.md` GAP-DRIFT-001) — resilience preserves *availability* but not guaranteed *verdict equivalence*.
- Degradation state isn't shared across processes, so cross-process observability is limited.
- The circuit breaker recovery timeout defaults to 120s (`orchestrator.py:78`); tuning is env-driven but untested under real load.

## Open questions
- Should degraded verdicts be flagged in the outbox so downstream consumers know a Python fallback produced them? (Currently only in audit `outcome=degraded`.)
