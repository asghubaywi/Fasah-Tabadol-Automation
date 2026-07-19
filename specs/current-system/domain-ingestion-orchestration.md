# Domain: Ingestion & Orchestration / الاستيعاب والتنسيق

**Primary code:** `src/pipeline/orchestrator.py`

## Goal / الهدف
Long-running loop that watches the inbox, drives each declaration file through parse → compliance → dispatch, and guarantees idempotent, resumable, audited processing.

## Actors / الأدوار
Operator (starts `python src/pipeline/orchestrator.py`); the Rust engine (subprocess); the browser worker (downstream, via `browser_tasks/`).

## Inputs / المدخلات
Files in `workspace/inbox/` with `.csv`/`.json` suffix, not starting with `.` or `tmp` — `orchestrator.py:474-481`. Config from `agent_fasah.yaml` (`load_config`, `orchestrator.py:84-92`).

## Outputs / المخرجات
- `workspace/outbox/track_*.json` (direct verdicts) — `orchestrator.py:382-416`.
- `workspace/outbox/browser_tasks/*.json` (hold/escalate) — `orchestrator.py:341-379`.
- Audit events; checkpoint + hash ledger updates.
- Files relocated to `inbox/processed/` or `inbox/quarantine/`.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-ING-001 | Poll every `poll_interval_secs` (default 15); filter dot/tmp files | `orchestrator.py:474-481,509-510` |
| REQ-ING-002 | Compute SHA-256; if in ledger → skip + move to processed | `orchestrator.py:484-488` |
| REQ-ING-003 | Parse → check → dispatch per file | `orchestrator.py:249-338` |
| REQ-ING-004 | Success → `processed/`; exception → `quarantine/` | `orchestrator.py:497,507` |
| REQ-ING-005 | Checkpoint marks in-flight/step/complete/failed; resume logs in-flight | `orchestrator.py:454-461,491-506` |
| REQ-ING-006 | SIGINT/SIGTERM set `running=False`, stop after cycle | `orchestrator.py:463-472` |
| REQ-ING-007 | `hold_pending_certificates`/`escalate_high_value` → browser; else direct outbox | `orchestrator.py:326-335` |

## Use cases / حالات الاستخدام
New CSV processed; duplicate CSV skipped; crash mid-file then resume; malformed file quarantined.

## Main scenario / السيناريو الأساسي
See REQ-ING-003; verdict routing per REQ-ING-007; hash recorded and file moved on success.

## Exception & failure scenarios
- Any `process_file` exception → audit `failure`, checkpoint `mark_failed`, move to `quarantine/` — `orchestrator.py:499-507`.
- Rust engine missing/failing → degrade to Python fallback (see `domain-resilience.md`), pipeline continues.

## Permissions / State changes
Filesystem read/write within `workspace/`. State: hash ledger, checkpoint JSON, moved files, outbox commands.

## Data / البيانات
Tracking command JSON: `command_type=shipment_status_update`, `declaration_number`, mapped `status`, `previous_status="received"`, `metadata{source, compliance_action, risk_score}` — `orchestrator.py:402-413`.

## Integrations
Rust CLI subprocess; hands off to browser worker via file drop; writes audit via `ResilientAuditLogger`.

## Proven behavior
Not exercised end-to-end in this env (no long-run test), but `process_file` is covered indirectly by `TestCascadingFailure::test_full_pipeline_without_rust_binary` and `TestCheckpointResume::*` (`test_dropout.py:696-819`, pass).

## Tests / الاختبارات
Fallback + checkpoint paths tested. **Not tested:** the `main()` poll loop, signal handling, duplicate skip, quarantine-on-failure, real subprocess invocation.

## Known constraints / القيود
- **No file-stability check**: files are read as soon as seen; a partially-written inbox file could be parsed mid-write. The Rust `stability.rs` exists but is **not used** here → **GAP-ARCH-002**.
- **Status mapping quirk**: `escalate_high_value` maps to `held` in the *direct outbox* branch (`orchestrator.py:396`), but `escalate_high_value` is normally routed to the *browser* branch — so this mapping is only reachable if routing changes. Latent inconsistency.
- Idempotency ledger and checkpoint are **separate** mechanisms tracking overlapping state.

## Open questions
- Should duplicate files be skipped silently or audited? (Currently logged, not audited.)
- Should quarantined files be retried automatically? (Currently manual.)
