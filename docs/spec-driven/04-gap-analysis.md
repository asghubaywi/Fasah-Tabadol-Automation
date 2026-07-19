# 04 — Gap Analysis / تحليل الفجوات

> Every finding is backed by direct evidence (code line or a real command result). Speculative items are marked as such.
> **Priority:** P0 critical (data loss / breach / direct compromise) · P1 high (blocks reliable operation) · P2 medium · P3 low.
> **No P0 findings were confirmed by direct evidence.** The most severe confirmed items are **P1**.

## Summary by priority

| Priority | Count | IDs |
|----------|-------|-----|
| P0 | 0 | — |
| P1 | 6 | GAP-CI-001, GAP-DEPLOY-001, GAP-BUG-001, GAP-DRIFT-001, GAP-TEST-001, GAP-QUAL-002 |
| P2 | 17 | GAP-BUG-002/003, GAP-CI-002, GAP-QUAL-001/003, GAP-CONTRACT-001, GAP-ARCH-001/002/003, GAP-DRIFT-002, GAP-TEST-002/003, GAP-SEC-001/002/005, GAP-OPS-001/003, GAP-DOC-001 |
| P3 | 10 | GAP-ARCH-004, GAP-TEST-004, GAP-SEC-003/004, GAP-OPS-002, GAP-DOC-002/003, and human-decision items |

Category legend: BUG (confirmed defect), CI, DEPLOY, QUAL (lint/format), CONTRACT, ARCH (architecture debt), DRIFT (Rust↔Python), TEST (coverage), SEC (security), OPS (operability), DOC (doc conflict), HUM (needs human decision).

---

## P1 — High

### GAP-CI-001 — CI is disconnected (branch mismatch)
- **Description:** CI triggers only on `main`, but the repo's default branch is `master`.
- **Evidence:** `.github/workflows/ci.yml:4-7`; `git remote show origin` → `HEAD branch: master`.
- **Impact:** No automated gate has ever run on the default branch; all quality regressions land unchecked.
- **Likelihood:** Certain (structural).
- **Fix:** Add `master` (and PR base `master`) to the workflow triggers, or rename the default branch — human decision on branch strategy.
- **Acceptance test:** A push/PR to the default branch shows a running CI check.
- **Files:** `.github/workflows/ci.yml`.
- **Needs human decision?** Yes (branch naming).

### GAP-DEPLOY-001 — Docker deployment is broken (missing Dockerfile)
- **Description:** `docker-compose.yml` builds from `Dockerfile` (targets `orchestrator`, `browser-worker`) that does not exist.
- **Evidence:** `docker-compose.yml:6-8,33-35`; `ls Dockerfile` → not found.
- **Impact:** The documented production deployment path (`README.md:243-250`) fails immediately.
- **Likelihood:** Certain.
- **Fix:** Add a multi-stage `Dockerfile` with `orchestrator` and `browser-worker` targets (Rust build stage + Python runtime + Playwright), or remove the compose deployment claim.
- **Acceptance test:** `docker compose build` succeeds; both services start.
- **Files:** new `Dockerfile`, `docker-compose.yml`.
- **Needs human decision?** No (but deployment target choices, yes).

### GAP-BUG-001 — Fallback parser crashes on a missing file
- **Description:** `parse_csv` computes the file SHA-256 **before** the read try/except, so a nonexistent file raises `FileNotFoundError` instead of returning an error result — defeating graceful degradation.
- **Evidence:** `fallback_parser.py:149` (hash) precedes `155-184` (guarded read); failing test `test_dropout.py::test_parse_nonexistent_file` (`06-baseline-verification.md`).
- **Impact:** In degraded mode, a missing/racing inbox file crashes `process_file` → quarantine instead of clean handling; contradicts the resilience design.
- **Likelihood:** Medium (file races, deleted files).
- **Fix:** Move `_sha256_file` inside a guard, or return an error dict on `OSError` before hashing.
- **Acceptance test:** `test_parse_nonexistent_file` passes.
- **Files:** `src/pipeline/fallback_parser.py`.
- **Needs human decision?** No.

### GAP-DRIFT-001 — Rust and Python compliance verdicts diverge
- **Description:** The Python fallback compliance differs from the authoritative Rust engine: banned-HS risk 95 vs 100; certificate matching is first-match (Py) vs union of 2- and 4-digit prefixes (Rust); Python never emits `approve_with_conditions`; escalated items are double-counted as held (Py). No test asserts equivalence.
- **Evidence:** `compliance.rs:150-239,260-291` vs `fallback_compliance.py:96-197`.
- **Impact:** **The same declaration can receive a different compliance verdict depending on whether Rust or the Python fallback ran** — a data-integrity/compliance-correctness risk (Constitution P14).
- **Likelihood:** Medium (only when degraded), but consequence is high.
- **Fix:** Choose the canonical semantics (human decision GAP-HUM-001), align the other implementation, and add golden-vector equivalence tests.
- **Acceptance test:** A shared fixture set produces identical verdicts+risk from `fasah-engine check` and the Python fallback.
- **Files:** `compliance.rs`, `fallback_compliance.py`, new tests.
- **Needs human decision?** Yes (canonical semantics).

### GAP-TEST-001 — The browser worker is entirely untested
- **Description:** `worker.py` (970 LoC, security-critical) has zero automated tests: gates, out_dir sanitization, domain allowlist, playbook flow, bundle building are all unverified by tests.
- **Evidence:** `tests/test_dropout.py` imports `browser.health_check`/`browser.retry` only; no import of `browser.worker`.
- **Impact:** The highest-risk component (drives a government portal, enforces security gates) can regress silently.
- **Likelihood:** High over time.
- **Fix:** Unit-test the pure/guardable functions (`resolve_out_dir`, `is_domain_allowed`, `validate_prod_config`, `check_artifact_limits`, `_resolve_playbook`, bundle assembly) with a mocked Playwright page.
- **Acceptance test:** Tests cover each gate's allow+deny path; run in CI.
- **Files:** `src/browser/worker.py`, new `tests/test_worker.py`.
- **Needs human decision?** No.

### GAP-QUAL-002 — `cargo clippy -- -D warnings` fails
- **Description:** Two `clippy::ptr_arg` errors (`&PathBuf` should be `&Path`).
- **Evidence:** `main.rs:109-110`; `cargo clippy -- -D warnings` → exit 101 (`06-baseline-verification.md`).
- **Impact:** The CI clippy gate would fail; code isn't lint-clean.
- **Likelihood:** Certain.
- **Fix:** Change `cmd_watch` params to `&Path`.
- **Acceptance test:** `cargo clippy -- -D warnings` exits 0.
- **Files:** `src/agents/src/main.rs`.
- **Needs human decision?** No.

---

## P2 — Medium

### GAP-BUG-002 — Resilient audit can raise (violates "never raises")
- **Evidence:** `resilient_audit.py:119` catches only `OSError`; failing test `test_never_raises`.
- **Impact:** A non-OSError during path resolution propagates into the caller; audit is supposed to be non-blocking.
- **Fix:** Broaden the guard to `Exception` (or wrap `_log_path()` + write). **Acceptance:** `test_never_raises` passes. **Files:** `resilient_audit.py`.

### GAP-BUG-003 — Health dashboard always reports the engine "degraded"
- **Evidence:** `health.py:62-76` probes `fasah-engine --version`; the CLI exits 1 on `--version` (`main.rs:34-36`; verified exit 1).
- **Impact:** False-negative health signal; operators can't trust the dashboard.
- **Fix:** Implement `--version` in the CLI (and/or probe with a real subcommand). **Acceptance:** `fasah-engine --version` exits 0 and health shows `healthy`. **Files:** `main.rs`, `health.py`.

### GAP-CI-002 — CI never runs the Python test suite
- **Evidence:** `ci.yml:40-60` runs only `ruff check src/`; no `pytest`.
- **Impact:** 54 resilience tests (incl. the 2 currently failing) are never gated. **Fix:** add a `pytest tests/` step. **Files:** `ci.yml`.

### GAP-QUAL-001 — `cargo fmt --all -- --check` fails
- **Evidence:** diffs in `compliance.rs:248`, `parser.rs:212`; exit 1. **Fix:** `cargo fmt --all`. **Acceptance:** fmt check exits 0.

### GAP-QUAL-003 — `ruff check src/` fails
- **Evidence:** `audit.py:10` unused `import os` (F401). **Fix:** remove the import. **Acceptance:** `ruff check src/` exits 0.

### GAP-CONTRACT-001 — Bundle output violates its own schema
- **Evidence:** `worker.py:920-924` writes `tool_versions:{playwright,...}`, but `fasah_bundle.schema.json:90-98` **requires** `agent_browser`; `_write_error_bundle` omits `tool_versions`. No runtime validation anywhere.
- **Impact:** Any external consumer validating bundles rejects them; contract is fictional. **Fix:** align worker↔schema (human: which is canonical) and validate at boundaries. **Files:** `worker.py`, `schemas/fasah_bundle.schema.json`.

### GAP-ARCH-001 — Dual dispatcher; result watcher loses declaration mapping
- **Evidence:** live dispatch is Python (`orchestrator.py:341-379`), but `result_watcher.rs:133-136` maps via the **Rust** `.pending_tasks.json` ledger that the Python writer never populates → `declaration_number = "UNKNOWN"`.
- **Impact:** Tracking/escalation for live-dispatched tasks lose their declaration linkage. **Fix:** unify on one dispatcher (human: which). **Files:** `dispatcher.rs`, `orchestrator.py`, `result_watcher.rs`.

### GAP-ARCH-002 — No file-stability check on ingest
- **Evidence:** `orchestrator.py:474-497` reads files immediately; `stability.rs` exists but is unwired.
- **Impact:** A file still being written can be parsed partially. **Fix:** require two stable stat() cycles before processing (port `stability.rs` behavior). **Files:** `orchestrator.py`.

### GAP-ARCH-003 — Shipment state machine not enforced at runtime
- **Evidence:** `orchestrator.py:389-397` writes statuses via a local map, bypassing `shipment.rs` transition checks.
- **Impact:** Illegal status jumps are possible; the tested state machine gives false assurance. **Fix:** route status writes through `can_transition_to`. **Files:** `orchestrator.py`, `shipment.rs`.

### GAP-DRIFT-002 — CSV parsing differs (Rust naive-split vs Python DictReader)
- **Evidence:** `parser.rs:100` splits on `,` (no quoting, positional); `fallback_parser.py:156` uses `csv.DictReader` (quote-aware, name-based).
- **Impact:** Quoted or column-reordered CSVs parse differently between engines. **Fix:** use a real CSV parser in Rust (e.g., `csv` crate) and match header-based field access. **Files:** `parser.rs`.

### GAP-TEST-002 — Orchestrator main loop untested
- **Evidence:** no test drives `main()`, signal handling, dedup-skip, or quarantine-on-failure. **Fix:** add loop/integration tests with a temp workspace.

### GAP-TEST-003 — No Rust↔Python equivalence tests
- Tied to GAP-DRIFT-001/002. **Fix:** shared golden vectors run through both engines.

### GAP-SEC-001 — `AGENT_BROWSER_ENCRYPTION_KEY` required but unused
- **Evidence:** validated for presence (`worker.py:167-168`) but never used to encrypt. **Impact:** false sense of a security control; session `state.json` stored plaintext. **Fix:** either encrypt session at rest with it or remove the control and document. **Needs human decision?** Yes (intent).

### GAP-SEC-002 — The inbox/bus is implicitly trusted (no validation)
- **Evidence:** any readable `inbox/` file is processed; task JSON isn't schema/size validated (`orchestrator.py:474-497`, `worker.py:800-810`). **Impact:** malformed/oversized/hostile inputs processed; DoS via huge files. **Fix:** validate task JSON against schema; cap inbox file size; document the trust boundary.

### GAP-SEC-005 — Sanction screening off by default
- **Evidence:** `sanctioned_countries: []` in both defaults and `fasah_rules.yaml:21`. **Impact:** the sanctioned-origin rule (highest priority) never fires until configured. **Fix:** operational — populate the list; flag empty list at startup. **Needs human decision?** Yes (policy/source of truth).

### GAP-OPS-001 — Degradation/breaker state invisible across processes
- **Evidence:** in-memory singletons (`degradation.py:200-210`); health CLI runs in a separate process (`health.py:197-205`). **Impact:** real-time degradation isn't observable by ops. **Fix:** persist/emit degradation state or expose it from the orchestrator.

### GAP-OPS-003 — No scheduler/runbook for `fasah-engine watch`
- **Evidence:** `watch` is one-shot (`main.rs:108-129`); nothing schedules it; no runbook. **Impact:** browser results may never be processed in a real deployment. **Fix:** define a loop/timer + operational runbook.

### GAP-DOC-001 — Core docs omit the resilience layer and misstate facts
- **Evidence:** `README.md`/`docs/architecture.md` never mention circuit breaker, fallbacks, checkpoint, degradation, health; say "13 security gates" (only 9–13 exist); imply cross-platform (worker is POSIX-only). **Fix:** update docs to match code.

---

## P3 — Low

- **GAP-ARCH-004** — `idempotency.rs`, `stability.rs` unused vs CLI; `tokio` dependency unused. Remove or wire in. (`lib.rs`, `Cargo.toml`.)
- **GAP-TEST-004** — No integration/E2E tests (CSV→outbox with real subprocess). Add one smoke E2E.
- **GAP-SEC-003** — Chromium `--no-sandbox` (`worker.py:404`) — accepted risk; document + container isolation.
- **GAP-SEC-004** — `Cargo.lock` git-ignored (`.gitignore:4`) — commit it for reproducible/audited builds (it's a binary/app).
- **GAP-OPS-002** — No metrics endpoint / alerting integration.
- **GAP-DOC-002** — `evidence/` is stale (Windows, earlier commit; `pytest.txt` "no tests ran"). Regenerate or remove.
- **GAP-DOC-003** — Docs require Python 3.11+, but stale evidence ran 3.10.11.

---

## Human-decision register / قرارات تحتاج اعتمادًا بشريًا
| ID | Decision needed |
|----|-----------------|
| GAP-HUM-001 | Canonical compliance semantics when Rust and Python disagree |
| GAP-HUM-002 | Legal/authorization basis and scope for automating the Fasah portal |
| GAP-HUM-003 | Validate compliance rule set against official SFDA/SASO/customs sources + versioning |
| GAP-HUM-004 | Which dispatcher (Rust `watch` ledger vs Python orchestrator) is canonical |
| GAP-HUM-005 | Whether/how to encrypt session `state.json` at rest (encryption-key intent) |
| GAP-HUM-006 | Branch strategy (`main` vs `master`) for CI |
| GAP-HUM-007 | Default sanctioned-countries policy and its authoritative source |
