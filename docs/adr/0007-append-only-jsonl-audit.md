# ADR 0007 — Append-only JSONL audit with in-memory buffer fallback

**Status:** Inferred — Requires Human Confirmation

## Context
Customs clearance requires an auditable trail, and audit writes must never block or crash the clearance pipeline.

## Decision
Write structured events as append-only daily JSONL; wrap the base logger in a `ResilientAuditLogger` that buffers in memory on disk failure, flushes on recovery, drops oldest when full, and never blocks.

## Evidence from the project
- `utils/audit.py`; `utils/resilient_audit.py`; wired at `orchestrator.py:438-439`.
- Tests: `TestResilientAudit` (buffer/flush/thread-safety pass).

## Alternatives
- Structured logging to a DB/SIEM; synchronous audit that blocks on failure.

## Pros
- Simple, greppable, durable-by-default; non-blocking; thread-safe.

## Cons / Risks
- **"Never raises" is not fully true** — `record()` only catches `OSError`; a non-OSError in `_log_path` propagates (GAP-BUG-002, failing test).
- No cryptographic tamper-evidence (append-only convention only).
- Buffer overflow **silently drops** audit events (only periodic stderr warning) — audit gaps possible under sustained disk failure.
- No rotation/retention in code.

## Revisit conditions
Fix the exception scope; consider hash-chaining for true immutability (Constitution P5); escalate dropped-event conditions; add rotation.
