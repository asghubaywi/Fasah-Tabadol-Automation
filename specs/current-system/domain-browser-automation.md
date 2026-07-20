# Domain: Browser Automation / أتمتة المتصفح

**Primary code:** `src/browser/worker.py` (970 LoC) · helpers `src/browser/health_check.py`, `src/browser/retry.py`

## Goal / الهدف
Pick up browser task envelopes and execute the read-only `fasah_search_inspect_v1` playbook on the Fasah portal via Playwright, producing a verifiable result bundle with evidence and hashes.

## Actors / الأدوار
Operator (runs the worker); the Fasah portal (external, authenticated via persisted session); result watcher (downstream consumer of `bundle.json`).

## Inputs / المدخلات
`browser_tasks/*.json` envelopes (`worker.py:985`). Env config: `ZC_ENV`, `FASAH_BASE_URL`, `AGENT_BROWSER_ALLOWED_DOMAINS`, `AGENT_BROWSER_ENCRYPTION_KEY`, timeouts, output limits (`worker.py:36-108`).

## Outputs / المخرجات
`browser_results/<out_dir>/`: `bundle.json`, `transcript.jsonl`, screenshots, `record_url.txt`, `status.txt`, `sha256sum.txt` — `worker.py:834-939`.

## Business rules & security gates / قواعد العمل والبوابات
| ID | Rule | Evidence |
|----|------|----------|
| REQ-BROW-002 | Playbook: goto `/en/authorized-employee/requests` → wait Angular → search → click first result → extract status | `worker.py:430-639` |
| REQ-BROW-003 | Reuse `storage_state`; redirect to login or 401/403 → `AUTH_FAIL` | `worker.py:419-466` |
| REQ-BROW-004 | Outcomes: FOUND / NOT_FOUND / AUTH_FAIL / TRANSIENT_FAIL / NEEDS_HUMAN | throughout `run_playwright_search` |
| REQ-BROW-005 | Bundle + transcript + canonical `sha256sum.txt` manifest | `worker.py:362-369,880-925` |
| REQ-BROW-006 (Gate 9) | ≤20 artifacts, ≤20 MB each, ≤50 MB per out_dir | `worker.py:190-210` |
| REQ-BROW-007 (Gate 10) | Prod fail-closed: requires allowlist+key+base_url, else `sys.exit(1)` | `worker.py:161-177` |
| REQ-BROW-008 (Gate 11) | Domain allowlist (wildcards); block `download`/`upload` | `worker.py:216-234,79` |
| REQ-BROW-009 (Gate 12) | Duplicate terminal-task skip; flock exclusive task lock | `worker.py:243-287` |
| REQ-BROW-010 (Gate 13) | Structured `E_*` error codes on every failure | `worker.py:84-108` |
| REQ-BROW-011 | `out_dir` reduced to safe basename `[A-Za-z0-9_-]{1,128}` | `worker.py:300-308` |
| REQ-BROW-012 | Legacy playbook aliases resolved + logged | `worker.py:764-778` |

## Use cases
Found + approved status; found + under-review; no results; session expired (auth fail); search box missing (needs human); browser crash (transient).

## Main scenario
Lock task → resolve out_dir → open transcript → launch Chromium (headless, `--no-sandbox`) → navigate/search/inspect → build bundle with hashes → move task to `state/processed/`.

## Exception & failure scenarios
Timeouts → TRANSIENT_FAIL + screenshot; login detected → AUTH_FAIL; element not found → NEEDS_HUMAN; output limit exceeded → TRANSIENT_FAIL; invalid task JSON → moved to `*.ERROR.json`. Consecutive-failure health guard skips tasks if browser likely crashed (`worker.py:790-798`).

## Permissions / State changes
Reads env + task; writes results, locks, session state, logs. Persists Playwright `storage_state` for login reuse.

## Data / البيانات
Bundle fields per `schemas/fasah_bundle.schema.json` — **but see constraint below**.

## Proven behavior
**Not executed in this environment** — Playwright/Chromium are not installed here, and running it needs a live Fasah session. Status of REQ-BROW-* is therefore **UNK (unverified)** except where pure-Python helpers are tested.

## Tests / الاختبارات
- `health_check.py` and `retry.py`: fully unit-tested (`test_dropout.py:527-653`, pass).
- `worker.py` core logic (gates, playbook, bundle building, out_dir sanitization, domain allowlist): **no tests at all.** This is the single largest untested surface.

## Known constraints / القيود
- **Contract violation (GAP-CONTRACT-001):** the bundle writes `tool_versions:{playwright, python, worker_script}` (`worker.py:920-924`) but `fasah_bundle.schema.json` **requires** `agent_browser` (not `playwright`). Real bundles would fail schema validation. Also `_write_error_bundle` omits `tool_versions` entirely (`worker.py:942-947`).
- **No runtime schema validation** — envelopes/bundles are never checked against `schemas/`.
- **POSIX-only (NFR-PORT-001):** `import fcntl` + `os.open(O_*)` at module top → cannot run on Windows.
- **`AGENT_BROWSER_ENCRYPTION_KEY`** is required in prod but never used to encrypt anything.
- Dead code: session-save block after both return branches in `run_playwright_search` (`worker.py:641-645`) is unreachable (the `finally` handles it).
- Selectors are brittle Fasah/Angular guesses; the portal UI can silently break them (expected for scraping).

## Open questions
- Is the portal contract (routes, selectors) validated against the real Fasah portal anywhere? (No evidence.)
- Should the encryption key actually encrypt the session `state.json` at rest? (Implied by name; not implemented.)
