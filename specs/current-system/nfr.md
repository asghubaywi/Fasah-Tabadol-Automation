# Non-Functional Requirements / المتطلبات غير الوظيفية

Cross-cutting requirements extracted from the code. Status per `05-requirements-traceability.md`.

## Security / الأمان

| ID | Requirement | Evidence | Status | Notes |
|----|-------------|----------|--------|-------|
| NFR-SEC-001 | Browser navigation restricted to an allowlist of domains | `worker.py:216-234` | IWT | Wildcards supported; **off if allowlist empty (dev)** |
| NFR-SEC-002 | Prod refuses to start without allowlist + encryption key + base URL | `worker.py:161-177` | IWT | Fail-closed |
| NFR-SEC-003 | `out_dir` reduced to a safe basename — path traversal blocked | `worker.py:300-308` | IWT | Regex `[A-Za-z0-9_-]{1,128}` |
| NFR-SEC-004 | Idempotency ledger rejects symlinked ledger files | `idempotency.rs:29-48` | IWT | Module not wired into CLI, though |
| NFR-SEC-005 | `download`/`upload` actions hard-blocked in the browser worker | `worker.py:79` | IWT | Read-only posture |
| NFR-SEC-006 | Secrets only from environment, never committed | `.gitignore:32-34`, `agent_fasah.yaml:33-36` | INF | No secret found in repo (good) |
| NFR-SEC-007 | Chromium launched `--no-sandbox` | `worker.py:404` | INF | **Accepted risk** for containerized runs; document + isolate |

**Security gaps (see gap analysis):** `AGENT_BROWSER_ENCRYPTION_KEY` is validated but unused; no runtime schema validation of inbound task JSON; no input size cap on inbox files; `Cargo.lock` is git-ignored (supply-chain reproducibility).

## Performance / الأداء

| ID | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| NFR-PERF-001 | Configurable poll intervals (orchestrator 15s, worker 3s) | `agent_fasah.yaml:22`, `worker.py:36` | IWT |
| NFR-PERF-002 | Hot parse/compliance path in Rust; browser output size capped | `parser.rs`, `worker.py:190-210` | INF |

No load/throughput targets or benchmarks exist. Scaling model is single-process poll loops; no concurrency beyond one file at a time in the orchestrator.

## Reliability / الموثوقية

| ID | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| NFR-REL-001 | Atomic writes for critical outputs (tmp→fsync→rename) | `dispatcher.rs:114-127`, `checkpoint.py:88-108` | PV |
| NFR-REL-002 | Idempotent, no-double-process file handling | `orchestrator.py:484-488` | IWT |
| NFR-REL-003 | Crash-safe checkpoint / resume | `checkpoint.py` | FV |
| NFR-REL-004 | Graceful degradation to Python fallbacks | `orchestrator.py:131-208` | FV |

**Caveat:** not every write is atomic — e.g., orchestrator tracking commands (`orchestrator.py:414-415`) and result-watcher outputs (`result_watcher.rs:252`) use plain `write`, so a crash mid-write can leave a truncated command file.

## Portability / قابلية النقل

| ID | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| NFR-PORT-001 | Browser worker is **POSIX-only** (`fcntl`, `os.open(O_*)`) | `worker.py:19,264` | INF |

Docs imply cross-platform (evidence captured on Windows), but `worker.py` cannot import on Windows. Rust engine + orchestrator + resilience layer are cross-platform.

## Observability / قابلية المراقبة

| ID | Requirement | Evidence | Status |
|----|-------------|----------|--------|
| NFR-OBS-001 | Auditable event trail (JSONL) | `resilient_audit.py` | PV |
| NFR-OBS-002 | Browser evidence: transcript + SHA-256 manifest per task | `worker.py:362-369` | UNK (untested) |
| NFR-OBS-003 | Health dashboard CLI | `health.py` | IWT (has bug GAP-BUG-003) |

No metrics endpoint, no centralized log shipping, no alerting integration in-repo.

## Compliance/Regulatory posture / الامتثال التنظيمي
The system encodes SFDA/SASO/customs rules but there is **no evidence** of validation against official regulatory sources, nor versioning of the rule set against regulation dates. Treat rule correctness as **unverified against authority** — human/domain-expert decision required.
