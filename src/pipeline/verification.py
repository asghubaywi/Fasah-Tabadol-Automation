"""
verification.py — Stage 5: Post-Execution Verification Layer
المرحلة الخامسة: طبقة التحقق بعد التنفيذ

Compares pipeline compliance decisions against actual Fasah portal outcomes
reported by the browser worker. Detects mismatches, generates alerts, and
produces a unified verification report.

Why this matters:
  - UI selectors may break silently (portal redesign)
  - Browser worker may extract wrong status text
  - Compliance rules may diverge from actual portal enforcement
  - Without verification, errors propagate undetected

Usage:
    from pipeline.verification import VerificationEngine
    engine = VerificationEngine(audit)
    result = engine.verify(decision, portal_outcome)
    report = engine.generate_report()
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("fasah.verification")


# ── Verification Status ──────────────────────────────────────────────────────

class VerificationStatus(str, Enum):
    """Outcome of comparing a pipeline decision against Fasah portal reality."""
    MATCH = "match"
    MISMATCH = "mismatch"
    INCONCLUSIVE = "inconclusive"  # portal status unreadable or unknown


class MismatchSeverity(str, Enum):
    """How critical the gap between decision and reality is."""
    CRITICAL = "critical"   # rejected by us but approved in Fasah, or vice versa
    WARNING = "warning"     # held vs approved, or minor status divergence
    INFO = "info"           # status wording differs but intent matches


# ── Data Structures ──────────────────────────────────────────────────────────

class VerificationRecord:
    """One decision ↔ portal comparison."""

    __slots__ = (
        "declaration_number", "pipeline_action", "expected_status",
        "portal_status", "status", "severity", "reason", "timestamp",
        "risk_score", "task_id",
    )

    def __init__(
        self,
        declaration_number: str,
        pipeline_action: str,
        expected_status: str,
        portal_status: str | None,
        task_id: str = "",
        risk_score: int = 0,
    ) -> None:
        self.declaration_number = declaration_number
        self.pipeline_action = pipeline_action
        self.expected_status = expected_status
        self.portal_status = portal_status
        self.task_id = task_id
        self.risk_score = risk_score
        self.timestamp = datetime.now(timezone.utc).isoformat()

        # Compute match
        self.status, self.severity, self.reason = _compare(
            pipeline_action, expected_status, portal_status
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration_number": self.declaration_number,
            "pipeline_action": self.pipeline_action,
            "expected_status": self.expected_status,
            "portal_status": self.portal_status,
            "verification_status": self.status.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "risk_score": self.risk_score,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
        }


# ── Comparison Logic ─────────────────────────────────────────────────────────

# Maps pipeline compliance action → expected portal status family
_ACTION_TO_EXPECTED: dict[str, str] = {
    "approve": "approved",
    "approve_with_conditions": "approved",
    "reject": "rejected",
    "reject_sanctioned": "rejected",
    "hold_pending_certificates": "held",
    "escalate_high_value": "held",
    "mandate_inspection": "held",
}

# Keywords that indicate a given status family (Arabic + English)
_STATUS_KEYWORDS: dict[str, list[str]] = {
    "approved": [
        "approved", "released", "cleared", "accepted",
        "مقبول", "موافق", "مفسوح", "تمت الموافقة",
    ],
    "rejected": [
        "rejected", "denied", "refused", "cancelled",
        "مرفوض", "مرفوضة", "ملغي",
    ],
    "held": [
        "hold", "pending", "review", "under review", "awaiting",
        "معلق", "قيد المراجعة", "بانتظار", "تحت المراجعة",
    ],
}


def _normalise_portal_status(portal_status: str | None) -> str | None:
    """Map raw portal status text to a status family (approved/rejected/held)."""
    if not portal_status:
        return None

    lower = portal_status.lower().strip()
    for family, keywords in _STATUS_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return family
    return None


def _compare(
    pipeline_action: str,
    expected_status: str,
    portal_status: str | None,
) -> tuple[VerificationStatus, MismatchSeverity, str]:
    """
    Compare pipeline decision against portal reality.

    مقارنة قرار خط الأنابيب مع الواقع في بوابة فسح.

    Returns (status, severity, reason).
    """
    if not portal_status:
        return (
            VerificationStatus.INCONCLUSIVE,
            MismatchSeverity.INFO,
            "Portal status not available or unreadable",
        )

    normalised = _normalise_portal_status(portal_status)
    if normalised is None:
        return (
            VerificationStatus.INCONCLUSIVE,
            MismatchSeverity.WARNING,
            f"Portal status '{portal_status}' could not be mapped to a known family",
        )

    if normalised == expected_status:
        return (
            VerificationStatus.MATCH,
            MismatchSeverity.INFO,
            f"Pipeline expected '{expected_status}', portal shows '{portal_status}' → match",
        )

    # ── Mismatch detected ────────────────────────────────────────────────
    # Critical: opposite outcomes
    critical_pairs = {
        ("approved", "rejected"),
        ("rejected", "approved"),
    }
    if (expected_status, normalised) in critical_pairs:
        return (
            VerificationStatus.MISMATCH,
            MismatchSeverity.CRITICAL,
            f"CRITICAL: Pipeline decided '{pipeline_action}' (expected '{expected_status}') "
            f"but Fasah portal shows '{portal_status}' (normalised: '{normalised}')",
        )

    # Warning: significant divergence
    return (
        VerificationStatus.MISMATCH,
        MismatchSeverity.WARNING,
        f"Pipeline decided '{pipeline_action}' (expected '{expected_status}') "
        f"but Fasah portal shows '{portal_status}' (normalised: '{normalised}')",
    )


# ── Verification Engine ──────────────────────────────────────────────────────

class VerificationEngine:
    """
    Accumulates verification records and generates reports.

    محرك التحقق: يجمع سجلات التحقق ويولد التقارير.
    """

    def __init__(self, audit: Any = None) -> None:
        self._records: list[VerificationRecord] = []
        self._audit = audit

    def verify(
        self,
        declaration_number: str,
        pipeline_action: str,
        portal_status: str | None,
        task_id: str = "",
        risk_score: int = 0,
    ) -> VerificationRecord:
        """
        Verify a single declaration: compare pipeline decision vs portal outcome.

        تحقق من إعلان واحد: قارن قرار خط الأنابيب مع نتيجة البوابة.
        """
        expected = _ACTION_TO_EXPECTED.get(pipeline_action, "unknown")
        record = VerificationRecord(
            declaration_number=declaration_number,
            pipeline_action=pipeline_action,
            expected_status=expected,
            portal_status=portal_status,
            task_id=task_id,
            risk_score=risk_score,
        )
        self._records.append(record)

        # Log + audit
        if record.status == VerificationStatus.MISMATCH:
            log.warning(
                "[VERIFICATION MISMATCH] %s: %s (severity=%s)",
                declaration_number, record.reason, record.severity.value,
            )
            if self._audit:
                self._audit.record(
                    "VerificationMismatch",
                    "agent_fasah",
                    "verification",
                    "mismatch",
                    record.to_dict(),
                    risk_level="high" if record.severity == MismatchSeverity.CRITICAL else "medium",
                )
        elif record.status == VerificationStatus.MATCH:
            log.info("[VERIFICATION OK] %s: %s", declaration_number, record.reason)
        else:
            log.info(
                "[VERIFICATION INCONCLUSIVE] %s: %s", declaration_number, record.reason,
            )

        return record

    def verify_result_action(self, result_action: dict[str, Any]) -> VerificationRecord:
        """
        Verify from a ResultAction dict (output of fasah-engine watch / result_watcher).

        تحقق من ResultAction (ناتج fasah-engine watch).
        """
        return self.verify(
            declaration_number=result_action.get("declaration_number", "UNKNOWN"),
            pipeline_action=result_action.get("predicted_action", ""),
            portal_status=result_action.get("actual_portal_status"),
            task_id=result_action.get("task_id", ""),
            risk_score=result_action.get("risk_score") or 0,
        )

    def generate_report(self) -> dict[str, Any]:
        """
        Generate a unified verification report for all checked declarations.

        إنشاء تقرير تحقق موحد لجميع الإعلانات التي تم فحصها.
        """
        total = len(self._records)
        matches = [r for r in self._records if r.status == VerificationStatus.MATCH]
        mismatches = [r for r in self._records if r.status == VerificationStatus.MISMATCH]
        inconclusive = [r for r in self._records if r.status == VerificationStatus.INCONCLUSIVE]

        critical = [r for r in mismatches if r.severity == MismatchSeverity.CRITICAL]
        warnings = [r for r in mismatches if r.severity == MismatchSeverity.WARNING]

        if total == 0:
            overall = "no_data"
        elif critical:
            overall = "FAILED"
        elif warnings:
            overall = "PASSED_WITH_WARNINGS"
        elif inconclusive and not matches:
            overall = "INCONCLUSIVE"
        else:
            overall = "PASSED"

        return {
            "verification_status": overall,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_verified": total,
                "matches": len(matches),
                "mismatches": len(mismatches),
                "inconclusive": len(inconclusive),
                "critical_mismatches": len(critical),
                "warnings": len(warnings),
            },
            "mismatches": [r.to_dict() for r in mismatches],
            "all_records": [r.to_dict() for r in self._records],
        }

    def save_report(self, output_dir: Path) -> Path:
        """
        Write report JSON to output_dir.

        كتابة تقرير JSON إلى مجلد الإخراج.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"verification_report_{ts}.json"
        report = self.generate_report()
        path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("Verification report saved: %s", path)
        return path

    @property
    def has_critical_mismatches(self) -> bool:
        return any(
            r.status == VerificationStatus.MISMATCH
            and r.severity == MismatchSeverity.CRITICAL
            for r in self._records
        )

    @property
    def records(self) -> list[VerificationRecord]:
        return list(self._records)
