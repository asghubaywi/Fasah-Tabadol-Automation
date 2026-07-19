# Domain: Compliance Checking / فحص الامتثال

**Primary code:** `src/agents/src/compliance.rs` (authoritative) · `src/pipeline/fallback_compliance.py` (degraded mode)

## Goal / الهدف
Assign each declaration a compliance **verdict** (`ComplianceAction`), a set of reasons, missing certificates, and a 0–100 risk score, from configurable rules.

## Actors / الأدوار
Orchestrator via `fasah-engine check <records.json> --rules <yaml>` (`orchestrator.py:183-185`); Python fallback in-process (`orchestrator.py:208`).

## Inputs / المدخلات
- A `ParseResult` JSON **or** a plain `DeclarationRecord[]` (`main.rs:82-90`).
- `ComplianceRules` from YAML (`config/fasah_rules.yaml`) or built-in defaults (`compliance.rs:48-87`).

## Outputs / المخرجات
`ComplianceResult { total_checked, approved, held, escalated, rejected, verdicts[] }`; each `ComplianceVerdict { declaration_number, action, reasons[], missing_certificates[], risk_score }` — `compliance.rs:108-125`.

## Business rules (priority-ordered, proven) / قواعد العمل
| ID | Rule | Action | Risk | Evidence |
|----|------|--------|------|----------|
| REQ-COMP-001 | Origin in `sanctioned_countries` | `reject_sanctioned` | 100 | `compliance.rs:141-148` |
| REQ-COMP-002 | HS (dots stripped) starts with a banned prefix | `reject` | 100 (Rust) / **95 (Py)** | `compliance.rs:150-162`; `fallback_compliance.py:96-103` |
| — | If rejected → return immediately (no further checks) | — | — | `compliance.rs:165-173` |
| REQ-COMP-003 | Missing any required cert for HS prefix | `hold_pending_certificates` | ≥60 (Rust) / 70 (Py) | `compliance.rs:175-209` |
| REQ-COMP-004 | `declared_value_sar` > `high_value_threshold_sar` | `escalate_high_value` (only if still Approve) | ≥70/80 | `compliance.rs:211-221` |
| REQ-COMP-005 | `weight_kg` > `max_weight_kg` | `mandate_inspection` (only if still Approve) | ≥50/60 | `compliance.rs:223-233` |
| REQ-COMP-006 | Approve but non-empty reasons | `approve_with_conditions` | ≥20 | `compliance.rs:235-239` (**Rust only**) |
| REQ-COMP-007 | Required certs = union of 2-digit **and** 4-digit prefix rules | — | — | `compliance.rs:175-193` |
| REQ-COMP-008 | Aggregate counts by action class | — | — | `compliance.rs:260-291` |

## Verdict taxonomy (contract) / تصنيف القرارات
`Approve, ApproveWithConditions, HoldPendingCertificates, EscalateHighValue, Reject, RejectSanctioned, MandateInspection` — `compliance.rs:89-106`. **Changing this enum is a P4/P10 event (needs ADR + human sign-off).**

## Use cases / حالات الاستخدام
Compliant electronics→approve; food w/o SFDA+Halal→hold; >500k SAR→escalate; banned weapon HS→reject; sanctioned origin→reject_sanctioned; >50t→mandate_inspection.

## Main / exception / failure scenarios
- Main: rules loaded, each record evaluated in priority order.
- Exception: rules YAML missing → Rust `check` errors out (`main.rs:95-98`); Python fallback silently uses hardcoded defaults (`fallback_compliance.py:63-68`). **Divergence.**
- Failure: none internal (pure); upstream failures handled by resilience layer.

## Permissions / State changes / Data
Pure, no I/O, no state. Consumes `DeclarationRecord`, `ComplianceRules`; produces verdicts.

## Integrations / التكاملات
Verdict `action` drives dispatch routing (`orchestrator.py:326`) and portal escalation logic.

## Proven behavior / السلوك المثبت
On the sample (`06-baseline-verification.md`): 2 approve (risk 0), 1 escalate_high_value (risk 70), 1 reject (risk 100), 1 hold_pending_certificates (risk 60). Matches rules.

## Tests / الاختبارات
- Rust: `compliance::tests::*` — approve electronics, hold missing cert, reject banned HS, escalate high value, reject sanctioned (`compliance.rs:329-372`, all pass).
- Python: `TestFallbackCompliance::*` — `test_dropout.py:134-242` (pass).
- **Missing:** no test compares Rust vs Python verdicts on the same input.

## Known constraints & divergences (Rust ⇄ Python) / القيود والتباينات
These are **confirmed** by reading both implementations (**GAP-DRIFT-001**):
1. **Banned-HS risk**: Rust 100 vs Python 95 (`compliance.rs:159` vs `fallback_compliance.py:101`).
2. **Cert matching**: Rust takes the **union** of the 2-digit and 4-digit prefix rules; Python checks 4-digit **then** 2-digit and `break`s on the first hit (`fallback_compliance.py:108-113`). Different results possible if both levels have rules.
3. **`approve_with_conditions`** is never emitted by Python (only `approve`).
4. **Count semantics**: Python counts an escalated item as **both** `escalated` and `held` (`fallback_compliance.py:195-197`), so `approved+held+rejected` can exceed `total_checked`; Rust counts each verdict once.
5. **Missing rules file**: Rust errors; Python defaults silently.
6. **`mandate_inspection`** in Rust only applies when the item is otherwise `Approve` (a high-value overweight item escalates, not inspects); Python's priority order returns high-value before weight too — but the interaction is untested.

## Open questions / الأسئلة غير المحسومة
- Which implementation is authoritative when they disagree? (Constitution P14 says they must be equivalent → **human decision** on the canonical semantics, then align the other.)
- Should `sanctioned_countries` be non-empty by default? It is empty in both default rules and YAML — sanction screening is effectively **off** until configured.
- HS certificate rules currently cover chapters 01–24, 28–38, 84–85 only; other regulated chapters are silently `approve`. Intended?
