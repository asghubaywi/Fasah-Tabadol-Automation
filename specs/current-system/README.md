# Current-System Specifications / مواصفات النظام الحالي

These specs describe **what the system does today**, reverse-engineered from code, tests, and real runs (Phase A). They are the baseline of record. Target-state and proposed work live in `specs/project-evolution/`.

Each domain file uses a fixed structure: Goal · Actors · Inputs · Outputs · Business rules · Use cases · Main/exception/failure scenarios · Permissions · State changes · Data · Integrations · Proven behavior · Tests · Code files · Known constraints · Open questions.

## Domain files

| # | Domain | File | Primary code |
|---|--------|------|--------------|
| 1 | Declaration parsing | [`domain-parsing.md`](domain-parsing.md) | `parser.rs`, `fallback_parser.py` |
| 2 | Compliance checking | [`domain-compliance.md`](domain-compliance.md) | `compliance.rs`, `fallback_compliance.py` |
| 3 | Ingestion & orchestration | [`domain-ingestion-orchestration.md`](domain-ingestion-orchestration.md) | `orchestrator.py` |
| 4 | Browser dispatch | [`domain-dispatch.md`](domain-dispatch.md) | `dispatcher.rs`, `orchestrator._dispatch_browser_task` |
| 5 | Browser automation | [`domain-browser-automation.md`](domain-browser-automation.md) | `worker.py` |
| 6 | Result processing | [`domain-result-processing.md`](domain-result-processing.md) | `result_watcher.rs` |
| 7 | Shipment state machine | [`domain-shipment-state.md`](domain-shipment-state.md) | `shipment.rs` |
| 8 | Resilience & degradation | [`domain-resilience.md`](domain-resilience.md) | `circuit_breaker.py`, `checkpoint.py`, `degradation.py`, `health_check.py`, `retry.py` |
| 9 | Audit logging | [`domain-audit.md`](domain-audit.md) | `audit.py`, `resilient_audit.py` |
| 10 | Health & observability | [`domain-health.md`](domain-health.md) | `health.py` |
| — | Non-functional requirements | [`nfr.md`](nfr.md) | cross-cutting |

## Requirement ID registry / سجل المعرفات

Status legend (matches `docs/spec-driven/05-requirements-traceability.md`): **FV** Fully Verified · **PV** Partially Verified · **IWT** Implemented Without Test · **DWI** Documented Without Implementation · **INF** Inferred · **UNK** Unknown · **DEP** Deprecated.

### Functional

| ID | Requirement (one line) | Status |
|----|------------------------|--------|
| REQ-PARSE-001 | CSV header must contain all 10 required columns | FV |
| REQ-PARSE-002 | Data rows need ≥10 comma fields or are error-skipped | IWT |
| REQ-PARSE-003 | `declared_value_sar` must be non-negative numeric | FV |
| REQ-PARSE-004 | `weight_kg` must be non-negative numeric | IWT |
| REQ-PARSE-005 | HS code must be 6–10 digits (dots allowed) | FV |
| REQ-PARSE-006 | `origin_country` must be ISO-3166 alpha-2 uppercase | FV |
| REQ-PARSE-007 | `required_certificates` are `;`-separated (Rust) | IWT |
| REQ-PARSE-008 | Emit SHA-256 `content_hash` of the file | IWT |
| REQ-PARSE-009 | Parse JSON array input into records | IWT |
| REQ-PARSE-010 | Invalid rows skipped; valid rows still processed | FV |
| REQ-COMP-001 | Sanctioned origin → `reject_sanctioned`, risk 100 (top priority) | FV |
| REQ-COMP-002 | Banned HS prefix → `reject`, risk 100 (Rust) / 95 (Py) | FV |
| REQ-COMP-003 | Missing required certs → `hold_pending_certificates` | FV |
| REQ-COMP-004 | Value > threshold → `escalate_high_value` | FV |
| REQ-COMP-005 | Weight > threshold → `mandate_inspection` | PV |
| REQ-COMP-006 | Minor reasons only → `approve_with_conditions` (Rust only) | IWT |
| REQ-COMP-007 | Cert requirements matched at 2- and 4-digit HS prefixes | PV |
| REQ-COMP-008 | Aggregate counts approved/held/escalated/rejected | IWT |
| REQ-COMP-009 | Rules loaded from YAML, else built-in defaults | PV |
| REQ-ING-001 | Poll inbox for `.csv`/`.json`, ignore dot/`tmp*` files | IWT |
| REQ-ING-002 | Skip duplicates via SHA-256 ledger | IWT |
| REQ-ING-003 | Per file: parse → check → dispatch | PV |
| REQ-ING-004 | Move done→`processed/`, failed→`quarantine/` | IWT |
| REQ-ING-005 | Checkpoint after each file; resume in-flight on restart | PV |
| REQ-ING-006 | Graceful shutdown on SIGINT/SIGTERM | IWT |
| REQ-ING-007 | Route verdicts: browser vs direct outbox | PV |
| REQ-DISP-001 | `hold`/`escalate` → browser task envelope | FV |
| REQ-DISP-002 | Deterministic `task_id` (`fasah-<decl>-<ts>`) | IWT |
| REQ-DISP-003 | Atomic task-file write (tmp→fsync→rename) | IWT |
| REQ-DISP-004 | Pending ledger; retry up to max attempts | FV |
| REQ-DISP-005 | Track `risk_score` + `predicted_outcome` | IWT |
| REQ-BROW-001 | Poll `browser_tasks/` inbox every `ZC_POLL_INTERVAL` | UNK |
| REQ-BROW-002 | `fasah_search_inspect_v1`: navigate→search→open→extract status | UNK |
| REQ-BROW-003 | Reuse session; detect login redirect → `AUTH_FAIL` | UNK |
| REQ-BROW-004 | Classify outcome FOUND/NOT_FOUND/AUTH_FAIL/TRANSIENT_FAIL/NEEDS_HUMAN | UNK |
| REQ-BROW-005 | Emit `bundle.json` + `transcript.jsonl` + `sha256sum.txt` | UNK |
| REQ-BROW-006 | Gate 9: artifact count/size/dir-size limits | UNK |
| REQ-BROW-007 | Gate 10: prod fail-closed on missing env | UNK |
| REQ-BROW-008 | Gate 11: domain allowlist; block download/upload | UNK |
| REQ-BROW-009 | Gate 12: duplicate detection + flock task locks | UNK |
| REQ-BROW-010 | Gate 13: structured `E_*` error codes | IWT |
| REQ-BROW-011 | Sanitize `out_dir` to safe basename (no traversal) | UNK |
| REQ-BROW-012 | Resolve legacy playbook aliases | UNK |
| REQ-RESULT-001 | Scan `browser_results/*/bundle.json` | FV |
| REQ-RESULT-002 | FOUND + status keywords (incl Arabic) → approved/held/rejected | FV |
| REQ-RESULT-003 | TRANSIENT_FAIL → retry; max exceeded → escalate | FV |
| REQ-RESULT-004 | AUTH_FAIL/NEEDS_HUMAN → escalation file | FV |
| REQ-RESULT-005 | Move processed result dir to `.processed/` | IWT |
| REQ-RESULT-006 | Record prediction-correctness (decision quality) | IWT |
| REQ-SHIP-001 | Shipment status enum (8 states) | FV |
| REQ-SHIP-002 | Enforce valid state transitions | FV |
| REQ-SHIP-003 | `rejected` & `released` are terminal | FV |
| REQ-SHIP-004 | Write `track_*.json` tracking command | IWT |
| REQ-RESIL-001 | Circuit breaker CLOSED/OPEN/HALF_OPEN | FV |
| REQ-RESIL-002 | Python fallback parser mirrors engine output shape | PV |
| REQ-RESIL-003 | Python fallback compliance mirrors verdicts | PV |
| REQ-RESIL-004 | Crash-safe checkpoint/resume | FV |
| REQ-RESIL-005 | Central degradation registry | FV |
| REQ-RESIL-006 | Browser health monitor (consecutive failures, stuck) | FV |
| REQ-RESIL-007 | Exponential backoff retry helpers | FV |
| REQ-AUDIT-001 | Append-only daily JSONL audit | PV |
| REQ-AUDIT-002 | Resilient audit never blocks; buffers; drops oldest | PV (1 test FAILS) |
| REQ-AUDIT-003 | Audit is thread-safe | FV |
| REQ-HEALTH-001 | Health dashboard: 7 component checks | IWT |
| REQ-HEALTH-002 | Exit 0/1/2 by worst status | IWT |
| REQ-HEALTH-003 | `--json` and `--watch N` modes | IWT |

### Non-functional (see `nfr.md`)

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-SEC-001 | Browser domain allowlist enforced | IWT |
| NFR-SEC-002 | Prod requires allowlist + key + base URL (fail-closed) | IWT |
| NFR-SEC-003 | `out_dir` sanitized against path traversal | IWT |
| NFR-SEC-004 | Idempotency ledger rejects symlinks | IWT |
| NFR-SEC-005 | `download`/`upload` hard-blocked in browser | IWT |
| NFR-SEC-006 | Secrets only from env, never in repo | INF |
| NFR-SEC-007 | Chromium runs `--no-sandbox` (accepted risk) | INF |
| NFR-PERF-001 | Configurable poll intervals | IWT |
| NFR-PERF-002 | Rust hot path; browser output-size caps | INF |
| NFR-REL-001 | Atomic file writes for critical outputs | PV |
| NFR-REL-002 | Idempotent file processing | IWT |
| NFR-REL-003 | Crash-safe checkpoint | FV |
| NFR-REL-004 | Graceful degradation to Python fallbacks | FV |
| NFR-PORT-001 | Browser worker is POSIX-only (`fcntl`) | INF |
| NFR-OBS-001 | Auditable event trail | PV |
| NFR-OBS-002 | Browser evidence transcript + hash manifest | UNK |
| NFR-OBS-003 | Health dashboard CLI | IWT |

**Counts:** 83 requirements total — 66 functional (REQ-*), 17 non-functional (NFR-*).
Test-linkage (see `docs/spec-driven/05-requirements-traceability.md`): **26 Fully Verified (~31%)**, **38 linked to ≥1 automated test (FV+PV, ~46%)**; the remainder are Implemented-Without-Test, Unknown/Unverified (chiefly the browser worker), or Inferred.
