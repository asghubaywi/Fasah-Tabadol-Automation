# ADR 0001 — Hybrid Rust engine + Python orchestration

**Status:** Inferred — Requires Human Confirmation

## Context
The system needs correct, fast, deterministic parsing/compliance logic *and* pragmatic glue for filesystem polling, subprocess management, and browser automation.

## Decision
Implement the pure decision logic (parse, compliance, dispatch, watch, shipment state) as a standalone **Rust** binary `fasah-engine`, and the orchestration + browser automation in **Python**, communicating via CLI argv + JSON on stdout.

## Evidence from the project
- `Cargo.toml` workspace + `src/agents/` Rust crate; `main.rs` CLI with `parse|check|watch`.
- `orchestrator.py:97-128` shells out to the binary and parses JSON.
- `lib.rs` docstring: "Used by the Python orchestrator via the `fasah-engine` CLI binary."

## Alternatives
- Pure Python (simpler, slower, weaker type guarantees).
- Pure Rust incl. browser (Rust browser automation is less mature than Playwright-Python).
- PyO3/FFI binding instead of subprocess (tighter coupling, harder builds).

## Pros
- Strong typing + performance for the hot path; pure, testable core.
- Python's mature Playwright + rapid iteration for glue.
- Loose coupling via CLI keeps the two independently testable.

## Cons / Risks
- **Two languages, two toolchains** to build/CI.
- Encourages **logic duplication** (see ADR 0004) and drift (GAP-DRIFT-001).
- Subprocess boundary is versioned only by argv/JSON convention — no typed contract.

## Revisit conditions
If duplication/drift becomes unmanageable, or if the browser step moves in-process, reconsider FFI or collapsing to one language.
