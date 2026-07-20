# ADR 0008 — Atomic writes + SHA-256 content idempotency

**Status:** Inferred — Requires Human Confirmation

## Context
A crash mid-write must not corrupt task/checkpoint files, and the same declaration file must never be processed twice.

## Decision
Use tmp→fsync→rename for critical writes, and a SHA-256 content-hash ledger to detect duplicate inputs before processing. A crash-safe, symlink-rejecting Rust ledger (`idempotency.rs`) exists; the orchestrator implements the same idea in Python.

## Evidence from the project
- Atomic writes: `dispatcher.rs:114-127`, `checkpoint.py:88-108`, `worker.py:363-368`.
- Idempotency: `orchestrator.py:213-235,484-488`; `idempotency.rs`.

## Alternatives
- Non-atomic writes + external dedup; DB unique constraints.

## Pros
- Crash safety and exactly-once ingest on the happy path.

## Cons / Risks
- **`idempotency.rs`/`stability.rs` are not wired into the running pipeline** — the Rust safeguards (symlink rejection, file-stability) are unused; the live Python path lacks a stability check (GAP-ARCH-002).
- **Not all writes are atomic** — orchestrator tracking commands and result-watcher outputs use plain `write` (truncation risk on crash).
- Two idempotency mechanisms (ledger + checkpoint) overlap.

## Revisit conditions
Decide whether the Rust or Python idempotency path is canonical, wire in file-stability before ingest, and make all outbox writes atomic.
