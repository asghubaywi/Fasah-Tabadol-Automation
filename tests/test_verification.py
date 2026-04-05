"""
test_verification.py — Stage 5 verification layer tests.
اختبارات المرحلة الخامسة: طبقة التحقق بعد التنفيذ

Tests the comparison logic between pipeline compliance decisions and
actual Fasah portal outcomes. Covers matches, mismatches (critical + warning),
inconclusive results, report generation, and orchestrator integration.

Run with: pytest tests/test_verification.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Path bootstrap ────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from pipeline.verification import (
    MismatchSeverity,
    VerificationEngine,
    VerificationRecord,
    VerificationStatus,
    _normalise_portal_status,
)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: status normalisation
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalisePortalStatus:
    def test_approved_english(self) -> None:
        assert _normalise_portal_status("Approved - Released") == "approved"

    def test_approved_arabic(self) -> None:
        assert _normalise_portal_status("مقبول") == "approved"
        assert _normalise_portal_status("مفسوح - تمت الموافقة") == "approved"

    def test_rejected_english(self) -> None:
        assert _normalise_portal_status("Rejected") == "rejected"
        assert _normalise_portal_status("Denied by customs") == "rejected"

    def test_rejected_arabic(self) -> None:
        assert _normalise_portal_status("مرفوض") == "rejected"

    def test_held_english(self) -> None:
        assert _normalise_portal_status("Under Review - Pending") == "held"
        assert _normalise_portal_status("Hold for documents") == "held"

    def test_held_arabic(self) -> None:
        assert _normalise_portal_status("معلق") == "held"
        assert _normalise_portal_status("قيد المراجعة") == "held"

    def test_unknown_status(self) -> None:
        assert _normalise_portal_status("some random text") is None

    def test_none_input(self) -> None:
        assert _normalise_portal_status(None) is None

    def test_empty_string(self) -> None:
        assert _normalise_portal_status("") is None


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: VerificationRecord creation
# ══════════════════════════════════════════════════════════════════════════════


class TestVerificationRecord:
    def test_match_approve_vs_approved(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-001",
            pipeline_action="approve",
            expected_status="approved",
            portal_status="Approved - Released",
        )
        assert rec.status == VerificationStatus.MATCH
        assert rec.severity == MismatchSeverity.INFO

    def test_match_reject_vs_rejected(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-002",
            pipeline_action="reject",
            expected_status="rejected",
            portal_status="مرفوض",
        )
        assert rec.status == VerificationStatus.MATCH

    def test_match_hold_vs_held(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-003",
            pipeline_action="hold_pending_certificates",
            expected_status="held",
            portal_status="Under Review - Pending documents",
        )
        assert rec.status == VerificationStatus.MATCH

    def test_critical_mismatch_rejected_but_approved(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-004",
            pipeline_action="reject",
            expected_status="rejected",
            portal_status="Approved",
        )
        assert rec.status == VerificationStatus.MISMATCH
        assert rec.severity == MismatchSeverity.CRITICAL
        assert "CRITICAL" in rec.reason

    def test_critical_mismatch_approved_but_rejected(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-005",
            pipeline_action="approve",
            expected_status="approved",
            portal_status="Rejected",
        )
        assert rec.status == VerificationStatus.MISMATCH
        assert rec.severity == MismatchSeverity.CRITICAL

    def test_warning_mismatch_held_but_approved(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-006",
            pipeline_action="hold_pending_certificates",
            expected_status="held",
            portal_status="Approved",
        )
        assert rec.status == VerificationStatus.MISMATCH
        assert rec.severity == MismatchSeverity.WARNING

    def test_inconclusive_no_portal_status(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-007",
            pipeline_action="approve",
            expected_status="approved",
            portal_status=None,
        )
        assert rec.status == VerificationStatus.INCONCLUSIVE

    def test_inconclusive_unrecognised_status(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-008",
            pipeline_action="approve",
            expected_status="approved",
            portal_status="بيانات غير معروفة",
        )
        assert rec.status == VerificationStatus.INCONCLUSIVE
        assert rec.severity == MismatchSeverity.WARNING

    def test_to_dict_has_all_fields(self) -> None:
        rec = VerificationRecord(
            declaration_number="FASAH-009",
            pipeline_action="approve",
            expected_status="approved",
            portal_status="Approved",
            task_id="fasah-FASAH-009-20260405_120000",
            risk_score=42,
        )
        d = rec.to_dict()
        assert d["declaration_number"] == "FASAH-009"
        assert d["verification_status"] == "match"
        assert d["risk_score"] == 42
        assert d["task_id"] == "fasah-FASAH-009-20260405_120000"
        assert "timestamp" in d


# ══════════════════════════════════════════════════════════════════════════════
# VerificationEngine tests
# ══════════════════════════════════════════════════════════════════════════════


class TestVerificationEngine:
    def test_verify_returns_record(self) -> None:
        engine = VerificationEngine()
        rec = engine.verify("FASAH-001", "approve", "Approved")
        assert rec.status == VerificationStatus.MATCH

    def test_accumulates_records(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "approve", "Approved")
        engine.verify("FASAH-002", "reject", "Rejected")
        assert len(engine.records) == 2

    def test_report_all_match(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "approve", "Approved - Released")
        engine.verify("FASAH-002", "reject", "مرفوض")
        report = engine.generate_report()
        assert report["verification_status"] == "PASSED"
        assert report["summary"]["matches"] == 2
        assert report["summary"]["mismatches"] == 0

    def test_report_critical_mismatch(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "reject", "Approved")
        report = engine.generate_report()
        assert report["verification_status"] == "FAILED"
        assert report["summary"]["critical_mismatches"] == 1
        assert engine.has_critical_mismatches

    def test_report_warning_only(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "hold_pending_certificates", "Approved")
        report = engine.generate_report()
        assert report["verification_status"] == "PASSED_WITH_WARNINGS"
        assert report["summary"]["warnings"] == 1
        assert not engine.has_critical_mismatches

    def test_report_inconclusive(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "approve", None)
        report = engine.generate_report()
        assert report["verification_status"] == "INCONCLUSIVE"

    def test_report_empty(self) -> None:
        engine = VerificationEngine()
        report = engine.generate_report()
        assert report["verification_status"] == "no_data"

    def test_verify_result_action_dict(self) -> None:
        engine = VerificationEngine()
        result_action = {
            "task_id": "fasah-FASAH-001-20260405",
            "declaration_number": "FASAH-001",
            "actual_portal_status": "Approved - Released",
            "predicted_action": "escalate",
            "risk_score": 70,
        }
        rec = engine.verify_result_action(result_action)
        # escalate → expected "held", portal says "approved" → mismatch (warning)
        assert rec.status == VerificationStatus.MISMATCH

    def test_audit_called_on_mismatch(self) -> None:
        audit = MagicMock()
        engine = VerificationEngine(audit=audit)
        engine.verify("FASAH-001", "reject", "Approved")
        audit.record.assert_called_once()
        call_args = audit.record.call_args
        assert call_args[0][0] == "VerificationMismatch"
        assert call_args[1]["risk_level"] == "high"

    def test_audit_not_called_on_match(self) -> None:
        audit = MagicMock()
        engine = VerificationEngine(audit=audit)
        engine.verify("FASAH-001", "approve", "Approved")
        audit.record.assert_not_called()

    def test_save_report(self, tmp_path: Path) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "approve", "Approved")
        engine.verify("FASAH-002", "reject", "Approved")
        path = engine.save_report(tmp_path)
        assert path.exists()
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["verification_status"] == "FAILED"
        assert len(report["all_records"]) == 2

    def test_mixed_results(self) -> None:
        engine = VerificationEngine()
        engine.verify("FASAH-001", "approve", "Approved")           # match
        engine.verify("FASAH-002", "reject", "Approved")            # critical
        engine.verify("FASAH-003", "hold_pending_certificates", None)  # inconclusive
        engine.verify("FASAH-004", "escalate_high_value", "Under Review")  # match
        report = engine.generate_report()
        assert report["verification_status"] == "FAILED"  # critical takes precedence
        assert report["summary"]["total_verified"] == 4
        assert report["summary"]["matches"] == 2
        assert report["summary"]["critical_mismatches"] == 1
        assert report["summary"]["inconclusive"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator integration helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorHelpers:
    def test_extract_decl_from_task_id(self) -> None:
        from pipeline.orchestrator import _extract_decl_from_task_id

        assert _extract_decl_from_task_id(
            "fasah-FASAH-2026-00002-20260318_120000_123"
        ) == "FASAH-2026-00002"

    def test_extract_decl_unknown(self) -> None:
        from pipeline.orchestrator import _extract_decl_from_task_id

        assert _extract_decl_from_task_id("random-id") == "UNKNOWN"

    def test_infer_action_no_file(self, tmp_path: Path) -> None:
        from pipeline.orchestrator import _infer_action_from_task_id

        result = _infer_action_from_task_id("some-task", tmp_path)
        assert result == ""

    def test_infer_action_from_pending(self, tmp_path: Path) -> None:
        from pipeline.orchestrator import _infer_action_from_task_id

        browser_tasks = tmp_path / "browser_tasks"
        browser_tasks.mkdir()
        pending = {
            "fasah-FASAH-001-20260405": {
                "predicted_outcome": "hold",
                "declaration_number": "FASAH-001",
            }
        }
        (browser_tasks / ".pending_tasks.json").write_text(
            json.dumps(pending), encoding="utf-8"
        )
        result = _infer_action_from_task_id("fasah-FASAH-001-20260405", tmp_path)
        assert result == "hold"


# ══════════════════════════════════════════════════════════════════════════════
# End-to-end: _verify_browser_results
# ══════════════════════════════════════════════════════════════════════════════


class TestVerifyBrowserResults:
    def test_verify_found_bundle_match(self, tmp_path: Path) -> None:
        """FOUND bundle with matching status → verification passes."""
        from pipeline.orchestrator import _verify_browser_results

        outbox = tmp_path / "outbox"
        results_dir = outbox / "browser_results"
        task_dir = results_dir / "fasah-FASAH-001-20260405_120000_000"
        task_dir.mkdir(parents=True)

        bundle = {
            "task_id": "fasah-FASAH-001-20260405_120000_000",
            "status": "FOUND",
            "current_status": "معلق - قيد المراجعة",
        }
        (task_dir / "bundle.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        # Write pending_tasks so action can be inferred
        browser_tasks = outbox / "browser_tasks"
        browser_tasks.mkdir(parents=True)
        pending = {
            "fasah-FASAH-001-20260405_120000_000": {
                "predicted_outcome": "hold",
                "declaration_number": "FASAH-001",
            }
        }
        (browser_tasks / ".pending_tasks.json").write_text(
            json.dumps(pending), encoding="utf-8"
        )

        audit = MagicMock()
        _verify_browser_results(results_dir, outbox, audit)

        # Should have created a verified marker
        marker = results_dir / ".verified" / "fasah-FASAH-001-20260405_120000_000.verified"
        assert marker.exists()

    def test_verify_found_bundle_mismatch(self, tmp_path: Path) -> None:
        """FOUND bundle with mismatching status → generates report."""
        from pipeline.orchestrator import _verify_browser_results

        outbox = tmp_path / "outbox"
        results_dir = outbox / "browser_results"
        task_dir = results_dir / "fasah-FASAH-002-20260405_120000_000"
        task_dir.mkdir(parents=True)

        # Pipeline said "hold" but portal says "Approved"
        bundle = {
            "task_id": "fasah-FASAH-002-20260405_120000_000",
            "status": "FOUND",
            "current_status": "Approved - Released",
        }
        (task_dir / "bundle.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        browser_tasks = outbox / "browser_tasks"
        browser_tasks.mkdir(parents=True)
        pending = {
            "fasah-FASAH-002-20260405_120000_000": {
                "predicted_outcome": "hold",
                "declaration_number": "FASAH-002",
            }
        }
        (browser_tasks / ".pending_tasks.json").write_text(
            json.dumps(pending), encoding="utf-8"
        )

        audit = MagicMock()
        _verify_browser_results(results_dir, outbox, audit)

        # Should have created a verification report
        reports_dir = outbox / "verification_reports"
        assert reports_dir.exists()
        report_files = list(reports_dir.glob("verification_report_*.json"))
        assert len(report_files) == 1

        report = json.loads(report_files[0].read_text(encoding="utf-8"))
        assert report["summary"]["mismatches"] > 0

        # Audit should have been called
        audit.record.assert_called()

    def test_skip_non_found_bundle(self, tmp_path: Path) -> None:
        """Non-FOUND bundles are marked as verified but not compared."""
        from pipeline.orchestrator import _verify_browser_results

        outbox = tmp_path / "outbox"
        results_dir = outbox / "browser_results"
        task_dir = results_dir / "fasah-FASAH-003-20260405_120000_000"
        task_dir.mkdir(parents=True)

        bundle = {
            "task_id": "fasah-FASAH-003-20260405_120000_000",
            "status": "TRANSIENT_FAIL",
        }
        (task_dir / "bundle.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        audit = MagicMock()
        _verify_browser_results(results_dir, outbox, audit)

        marker = results_dir / ".verified" / "fasah-FASAH-003-20260405_120000_000.verified"
        assert marker.exists()
        assert marker.read_text() == "TRANSIENT_FAIL"

    def test_idempotent_no_double_verify(self, tmp_path: Path) -> None:
        """Running verification twice on the same bundle only verifies once."""
        from pipeline.orchestrator import _verify_browser_results

        outbox = tmp_path / "outbox"
        results_dir = outbox / "browser_results"
        task_dir = results_dir / "fasah-FASAH-004-20260405_120000_000"
        task_dir.mkdir(parents=True)

        bundle = {
            "task_id": "fasah-FASAH-004-20260405_120000_000",
            "status": "FOUND",
            "current_status": "Approved",
        }
        (task_dir / "bundle.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )

        audit = MagicMock()
        _verify_browser_results(results_dir, outbox, audit)
        _verify_browser_results(results_dir, outbox, audit)

        # Second run should not produce a second report
        reports_dir = outbox / "verification_reports"
        if reports_dir.exists():
            report_files = list(reports_dir.glob("verification_report_*.json"))
            assert len(report_files) <= 1

    def test_empty_results_dir(self, tmp_path: Path) -> None:
        """No browser results → no-op."""
        from pipeline.orchestrator import _verify_browser_results

        audit = MagicMock()
        _verify_browser_results(tmp_path / "nonexistent", tmp_path, audit)
        audit.record.assert_not_called()
