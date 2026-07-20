# Domain: Health & Observability / الصحة والمراقبة

**Primary code:** `src/utils/health.py` (system dashboard) · `src/browser/health_check.py` (browser monitor — see `domain-resilience.md`)

## Goal / الهدف
Give operators a one-shot / watch view of whether every component is healthy, degraded, or failed, with an actionable exit code.

## Actors / الأدوار
Operator (`python -m src.utils.health [--json] [--watch N]`).

## Inputs / Outputs
Input: environment + filesystem state. Output: human table or JSON report; process exit code.

## Business rules / قواعد العمل
| ID | Rule | Evidence |
|----|------|----------|
| REQ-HEALTH-001 | 7 checks: rust_engine, playwright, config, workspace, audit, degradation, checkpoint | `health.py:285-293` |
| REQ-HEALTH-002 | Exit 0 healthy / 1 degraded / 2 failed | `health.py:381-386` |
| REQ-HEALTH-003 | `--json` machine output; `--watch N` refresh loop | `health.py:355-379` |

## Use cases
Pre-flight check before starting the pipeline; continuous watch dashboard; JSON scrape for external monitoring.

## Main / exception / failure scenarios
Aggregates worst component status to `overall`. Missing binary → failed; low disk (<0.5 GB) → degraded; audit dir unwritable → failed.

## Permissions / State changes / Data
Read-only except a `.health_write_probe` temp file in the audit dir (`health.py:189-191`).

## Proven behavior / Tests
**Not tested** (no tests import `health.py`). Executed indirectly only.

## Known constraints / القيود
- **Confirmed bug (GAP-BUG-003):** `_check_rust_engine` runs `fasah-engine --version` and treats non-zero exit as *degraded*. The CLI does **not** implement `--version` (needs ≥3 args) and exits **1** — verified in `06-baseline-verification.md`. So the dashboard **always reports the Rust engine as degraded** even when it is fully functional.
- The degradation check runs in a **separate process** from the orchestrator, so its in-memory registry is always empty → always "healthy" regardless of real runtime degradation (`health.py:197-205`, acknowledged in the code comment).
- No HTTP/metrics endpoint; observability is CLI + log files + audit only.

## Open questions
- Should health be exposed as an HTTP endpoint / Prometheus metrics for real monitoring? (Ops readiness gap.)
- Should degradation state be persisted so cross-process health is meaningful?
