# 01 — Project Vision / رؤية المشروع

> **Status:** Discovery artifact. Answers below are grounded in code where possible.
> Where the evidence does not establish an answer, the item is explicitly marked
> **`غير مؤكد — يحتاج قرارًا بشريًا` (Uncertain — requires a human decision)** rather than invented.

---

## 1. What problem does it solve? / ما المشكلة التي يحلها؟

**Proven.** It removes the manual, error-prone loop of transcribing *Tabadol* customs declarations into the *Fasah* clearance portal, judging their regulatory compliance, and tracking their status. It ingests declaration files, applies Saudi compliance rules (ZATCA/SFDA/SASO-style: banned HS codes, sanctioned origins, required certificates, value/weight thresholds), and automates portal lookups — producing an auditable trail throughout (`README.md:11-14`, `compliance.rs`, `worker.py`).

## 2. Who is the target user? / من المستخدم المستهدف؟

**Inferred — needs human confirmation.** Customs brokers / clearance operators and compliance officers operating the pipeline internally. There is no end-user auth, UI, or tenant model in the code (`§11` of inventory), so the "user" today is an **operator running two processes**, not an interactive app user.

## 3. What practical value does it deliver? / ما القيمة العملية؟

**Proven (as capability, not as measured outcome):**
- Automated, rule-based triage of declarations into approve / hold / escalate / reject / inspect (`compliance.rs:89-106`).
- Automated portal status verification for the subset needing it (`worker.py`).
- A tamper-evident, append-only audit trail and SHA-256-manifested browser evidence bundles.
- Resilience: keeps running (degraded) when the Rust engine or disk misbehaves (`orchestrator.py`, `circuit_breaker.py`).

**Not proven:** any quantitative benefit (time saved, throughput, accuracy vs humans). No benchmarks exist. → `غير مؤكد — يحتاج قرارًا بشريًا`.

## 4. What core operations does it support? / ما العمليات الأساسية؟

**Proven:**
1. Parse declaration CSV/JSON → structured records (`parser.rs`).
2. Compliance evaluation → per-declaration verdict + risk score (`compliance.rs`).
3. Dispatch: outbox tracking command **or** browser task (`orchestrator.py:316-338`).
4. Browser portal search/inspect playbook `fasah_search_inspect_v1` (`worker.py:735-752`).
5. Result processing → shipment status update or human escalation (`result_watcher.rs`).
6. Idempotent, resumable, audited batch processing (`checkpoint.py`, idempotency ledger).

## 5. What is it explicitly NOT trying to solve? / ما الذي لا يحاوله؟

**Inferred from absence in code (needs confirmation):**
- It does **not** submit or edit declarations on Fasah — the only playbook is **search/inspect (read-only)**; `download`/`upload` are hard-blocked (`worker.py:79`, `V1_BLOCKED_ACTIONS`).
- It does **not** authenticate end users or manage roles.
- It does **not** pull from Tabadol via API — input is file-drop only.
- It does **not** persist to a database or provide reporting/analytics.
- It does **not** perform customs valuation, duty calculation, or payment.

## 6. What are the functional boundaries? / ما الحدود الوظيفية؟

Input boundary: a CSV/JSON file in `workspace/inbox/`. Output boundary: JSON command files in `workspace/outbox/` and evidence bundles in `browser_results/`. Everything between is in-scope; anything requiring writing to Fasah, calling Tabadol APIs, or human decisioning is **out of scope / escalated** (`result_watcher.rs:167-176`).

## 7. Most important success scenario / أهم سيناريو نجاح

**Proven end-to-end shape:** A Tabadol CSV lands in the inbox → parsed → each declaration judged → compliant ones written directly as `approved` tracking commands; hold/escalate ones sent to the browser worker → worker finds the record on Fasah and extracts status → result watcher maps it to `approved`/`held`/`rejected` → tracking command written → audit updated. The file is moved to `processed/` and recorded in the idempotency ledger so it is never reprocessed.

## 8. Most important failure scenario to prevent / أهم سيناريو فشل يجب منعه

**Proven design intent:** the system must **never silently mis-clear or lose a declaration.** Guardrails observed:
- Fail-closed prod startup (`worker.py:161-177`).
- Fail-safe verdict routing: unknown/failed portal states escalate to a human, never auto-approve (`result_watcher.rs`).
- Quarantine on pipeline failure instead of dropping the file (`orchestrator.py:499-507`).
- Idempotency ledger prevents double-processing (`orchestrator.py:484-488`).

**Caveat:** two current bugs undermine "never crash / never lose audit" (fallback parser crash on missing file; audit logger can raise) — see gap analysis GAP-BUG-001/002.

## 9. What does success look like in 1 year? / بعد سنة؟

`غير مؤكد — يحتاج قرارًا بشريًا`. No roadmap, milestones, or KPIs exist in the repo. A defensible *proposed* 1-year definition (subject to human approval) lives in `specs/project-evolution/plan.md`: green CI on `master`, all quality gates enforced, tested browser + orchestrator paths, verified Rust↔Python equivalence, working containerized deployment, and a documented operational runbook.

## 10. How could it evolve over 3–5 years without breaking its core? / خلال ٣–٥ سنوات؟

`غير مؤكد — يحتاج قرارًا بشريًا` (no evidence in repo). **Constraints the core imposes on any evolution** (proven): the file-based contract (`schemas/*.json`), the verdict taxonomy (`ComplianceAction`), and the shipment state machine (`shipment.rs`) are the stable spine. Plausible non-breaking directions — a real Tabadol API ingestor behind the same inbox contract, additional read-only playbooks, a persistent store *behind* the current file interface, or a reporting surface over the audit log — are candidates only, not commitments.

---

## Vision guardrails (binding on future work)

- Do not expand the browser worker beyond **read-only** portal actions without an explicit human decision and an ADR — writing to Fasah is a fundamentally different risk class.
- Do not claim throughput/accuracy value without measured evidence.
- Preserve the file-based contracts and verdict taxonomy as the compatibility spine.
