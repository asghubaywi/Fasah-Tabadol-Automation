# 03 — Current Architecture (As-Built) / المعمارية الفعلية

> This documents the architecture **that exists**, including its warts — not an idealized target. Target-state lives in `specs/project-evolution/plan.md`.

## Component map / خريطة المكونات

```mermaid
flowchart TB
    subgraph ext[External]
        TAB[Tabadol export CSV/JSON]
        FASAH[Fasah portal]
    end

    subgraph proc1[Process: Orchestrator - Python]
        ORCH[orchestrator.py main loop]
        CB[circuit_breaker.py]
        FBP[fallback_parser.py]
        FBC[fallback_compliance.py]
        CKPT[checkpoint.py]
        DEG[degradation.py]
        AUD[resilient_audit.py]
    end

    subgraph eng[Subprocess: fasah-engine - Rust]
        PARSE[parser.rs]
        COMP[compliance.rs]
        DISPR[dispatcher.rs]
        WATCH[result_watcher.rs]
        SHIP[shipment.rs]
        IDEM[idempotency.rs - unwired]
        STAB[stability.rs - unwired]
    end

    subgraph proc2[Process: Browser Worker - Python]
        WORK[worker.py + Playwright]
        BHEALTH[health_check.py]
        RETRY[retry.py]
    end

    subgraph fs[workspace/ filesystem = the message bus]
        INBOX[(inbox/)]
        OUTBOX[(outbox/)]
        BTASKS[(outbox/browser_tasks/)]
        BRES[(outbox/browser_results/)]
        AUDITF[(audit/*.jsonl)]
        STATE[(state/)]
    end

    TAB --> INBOX --> ORCH
    ORCH -->|subprocess parse/check| eng
    ORCH -. circuit open .-> FBP & FBC
    ORCH --> CKPT & DEG & AUD
    ORCH -->|approve/reject| OUTBOX
    ORCH -->|hold/escalate| BTASKS
    BTASKS --> WORK --> FASAH
    WORK --> BRES
    BRES -->|fasah-engine watch| WATCH --> OUTBOX
    AUD --> AUDITF
    WORK --> STATE
```

## Data flow — happy path / تدفق البيانات (مسار النجاح)

```mermaid
sequenceDiagram
    participant Op as Operator
    participant O as orchestrator.py
    participant E as fasah-engine (Rust)
    participant FS as workspace/
    participant W as worker.py
    participant P as Fasah portal

    Op->>FS: drop declarations.csv in inbox/
    O->>FS: poll, SHA-256, check idempotency ledger
    O->>E: parse declarations.csv
    E-->>O: ParseResult JSON
    O->>E: check records.json --rules fasah_rules.yaml
    E-->>O: ComplianceResult (verdicts)
    alt approve / reject / inspect
        O->>FS: write outbox/track_*.json
    else hold / escalate
        O->>FS: write outbox/browser_tasks/<id>.json
        W->>FS: poll browser_tasks/, flock lock
        W->>P: navigate, search, inspect (read-only)
        W->>FS: write browser_results/<id>/bundle.json + manifest
        Note over FS: fasah-engine watch (separate invocation)
        E->>FS: bundle.json -> outbox/track_*.json OR escalation_*.json
    end
    O->>FS: append audit event, move file to processed/, record hash
```

## Failure / degradation paths / مسارات الفشل والتدهور

```mermaid
flowchart LR
    A[run_engine via circuit breaker] -->|success| OK[use Rust result]
    A -->|FileNotFound / RuntimeError| F[mark_degraded + Python fallback]
    A -->|CircuitOpenError after 3 fails| F
    F --> CONT[pipeline continues, outcome=degraded in audit]
    P[process_file raises] --> Q[quarantine file + audit failure + checkpoint mark_failed]
    D[disk write fails in audit] --> B[buffer in memory, drop oldest at 500, stderr warn]
    BW[browser: 5 consecutive failures] --> SK[skip tasks until worker restart]
    PT[TRANSIENT_FAIL bundle] --> RT[retry up to max] --> ESC[escalation_*.json]
```

## Module boundaries / حدود الوحدات

| Boundary | Contract | Coupling |
|----------|----------|----------|
| Orchestrator ↔ engine | CLI argv + JSON on stdout | Loose (subprocess); versioned only by argv shape |
| Orchestrator ↔ worker | `browser_tasks/*.json` (`fasah_task.schema.json`) | Loose (file drop); **schema not enforced** |
| Worker ↔ result watcher | `browser_results/*/bundle.json` (`fasah_bundle.schema.json`) | Loose (file drop); **impl violates schema — GAP-CONTRACT-001** |
| Engine ↔ engine (dispatch/watch) | `.pending_tasks.json` ledger | Shared file; **bypassed by Python dispatcher — GAP-ARCH-001** |

## Entry points / نقاط الدخول
`fasah-engine {parse,check,watch}` (`main.rs`); `orchestrator.py`; `worker.py`; `python -m src.utils.health`.

## External connections / الاتصالات الخارجية
Only the browser worker reaches the network (Fasah portal via Chromium). Everything else is local filesystem + subprocess. No inbound network listeners.

## Trust model / نموذج الثقة
- **Implicit trust of the inbox**: anything readable in `inbox/` is processed; no authentication of the file's origin, no signature, no size cap.
- **Portal trust** via persisted session cookies; the worker fails closed to `AUTH_FAIL` rather than attempting credential entry.
- **Prod hardening** only on the browser worker (gates 10/11); the orchestrator has no equivalent prod gate.
- Trust boundary between processes is the filesystem — whoever can write `workspace/` can inject tasks/commands.

## Where state lives / أماكن تخزين الحالة
Filesystem only: idempotency ledger, checkpoint JSON, outbox commands, audit JSONL, browser session `state.json`, task locks. In-memory only: circuit-breaker state, degradation registry, browser health counters (lost on restart).

## Lifecycle of the primary entity (a declaration) / دورة حياة الكيان
`received → parsed → checked → {approved | approved_with_conditions | held | rejected} → (held ⇄ checked) → released` (`shipment.rs`). **Note:** transitions are *defined and tested* but **not enforced at runtime** because the live orchestrator writes statuses directly (GAP-ARCH-003).

## Critical dependencies / الاعتماديات الحرجة
- Rust toolchain to build `fasah-engine` (fallbacks mitigate runtime absence, not build).
- Playwright + Chromium for any portal interaction (no fallback — if absent, hold/escalate items simply never get portal status).
- Filesystem durability + a stable single writer per directory.

## Bottlenecks / نقاط الاختناق
- Orchestrator processes **one file at a time**, sleeping between polls — throughput-bound by poll interval and browser latency.
- Browser worker is serial per task with multi-second Angular settle waits (`worker.py:445-446`).
- No parallelism/queue; scaling is "run more workers" but there is no work-partitioning to make that safe.

## Stable vs volatile components / المكونات المستقرة مقابل المتغيرة
| Stable (change rarely, well-tested) | Volatile (expected to change / fragile) |
|---|---|
| `parser.rs`, `compliance.rs`, `shipment.rs`, verdict taxonomy | `worker.py` portal selectors/routes (external UI drift) |
| Circuit breaker, checkpoint, degradation | `fasah_rules.yaml` (regulatory changes — by design) |
| File contracts (schemas) | Dual dispatcher / fallback drift (needs consolidation) |

## Architectural smells (as-built) / روائح معمارية
1. **Dual implementation drift** — parse/compliance/dispatch exist twice (Rust + Python) with confirmed divergences.
2. **Unwired modules** — `idempotency.rs`, `stability.rs`, `shipment.rs` transition-enforcement, and the JSON schemas are present but not on the live path.
3. **Contract not enforced** — schemas are documentation, not validation; one is already violated.
4. **Observability blind spots** — in-memory-only health/degradation across process boundaries; health CLI has a false-negative bug.
