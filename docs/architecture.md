# Architecture / المعمارية

## Pipeline Overview / نظرة عامة على خط المعالجة

```
Tabadol CSV Export
      │
      ▼
[inbox/]  ◄─── Drop CSV/JSON files here
      │
      ▼
 orchestrator.py  (Python)
      │
      ├─► fasah-engine parse <file.csv>   ──► ParseResult JSON
      │         (Rust)
      │
      ├─► fasah-engine check <records.json> ──► ComplianceResult JSON
      │         (Rust)
      │
      ├─► APPROVE/REJECT  ──────────────────► outbox/track_*.json
      │   (direct to outbox)
      │
      └─► HOLD / ESCALATE ─────────────────► outbox/browser_tasks/*.json
                │                                        │
                │                                        ▼
                │                               browser/worker.py (Python + Playwright)
                │                                        │
                │                                        ▼
                │                               outbox/browser_results/<task_id>/bundle.json
                │                                        │
                └────────────────────────────────────────┘
                                   │
                         Result watcher (via fasah-engine watch)
                                   │
                                   ▼
                         outbox/track_*.json  OR  outbox/escalation_*.json
```

## Component Map / خريطة المكونات

| Component | Language | Location | Purpose |
|-----------|----------|----------|---------|
| `fasah-engine` | Rust | `src/agents/` | CSV parser + compliance checker CLI |
| `orchestrator.py` | Python | `src/pipeline/` | Main event loop, inbox polling, audit logging |
| `worker.py` | Python | `src/browser/` | Playwright browser automation for Fasah portal |
| `audit.py` | Python | `src/utils/` | JSONL audit logger (append-only) |
| `config/agent_fasah.yaml` | YAML | `config/` | Agent runtime configuration |
| `config/fasah_rules.yaml` | YAML | `config/` | Compliance rules (editable without rebuild) |
| `schemas/` | JSON Schema | `schemas/` | Task envelope + bundle format contracts |

## Rust Engine Modules / وحدات محرك Rust

```
src/agents/src/
├── lib.rs           # Public API
├── main.rs          # CLI entry point (parse / check / watch)
├── parser.rs        # CSV/JSON → DeclarationRecord[] (pure)
├── compliance.rs    # ComplianceRules + check_all() (pure)
├── dispatcher.rs    # BrowserDispatcher — writes task JSON files
├── result_watcher.rs # Scans browser_results/ → ResultAction[]
├── shipment.rs      # ShipmentStatus state machine + TrackingCommand
├── idempotency.rs   # SHA-256 content hash ledger (crash-safe)
└── stability.rs     # File mtime/size stability tracker
```

## Data Flow Details / تفاصيل تدفق البيانات

### 1. Parse Stage
- Input: Tabadol CSV export (10 required columns)
- Rust validates: HS code format, ISO country code, non-negative values
- Output: `ParseResult` with `records[]` and content SHA-256 hash

### 2. Compliance Stage
- Input: `DeclarationRecord[]` + compliance rules YAML
- Checks (in order): sanctioned country → banned HS → certificates → high value → overweight
- Output: `ComplianceResult` with per-declaration verdicts + risk scores (0-100)

### 3. Dispatch Stage
| Verdict | Action |
|---------|--------|
| `approve` / `approve_with_conditions` | Write tracking command to outbox |
| `reject` / `reject_sanctioned` | Write rejection command to outbox |
| `hold_pending_certificates` | Write browser task → Playwright worker |
| `escalate_high_value` | Write browser task → Playwright worker |
| `mandate_inspection` | Write hold command to outbox |

### 4. Browser Automation
- Worker polls `outbox/browser_tasks/` for `*.json` task envelopes
- Executes `fasah_search_inspect_v1` playbook via Playwright
- Navigates Fasah portal, searches declaration, extracts status
- Writes `bundle.json` to `outbox/browser_results/<task_id>/`

### 5. Result Processing
- `fasah-engine watch` scans `browser_results/`
- Maps bundle status → shipment status: `FOUND+approval→approved`, `FOUND+hold→held`
- Writes final tracking commands to outbox
- Retries on `TRANSIENT_FAIL` (max 3 attempts)
- Escalates on `AUTH_FAIL` / `NEEDS_HUMAN`

## Security Gates / بوابات الأمان

The browser worker enforces 13 security gates:

| Gate | Description |
|------|-------------|
| 9 | Output limits: max 20 artifacts, 20MB each, 50MB per task |
| 10 | Prod startup validation: required env vars must be set |
| 11 | Domain allowlist: `AGENT_BROWSER_ALLOWED_DOMAINS` enforced |
| 12 | Idempotency: duplicate task detection + flock-based task locks |
| 13 | Structured error codes: `E_*` enum for monitoring/alerting |

## Audit Trail / سجل المراجعة

All agent events are written to `workspace/audit/agent_fasah_YYYY-MM-DD.jsonl`:

```json
{"ts": "2026-04-05T10:00:00Z", "agent_id": "agent_fasah", "action": "AgentStarted", ...}
{"ts": "2026-04-05T10:00:01Z", "action": "ToolCompleted", "tool": "fasah_declaration_parse", ...}
{"ts": "2026-04-05T10:00:02Z", "action": "ToolCompleted", "tool": "fasah_compliance_check", ...}
{"ts": "2026-04-05T10:00:03Z", "action": "ToolInvoked", "tool": "browser_dispatch", ...}
```
