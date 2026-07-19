# ADR 0006 — Playwright browser worker: read-only portal actions + security gates

**Status:** Inferred — Requires Human Confirmation

## Context
Fasah has no public API for the needed lookups; status must be read from the portal UI. Automating a government portal is high-risk, so it must be tightly constrained and auditable.

## Decision
Use Playwright (Chromium) in a dedicated worker that executes only the read-only `fasah_search_inspect_v1` playbook, guarded by security gates 9–13 (output limits, prod fail-closed, domain allowlist, blocked download/upload, idempotency + flock locks, structured error codes), producing hashed evidence bundles.

## Evidence from the project
- `worker.py` (gates at `69-110,161-234,243-287`; playbook `735-752`; bundle `834-939`).
- `V1_BLOCKED_ACTIONS = {download, upload}` (`worker.py:79`).

## Alternatives
- Direct HTTP calls (no stable API); Selenium; RPA tooling.

## Pros
- Handles the Angular SPA; defense-in-depth; tamper-evident evidence; fail-closed in prod.

## Cons / Risks
- **Untested** — no automated tests exercise `worker.py` (largest coverage gap).
- Brittle selectors/routes; portal UI drift silently breaks it.
- **POSIX-only** (`fcntl`); `--no-sandbox`; `AGENT_BROWSER_ENCRYPTION_KEY` required but unused.
- Bundle output **violates its own schema** (GAP-CONTRACT-001).

## Revisit conditions
If Fasah exposes an API, prefer it. Before production: add tests (mock page), enforce the bundle schema, resolve the encryption-key intent, and confirm the legal basis for portal automation (human decision).
