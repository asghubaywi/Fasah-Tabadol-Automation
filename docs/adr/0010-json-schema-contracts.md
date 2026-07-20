# ADR 0010 — JSON-Schema file contracts (currently advisory)

**Status:** Inferred — Requires Human Confirmation

## Context
The file-based bus needs agreed shapes for the browser task envelope and the result bundle so independent processes interoperate.

## Decision
Define `schemas/fasah_task.schema.json` and `schemas/fasah_bundle.schema.json` (JSON Schema draft 2020-12) as the contracts between orchestrator, worker, and result watcher.

## Evidence from the project
- `schemas/*.json`; producers `dispatcher.rs`/`orchestrator.py` (task) and `worker.py` (bundle); consumer `result_watcher.rs`.

## Alternatives
- Typed shared library / protobuf; no explicit contract at all.

## Pros
- Documents the interface; enables future validation and external tooling.

## Cons / Risks
- **Not enforced at runtime** — nothing validates messages against these schemas; they are decoration today.
- **Already violated**: the worker's `tool_versions` uses `playwright` while the schema *requires* `agent_browser`; the error-bundle path omits `tool_versions` entirely (GAP-CONTRACT-001). Real bundles would fail validation.
- Schemas carry `zeroclaw.gov` `$id`s (ADR 0009).

## Revisit conditions
Decide whether schemas are authoritative. If yes: fix the worker to match (or fix the schema to match reality), then **enforce** validation at both producer and consumer boundaries.
