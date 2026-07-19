# 00 — Current Project Inventory / جرد المشروع الحالي

> **Status:** Discovery artifact (Phase A). Describes the project **as it actually is**, derived from code, tests, configs, and real execution — not from aspirational docs.
> **Method:** Where documentation and code disagreed, code + tests + runtime behavior won, and the conflict is documented explicitly.
> **Date generated:** 2026-07-19 · **Commit base:** `b5d1587` (branch `master`)
> **Verification environment:** Linux, Rust 1.94.1, Python 3.11.15 (see `06-baseline-verification.md`).

Every non-trivial claim below cites the file/dir that proves it.

---

## 1. Project name & actual purpose / الاسم والغرض الفعلي

**Name:** `Fasah-Tabadol-Automation` (`Cargo.toml`, `README.md`).

**Actual purpose (proven by code):** An **end-to-end customs-clearance automation pipeline** that:
1. Ingests customs **declaration files** (CSV or JSON) exported from the *Tabadol* trade platform — `src/pipeline/orchestrator.py:474-481`, `src/agents/src/parser.rs`.
2. Evaluates each declaration against Saudi regulatory **compliance rules** (banned goods, sanctioned origins, required certificates, value/weight thresholds) — `src/agents/src/compliance.rs:129-248`.
3. Routes each verdict: direct outbox tracking commands for terminal verdicts, or **browser tasks** for verdicts needing portal verification — `src/pipeline/orchestrator.py:316-338`.
4. Drives the **Fasah** clearance portal via a Playwright browser worker to look up declaration status — `src/browser/worker.py:375-665`.
5. Feeds portal results back into shipment-status tracking commands and human escalations — `src/agents/src/result_watcher.rs`.

**One-line truth:** it is a **file-driven, dual-language (Rust core + Python orchestration) batch automation agent** for customs declarations, communicating entirely through JSON files on disk.

## 2. Users / beneficiaries / المستخدمون والمستفيدون

Not stated explicitly anywhere in the repo. **Inferred from behavior** (needs human confirmation):
- Customs brokers / clearance operators who receive Tabadol CSV exports and must file/track them on Fasah.
- Compliance officers relying on the audit trail (`workspace/audit/*.jsonl`) and escalation records.
- Operators running the orchestrator + browser worker as long-lived processes.

There is **no user-facing UI, no authentication of end users, and no multi-tenant concept** in the code. It is an operator-run automation, not an application with logins.

## 3. Problem it solves / المشكلة

Manual customs clearance requires re-keying each Tabadol declaration into Fasah, manually judging compliance, and manually checking portal status. This repo automates the ingest→judge→file→track loop with an auditable, resumable pipeline (`README.md:11-14`).

## 4. Technologies used / التقنيات

| Layer | Technology | Evidence |
|-------|-----------|----------|
| Core logic engine | **Rust 2021**, crate `fasah-engine` | `src/agents/Cargo.toml` |
| Rust deps | serde, serde_json, serde_yaml, chrono, uuid, sha2, hex, regex, anyhow, tokio, tracing, fs2 | `src/agents/Cargo.toml:16-32` |
| Orchestration / glue | **Python 3.11+** | `src/pipeline/`, `requirements.txt` |
| Browser automation | **Playwright** (Python, Chromium) | `src/browser/worker.py`, `requirements.txt` |
| Config | YAML (`pyyaml`, `serde_yaml`) | `config/*.yaml` |
| Contracts | JSON Schema (draft 2020-12) | `schemas/*.json` |
| Packaging / deploy | Docker Compose (**Dockerfile missing — see §17**) | `docker-compose.yml` |
| CI | GitHub Actions | `.github/workflows/ci.yml` |

> **Note:** `tokio` is a dependency but the CLI `main.rs` is fully synchronous (`fn main() -> anyhow::Result<()>`). Async runtime appears **unused** by the current binary — `src/agents/src/main.rs:31`.

## 5. Folder structure / هيكل المجلدات

```
Fasah-Tabadol-Automation/
├── Cargo.toml                  # Rust workspace (members = ["src/agents"])
├── requirements.txt            # Python deps (playwright, pyyaml, python-dotenv)
├── docker-compose.yml          # 2 services: orchestrator, browser-worker (needs Dockerfile — MISSING)
├── .github/workflows/ci.yml    # CI (triggers on `main` — repo default is `master`; see §16)
├── config/
│   ├── agent_fasah.yaml        # Orchestrator runtime config
│   └── fasah_rules.yaml        # Compliance rules (editable, no rebuild)
├── schemas/
│   ├── fasah_task.schema.json  # Browser task envelope contract
│   └── fasah_bundle.schema.json# Browser result bundle contract
├── examples/sample_declarations.csv  # 5 sample declarations
├── evidence/                   # STALE test/line-count captures (Windows; see §14)
├── src/
│   ├── agents/src/             # Rust engine (fasah-engine)
│   │   ├── main.rs             # CLI: parse | check | watch
│   │   ├── lib.rs              # Public module exports
│   │   ├── parser.rs           # CSV/JSON → DeclarationRecord[] (pure)
│   │   ├── compliance.rs       # Rules + verdicts (pure)
│   │   ├── dispatcher.rs       # Browser task envelope writer + retry ledger
│   │   ├── result_watcher.rs   # bundle.json → shipment status / escalation
│   │   ├── shipment.rs         # Shipment status state machine
│   │   ├── idempotency.rs      # SHA-256 ledger (⚠ NOT wired into CLI — see §15)
│   │   └── stability.rs        # File mtime/size stability (⚠ NOT wired into CLI — see §15)
│   ├── pipeline/
│   │   ├── orchestrator.py     # Main event loop (poll → parse → check → dispatch)
│   │   ├── circuit_breaker.py  # Circuit breaker for the Rust engine
│   │   ├── fallback_parser.py  # Pure-Python parser (degradation)
│   │   ├── fallback_compliance.py # Pure-Python compliance (degradation)
│   │   └── checkpoint.py       # Crash-safe checkpoint / resume
│   ├── browser/
│   │   ├── worker.py           # Playwright worker + security gates 9–13
│   │   ├── health_check.py     # Browser worker health monitor
│   │   └── retry.py            # Exponential backoff helpers
│   └── utils/
│       ├── audit.py            # JSONL audit logger (base)
│       ├── resilient_audit.py  # Audit logger with in-memory buffer fallback
│       ├── degradation.py      # Central component-health/degradation registry
│       └── health.py           # System health dashboard CLI
└── tests/
    └── test_dropout.py         # 54 Python resilience tests (2 currently FAIL — §14)
```

## 6. Main entry points / نقاط الدخول

| Entry point | Command | File |
|-------------|---------|------|
| Rust CLI | `fasah-engine parse\|check\|watch` | `src/agents/src/main.rs:31-58` |
| Orchestrator | `python src/pipeline/orchestrator.py` | `orchestrator.py:519-520` |
| Browser worker | `python src/browser/worker.py` | `worker.py:1015-1016` |
| Health dashboard | `python -m src.utils.health` | `health.py:389-390` |

## 7. Modules & components / الوحدات

See §5 tree. Two runtime processes (orchestrator, browser worker) plus one CLI engine invoked as a subprocess by the orchestrator (`orchestrator.py:97-128`). The engine, fallbacks, resilience, audit, and health modules are libraries consumed by those processes.

## 8. Databases & storage / قواعد البيانات والتخزين

**There is no database.** All state is files on disk under `workspace/` (`orchestrator.py:424-436`):
- `workspace/inbox/` — incoming declaration files; `processed/`, `quarantine/` subdirs.
- `workspace/inbox/.processed_hashes` — SHA-256 idempotency ledger (`orchestrator.py:221-235`).
- `workspace/inbox/.pipeline_checkpoint.json` — crash/resume checkpoint (`checkpoint.py:41`).
- `workspace/outbox/` — tracking commands (`track_*.json`), escalations, `browser_tasks/`, `browser_results/`.
- `workspace/audit/agent_fasah_YYYY-MM-DD.jsonl` — daily append-only audit (`audit.py:27-29`).
- `workspace/state/` — browser worker locks, processed tasks, logs; session storage default `/var/lib/zeroclaw/fasah/state/sessions` (`worker.py:58-60`).

> `workspace/` is git-ignored (`.gitignore:23-30`) and created at runtime; it is **not** committed.

## 9. External integrations / التكاملات الخارجية

| Integration | Direction | Evidence | Notes |
|-------------|-----------|----------|-------|
| **Tabadol** platform | inbound (CSV/JSON files) | `README.md`, `parser.rs` | Integration is **file drop only** — no API client exists in the repo. |
| **Fasah** portal | outbound (Playwright browser) | `worker.py:375-665` | Real DOM automation against `FASAH_BASE_URL`. Selectors are Fasah/Angular-specific. |
| Playwright/Chromium | local subprocess | `worker.py:400-405` | Launched `--no-sandbox`, headless. |

No message brokers, no cloud SDKs, no outbound HTTP API clients.

## 10. Scheduled / background jobs / المهام المجدولة والخلفية

No cron/systemd timers in-repo. Two **long-running poll loops**:
- Orchestrator polls inbox every `poll_interval_secs` (default 15s) — `orchestrator.py:474-510`, `config/agent_fasah.yaml:22`.
- Browser worker polls task inbox every `ZC_POLL_INTERVAL` (default 3s) — `worker.py:983-1006`.

## 11. AuthN / AuthZ / المصادقة والصلاحيات

- **No end-user authentication or authorization exists.** The pipeline trusts whoever can drop a file in the inbox and whoever runs the processes.
- **Portal auth** is via a persisted Playwright `storage_state` (session cookies) at `state.json`; the worker returns `AUTH_FAIL` when redirected to login (`worker.py:419-466`). Login itself is **manual/out-of-band** (`docs/setup.md:146-152`).
- **Prod fail-closed gate:** in `ZC_ENV=prod` the worker refuses to start unless `AGENT_BROWSER_ALLOWED_DOMAINS`, `AGENT_BROWSER_ENCRYPTION_KEY`, and `FASAH_BASE_URL` are set (`worker.py:161-177`).
- `AGENT_BROWSER_ENCRYPTION_KEY` is **required but never actually used** to encrypt anything in the code (validated for presence only) — see gap analysis.

## 12. Audit & logging / التدقيق والسجلات

- Append-only daily **JSONL** audit (`utils/audit.py`), with a resilient in-memory-buffer variant used by the orchestrator (`utils/resilient_audit.py`, wired at `orchestrator.py:438-439`).
- Browser worker writes a per-task `transcript.jsonl` and `bundle.json` with SHA-256 manifest (`worker.py:314-333`, `362-369`).
- Standard `logging` to stdout + a `worker.log` file (`worker.py:114-123`).

## 13. Existing tests / الاختبارات الموجودة

| Suite | Count | Result (this env) | Evidence |
|-------|-------|-------------------|----------|
| Rust unit tests | 19 | **19 pass** | `cargo test` — see `06-baseline-verification.md` |
| Python `tests/test_dropout.py` | 54 | **52 pass, 2 FAIL** | `pytest tests/` — §14 |

**Coverage is uneven:** the Rust engine and the Python *resilience* layer are tested; the **browser worker (`worker.py`), the orchestrator main loop, and Rust↔Python fallback equivalence are NOT tested**. No integration or E2E tests exist.

## 14. Local run / التشغيل المحلي

Proven working in this environment:
- `cargo build` → OK; `cargo test` → 19/19 pass.
- `fasah-engine parse examples/sample_declarations.csv` → 5 valid records.
- `fasah-engine check … --rules config/fasah_rules.yaml` → 2 approve, 1 hold, 1 escalate, 1 reject (`06-baseline-verification.md`).
- `pytest tests/` → **2 failures** (`test_parse_nonexistent_file`, `test_never_raises`) — both are **real bugs**, not environment issues (see `04-gap-analysis.md` GAP-BUG-001/002).

**Stale evidence warning:** the committed `evidence/` folder was captured on **Windows** (`C:\Users\User\…`) at an **earlier commit**. `evidence/pytest.txt` reports *"no tests ran / file or directory not found: tests/"*, and `evidence/line_counts.txt` omits every resilience module (circuit_breaker, checkpoint, fallback_*, degradation, health, resilient_audit, worker health/retry). The committed evidence therefore **does not reflect the current code** and must not be trusted as a baseline.

## 15. Strengths / نقاط القوة

1. **Clean domain/infra separation** — Rust parser/compliance are pure, I/O-free, unit-tested functions (`parser.rs:56`, `compliance.rs:129`).
2. **Genuine resilience engineering** — circuit breaker, Python fallbacks, checkpoint/resume, resilient audit, degradation registry (`src/pipeline/`, `src/utils/`).
3. **Crash-safe writes** — atomic tmp→fsync→rename for task envelopes and checkpoints (`dispatcher.rs:114-127`, `checkpoint.py:88-108`).
4. **Defense-in-depth on the browser worker** — domain allowlist, output-size limits, out_dir sanitization, flock task locks, structured error codes, prod fail-closed (`worker.py` gates 9–13).
5. **Config-driven compliance** — rules live in YAML, no rebuild to change (`fasah_rules.yaml`).

## 16. Fragile / risky areas / المناطق الهشة

1. **CI is disconnected** — `.github/workflows/ci.yml:4-7` triggers on `main`, but the repo's default branch is `master` (`git remote show origin` → HEAD branch: master). CI has effectively never gated anything.
2. **All lint/format gates are currently red** — `cargo fmt --check` fails, `cargo clippy -- -D warnings` fails (2 `ptr_arg` errors in `main.rs:109-110`), `ruff check src/` fails (1 error in `audit.py:10`). Only `cargo test` is green.
3. **Rust vs Python behavioral drift** — the fallbacks are hand-reimplementations of the Rust logic with subtle differences (cert-matching union vs first-match; banned-HS risk 100 vs 95; `approve_with_conditions` never emitted by Python). No test asserts equivalence.
4. **Broken deployment path** — `docker-compose.yml` references a `Dockerfile` that does not exist.
5. **Contract not enforced** — bundle/task JSON is never validated against `schemas/`, and the worker's real `tool_versions` violates `fasah_bundle.schema.json` (writes `playwright`, schema requires `agent_browser`).
6. **POSIX-only worker** — `worker.py` imports `fcntl` and uses `os.open(O_*)` at module top; it cannot run on Windows despite docs implying cross-platform.

## 17. Unclear / not-understood modules / الوحدات غير المفهومة

- **`idempotency.rs` and `stability.rs`** are exported from `lib.rs` but **not referenced by `main.rs`** and have **no tests**. The orchestrator re-implements the same ideas in Python (`compute_sha256`, hash ledger). These Rust modules appear to be **dead relative to the running pipeline** — needs human confirmation on intent.
- The unused `tokio` dependency (§4).

## 18. Abandoned / duplicated / provenance leftovers / ملفات مهجورة أو مكررة

- **`evidence/`** — stale captures from another OS/commit (§14). Candidate for regeneration or removal.
- **"ZeroClaw" provenance** — this project was clearly **extracted from a larger parent system called ZeroClaw**: security "Gates **9–13**" imply gates 1–8 elsewhere (`worker.py:69-110`, `docs/architecture.md:100-111`); schema `$id`s point to `https://zeroclaw.gov/schemas/…`; session path default `/var/lib/zeroclaw/…`; user-agent `ZeroClaw-FasahWorker`; `audit.py` docstring says *"Replaces the ZeroClaw core_audit crate"*. This is not a defect but explains numbering/naming anomalies.
- **Duplicated logic (intentional):** parse + compliance exist in both Rust and Python (fallbacks). Duplicated by design for degradation, but drift-prone (§16.3).

## 19. Inventory summary / الخلاصة

| Dimension | Reality |
|-----------|---------|
| Type | File-driven batch automation agent (not a service/app) |
| Languages | Rust (core, ~1.8k LoC) + Python (glue/browser/resilience, ~2.6k LoC) |
| State | Filesystem only; no DB |
| Tests | Rust 19/19 ✅; Python 52/54 (2 real failures) ⚠ |
| Quality gates | fmt ❌, clippy ❌, ruff ❌, pytest ⚠, cargo test ✅ |
| CI | Present but disconnected (branch mismatch) ❌ |
| Deploy | Compose file present, Dockerfile missing ❌ |
| Production-ready? | **No evidence supports this claim.** |
