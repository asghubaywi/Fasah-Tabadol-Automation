# Fasah-Tabadol-Automation — Engineering Constitution / دستور المشروع الهندسي

> **This is the highest-authority document for engineering decisions in this repository.**
> Any human or AI agent MUST read it before modifying code.
> It is derived from the project's *actual* established behavior (cited), not generic best practice.
> Canonical copy: `.specify/memory/constitution.md` · Mirror: `docs/spec-driven/02-constitution.md` (keep both in sync).
>
> **Version:** 1.0.0 (ratified as a discovery baseline, 2026-07-19). Amendments require a human-approved ADR.

---

## Preamble

This project clears customs declarations. A wrong `approve`, a lost declaration, or a falsified audit line can have legal, financial, and regulatory consequences. The principles below prioritize **correctness, safety, and evidence over speed and cleverness.**

---

## Principles / المبادئ

### P1 — Data integrity before execution speed / سلامة البيانات قبل السرعة
Never trade correctness or durability for throughput. Writes that matter are **atomic** (tmp → fsync → rename) and idempotent, as already practiced in `dispatcher.rs:114-127` and `checkpoint.py:88-108`. New persistence code must match this bar.

### P2 — Tests are part of "done" / الاختبارات جزء من الاكتمال
A change is not complete until it has an automated test or a documented, reproducible verification. Match the existing style: pure-logic units for Rust (`compliance.rs` tests), behavior/failure-injection for Python (`test_dropout.py`). "It compiles" and "it ran once" are not "done".

### P3 — Do not change established behavior without documentation / لا تغيّر السلوك القائم دون توثيق
The current observable behavior is the baseline of record (see `05-requirements-traceability.md`). Any intended behavior change must be stated in the relevant spec, justified, and, if it touches a public contract, backed by an ADR.

### P4 — Contracts and interfaces stay stable / العقود مستقرة
The file contracts (`schemas/fasah_task.schema.json`, `schemas/fasah_bundle.schema.json`), the verdict taxonomy (`ComplianceAction` in `compliance.rs`), and the shipment state machine (`shipment.rs`) are the compatibility spine. Backward-compatible extension is allowed; breaking them requires an ADR and explicit human approval. (Note: an existing schema/impl drift is logged as GAP-CONTRACT-001 and must be resolved *toward* the contract, not by silently breaking it.)

### P5 — Audit and logs are append-only, never rewritten / السجلات لا تُعدَّل رجعيًا
The audit trail (`utils/audit.py`, `resilient_audit.py`) is append-only JSONL. Never mutate or delete historical audit lines, retro-date events, or "clean up" past entries. Redaction, if ever needed, is a new event, not an edit.

### P6 — Fail safe / fail closed, never fail open / الفشل الآمن أفضل من الاستمرار غير الموثوق
When trust cannot be established, stop or escalate — do not proceed. This is already the pattern: prod startup fail-closed (`worker.py:161-177`), unknown portal status → human escalation not auto-approve (`result_watcher.rs:167-176`), pipeline error → quarantine not drop (`orchestrator.py:499-507`). Preserve it.

### P7 — Secrets never live in code or the repo / الأسرار خارج الكود والمستودع
Credentials and keys come only from the environment (`.env`, secrets manager), never committed. `.env` is git-ignored (`.gitignore:32-34`); config files explicitly defer to env (`agent_fasah.yaml:33-36`). No secret may be added to source, tests, fixtures, or docs.

### P8 — Separate domain logic from infrastructure / فصل منطق المجال عن البنية التحتية
Keep decision logic pure and I/O at the edges, as the Rust engine already does (parser/compliance are pure; dispatch/watch do I/O). Do not embed portal, filesystem, or network specifics into compliance/parse logic.

### P9 — Small, verifiable changes over big rewrites / تغييرات صغيرة قابلة للتحقق
Prefer minimal, reviewable diffs each with a test or verification artifact. No broad refactor or technology swap during discovery. Do not replace Rust, Python, Playwright, or the file-based design merely because a newer option exists.

### P10 — Sensitive decisions require a human / القرارات الحساسة تحتاج موافقة بشرية
An AI agent must **stop and ask** before: changing compliance rule semantics, expanding the browser worker beyond read-only actions, altering the verdict taxonomy or state machine, touching security gates, or anything that could mis-clear or lose a declaration.

### P11 — No claim of readiness without evidence / لا ادعاء للجاهزية دون دليل
Do not describe anything as "ready", "complete", "secure", "verified", or "production-ready" without direct evidence from code + tests + a real run. Report what was actually executed and its result (`06-baseline-verification.md` is the template).

### P12 — Every important requirement is traceable to code and a test / التتبع
Each significant requirement carries a stable ID (`REQ-*`, `NFR-*`) and maps to its implementation and test in `05-requirements-traceability.md`. When you change behavior, update the trace.

### P13 — Privacy & data protection / الخصوصية وحماية البيانات
Declarations contain importer identities and commercial data. Do not log full declaration payloads at INFO, do not export workspace data off-host, and redact sensitive fields before sharing audit/evidence (as `CONTRIBUTING.md:100-103` already asks). Treat `workspace/` as confidential.

### P14 — Rust and Python decision logic must stay equivalent / تكافؤ المحركين
The Python fallbacks (`fallback_parser.py`, `fallback_compliance.py`) must produce verdicts equivalent to the Rust engine for the same input. Any intentional divergence must be documented and tested; unintentional drift is a bug (GAP-DRIFT-001).

### P15 — Every AI agent reads this constitution first / قراءة الدستور أولًا
Before editing, an agent must load this file and the spec for the area it touches (`AGENTS.md`, `CLAUDE.md` enforce this).

---

## Definition of Done (binding checklist)

- [ ] Behavior matches (or intentionally + documentedly updates) the relevant spec in `specs/current-system/`.
- [ ] `cargo test` and `pytest tests/` pass (or newly-added tests pass and pre-existing failures are not worsened).
- [ ] `cargo fmt --all -- --check`, `cargo clippy -- -D warnings`, and `ruff check src/` pass for touched code.
- [ ] Traceability matrix updated for any requirement touched.
- [ ] No secret added; no audit line rewritten; no contract broken without an ADR.
- [ ] Human sign-off obtained for any P10 item.

## Amendment process

Constitution changes are proposed via an ADR in `docs/adr/`, approved by a human, then applied to **both** copies with a bumped version. AI agents may draft amendments but may not ratify them.
