# Domain: Result Processing / معالجة النتائج

**Primary code:** `src/agents/src/result_watcher.rs` (invoked by `fasah-engine watch`)

## Goal / الهدف
Scan completed browser result bundles and turn them into shipment-status tracking commands, retries, or human escalations — never auto-approving on ambiguity.

## Actors / الأدوار
Operator/cron running `fasah-engine watch <results_dir> <outbox_dir>`; the Rust `BrowserDispatcher` (for retries).

## Inputs / المدخلات
`browser_results/<dir>/bundle.json` (`BrowserBundle{task_id,status,error_code,error_detail,record_url,current_status}`) — `result_watcher.rs:25-37`; pending-task ledger for declaration mapping + prediction.

## Outputs / المخرجات
- `track_<decl>_<ts>.json` shipment-status update (`result_watcher.rs:232-254`).
- `escalation_<decl>_<ts>.json` on auth/needs-human/max-retries (`result_watcher.rs:260-284`).
- `ResultAction[]` printed as JSON; processed dirs moved to `.processed/`.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-RESULT-001 | Only dirs containing `bundle.json` are processed | `result_watcher.rs:82-94` |
| REQ-RESULT-002 | FOUND: match status keywords (EN+AR) → approved / rejected / held; unknown → no status | `result_watcher.rs:207-258` |
| REQ-RESULT-003 | TRANSIENT_FAIL → `retry`; if max exceeded → escalate | `result_watcher.rs:143-166` |
| REQ-RESULT-004 | AUTH_FAIL / NEEDS_HUMAN → escalation file | `result_watcher.rs:167-176` |
| REQ-RESULT-005 | Processed result dir moved to `.processed/` | `result_watcher.rs:97-109` |
| REQ-RESULT-006 | Compute `prediction_correct` from predicted vs actual | `result_watcher.rs:179-189` |

## Keyword mapping (proven)
- approve: `approved, مقبول, موافق, released, cleared, مفسوح`
- hold: `hold, pending, review, معلق, قيد المراجعة, under review`
- reject: `rejected, مرفوض, denied, refused` — `result_watcher.rs:218-220`.
Reject is checked **before** hold; approve first of all.

## Use cases / main / exception / failure
Found-approved → status update; found-under-review → held; transient → retry then escalate; auth fail → escalate; unrecognized status → `portal_status_unrecognized`, no status change (fail-safe).

## Permissions / State changes / Data
Writes tracking/escalation JSON to outbox; moves result dirs; updates pending ledger via dispatcher. `EscalationCommand{command_type, declaration_number, reason, browser_status, error_code, error_detail, timestamp}`.

## Integrations
Bridges browser worker output back into shipment tracking; shares the pending ledger with `dispatcher.rs`.

## Proven behavior
Rust-tested: parse found bundle, handle found→approved, handle found→held, write escalation — `result_watcher.rs:286-362` (pass).

## Tests / الاختبارات
Rust unit tests cover the core mappings. **Not tested:** TRANSIENT_FAIL retry→escalate end-to-end, `.processed/` move, decision-quality flags, unknown-status branch.

## Known constraints / القيود
- Declaration number is `"UNKNOWN"` if the task isn't in the Rust pending ledger — which is the case when the **orchestrator** (Python) dispatched it, since the Python writer doesn't populate the Rust ledger. So `watch` may lose declaration mapping for live-dispatched tasks → **GAP-ARCH-001** (dispatcher duplication).
- Status keyword matching is substring-based and case-folded; portal wording changes can misclassify.
- `prediction_correct` for `hold` counts `rejected` as correct too (`result_watcher.rs:184`).

## Open questions
- Should `watch` run as a daemon or one-shot? (CLI is one-shot; no loop in Rust.)
- How is `watch` scheduled in production? No scheduler is defined.
