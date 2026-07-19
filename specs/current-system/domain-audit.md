# Domain: Audit Logging / سجل التدقيق

**Primary code:** `src/utils/audit.py` (base) · `src/utils/resilient_audit.py` (production logger used by orchestrator)

## Goal / الهدف
Produce an append-only, tamper-evident event trail that never blocks or crashes the pipeline, even under disk failure.

## Actors / الأدوار
Orchestrator (primary writer via `ResilientAuditLogger`); any component recording events.

## Inputs / Outputs
Input: `record(action, subject, tool, outcome, data?, risk_level?)`. Output: one JSON object per line in `<audit_dir>/<agent_id>_YYYY-MM-DD.jsonl` — `audit.py:31-56`.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-AUDIT-001 | Append-only daily JSONL; one file per agent per UTC day | `audit.py:27-53` |
| REQ-AUDIT-002 | Resilient logger buffers on I/O failure, flushes on recovery, drops oldest when full (`maxlen=500`), warns to stderr | `resilient_audit.py:112-165` |
| REQ-AUDIT-003 | All writes are thread-safe (lock-guarded) | `resilient_audit.py:88-89` |

Event shape: `{ts, agent_id, action, subject, tool, outcome, risk_level, data}`.

## Use cases
Record AgentStarted/Stopped, ToolCompleted (parse/check), ToolInvoked (browser_dispatch), pipeline failure; buffer during a disk outage; flush on recovery.

## Main / exception / failure scenarios
- Main: write line to today's file.
- Exception: `OSError` on write → buffer in memory, print stderr warning, continue.
- **Failure (bug):** if `_log_path()` itself raises a non-`OSError` exception, `record()` **propagates** it — violating the "never raises" contract. Confirmed by failing test `test_never_raises` → **GAP-BUG-002** (`resilient_audit.py:119` only catches `OSError`).

## Permissions / State changes / Data
Append to audit files; maintains in-memory buffer + counters (`buffered_total`, `dropped_total`, `write_failures`).

## Integrations
Consumed by operators/compliance for the audit trail; `health.py` probes audit-dir writability.

## Proven behavior / Tests
`TestResilientAudit`: normal write, buffer on failure, flush on recovery, thread safety — pass; **`test_never_raises` FAILS** (`test_dropout.py:432-439`).

## Known constraints / القيود
- Base `AuditLogger.record` swallows `OSError` and prints to stderr (events silently lost if not using the resilient variant).
- No integrity chaining (e.g., hash-linked lines) — "tamper-evident" is by append-only convention + filesystem permissions, not cryptographic linkage.
- No rotation/retention in code (docs recommend external logrotate — `README.md:257`).

## Open questions
- Should audit lines be hash-chained for true tamper-evidence? (Constitution P5 implies strong immutability; current guarantee is weaker.)
- Should dropped audit events (buffer overflow) themselves be escalated? (Currently only a periodic stderr warning.)
