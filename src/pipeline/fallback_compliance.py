"""
fallback_compliance.py — Pure Python compliance checker fallback.
مدقق الامتثال الاحتياطي — يُستخدم عند فشل محرك Rust

Implements the same priority-ordered rules as ``fasah-engine check`` and
returns a ComplianceResult-compatible dict so the rest of the pipeline
continues without the Rust binary.

Priority order (mirrors compliance.rs):
    1  Sanctioned country → reject_sanctioned  (risk 100)
    2  Banned HS prefix   → reject             (risk 95)
    3  Missing certs      → hold_pending_certs (risk 70)
    4  High value         → escalate_high_value(risk 80)
    5  Overweight         → mandate_inspection  (risk 60)
    *  Otherwise          → approve             (risk 0)
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
    """
    decl_num = record.get("declaration_number", "UNKNOWN")
    hs_raw = str(record.get("hs_code", "")).strip()
    hs = hs_raw.replace(".", "")  # normalise 8471.30.00 → 847130
    origin = str(record.get("origin_country", "")).strip().upper()
    declared_value = float(record.get("declared_value_sar", 0) or 0)
    weight = float(record.get("weight_kg", 0) or 0)
    certs = [c.strip().upper() for c in record.get("required_certificates", [])]

    # ── Priority 1: Sanctioned country ───────────────────────────────────────
    sanctioned = [c.strip().upper() for c in rules.get("sanctioned_countries", [])]
    if origin in sanctioned:
        return {
            "declaration_number": decl_num,
            "action": "reject_sanctioned",
            "risk_score": 100,
            "reasons": [f"Origin country '{origin}' is sanctioned"],
        }

    # ── Priority 2: Banned HS prefix ─────────────────────────────────────────
    for prefix in rules.get("banned_hs_prefixes", []):
        if hs.startswith(str(prefix)):
            return {
                "declaration_number": decl_num,
                "action": "reject",
                "risk_score": 95,
                "reasons": [f"HS code '{hs_raw}' matches banned prefix '{prefix}'"],
            }

    # ── Priority 3: Missing certificates ─────────────────────────────────────
    cert_requirements: dict[str, list[str]] = rules.get("certificate_requirements", {})
    required: list[str] = []
    # Check 4-digit heading first, then 2-digit chapter
    for prefix_len in (4, 2):
        prefix = hs[:prefix_len]
        if prefix in cert_requirements:
            required = [c.strip().upper() for c in cert_requirements[prefix]]
            break

    if required:
        missing = [c for c in required if c not in certs]
        if missing:
            return {
                "declaration_number": decl_num,
                "action": "hold_pending_certificates",
                "risk_score": 70,
                "reasons": [f"Missing required certificates: {', '.join(missing)}"],
            }

    # ── Priority 4: High value ────────────────────────────────────────────────
    threshold = float(rules.get("high_value_threshold_sar", 500_000.0))
    if declared_value > threshold:
        return {
            "declaration_number": decl_num,
            "action": "escalate_high_value",
            "risk_score": 80,
            "reasons": [
                f"Declared value {declared_value:,.2f} SAR exceeds threshold "
                f"{threshold:,.2f} SAR"
            ],
        }

    # ── Priority 5: Overweight ────────────────────────────────────────────────
    max_weight = float(rules.get("max_weight_kg", 50_000.0))
    if weight > max_weight:
        return {
            "declaration_number": decl_num,
            "action": "mandate_inspection",
            "risk_score": 60,
            "reasons": [
                f"Weight {weight:,.2f} kg exceeds limit {max_weight:,.2f} kg"
            ],
        }

    # ── All clear ─────────────────────────────────────────────────────────────
    return {
        "declaration_number": decl_num,
        "action": "approve",
        "risk_score": 0,
        "reasons": [],
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

    for record in records:
        verdict = _check_record(record, rules)
        verdicts.append(verdict)
        action = verdict["action"]

        if action in ("approve", "approve_with_conditions"):
            counts["approved"] += 1
        elif action in ("hold_pending_certificates", "mandate_inspection"):
            counts["held"] += 1
        elif action in ("reject", "reject_sanctioned"):
            counts["rejected"] += 1
        elif action == "escalate_high_value":
            counts["escalated"] += 1
            counts["held"] += 1  # escalated also counts as held

    return {
        "total_checked": len(records),
        "approved": counts["approved"],
        "held": counts["held"],
        "rejected": counts["rejected"],
        "escalated": counts["escalated"],
        "verdicts": verdicts,
    }
