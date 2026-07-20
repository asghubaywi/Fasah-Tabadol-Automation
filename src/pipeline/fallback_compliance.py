"""
fallback_compliance.py — Pure Python compliance checker fallback.
مدقق الامتثال الاحتياطي — يُستخدم عند فشل محرك Rust

Implements the same priority-ordered rules as ``fasah-engine check`` and
returns a ComplianceResult-compatible dict so the rest of the pipeline
continues without the Rust binary.

Priority order and risk scores mirror compliance.rs::check_declaration exactly
(the Rust engine is authoritative; this is the degraded-mode fallback):
    1  Sanctioned country → reject_sanctioned      (risk 100, early return)
    2  Banned HS prefix   → reject                 (risk 100, early return)
    3  Missing certs      → hold_pending_certs     (risk max(.,60))
    4  High value         → escalate_high_value    (risk max(.,70); only if still approve)
    5  Overweight         → mandate_inspection     (risk max(.,50); only if still approve)
    6  Approve + reasons  → approve_with_conditions(risk max(.,20))
    *  Otherwise          → approve                (risk 0)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("fasah.fallback_compliance")

# ── Default rules — mirrors config/fasah_rules.yaml ──────────────────────────
_DEFAULT_RULES: dict[str, Any] = {
    "banned_hs_prefixes": ["9301", "9302", "2403"],
    "sanctioned_countries": [],
    "high_value_threshold_sar": 500_000.0,
    "max_weight_kg": 50_000.0,
    "certificate_requirements": {
        # Food (HS 01–24)
        **{str(i).zfill(2): ["SFDA", "Halal"] for i in range(1, 25)},
        # Electronics (HS 84–85)
        "84": ["SASO"],
        "85": ["SASO"],
        # Chemicals (HS 28–38)
        **{str(i): ["SASO", "HazMat"] for i in range(28, 39)},
    },
}


def _load_rules(rules_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load compliance rules from YAML, falling back to built-in defaults.

    تحميل قواعد الامتثال من YAML مع الرجوع إلى القيم الافتراضية المدمجة.
    """
    import yaml  # optional import — don't fail at module load time

    if rules_path is None:
        rules_path = os.environ.get(
            "FASAH_RULES",
            str(Path(__file__).parent.parent.parent / "config" / "fasah_rules.yaml"),
        )

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or {}
        log.debug("Fallback compliance: rules loaded from %s", rules_path)
        return rules
    except OSError:
        log.warning(
            "[DEGRADED] Cannot load rules from '%s' — using hardcoded defaults",
            rules_path,
        )
        return dict(_DEFAULT_RULES)


def _check_record(record: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """
    Apply compliance rules to one record and return a verdict dict.

    تطبيق قواعد الامتثال على سجل واحد وإعادة حكم الامتثال.

    This MUST stay behaviourally equivalent to the authoritative Rust engine
    (``src/agents/src/compliance.rs::check_declaration``) — see Constitution P14
    and the equivalence suite in ``tests/test_equivalence.py``. The Rust engine
    is the source of truth; this fallback mirrors its accumulate-then-decide
    logic, risk scores, certificate union, and priority ordering exactly.
    Comparisons are case-sensitive to match Rust (the parser already normalises
    origin to upper-case ISO-2).
    """
    decl_num = record.get("declaration_number", "UNKNOWN")
    hs_raw = str(record.get("hs_code", "")).strip()
    hs = hs_raw.replace(".", "")  # normalise 8471.30.00 → 847130
    origin = str(record.get("origin_country", "")).strip()
    declared_value = float(record.get("declared_value_sar", 0) or 0)
    weight = float(record.get("weight_kg", 0) or 0)
    provided: set[str] = set(record.get("required_certificates", []) or [])

    reasons: list[str] = []
    missing_certs: list[str] = []
    risk_score = 0
    action = "approve"

    # 1. Sanctioned country (highest priority) — mirrors compliance.rs step 1
    sanctioned = set(rules.get("sanctioned_countries", []) or [])
    if origin in sanctioned:
        reasons.append(f"origin country '{origin}' is under trade sanctions")
        risk_score = 100
        action = "reject_sanctioned"

    # 2. Banned HS prefix — step 2
    for banned in rules.get("banned_hs_prefixes", []) or []:
        banned_clean = str(banned).replace(".", "")
        if hs.startswith(banned_clean):
            reasons.append(f"HS code '{hs_raw}' matches banned prefix '{banned}'")
            risk_score = 100
            action = "reject"

    # Early return if already rejected (matches Rust's early return)
    if action in ("reject", "reject_sanctioned"):
        return {
            "declaration_number": decl_num,
            "action": action,
            "reasons": reasons,
            "missing_certificates": missing_certs,
            "risk_score": risk_score,
        }

    # 3. Certificate requirements — UNION of 2-digit and 4-digit prefixes (step 3)
    cert_requirements: dict[str, list[str]] = rules.get("certificate_requirements", {}) or {}
    required: set[str] = set()
    hs_prefix_2 = hs[:2] if len(hs) >= 2 else hs
    hs_prefix_4 = hs[:4] if len(hs) >= 4 else hs
    if hs_prefix_2 in cert_requirements:
        required.update(cert_requirements[hs_prefix_2])
    if hs_prefix_4 in cert_requirements:
        required.update(cert_requirements[hs_prefix_4])

    # BTreeSet ordering in Rust → iterate sorted for a deterministic missing list
    for req in sorted(required):
        if req not in provided:
            missing_certs.append(req)

    if missing_certs:
        reasons.append(f"missing certificates: {', '.join(missing_certs)}")
        risk_score = max(risk_score, 60)
        action = "hold_pending_certificates"

    # 4. High-value check — step 4 (only overrides a still-Approve action)
    threshold = float(rules.get("high_value_threshold_sar", 500_000.0))
    if declared_value > threshold:
        reasons.append(
            f"declared value {declared_value} SAR exceeds threshold {threshold} SAR"
        )
        risk_score = max(risk_score, 70)
        if action == "approve":
            action = "escalate_high_value"

    # 5. Overweight check — step 5 (only overrides a still-Approve action)
    max_weight = float(rules.get("max_weight_kg", 50_000.0))
    if weight > max_weight:
        reasons.append(
            f"weight {weight} kg exceeds inspection threshold {max_weight} kg"
        )
        risk_score = max(risk_score, 50)
        if action == "approve":
            action = "mandate_inspection"

    # 6. Minor notes → conditional approval — step 6
    if action == "approve" and reasons:
        action = "approve_with_conditions"
        risk_score = max(risk_score, 20)

    return {
        "declaration_number": decl_num,
        "action": action,
        "reasons": reasons,
        "missing_certificates": missing_certs,
        "risk_score": risk_score,
    }


def check_compliance(
    parse_result: dict[str, Any],
    rules_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run compliance checks on all records from a ParseResult dict.

    تشغيل فحوصات الامتثال على جميع السجلات من نتيجة التحليل.

    Args:
        parse_result: Output of parse_file() or fasah-engine parse.
        rules_path:   Path to fasah_rules.yaml (None = use FASAH_RULES env).

    Returns:
        ComplianceResult-compatible dict matching ``fasah-engine check`` output.
    """
    log.warning(
        "[DEGRADED] Python fallback compliance checker active (Rust engine unavailable)"
    )

    rules = _load_rules(rules_path)
    records: list[dict[str, Any]] = parse_result.get("records", [])
    verdicts: list[dict[str, Any]] = []
    counts = {"approved": 0, "held": 0, "rejected": 0, "escalated": 0}

    # Count each verdict exactly once, mirroring compliance.rs::check_all so the
    # aggregate totals match the Rust engine (approved+held+escalated+rejected
    # == total_checked). Escalate and mandate-inspection both count as escalated.
    for record in records:
        verdict = _check_record(record, rules)
        verdicts.append(verdict)
        action = verdict["action"]

        if action in ("approve", "approve_with_conditions"):
            counts["approved"] += 1
        elif action == "hold_pending_certificates":
            counts["held"] += 1
        elif action in ("escalate_high_value", "mandate_inspection"):
            counts["escalated"] += 1
        elif action in ("reject", "reject_sanctioned"):
            counts["rejected"] += 1

    return {
        "total_checked": len(records),
        "approved": counts["approved"],
        "held": counts["held"],
        "rejected": counts["rejected"],
        "escalated": counts["escalated"],
        "verdicts": verdicts,
    }
