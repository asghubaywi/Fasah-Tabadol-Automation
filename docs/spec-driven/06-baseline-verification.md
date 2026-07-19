# 06 — Baseline Verification / تقرير التحقق من الخط الأساسي

> Real commands, real results, this environment. This **replaces** the stale `evidence/` folder (captured on Windows at an earlier commit) as the trustworthy baseline.
> **Discovery phase only** — no product code was modified to produce this. The single environment change was installing `pytest` (absent by default) to execute the repository's own test suite; nothing in `src/` was touched.

## Environment / البيئة
| Item | Value |
|------|-------|
| OS | Linux 6.18.5 (x86_64) |
| Rust | rustc 1.94.1 / cargo 1.94.1 |
| Python | CPython 3.11.15 |
| ruff | 0.15.8 |
| pytest | 9.1.1 (installed during verification; not vendored) |
| pyyaml | 6.0.1 |
| Playwright / Chromium | **not installed** → `worker.py` could not be exercised |
| Commit base | `b5d1587` (branch `master`) |

## Commands executed & results / الأوامر والنتائج

| # | Command | Exit | Result |
|---|---------|-----:|--------|
| 1 | `cargo build` | 0 | Compiles clean (first build ~26s). |
| 2 | `cargo test` | 0 | **19 passed, 0 failed** (lib). `main.rs` 0 tests; doc-tests 0. |
| 3 | `cargo fmt --all -- --check` | **1** | **FAIL** — formatting diffs in `compliance.rs:248` (`check_all` signature) and `parser.rs:212` (`parse_json`). |
| 4 | `cargo clippy -- -D warnings` | **101** | **FAIL** — 2 × `clippy::ptr_arg` (`&PathBuf`→`&Path`) at `main.rs:109` and `:110`. |
| 5 | `ruff check src/` | **1** | **FAIL** — 1 × `F401` unused `import os` at `audit.py:10`. |
| 6 | `pytest tests/` | **1** | **2 failed, 52 passed** (see below). |
| 7 | `fasah-engine parse examples/sample_declarations.csv` | 0 | 5 total / **5 valid** / 0 invalid. |
| 8 | `fasah-engine check … --rules config/fasah_rules.yaml` | 0 | approved 2, held 1, escalated 1, rejected 1 (per-declaration below). |
| 9 | `fasah-engine --version` | **1** | **No `--version` support** — prints usage, exits 1 (root cause of health-dashboard false "degraded", GAP-BUG-003). |

## Rust test detail / تفاصيل اختبارات Rust
19 passing tests across `compliance` (5), `parser` (3), `dispatcher` (4), `result_watcher` (4), `shipment` (3). Full green.

## Python test detail / تفاصيل اختبارات Python
**52 passed, 2 failed** in `tests/test_dropout.py`:
- ❌ `TestFallbackParser::test_parse_nonexistent_file` — `fallback_parser.parse_csv` raises `FileNotFoundError` (hash computed before the read guard). → **GAP-BUG-001**.
- ❌ `TestResilientAudit::test_never_raises` — `record()` propagates a non-`OSError` exception; "never raises" guarantee violated. → **GAP-BUG-002**.

Both are **real code defects**, reproducible and independent of this environment. All resilience/circuit-breaker/checkpoint/degradation/health-monitor/retry tests pass.

## Engine behavioral evidence / السلوك الفعلي للمحرك
`fasah-engine check` on the 5-row sample (default `config/fasah_rules.yaml`):

| Declaration | HS | Origin | Value SAR | Verdict | Risk |
|-------------|----|--------|----------:|---------|-----:|
| FASAH-2026-00001 | 8471.30.00 | CN | 150,000 | `approve` | 0 |
| FASAH-2026-00002 | 0402.10.00 | NZ | 85,000 | `approve` | 0 |
| FASAH-2026-00003 | 8471.60.00 | KR | 750,000 | `escalate_high_value` | 70 |
| FASAH-2026-00004 | 9301.00.00 | US | 10,000 | `reject` (banned HS) | 100 |
| FASAH-2026-00005 | 0302.10.00 | NO | 95,000 | `hold_pending_certificates` (missing SFDA+Halal) | 60 |

This matches the documented rules and confirms the core decision path works correctly.

## Coverage not exercised here / ما لم يُختبر
- **Browser worker** (`worker.py`): Playwright/Chromium absent + needs a live Fasah session → all REQ-BROW-* remain **Unknown** (unverified). Compounded by having **zero** automated tests (GAP-TEST-001).
- **Orchestrator main loop / `fasah-engine watch` end-to-end**: not run as long-lived processes.
- **Docker build**: not attempted (no `Dockerfile` exists — GAP-DEPLOY-001).

## CI reality / واقع الـ CI
`.github/workflows/ci.yml` triggers on `main`; the default branch is `master`, so **CI has effectively never run** (GAP-CI-001). If it did run, of its 5 check steps **3 would fail today** (fmt #3, clippy #4, ruff #5), 1 passes (`cargo test` #2), and `pytest` is **not in CI at all** (GAP-CI-002).

## Warnings / التحذيرات
- Committed `evidence/` is stale and contradicts this report (its `pytest.txt` says "no tests ran"). Do not trust it.
- `serde_yaml` (a dependency) is marked deprecated upstream (`0.9.34+deprecated`) — future maintenance flag, not a current failure.

## Baseline stability verdict / حكم استقرار الخط الأساسي
**PARTIALLY STABLE.**
- ✅ **Stable & verified:** Rust core (build + 19 tests + correct engine behavior) and the Python resilience layer (52 tests).
- ⚠ **Not stable / not green:** all format+lint gates (fmt, clippy, ruff) fail; 2 Python tests fail; CI is disconnected; Docker deployment is broken; the security-critical browser worker is entirely unverified.

The core logic is trustworthy; the surrounding quality/CI/deployment/verification scaffolding is not. **No basis exists to call the system production-ready.**
