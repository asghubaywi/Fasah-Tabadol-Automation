# ADR 0002 — Filesystem as the message bus (no DB / no queue)

**Status:** Inferred — Requires Human Confirmation

## Context
Components (orchestrator, engine, browser worker, result watcher) must exchange work and results, survive restarts, and leave an audit trail.

## Decision
Use the `workspace/` directory tree as the sole integration medium: inbox files in, JSON command/result files out, with `processed/`, `quarantine/`, `browser_tasks/`, `browser_results/`, `audit/`, `state/` subtrees. No database, message broker, or network IPC.

## Evidence from the project
- `orchestrator.py:424-436` creates the directory tree; polling loop `474-510`.
- `dispatcher.rs`/`worker.py`/`result_watcher.rs` all read/write JSON files.
- `.gitignore:23-30` treats `workspace/` as runtime-only.

## Alternatives
- SQLite/Postgres for state + a real queue (Redis/RabbitMQ).
- In-memory pipeline within one process.

## Pros
- Zero infra dependencies; trivial to inspect/debug; natural durability + audit.
- Atomic rename gives crash-safe handoff.

## Cons / Risks
- **No access control** on the "bus" — anyone who can write `workspace/` injects work (trust-model gap).
- **No file-stability guarantee** on ingest (GAP-ARCH-002); partially-written files can be read.
- Scaling/concurrency is awkward; directory scans get slow at volume; no transactional multi-file updates.

## Revisit conditions
If throughput, multi-writer concurrency, or access control become requirements, introduce a real queue/DB **behind** the current file contract rather than replacing it wholesale.
