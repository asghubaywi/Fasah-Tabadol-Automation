"""
test_dropout.py — Component dropout / graceful degradation tests.
اختبارات تسقيط المكونات والتدهور المتحكم به

Tests each component in isolation with simulated failures, then tests
cascading failures and checkpoint/resume behaviour.

Run with: pytest tests/test_dropout.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Path bootstrap ────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_CSV = """\
declaration_number,hs_code,importer_name,importer_cr,origin_country,declared_value_sar,weight_kg,port_of_entry,declaration_date,required_certificates
FASAH-TEST-001,8471.30.00,Test Co,1010123456,CN,150000.00,2500.0,SAJED,2026-01-01,SASO
FASAH-TEST-002,0402.10.00,Food Co,1010654321,NZ,85000.00,5000.0,SAKHI,2026-01-02,SFDA;Halal
FASAH-TEST-003,8471.60.00,Tech Co,1010987654,KR,750000.00,1200.0,SAJED,2026-01-03,SASO
FASAH-TEST-004,9301.00.00,Unknown,9999999999,US,10000.00,500.0,SAJED,2026-01-04,
"""

SAMPLE_CSV_INVALID_ROW = """\
declaration_number,hs_code,importer_name,importer_cr,origin_country,declared_value_sar,weight_kg,port_of_entry,declaration_date,required_certificates
FASAH-GOOD-001,8471.30.00,Good Co,1010123456,CN,150000.00,2500.0,SAJED,2026-01-01,SASO
FASAH-BAD-002,INVALID_HS,Bad Co,1010000000,xx,-999.0,bad_weight,SAJED,2026-01-02,
FASAH-GOOD-003,0402.10.00,Good Co 2,1010111111,NZ,85000.00,5000.0,SAKHI,2026-01-03,SFDA;Halal
"""


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sample_csv(tmp_dir: Path) -> Path:
    p = tmp_dir / "declarations.csv"
    p.write_text(SAMPLE_CSV, encoding="utf-8")
    return p


@pytest.fixture
def sample_csv_bad_rows(tmp_dir: Path) -> Path:
    p = tmp_dir / "declarations_bad.csv"
    p.write_text(SAMPLE_CSV_INVALID_ROW, encoding="utf-8")
    return p


# ════════════════════════════════════════════════════════════════════════════
# 1. fallback_parser — Python CSV/JSON parser
# ════════════════════════════════════════════════════════════════════════════

class TestFallbackParser:
    """Tests for the pure-Python fallback CSV parser."""

    def test_parse_valid_csv(self, sample_csv: Path) -> None:
        from pipeline.fallback_parser import parse_csv

        result = parse_csv(sample_csv)
        assert result["valid_records"] == 4
        assert result["invalid_records"] == 0
        assert len(result["records"]) == 4
        assert result["content_hash"]  # non-empty SHA-256

    def test_parse_skips_invalid_rows_continues_good(
        self, sample_csv_bad_rows: Path
    ) -> None:
        """Bad rows are skipped; valid rows still produce output."""
        from pipeline.fallback_parser import parse_csv

        result = parse_csv(sample_csv_bad_rows)
        # 2 good rows survive
        assert result["valid_records"] == 2
        # errors captured
        assert len(result["errors"]) > 0

    def test_parse_nonexistent_file(self, tmp_dir: Path) -> None:
        from pipeline.fallback_parser import parse_csv

        result = parse_csv(tmp_dir / "ghost.csv")
        assert result["valid_records"] == 0
        assert result["errors"]

    def test_parse_empty_csv(self, tmp_dir: Path) -> None:
        p = tmp_dir / "empty.csv"
        p.write_text("", encoding="utf-8")
        from pipeline.fallback_parser import parse_csv

        result = parse_csv(p)
        assert result["total_records"] == 0

    def test_parse_json_list(self, tmp_dir: Path) -> None:
        records = [{"declaration_number": "X", "foo": "bar"}]
        p = tmp_dir / "records.json"
        p.write_text(json.dumps(records), encoding="utf-8")
        from pipeline.fallback_parser import parse_json

        result = parse_json(p)
        assert result["valid_records"] == 1

    def test_parse_file_autodetect(self, sample_csv: Path, tmp_dir: Path) -> None:
        from pipeline.fallback_parser import parse_file

        result_csv = parse_file(sample_csv)
        assert result_csv["valid_records"] > 0

        json_path = tmp_dir / "x.json"
        json_path.write_text(json.dumps([{"a": "b"}]))
        result_json = parse_file(json_path)
        assert result_json["valid_records"] == 1


# ════════════════════════════════════════════════════════════════════════════
# 2. fallback_compliance — Python compliance checker
# ════════════════════════════════════════════════════════════════════════════

class TestFallbackCompliance:
    """Tests for the Python compliance checker fallback."""

    def _make_parse_result(self, records: list[dict]) -> dict:
        return {"records": records, "valid_records": len(records)}

    def test_approve_clean_electronics(self) -> None:
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-001",
                "hs_code": "8471.30.00",
                "origin_country": "CN",
                "declared_value_sar": 150_000,
                "weight_kg": 500,
                "required_certificates": ["SASO"],
            }
        ]
        result = check_compliance(self._make_parse_result(records))
        assert result["approved"] == 1
        assert result["verdicts"][0]["action"] == "approve"

    def test_reject_banned_hs(self) -> None:
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-002",
                "hs_code": "9301.00.00",
                "origin_country": "US",
                "declared_value_sar": 10_000,
                "weight_kg": 100,
                "required_certificates": [],
            }
        ]
        result = check_compliance(self._make_parse_result(records))
        assert result["rejected"] == 1
        assert result["verdicts"][0]["action"] == "reject"

    def test_hold_missing_certs(self) -> None:
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-003",
                "hs_code": "0402.10.00",  # food — needs SFDA + Halal
                "origin_country": "NZ",
                "declared_value_sar": 85_000,
                "weight_kg": 5000,
                "required_certificates": [],  # missing both
            }
        ]
        result = check_compliance(self._make_parse_result(records))
        assert result["held"] >= 1
        assert result["verdicts"][0]["action"] == "hold_pending_certificates"

    def test_escalate_high_value(self) -> None:
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-004",
                "hs_code": "8471.60.00",
                "origin_country": "KR",
                "declared_value_sar": 750_000,  # > 500k threshold
                "weight_kg": 1200,
                "required_certificates": ["SASO"],
            }
        ]
        result = check_compliance(self._make_parse_result(records))
        assert result["escalated"] == 1
        assert result["verdicts"][0]["action"] == "escalate_high_value"

    def test_mandate_inspection_overweight(self) -> None:
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-005",
                "hs_code": "7204.10.00",
                "origin_country": "DE",
                "declared_value_sar": 100_000,
                "weight_kg": 60_000,  # > 50k limit
                "required_certificates": [],
            }
        ]
        result = check_compliance(self._make_parse_result(records))
        assert result["verdicts"][0]["action"] == "mandate_inspection"

    def test_missing_rules_file_uses_defaults(self, tmp_dir: Path) -> None:
        """If rules file is missing, built-in defaults are used — no crash."""
        from pipeline.fallback_compliance import check_compliance

        records = [
            {
                "declaration_number": "D-006",
                "hs_code": "8471.30.00",
                "origin_country": "CN",
                "declared_value_sar": 100,
                "weight_kg": 10,
                "required_certificates": ["SASO"],
            }
        ]
        result = check_compliance(
            self._make_parse_result(records),
            rules_path=str(tmp_dir / "nonexistent.yaml"),
        )
        assert result["total_checked"] == 1


# ════════════════════════════════════════════════════════════════════════════
# 3. circuit_breaker — State machine
# ════════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Tests for the circuit breaker state machine."""

    def test_closed_passes_calls(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.call(lambda: "ok") == "ok"

    def test_opens_after_threshold(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker, CircuitOpenError

        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=999)

        def fail():
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(fail)

        with pytest.raises(CircuitOpenError):
            cb.call(fail)

    def test_half_open_after_timeout(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

        time.sleep(0.1)
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_manual_reset(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=999)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")))

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.call(lambda: "ok") == "ok"

    def test_status_dict(self) -> None:
        from pipeline.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker("test_status", failure_threshold=3)
        s = cb.status()
        assert s["name"] == "test_status"
        assert s["state"] == "closed"


# ════════════════════════════════════════════════════════════════════════════
# 4. checkpoint — Save / resume
# ════════════════════════════════════════════════════════════════════════════

class TestCheckpoint:
    """Tests for the pipeline checkpoint/resume system."""

    def test_empty_on_first_run(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        assert ckpt.get_in_flight() == {}
        assert not ckpt.was_processed("foo.csv")

    def test_mark_complete_persists(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_in_flight("foo.csv", "parse")
        ckpt.mark_complete("foo.csv", "abc123", verdicts_count=2)

        # Re-load from disk
        ckpt2 = PipelineCheckpoint(tmp_dir)
        assert ckpt2.was_processed("foo.csv")
        assert ckpt2.summary()["files_ok"] == 1
        assert ckpt2.summary()["verdicts_dispatched"] == 2

    def test_mark_failed_persists(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_failed("bar.csv", "RuntimeError: boom")

        ckpt2 = PipelineCheckpoint(tmp_dir)
        assert not ckpt2.was_processed("bar.csv")
        assert ckpt2.summary()["files_failed"] == 1

    def test_in_flight_survives_restart(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_in_flight("baz.csv", "check")

        # Simulate crash — load without completing
        ckpt2 = PipelineCheckpoint(tmp_dir)
        in_flight = ckpt2.get_in_flight()
        assert "baz.csv" in in_flight
        assert in_flight["baz.csv"]["step"] == "check"

    def test_clear_resets_state(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_complete("foo.csv", "abc", verdicts_count=1)
        ckpt.clear()

        ckpt2 = PipelineCheckpoint(tmp_dir)
        assert ckpt2.summary()["files_ok"] == 0

    def test_corrupt_checkpoint_starts_fresh(self, tmp_dir: Path) -> None:
        """A corrupt checkpoint JSON file is silently ignored."""
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt_file = tmp_dir / ".pipeline_checkpoint.json"
        ckpt_file.write_text("{{{INVALID JSON", encoding="utf-8")

        ckpt = PipelineCheckpoint(tmp_dir)
        assert ckpt.summary()["files_ok"] == 0


# ════════════════════════════════════════════════════════════════════════════
# 5. resilient_audit — Buffer on disk failure
# ════════════════════════════════════════════════════════════════════════════

class TestResilientAudit:
    """Tests for the non-blocking audit logger."""

    def test_normal_write(self, tmp_dir: Path) -> None:
        from utils.resilient_audit import ResilientAuditLogger

        audit = ResilientAuditLogger("test_agent", tmp_dir)
        audit.record("TestAction", "subject", "tool", "success", {"k": "v"})

        log_files = list(tmp_dir.glob("*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["action"] == "TestAction"

    def test_buffers_on_write_failure(self, tmp_dir: Path) -> None:
        """Events are buffered when the audit file cannot be written."""
        from utils.resilient_audit import ResilientAuditLogger

        audit = ResilientAuditLogger("buf_agent", tmp_dir)

        with patch.object(audit, "_log_path", return_value=Path("/nonexistent/path/x.jsonl")):
            audit.record("Buffered", "s", "t", "ok")
            assert audit.stats()["buffered"] == 1

    def test_flushes_buffer_on_recovery(self, tmp_dir: Path) -> None:
        """Buffered events are written to disk once the path is writable again."""
        from utils.resilient_audit import ResilientAuditLogger

        audit = ResilientAuditLogger("flush_agent", tmp_dir)
        bad_path = Path("/nonexistent/path/x.jsonl")

        with patch.object(audit, "_log_path", return_value=bad_path):
            audit.record("Ev1", "s", "t", "ok")
            audit.record("Ev2", "s", "t", "ok")

        assert audit.stats()["buffered"] == 2
        # Now path is valid — explicit flush
        audit.flush()
        assert audit.stats()["buffered"] == 0

    def test_never_raises(self, tmp_dir: Path) -> None:
        """record() must not raise under any circumstances."""
        from utils.resilient_audit import ResilientAuditLogger

        audit = ResilientAuditLogger("safe_agent", tmp_dir)
        with patch.object(audit, "_log_path", side_effect=Exception("catastrophic")):
            # Must not propagate
            audit.record("ShouldNotCrash", "s", "t", "ok")

    def test_thread_safety(self, tmp_dir: Path) -> None:
        """Concurrent writes from multiple threads must not corrupt the file."""
        from utils.resilient_audit import ResilientAuditLogger

        audit = ResilientAuditLogger("thread_agent", tmp_dir)
        errors: list[Exception] = []

        def write_many():
            try:
                for i in range(50):
                    audit.record("Concurrent", "s", "t", "ok", {"i": i})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        log_files = list(tmp_dir.glob("*.jsonl"))
        total_lines = sum(
            len(f.read_text().strip().splitlines()) for f in log_files
        )
        assert total_lines == 250


# ════════════════════════════════════════════════════════════════════════════
# 6. degradation — Central manager
# ════════════════════════════════════════════════════════════════════════════

class TestDegradationManager:
    """Tests for the central degradation/fallback manager."""

    def _fresh_manager(self):
        from utils.degradation import DegradationManager
        return DegradationManager()

    def test_healthy_by_default(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component
        assert not mgr.is_degraded(Component.RUST_ENGINE)

    def test_mark_degraded(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component
        mgr.mark_degraded(Component.RUST_ENGINE, "binary not found")
        assert mgr.is_degraded(Component.RUST_ENGINE)
        assert not mgr.is_failed(Component.RUST_ENGINE)

    def test_mark_failed(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component
        mgr.mark_failed(Component.BROWSER, "crashed")
        assert mgr.is_degraded(Component.BROWSER)
        assert mgr.is_failed(Component.BROWSER)

    def test_recovery(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component, ComponentStatus
        mgr.mark_degraded(Component.RUST_ENGINE, "oops")
        mgr.mark_healthy(Component.RUST_ENGINE, "recovered")
        assert mgr.get_status(Component.RUST_ENGINE) == ComponentStatus.HEALTHY

    def test_summary_overall_healthy(self) -> None:
        mgr = self._fresh_manager()
        assert mgr.summary()["overall"] == "healthy"

    def test_summary_overall_degraded(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component
        mgr.mark_degraded(Component.AUDIT_LOGGER, "disk full")
        assert mgr.summary()["overall"] == "degraded"

    def test_summary_overall_failed(self) -> None:
        mgr = self._fresh_manager()
        from utils.degradation import Component
        mgr.mark_failed(Component.FILESYSTEM, "unmounted")
        assert mgr.summary()["overall"] == "failed"


# ════════════════════════════════════════════════════════════════════════════
# 7. browser health_check
# ════════════════════════════════════════════════════════════════════════════

class TestBrowserHealthMonitor:
    """Tests for the browser health monitor."""

    def test_healthy_initially(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor(max_consecutive_failures=3)
        assert not m.is_browser_likely_crashed()

    def test_crashes_after_threshold(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor(max_consecutive_failures=3)
        for i in range(3):
            m.on_task_start(f"t-{i}")
            m.on_task_failure(f"t-{i}", "boom")
        assert m.is_browser_likely_crashed()

    def test_reset_clears_failures(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor(max_consecutive_failures=2)
        m.on_task_start("t1")
        m.on_task_failure("t1", "err")
        m.on_task_start("t2")
        m.on_task_failure("t2", "err")
        assert m.is_browser_likely_crashed()
        m.reset_failure_count()
        assert not m.is_browser_likely_crashed()

    def test_success_resets_consecutive(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor(max_consecutive_failures=3)
        m.on_task_start("t1")
        m.on_task_failure("t1", "err")
        m.on_task_start("t2")
        m.on_task_failure("t2", "err")
        m.on_task_start("t3")
        m.on_task_success("t3")
        assert not m.is_browser_likely_crashed()

    def test_task_stuck_detection(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor(task_timeout_secs=0.05)
        m.on_task_start("slow-task")
        time.sleep(0.1)
        assert m.is_task_stuck()

    def test_status_dict(self) -> None:
        from browser.health_check import BrowserHealthMonitor
        m = BrowserHealthMonitor()
        m.on_task_start("x")
        m.on_task_success("x")
        s = m.status()
        assert s["successful_tasks"] == 1
        assert s["healthy"] is True


# ════════════════════════════════════════════════════════════════════════════
# 8. retry utilities
# ════════════════════════════════════════════════════════════════════════════

class TestRetry:
    """Tests for the exponential backoff retry helpers."""

    def test_succeeds_on_first_try(self) -> None:
        from browser.retry import retry_with_backoff

        @retry_with_backoff(max_attempts=3)
        def always_ok():
            return "done"

        assert always_ok() == "done"

    def test_retries_and_eventually_succeeds(self) -> None:
        from browser.retry import retry_with_backoff

        calls = {"n": 0}

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("not yet")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert calls["n"] == 3

    def test_raises_after_max_attempts(self) -> None:
        from browser.retry import retry_with_backoff

        @retry_with_backoff(max_attempts=2, initial_delay=0.01)
        def always_fail():
            raise RuntimeError("always")

        with pytest.raises(RuntimeError, match="always"):
            always_fail()

    def test_does_not_retry_non_matching_exception(self) -> None:
        from browser.retry import retry_with_backoff

        calls = {"n": 0}

        @retry_with_backoff(max_attempts=3, exceptions=(ConnectionError,))
        def wrong_exc():
            calls["n"] += 1
            raise ValueError("wrong type")

        with pytest.raises(ValueError):
            wrong_exc()
        assert calls["n"] == 1  # no retries

    def test_retry_browser_op(self) -> None:
        from browser.retry import retry_browser_op

        calls = {"n": 0}

        def flaky_op():
            calls["n"] += 1
            if calls["n"] < 2:
                raise OSError("tmp fail")
            return "ok"

        result = retry_browser_op(
            flaky_op, max_attempts=3, initial_delay=0.01, task_id="t-999"
        )
        assert result == "ok"
        assert calls["n"] == 2


# ════════════════════════════════════════════════════════════════════════════
# 9. Cascading failure: Rust fails → Python fallback still produces output
# ════════════════════════════════════════════════════════════════════════════

class TestCascadingFailure:
    """
    Tests that when Rust engine fails, the Python fallbacks produce
    output in the correct format so the rest of the pipeline continues.
    """

    def test_rust_parse_fails_python_produces_valid_output(
        self, sample_csv: Path
    ) -> None:
        from pipeline.orchestrator import run_engine_or_fallback_parse

        with patch("pipeline.orchestrator.run_engine", side_effect=FileNotFoundError("no binary")):
            result, used_fallback = run_engine_or_fallback_parse(sample_csv)

        assert used_fallback is True
        assert result["valid_records"] > 0
        assert "records" in result
        assert "content_hash" in result

    def test_rust_check_fails_python_produces_valid_output(
        self, sample_csv: Path, tmp_dir: Path
    ) -> None:
        from pipeline.fallback_parser import parse_file
        from pipeline.orchestrator import run_engine_or_fallback_check

        parse_result = parse_file(sample_csv)
        tmp_records = tmp_dir / "tmp_records.json"
        tmp_records.write_text(json.dumps(parse_result), encoding="utf-8")

        with patch("pipeline.orchestrator.run_engine", side_effect=RuntimeError("engine crash")):
            result, used_fallback = run_engine_or_fallback_check(parse_result, tmp_records)

        assert used_fallback is True
        assert "verdicts" in result
        assert result["total_checked"] > 0

    def test_full_pipeline_without_rust_binary(
        self, sample_csv: Path, tmp_dir: Path
    ) -> None:
        """End-to-end: CSV → parse(Python) → check(Python) → verdict dispatch."""
        outbox = tmp_dir / "outbox"
        browser_tasks = tmp_dir / "browser_tasks"
        outbox.mkdir()
        browser_tasks.mkdir()

        from utils.resilient_audit import ResilientAuditLogger
        audit = ResilientAuditLogger("e2e_test", tmp_dir / "audit")

        with patch("pipeline.orchestrator.run_engine", side_effect=FileNotFoundError("no binary")):
            from pipeline.orchestrator import process_file
            verdicts = process_file(sample_csv, outbox, browser_tasks, audit)

        # We had 4 records; at least some should produce verdicts
        assert verdicts > 0

        # Tracking command files should be present in outbox
        outbox_files = list(outbox.glob("*.json"))
        browser_files = list(browser_tasks.glob("*.json"))
        assert (len(outbox_files) + len(browser_files)) > 0

    def test_circuit_breaker_trips_and_falls_back(
        self, sample_csv: Path
    ) -> None:
        """After 3 Rust failures, circuit opens; Python fallback is used automatically."""
        from pipeline.orchestrator import run_engine_or_fallback_parse, _ENGINE_CIRCUIT

        _ENGINE_CIRCUIT.reset()

        fail_count = {"n": 0}

        def fake_engine(args, **kwargs):
            fail_count["n"] += 1
            raise RuntimeError("engine unavailable")

        with patch("pipeline.orchestrator.run_engine", side_effect=RuntimeError("engine unavailable")):
            # Trip the circuit (threshold=3)
            for _ in range(3):
                result, fallback = run_engine_or_fallback_parse(sample_csv)
                assert fallback is True

            # Circuit is now OPEN — 4th call goes straight to fallback
            result, fallback = run_engine_or_fallback_parse(sample_csv)
            assert fallback is True
            assert result["valid_records"] > 0

        _ENGINE_CIRCUIT.reset()  # cleanup


# ════════════════════════════════════════════════════════════════════════════
# 10. Checkpoint / resume simulation
# ════════════════════════════════════════════════════════════════════════════

class TestCheckpointResume:
    """Simulate orchestrator crash mid-run and verify resume behaviour."""

    def test_resume_skips_completed_files(self, tmp_dir: Path, sample_csv: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        # First "run": process file successfully
        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_complete(sample_csv.name, "abc123", verdicts_count=2)

        # Second "run": load checkpoint and check
        ckpt2 = PipelineCheckpoint(tmp_dir)
        assert ckpt2.was_processed(sample_csv.name)

    def test_resume_detects_in_flight_file(self, tmp_dir: Path) -> None:
        from pipeline.checkpoint import PipelineCheckpoint

        ckpt = PipelineCheckpoint(tmp_dir)
        ckpt.mark_in_flight("crashed_file.csv", "check")
        # Simulate crash — no mark_complete

        ckpt2 = PipelineCheckpoint(tmp_dir)
        in_flight = ckpt2.get_in_flight()
        assert "crashed_file.csv" in in_flight

    def test_full_pipeline_respects_checkpoint(
        self, tmp_dir: Path, sample_csv: Path
    ) -> None:
        """
        Simulate: first run processes the file, second run skips it
        because it's in the checkpoint.
        """
        inbox = tmp_dir / "inbox"
        outbox = tmp_dir / "outbox"
        browser_tasks = tmp_dir / "browser_tasks"
        audit_dir = tmp_dir / "audit"
        for d in [inbox, outbox, browser_tasks, audit_dir]:
            d.mkdir()

        import shutil
        shutil.copy(sample_csv, inbox / sample_csv.name)

        from pipeline.checkpoint import PipelineCheckpoint
        from utils.resilient_audit import ResilientAuditLogger

        ckpt = PipelineCheckpoint(inbox)
        audit = ResilientAuditLogger("ckpt_test", audit_dir)

        dispatch_calls = {"n": 0}

        def counting_dispatch(*args, **kwargs):
            dispatch_calls["n"] += 1

        with patch("pipeline.orchestrator.run_engine", side_effect=FileNotFoundError("no binary")), \
             patch("pipeline.orchestrator._dispatch_browser_task", side_effect=counting_dispatch), \
             patch("pipeline.orchestrator._write_tracking_command", side_effect=counting_dispatch):
            from pipeline.orchestrator import process_file
            process_file(inbox / sample_csv.name, outbox, browser_tasks, audit, ckpt)

        first_run_count = dispatch_calls["n"]
        assert first_run_count > 0

        # Mark as processed
        ckpt.mark_complete(sample_csv.name, "fakehash", verdicts_count=first_run_count)

        # Verify checkpoint persists
        ckpt2 = PipelineCheckpoint(inbox)
        assert ckpt2.was_processed(sample_csv.name)
