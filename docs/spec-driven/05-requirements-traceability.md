# 05 — Requirements Traceability Matrix / مصفوفة التتبع

Maps every requirement → spec → implementation → interface → storage → test → coverage status → gap.

**Coverage states:** `Fully Verified` (passing test covers it) · `Partially Verified` (some test / with caveats) · `Implemented Without Test` · `Documented Without Implementation` · `Inferred` · `Unknown` (implemented but unverified here) · `Deprecated`.

**Common columns:** *Interface* is CLI/file for almost everything (no REST API, no UI). *Storage* is the filesystem (no DB). These are stated once here and abbreviated as `CLI/file` / `FS` below.

## Functional requirements

| ID | Spec | Implementation (file:lines) | Test | Coverage | Gap |
|----|------|-----------------------------|------|----------|-----|
| REQ-PARSE-001 | parsing | `parser.rs:69-91` | `parser.rs:test_parse_valid_csv` | Fully Verified | — |
| REQ-PARSE-002 | parsing | `parser.rs:101-108` | — | Implemented Without Test | — |
| REQ-PARSE-003 | parsing | `parser.rs:111-129` | `parser.rs:test_parse_negative_value` | Fully Verified | — |
| REQ-PARSE-004 | parsing | `parser.rs:132-142` | — | Implemented Without Test | — |
| REQ-PARSE-005 | parsing | `parser.rs:152-162` | `parser.rs:test_parse_valid_csv` | Fully Verified | — |
| REQ-PARSE-006 | parsing | `parser.rs:165-173` | `parser.rs:test_parse_invalid_country_code` | Fully Verified | — |
| REQ-PARSE-007 | parsing | `parser.rs:144-149` | — | Implemented Without Test | GAP-DRIFT-002 |
| REQ-PARSE-008 | parsing | `parser.rs:191-193` | — | Implemented Without Test | — |
| REQ-PARSE-009 | parsing | `parser.rs:214-231` | — | Implemented Without Test | — |
| REQ-PARSE-010 | parsing | `parser.rs:94-188` | `test_dropout.py:test_parse_skips_invalid_rows...` | Fully Verified | — |
| REQ-COMP-001 | compliance | `compliance.rs:141-148` | `compliance.rs:test_reject_sanctioned_country` | Fully Verified | — |
| REQ-COMP-002 | compliance | `compliance.rs:150-162` | `compliance.rs:test_reject_banned_hs_code` | Fully Verified | GAP-DRIFT-001 (risk 100 vs 95) |
| REQ-COMP-003 | compliance | `compliance.rs:175-209` | `compliance.rs:test_hold_missing_certificate` | Fully Verified | GAP-DRIFT-001 |
| REQ-COMP-004 | compliance | `compliance.rs:211-221` | `compliance.rs:test_escalate_high_value` | Fully Verified | — |
| REQ-COMP-005 | compliance | `compliance.rs:223-233` | `test_dropout.py:test_mandate_inspection_overweight` (Py only) | Partially Verified | Rust path untested |
| REQ-COMP-006 | compliance | `compliance.rs:235-239` | — | Implemented Without Test | GAP-DRIFT-001 (Py never emits) |
| REQ-COMP-007 | compliance | `compliance.rs:175-193` | — | Partially Verified | GAP-DRIFT-001 (union vs first-match) |
| REQ-COMP-008 | compliance | `compliance.rs:260-291` | indirect | Implemented Without Test | GAP-DRIFT-001 (count semantics) |
| REQ-COMP-009 | compliance | `main.rs:93-101`, `fallback_compliance.py:44-68` | `test_dropout.py:test_missing_rules_file...` | Partially Verified | GAP-DRIFT-001 (#5) |
| REQ-ING-001 | ingestion | `orchestrator.py:474-481` | — | Implemented Without Test | GAP-TEST-002 |
| REQ-ING-002 | ingestion | `orchestrator.py:484-488` | — | Implemented Without Test | GAP-TEST-002 |
| REQ-ING-003 | ingestion | `orchestrator.py:249-338` | `test_dropout.py:test_full_pipeline_without_rust_binary` | Partially Verified | — |
| REQ-ING-004 | ingestion | `orchestrator.py:497,507` | — | Implemented Without Test | GAP-TEST-002 |
| REQ-ING-005 | ingestion | `orchestrator.py:454-506`, `checkpoint.py` | `TestCheckpointResume` | Partially Verified | loop path untested |
| REQ-ING-006 | ingestion | `orchestrator.py:463-472` | — | Implemented Without Test | GAP-TEST-002 |
| REQ-ING-007 | ingestion | `orchestrator.py:326-335` | `test_full_pipeline_without_rust_binary` | Partially Verified | — |
| REQ-DISP-001 | dispatch | `dispatcher.rs:73-78` | `dispatcher.rs:test_needs_browser_verification` | Fully Verified | — |
| REQ-DISP-002 | dispatch | `dispatcher.rs:97-99` | `dispatcher.rs:test_dispatch_creates_task_file` | Implemented Without Test (Py path) | GAP-ARCH-001 |
| REQ-DISP-003 | dispatch | `dispatcher.rs:114-127` | indirect | Implemented Without Test | — |
| REQ-DISP-004 | dispatch | `dispatcher.rs:152-207` | `test_retry_increments_attempt`, `test_retry_max_exceeded` | Fully Verified | — |
| REQ-DISP-005 | dispatch | `dispatcher.rs:129-146` | — | Implemented Without Test | GAP-ARCH-001 (Py omits) |
| REQ-BROW-001 | browser | `worker.py:983-1006` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-002 | browser | `worker.py:430-639` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-003 | browser | `worker.py:419-466` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-004 | browser | `worker.py` (throughout) | — | Unknown | GAP-TEST-001 |
| REQ-BROW-005 | browser | `worker.py:880-925` | — | Unknown | GAP-TEST-001, GAP-CONTRACT-001 |
| REQ-BROW-006 | browser | `worker.py:190-210` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-007 | browser | `worker.py:161-177` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-008 | browser | `worker.py:216-234,79` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-009 | browser | `worker.py:243-287` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-010 | browser | `worker.py:84-108` | — | Implemented Without Test | GAP-TEST-001 |
| REQ-BROW-011 | browser | `worker.py:300-308` | — | Unknown | GAP-TEST-001 |
| REQ-BROW-012 | browser | `worker.py:764-778` | — | Unknown | GAP-TEST-001 |
| REQ-RESULT-001 | result | `result_watcher.rs:82-94` | `result_watcher.rs:test_parse_found_bundle` | Fully Verified | — |
| REQ-RESULT-002 | result | `result_watcher.rs:207-258` | `test_handle_found_approved/held` | Fully Verified | — |
| REQ-RESULT-003 | result | `result_watcher.rs:143-166` | partial | Fully Verified | escalate path partial |
| REQ-RESULT-004 | result | `result_watcher.rs:167-176` | `test_write_escalation` | Fully Verified | — |
| REQ-RESULT-005 | result | `result_watcher.rs:97-109` | — | Implemented Without Test | — |
| REQ-RESULT-006 | result | `result_watcher.rs:179-189` | — | Implemented Without Test | GAP-ARCH-001 |
| REQ-SHIP-001 | shipment | `shipment.rs:19-30` | `shipment.rs:test_*` | Fully Verified | — |
| REQ-SHIP-002 | shipment | `shipment.rs:34-56` | `test_valid_transitions` | Fully Verified | GAP-ARCH-003 (not enforced live) |
| REQ-SHIP-003 | shipment | `shipment.rs:53-54` | `test_terminal_states` | Fully Verified | — |
| REQ-SHIP-004 | shipment | `shipment.rs:76-101` | — | Implemented Without Test | GAP-ARCH-003 |
| REQ-RESIL-001 | resilience | `circuit_breaker.py:53-199` | `TestCircuitBreaker` (6) | Fully Verified | — |
| REQ-RESIL-002 | resilience | `fallback_parser.py` | `TestFallbackParser` | Partially Verified | GAP-BUG-001, GAP-DRIFT-002 |
| REQ-RESIL-003 | resilience | `fallback_compliance.py` | `TestFallbackCompliance` | Partially Verified | GAP-DRIFT-001 |
| REQ-RESIL-004 | resilience | `checkpoint.py:45-208` | `TestCheckpoint` (6) | Fully Verified | — |
| REQ-RESIL-005 | resilience | `degradation.py:43-210` | `TestDegradationManager` (7) | Fully Verified | GAP-OPS-001 |
| REQ-RESIL-006 | resilience | `health_check.py:34-175` | `TestBrowserHealthMonitor` (6) | Fully Verified | — |
| REQ-RESIL-007 | resilience | `retry.py:29-141` | `TestRetry` (5) | Fully Verified | — |
| REQ-AUDIT-001 | audit | `audit.py:31-56` | via `TestResilientAudit` | Partially Verified | — |
| REQ-AUDIT-002 | audit | `resilient_audit.py:112-165` | `TestResilientAudit` | Partially Verified | GAP-BUG-002 (test fails) |
| REQ-AUDIT-003 | audit | `resilient_audit.py:88-89` | `test_thread_safety` | Fully Verified | — |
| REQ-HEALTH-001 | health | `health.py:285-293` | — | Implemented Without Test | GAP-BUG-003 |
| REQ-HEALTH-002 | health | `health.py:381-386` | — | Implemented Without Test | — |
| REQ-HEALTH-003 | health | `health.py:355-379` | — | Implemented Without Test | — |

## Non-functional requirements

| ID | Implementation | Test | Coverage | Gap |
|----|----------------|------|----------|-----|
| NFR-SEC-001 | `worker.py:216-234` | — | Implemented Without Test | GAP-TEST-001 |
| NFR-SEC-002 | `worker.py:161-177` | — | Implemented Without Test | GAP-TEST-001 |
| NFR-SEC-003 | `worker.py:300-308` | — | Implemented Without Test | GAP-TEST-001 |
| NFR-SEC-004 | `idempotency.rs:29-48` | — | Implemented Without Test | GAP-ARCH-004 (unwired) |
| NFR-SEC-005 | `worker.py:79` | — | Implemented Without Test | GAP-TEST-001 |
| NFR-SEC-006 | `.gitignore:32-34` | secret-scan (manual) | Inferred | — |
| NFR-SEC-007 | `worker.py:404` | — | Inferred | GAP-SEC-003 |
| NFR-PERF-001 | `agent_fasah.yaml:22`, `worker.py:36` | — | Implemented Without Test | — |
| NFR-PERF-002 | `parser.rs`, `worker.py:190-210` | — | Inferred | — |
| NFR-REL-001 | `dispatcher.rs:114-127`, `checkpoint.py:88-108` | indirect | Partially Verified | not all writes atomic |
| NFR-REL-002 | `orchestrator.py:484-488` | — | Implemented Without Test | GAP-ARCH-002 |
| NFR-REL-003 | `checkpoint.py` | `TestCheckpoint` | Fully Verified | — |
| NFR-REL-004 | `orchestrator.py:131-208` | `TestCascadingFailure` | Fully Verified | — |
| NFR-PORT-001 | `worker.py:19,264` | — | Inferred | POSIX-only |
| NFR-OBS-001 | `resilient_audit.py` | `TestResilientAudit` | Partially Verified | GAP-BUG-002 |
| NFR-OBS-002 | `worker.py:362-369` | — | Unknown | GAP-TEST-001 |
| NFR-OBS-003 | `health.py` | — | Implemented Without Test | GAP-BUG-003 |

## Coverage roll-up / ملخص التغطية

| State | Functional | NFR | Total | % of 83 |
|-------|-----------:|----:|------:|--------:|
| Fully Verified | 24 | 2 | **26** | 31.3% |
| Partially Verified | 10 | 2 | **12** | 14.5% |
| Implemented Without Test | 21 | 8 | **29** | 34.9% |
| Unknown (unverified) | 11 | 1 | **12** | 14.5% |
| Inferred | 0 | 4 | **4** | 4.8% |
| **Linked to ≥1 test (FV+PV)** | 34 | 4 | **38** | **45.8%** |

**Documented Without Implementation:** none material (docs mostly under-document real features rather than over-promise; the reverse case is the schema `agent_browser` field — GAP-CONTRACT-001). **Deprecated:** none formally; `idempotency.rs`/`stability.rs` are *de facto* unused (GAP-ARCH-004).
