# Project Evolution Plan / خطة تطوير المشروع

> Phased, dependency-ordered. **Discovery (Phase A) is done; this plan is Phase B and requires explicit human approval before any P-1/onward implementation begins.** Phase 0 is documentation/tiny-fix only and is the natural continuation of discovery.
> Priorities reference `docs/spec-driven/04-gap-analysis.md`.

---

## Phase 0 — Stabilize knowledge & unblock the gates / تثبيت المعرفة
**Goal:** Make the baseline honest and the quality gates *runnable and green*, without changing runtime behavior.
**Scope:** Fix formatting/lint so gates pass (GAP-QUAL-001/002/003); connect CI to the real branch and add pytest (GAP-CI-001/002); regenerate/replace stale `evidence/` (GAP-DOC-002); correct docs to match code (GAP-DOC-001/003); ratify or amend the inferred ADRs and constitution (human).
**Out of scope:** Any behavior change; the 2 failing-test *bug fixes* (those are Phase 1).
**Prerequisites:** This discovery report; human confirmation of the inferred ADRs.
**Deliverables:** Green `cargo fmt`/`clippy`/`ruff`; CI running on the default branch incl. `pytest`; updated README/architecture; ratified constitution/ADRs.
**Acceptance criteria:** All four gates pass locally and in CI on the default branch; docs no longer contradict code.
**Risks:** `cargo fmt --all` reformats broadly — do it as one isolated commit. **Rollback:** revert the formatting/CI commits (no behavior touched).
**Evidence for closure:** CI run URL showing green fmt+clippy+ruff+cargo test+pytest; updated `06-baseline-verification.md`.

## Phase 1 — Close critical correctness & safety gaps / إغلاق المخاطر الحرجة (P0/P1)
**Goal:** Eliminate the confirmed high-severity defects and data-integrity risks.
**Scope:** Fix fallback-parser crash (GAP-BUG-001); fix resilient-audit "never raises" (GAP-BUG-002); fix health `--version` false-degrade (GAP-BUG-003); decide + enforce canonical compliance semantics and add Rust↔Python equivalence tests (GAP-DRIFT-001, needs GAP-HUM-001); provide a working `Dockerfile` (GAP-DEPLOY-001); add file-stability-before-ingest (GAP-ARCH-002); populate/flag sanctioned-countries policy (GAP-SEC-005, needs GAP-HUM-007).
**Out of scope:** Broad refactors; browser test build-out (Phase 2); dispatcher consolidation (Phase 3).
**Prerequisites:** Phase 0 gates green; human decisions GAP-HUM-001, GAP-HUM-007.
**Deliverables:** Passing `pytest` (0 failures); equivalence test suite; buildable container; startup warning when sanctions list empty.
**Acceptance criteria:** `cargo test` + `pytest` fully green; equivalence vectors identical across engines; `docker compose build` succeeds.
**Risks:** Aligning compliance semantics changes verdicts (data-integrity sensitive) — gate behind human sign-off + audit. **Rollback:** per-fix revert; equivalence tests protect against regressions.
**Evidence for closure:** Green test runs; equivalence report; container build log.

## Phase 2 — Testability & verification / رفع قابلية الاختبار
**Goal:** Cover the untested, highest-risk surfaces.
**Scope:** Unit-test `worker.py` gates/sanitizers/bundle with a mocked page (GAP-TEST-001); orchestrator loop/signal/quarantine/dedup tests (GAP-TEST-002); Rust↔Python equivalence expansion (GAP-TEST-003); one E2E smoke (CSV→outbox with real subprocess) (GAP-TEST-004); enforce bundle/task schema validation at boundaries (GAP-CONTRACT-001).
**Out of scope:** New product features.
**Prerequisites:** Phase 1 (so tests assert *correct* behavior).
**Deliverables:** Test suites for worker + orchestrator + E2E; schema-validation guards.
**Acceptance criteria:** Worker gate allow/deny paths tested; E2E passes in CI; invalid bundles/tasks are rejected with a structured error.
**Risks:** Playwright mocking effort. **Rollback:** tests are additive; revert individually.
**Evidence for closure:** Coverage delta; CI green including new suites.

## Phase 3 — Architecture hardening / تقوية المعمارية
**Goal:** Remove duplication and un-wired safety nets; stabilize contracts.
**Scope:** Consolidate the dual dispatcher (GAP-ARCH-001, needs GAP-HUM-004); wire shipment-state enforcement into the live path (GAP-ARCH-003); resolve `idempotency.rs`/`stability.rs`/`tokio` (wire in or remove — GAP-ARCH-004); make all outbox writes atomic; fix Rust CSV parsing to a real CSV reader (GAP-DRIFT-002); commit `Cargo.lock` (GAP-SEC-004).
**Out of scope:** New playbooks / portal write actions.
**Prerequisites:** Phase 2 tests (safety net for refactor).
**Deliverables:** Single dispatcher; enforced transitions; atomic writes; robust CSV; reproducible builds.
**Acceptance criteria:** No `UNKNOWN` declaration mapping in `watch`; illegal status transitions rejected; equivalence tests still green.
**Risks:** Refactor regressions — rely on Phase 2 coverage. **Rollback:** revert per change; contracts pinned by tests.
**Evidence for closure:** Green suites; before/after architecture note.

## Phase 4 — Operational readiness / الجاهزية التشغيلية
**Goal:** Make it deployable, observable, and recoverable.
**Scope:** Logging/metrics/health endpoint (GAP-OPS-001/002); scheduler + runbook for `fasah-engine watch` (GAP-OPS-003); backups/retention for `workspace/` and audit rotation; encryption-at-rest decision for session state (GAP-SEC-001, needs GAP-HUM-005); inbox input validation + size caps (GAP-SEC-002); document `--no-sandbox` isolation (GAP-SEC-003).
**Out of scope:** New clearance features.
**Prerequisites:** Phases 1–3.
**Deliverables:** Health/metrics surface; runbooks; backup + rotation config; hardened inbox.
**Acceptance criteria:** Health reflects real degradation across processes; documented, tested recovery from a simulated crash; oversized/hostile inbox inputs rejected.
**Risks:** Scope creep into infra. **Rollback:** feature-flag new surfaces.
**Evidence for closure:** Runbook, a recorded recovery drill, monitoring screenshots/logs.

## Phase 5 — Approved functional evolution / التطوير الوظيفي
**Goal:** Only human-approved new capability, on a stable base.
**Scope:** Candidates only, each needing its own spec + ADR + human approval: a real Tabadol ingestion API behind the inbox contract; additional read-only playbooks; a reporting surface over the audit log; (explicitly gated) any portal write action — a different risk class requiring GAP-HUM-002.
**Out of scope:** Anything not spec'd + approved.
**Prerequisites:** Phases 0–4 complete; per-feature approval.
**Deliverables:** Per approved feature.
**Acceptance criteria:** Feature spec traced end-to-end with tests; no regression in equivalence/contract suites.
**Risks:** Expanding portal scope beyond read-only (legal + safety). **Rollback:** feature-flagged; revert per feature.
**Evidence for closure:** Feature-level traceability + green suites.

---

## Dependency order
`Phase 0 → 1 → 2 → 3 → 4 → 5` (each depends on the prior). Within a phase, tasks are ordered in `tasks.md`. Human-decision items (GAP-HUM-*) gate the phases that consume them and should be resolved early.
