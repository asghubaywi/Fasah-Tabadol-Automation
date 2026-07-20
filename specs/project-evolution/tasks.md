# Executable Tasks / المهام التنفيذية

> Derived from `plan.md`, dependency-ordered. Each task is concrete and independently verifiable.
>
> **✅ Executed in the "merge & fix everything" pass (all gates green — see `docs/spec-driven/06-baseline-verification.md`):**
> T-001, T-002, T-003 (gates), T-101, T-102, T-103 (bugs), T-105 (compliance equivalence),
> T-004 (CI on main+master +pytest), T-106 (Dockerfile — added, not built here), T-306 (Cargo.lock),
> T-108 (empty-sanctions warning), and T-201 **partially** (worker gate tests; live playbook still TODO).
> **Remaining / deferred** (larger change or needs a human decision): T-202, T-203, T-204, all of Phase 3–5,
> and every `👤` task. See `04-gap-analysis.md` §Resolution.
> Fields: Goal · Files · Requirements · Depends-on · Steps · Tests · Acceptance · Closure evidence · Risk · Parallelizable · Needs human approval · May change existing behavior.

Legend: 🟢 low risk · 🟡 medium · 🔴 high. ⚠ = may change runtime behavior. 👤 = needs human approval.

---

## Phase 0 — Stabilize knowledge & gates

### T-001 — Apply rustfmt across the crate
- **Goal:** Make `cargo fmt --all -- --check` pass (GAP-QUAL-001).
- **Files:** `src/agents/src/compliance.rs`, `parser.rs` (whatever fmt touches).
- **Requirements:** dev-quality gate. **Depends-on:** —.
- **Steps:** Run `cargo fmt --all`; review the diff is formatting-only; commit in isolation.
- **Tests:** `cargo test` still 19/19. **Acceptance:** `cargo fmt --all -- --check` exits 0.
- **Closure evidence:** command exit 0 + green tests. **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-002 — Fix clippy `ptr_arg` in `cmd_watch`
- **Goal:** `cargo clippy -- -D warnings` passes (GAP-QUAL-002).
- **Files:** `src/agents/src/main.rs:108-129`.
- **Steps:** Change `results_dir: &PathBuf, outbox_dir: &PathBuf` → `&Path`; adjust call sites.
- **Tests:** `cargo test`; `cargo clippy -- -D warnings`. **Acceptance:** clippy exits 0.
- **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-003 — Remove unused `import os` in audit.py
- **Goal:** `ruff check src/` passes (GAP-QUAL-003). **Files:** `src/utils/audit.py:10`.
- **Steps:** Delete the import (or `ruff check --fix`). **Tests:** `pytest tests/`; `ruff check src/`. **Acceptance:** ruff exits 0.
- **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-004 — Connect CI to the default branch and add pytest
- **Goal:** CI actually runs, and gates Python tests (GAP-CI-001/002).
- **Files:** `.github/workflows/ci.yml`.
- **Depends-on:** T-001..T-003 (so CI goes green), 👤 GAP-HUM-006 (branch strategy).
- **Steps:** Set triggers to the default branch (`master` or after a rename); add `- run: pip install pytest && pytest tests/` to the Python job (pytest doesn't need Playwright).
- **Tests:** Observe a CI run. **Acceptance:** CI executes on default-branch push/PR and all steps pass.
- **Closure evidence:** CI run URL, all green. **Risk:** 🟢. **Parallel:** no. **Human:** yes (branch). **Behavior change:** no.

### T-005 — Regenerate or remove stale `evidence/`
- **Goal:** Remove misleading Windows/earlier-commit captures (GAP-DOC-002).
- **Files:** `evidence/*`. **Steps:** Regenerate from a Linux run (or delete and rely on `06-baseline-verification.md`). **Acceptance:** `evidence/` reflects the current commit or is gone. **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-006 — Reconcile README/architecture docs with reality
- **Goal:** Docs describe the resilience layer, correct gate numbering, POSIX-only worker (GAP-DOC-001/003).
- **Files:** `README.md`, `docs/architecture.md`. **Steps:** Add resilience/health sections; correct "13 gates" → "gates 9–13 (inherited)"; state POSIX-only; fix Python version note; link the spec-driven docs. **Acceptance:** No remaining doc↔code contradiction from the gap list. **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-007 — 👤 Ratify or amend constitution + inferred ADRs
- **Goal:** Convert `Inferred` ADRs to human-approved status; ratify constitution v1.0.0.
- **Files:** `docs/adr/*`, `.specify/memory/constitution.md` + mirror. **Steps:** Maintainer reviews each ADR; confirm/amend; update status + version. **Acceptance:** ADR statuses reflect a real human decision. **Risk:** 🟢. **Parallel:** yes. **Human:** yes. **Behavior change:** no.

---

## Phase 1 — Critical correctness & safety (P1)

### T-101 — Fix fallback parser crash on missing file ⚠
- **Goal:** `parse_csv`/`parse_file` return an error result (not raise) for a missing/unreadable file (GAP-BUG-001).
- **Files:** `src/pipeline/fallback_parser.py:46-193`. **Requirements:** REQ-RESIL-002, REQ-PARSE-010.
- **Depends-on:** T-003. **Steps:** Guard `_sha256_file` (try/except → error dict), or compute the hash inside the read guard; keep output shape identical.
- **Tests:** `test_dropout.py::test_parse_nonexistent_file` passes; add empty/permission-denied cases. **Acceptance:** `pytest tests/` green. **Closure evidence:** test output. **Risk:** 🟡 ⚠ (changes degraded-path behavior from crash→graceful). **Parallel:** yes. **Human:** no.

### T-102 — Make ResilientAuditLogger truly non-raising ⚠
- **Goal:** `record()` never propagates (GAP-BUG-002). **Files:** `src/utils/resilient_audit.py:112-165`.
- **Depends-on:** —. **Steps:** Broaden the guard around `_log_path()`+write to `Exception` (still buffer/warn). **Tests:** `test_never_raises` passes; existing audit tests stay green. **Acceptance:** `pytest tests/` green. **Risk:** 🟡 ⚠. **Parallel:** yes. **Human:** no.

### T-103 — Implement `fasah-engine --version`
- **Goal:** Fix the health false-degrade (GAP-BUG-003). **Files:** `src/agents/src/main.rs`, (optionally) `health.py:62-76`.
- **Steps:** Handle `--version`/`-V` before the arg-count check, print `env!("CARGO_PKG_VERSION")`, exit 0. **Tests:** add a small check that `--version` exits 0; `cargo test`. **Acceptance:** `fasah-engine --version` exits 0; `python -m src.utils.health` shows engine `healthy`. **Closure evidence:** command outputs. **Risk:** 🟢. **Parallel:** yes. **Human:** no. **Behavior change:** additive.

### T-104 — 👤 Decide canonical compliance semantics
- **Goal:** Resolve GAP-HUM-001: is Rust or Python authoritative, and what is the intended cert-matching / risk-score / count behavior?
- **Files:** decision recorded as a new ADR. **Depends-on:** `domain-compliance.md`. **Acceptance:** Written decision covering each divergence in GAP-DRIFT-001. **Risk:** 🟢 (decision only). **Parallel:** yes. **Human:** yes. **Behavior change:** enables T-105.

### T-105 — Align fallback compliance to canonical semantics + golden-vector equivalence tests ⚠
- **Goal:** Rust and Python produce identical verdicts+risk (GAP-DRIFT-001, REQ-COMP-*, Constitution P14).
- **Files:** `fallback_compliance.py`, possibly `compliance.rs`, new `tests/test_compliance_equivalence.py` + shared fixtures.
- **Depends-on:** T-104. **Steps:** Build a fixture set spanning every rule/branch; run through `fasah-engine check` and the Python fallback; assert equality; fix the non-canonical side.
- **Tests:** new equivalence suite. **Acceptance:** all vectors identical; `cargo test` + `pytest` green. **Risk:** 🔴 ⚠ (verdict semantics — data-integrity). **Parallel:** no. **Human:** yes (via T-104).

### T-106 — Add multi-stage Dockerfile
- **Goal:** `docker compose build/up` works (GAP-DEPLOY-001). **Files:** new `Dockerfile`, maybe `docker-compose.yml`.
- **Steps:** Stage 1 Rust build → `fasah-engine`; stage `orchestrator` (Python + engine + config); stage `browser-worker` (Python + Playwright + Chromium). Respect the compose `target`s.
- **Tests:** `docker compose build`; smoke-run orchestrator against sample. **Acceptance:** both images build; orchestrator processes the sample CSV. **Risk:** 🟡. **Parallel:** yes. **Human:** no. **Behavior change:** additive.

### T-107 — File-stability check before ingest ⚠
- **Goal:** Don't process partially-written inbox files (GAP-ARCH-002, NFR-REL-002). **Files:** `src/pipeline/orchestrator.py:474-497`.
- **Steps:** Require size+mtime unchanged across two poll cycles before processing (port `stability.rs` logic to Python, or invoke it).
- **Tests:** unit test simulating a growing file. **Acceptance:** a file whose size changes between polls is skipped until stable. **Risk:** 🟡 ⚠ (adds a one-cycle delay). **Parallel:** yes. **Human:** no.

### T-108 — Flag empty sanctions list at startup 👤
- **Goal:** Surface that sanction screening is off (GAP-SEC-005); set policy (GAP-HUM-007). **Files:** `orchestrator.py`/`worker.py` startup, `config/fasah_rules.yaml`.
- **Steps:** Log a prominent WARN + audit event if `sanctioned_countries` is empty; populate per approved policy. **Acceptance:** empty list produces a startup warning + audit line. **Risk:** 🟢. **Parallel:** yes. **Human:** yes (policy). **Behavior change:** additive (log/audit only).

---

## Phase 2 — Testability & verification

### T-201 — Unit-test the browser worker gates & helpers
- **Goal:** Cover `worker.py` pure/guardable logic (GAP-TEST-001, REQ-BROW-006..011, NFR-SEC-001..005). **Files:** new `tests/test_worker.py`.
- **Depends-on:** Phase 1. **Steps:** Test `is_domain_allowed` (allow+deny+wildcard), `resolve_out_dir` (traversal rejected), `validate_prod_config` (missing env exits), `check_artifact_limits` (each limit), `_resolve_playbook` (alias + unknown), bundle assembly with a `MagicMock` page.
- **Acceptance:** allow+deny path per gate; runs in CI (no real browser). **Risk:** 🟡. **Parallel:** yes. **Human:** no. **Behavior change:** no (tests only).

### T-202 — Orchestrator loop/lifecycle tests
- **Goal:** Cover poll filter, dedup-skip, quarantine-on-failure, signal shutdown (GAP-TEST-002, REQ-ING-001/002/004/006). **Files:** new `tests/test_orchestrator_loop.py`. **Steps:** Drive `main()`/`process_file` against a temp workspace with mocked engine. **Acceptance:** each lifecycle branch asserted. **Risk:** 🟡. **Parallel:** yes. **Human:** no. **Behavior change:** no.

### T-203 — Enforce task/bundle schema at boundaries + fix `tool_versions` ⚠
- **Goal:** Make the contracts real (GAP-CONTRACT-001, REQ-BROW-005). **Files:** `worker.py`, `orchestrator.py`, `result_watcher.rs`, `schemas/fasah_bundle.schema.json`.
- **Depends-on:** 👤 which side is canonical (`agent_browser` vs `playwright`). **Steps:** Validate envelopes on produce+consume; reconcile the `tool_versions` key; include it in error bundles. **Tests:** valid passes, invalid rejected with `E_*`. **Acceptance:** a real bundle validates against the schema. **Risk:** 🟡 ⚠. **Parallel:** no. **Human:** yes (canonical key).

### T-204 — End-to-end smoke test
- **Goal:** CSV→outbox with the real Rust subprocess (GAP-TEST-004). **Files:** new `tests/test_e2e_smoke.py`. **Steps:** Build engine, drop the sample CSV, run one orchestrator cycle, assert outbox commands match expected verdicts. **Acceptance:** E2E passes in CI (Rust available). **Risk:** 🟡. **Parallel:** yes. **Human:** no. **Behavior change:** no.

---

## Phase 3 — Architecture hardening (each 🟡/🔴 ⚠, depends on Phase 2 coverage)

### T-301 — 👤 Consolidate the dual dispatcher
Unify Python-orchestrator vs Rust-`watch` dispatch on one canonical path (GAP-ARCH-001, GAP-HUM-004) so `result_watcher` never sees `UNKNOWN`. Files: `dispatcher.rs`, `orchestrator.py`, `result_watcher.rs`. Tests: watch resolves declaration for a live-dispatched task. Risk: 🔴 ⚠.

### T-302 — Enforce shipment transitions on the live path ⚠
Route orchestrator/result-watcher status writes through `ShipmentStatus::can_transition_to` (GAP-ARCH-003). Reject/handle illegal jumps. Tests: illegal transition rejected. Risk: 🟡 ⚠.

### T-303 — Resolve unused modules & deps
Wire in or delete `idempotency.rs`, `stability.rs`; remove unused `tokio` (GAP-ARCH-004). Tests: `cargo test`/clippy green. Risk: 🟡 (⚠ if wired in).

### T-304 — Make all outbox writes atomic ⚠
Convert plain `write` in `orchestrator.py:414-415` and `result_watcher.rs:252,282` to tmp→fsync→rename (NFR-REL-001). Tests: crash-injection leaves no truncated command. Risk: 🟡 ⚠.

### T-305 — Robust Rust CSV parsing ⚠
Replace naive `split(',')`+positional access with the `csv` crate + header-name access (GAP-DRIFT-002). Tests: quoted/reordered CSV matches the Python parser (equivalence). Risk: 🟡 ⚠.

### T-306 — Commit `Cargo.lock`
Remove it from `.gitignore` and commit for reproducible builds (GAP-SEC-004). Risk: 🟢. Behavior change: no.

---

## Phase 4 — Operational readiness (depends on Phase 3)

- **T-401** — Cross-process health/metrics surface (persist/emit degradation; optional HTTP/metrics) — GAP-OPS-001/002. 🟡
- **T-402** — Scheduler + runbook for `fasah-engine watch` (loop or timer; documented ops) — GAP-OPS-003. 🟡 ⚠
- **T-403** — `workspace/` backup policy + audit log rotation/retention. 🟢
- **T-404** — 👤 Decide + implement session `state.json` encryption-at-rest using `AGENT_BROWSER_ENCRYPTION_KEY`, or remove the control — GAP-SEC-001/HUM-005. 🟡 ⚠
- **T-405** — Inbox input validation + size caps; validate task JSON (GAP-SEC-002). 🟡 ⚠

---

## Phase 5 — Approved functional evolution (each needs its own spec + ADR + 👤)

- **T-501** — Tabadol ingestion API behind the inbox contract (candidate). 🔴 ⚠ 👤
- **T-502** — Additional read-only portal playbooks (candidate). 🟡 👤
- **T-503** — Reporting surface over the audit log (candidate). 🟡 👤
- **T-504** — 👤 **Gated**: any portal *write* action — different risk class; requires GAP-HUM-002 (legal/authorization) before design. 🔴 ⚠ 👤

---

## First 5 recommended tasks / أول خمس مهام موصى بها
1. **T-002** (clippy) 2. **T-003** (ruff) 3. **T-001** (fmt) 4. **T-004** (connect CI + pytest) 5. **T-101** (fix fallback-parser crash).
These 5 are low/medium risk, need no human decision (except T-004 branch naming), and immediately turn the baseline from "all gates red" to "gates green, tests passing," unblocking everything else.
