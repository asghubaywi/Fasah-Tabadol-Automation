# Domain: Browser Dispatch / إرسال مهام المتصفح

**Primary code:** `src/agents/src/dispatcher.rs` (used by `fasah-engine watch` retry path) · `src/pipeline/orchestrator.py:341-379` (used by the live orchestrator)

> **Note — two dispatchers exist.** The orchestrator writes browser task envelopes itself in Python (`_dispatch_browser_task`); the Rust `BrowserDispatcher` is used by `fasah-engine watch` for retry bookkeeping. Both must emit the same envelope shape (`schemas/fasah_task.schema.json`).

## Goal / الهدف
Convert a `hold`/`escalate` verdict into a browser task envelope the worker can execute, and (Rust side) maintain a pending-task ledger with bounded retries.

## Actors / الأدوار
Orchestrator (Python writer); `fasah-engine watch` (Rust retrier); browser worker (consumer).

## Inputs / المدخلات
Declaration number + `ComplianceAction` (+ risk score). Rust: existing `.pending_tasks.json` ledger.

## Outputs / المخرجات
`browser_tasks/<task_id>.json` envelope: `{task_id, playbook:"fasah_search_inspect_v1", params:{base_url, query}, session_name:"fasah_agent", outputs:{out_dir}}` — `dispatcher.rs:101-112`, `orchestrator.py:354-360`.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-DISP-001 | Only `HoldPendingCertificates`/`EscalateHighValue` need browser | `dispatcher.rs:73-78` |
| REQ-DISP-002 | `task_id = fasah-<safe_decl>-<UTC ts>` (`/\ ` → `_`) | `dispatcher.rs:97-99`, `orchestrator.py:349-351` |
| REQ-DISP-003 | Atomic write: tmp → fsync → rename (Rust); tmp → rename (Py) | `dispatcher.rs:114-127`; `orchestrator.py:363-368` |
| REQ-DISP-004 | Pending ledger; `retry` increments `attempt`; stop at `max_retries` | `dispatcher.rs:152-207` |
| REQ-DISP-005 | Persist `risk_score` + `predicted_outcome` for decision-quality tracking | `dispatcher.rs:129-146` |

## Use cases
Dispatch a hold task; retry a transient failure; refuse retry after max attempts; mark completed.

## Main / exception / failure scenarios
- Main: verdict → envelope written atomically → (Rust) ledger updated.
- Exception: `retry` on unknown task_id → `Ok(None)` (`dispatcher.rs:153-156`).
- Failure: I/O errors bubble up as `anyhow::Result` (Rust) / exception (Py, caught by orchestrator).

## Permissions / State changes / Data
Writes into `browser_tasks/`; Rust maintains `.pending_tasks.json`. `PendingTask{declaration_number, dispatched_at, attempt, action, risk_score, predicted_outcome}`.

## Integrations
Envelope contract = `schemas/fasah_task.schema.json`. Consumed by `worker.py`.

## Proven behavior
Rust dispatcher fully unit-tested: creates task file, increments retry, enforces max — `dispatcher.rs:244-317` (pass).

## Tests / الاختبارات
Rust: `test_dispatch_creates_task_file`, `test_retry_increments_attempt`, `test_retry_max_exceeded`, `test_needs_browser_verification`. Python `_dispatch_browser_task`: **untested directly**.

## Known constraints / القيود
- **Duplicated envelope logic** in Rust and Python; the Python path is the live one, the Rust ledger/retry is only reached via `watch`. Drift risk between the two writers.
- The Python writer does **not** maintain a pending ledger or risk/prediction fields — so decision-quality tracking only works if `fasah-engine watch` is the retry driver.
- `task_id` uses second/millisecond timestamps; extremely rapid dispatch for the same declaration could collide (Python uses microseconds truncated to 22 chars; Rust uses `%3f` millis).

## Open questions
- Which dispatcher is canonical for production — Python (orchestrator) or Rust (`watch`)? Needs a human decision to remove the duplication.
