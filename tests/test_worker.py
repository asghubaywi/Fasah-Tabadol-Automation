"""
test_worker.py — Unit tests for the browser worker's security gates & helpers.
اختبارات بوابات الأمان في عامل المتصفح

Covers the pure/guardable logic of worker.py without launching a real browser
(Playwright is imported lazily inside run_playwright_search, so importing the
module here needs no Chromium): domain allowlist (Gate 11), out_dir
sanitisation (path-traversal defence), prod fail-closed (Gate 10), output
limits (Gate 9), and playbook alias resolution.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# Redirect the worker's module-level directory creation into a temp dir BEFORE
# importing it, so importing the module never writes logs/state into the repo.
_TMP = Path(tempfile.mkdtemp(prefix="fasah_worker_test_"))
os.environ["ZC_LOG_DIR"] = str(_TMP / "logs")
os.environ["ZC_STATE"] = str(_TMP / "state")
os.environ["ZC_OUTBOX"] = str(_TMP / "outbox")
os.environ.setdefault("ZC_ENV", "dev")

from browser import worker  # noqa: E402


# ── Gate 11: domain allowlist ─────────────────────────────────────────────────

class TestDomainAllowlist:
    def test_empty_allowlist_allows_all(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ALLOWED_DOMAINS", "")
        assert worker.is_domain_allowed("https://anything.example.com/x") is True

    def test_exact_match(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ALLOWED_DOMAINS", "fasah.gov.sa")
        assert worker.is_domain_allowed("https://fasah.gov.sa/en/req") is True
        assert worker.is_domain_allowed("https://evil.com/fasah.gov.sa") is False

    def test_wildcard_match(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ALLOWED_DOMAINS", "*.fasah.gov.sa,fasah.gov.sa")
        assert worker.is_domain_allowed("https://portal.fasah.gov.sa/x") is True
        assert worker.is_domain_allowed("https://fasah.gov.sa/x") is True
        assert worker.is_domain_allowed("https://fasah.gov.sa.evil.com/x") is False
        assert worker.is_domain_allowed("https://notfasah.com/x") is False


# ── out_dir sanitisation (path-traversal defence) ─────────────────────────────

class TestResolveOutDir:
    def test_valid_name(self) -> None:
        out = worker.resolve_out_dir({"outputs": {"out_dir": "task_abc-123"}})
        assert out.parent == worker.OUTBOX_DIR
        assert out.name == "task_abc-123"

    def test_traversal_reduced_to_basename(self) -> None:
        # A traversal attempt must never escape OUTBOX_DIR.
        out = worker.resolve_out_dir({"outputs": {"out_dir": "../../../etc/passwd"}})
        assert out.parent == worker.OUTBOX_DIR
        assert out.name == "passwd"

    def test_invalid_chars_rejected(self) -> None:
        with pytest.raises(ValueError):
            worker.resolve_out_dir({"outputs": {"out_dir": "bad name!"}})


# ── Playbook resolution ───────────────────────────────────────────────────────

class TestResolvePlaybook:
    def test_canonical_passthrough(self) -> None:
        assert worker._resolve_playbook("fasah_search_inspect_v1") == "fasah_search_inspect_v1"

    def test_alias_resolves(self) -> None:
        assert worker._resolve_playbook("fasah_search") == "fasah_search_inspect_v1"
        assert worker._resolve_playbook("search_application_status") == "fasah_search_inspect_v1"

    def test_unknown_passthrough(self) -> None:
        # Unknown names pass through so the caller can raise E_UNKNOWN_PLAYBOOK.
        assert worker._resolve_playbook("nope_v9") == "nope_v9"


# ── Gate 9: output limits ─────────────────────────────────────────────────────

class TestOutputLimits:
    def test_within_limits_ok(self, tmp_path: Path) -> None:
        worker.check_artifact_limits([], tmp_path)  # must not raise

    def test_too_many_artifacts_raises(self, tmp_path: Path) -> None:
        artifacts = [
            {"name": f"a{i}", "path": "/nonexistent", "type": "screenshot"}
            for i in range(worker.MAX_ARTIFACTS_PER_TASK + 1)
        ]
        with pytest.raises(worker.OutputLimitError) as exc:
            worker.check_artifact_limits(artifacts, tmp_path)
        assert exc.value.error_code == worker.ErrorCode.ARTIFACT_LIMIT_EXCEEDED


# ── Gate 10: prod fail-closed ─────────────────────────────────────────────────

class TestValidateProdConfig:
    def test_dev_is_noop(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ZC_ENV", "dev")
        worker.validate_prod_config()  # must not raise/exit

    def test_prod_missing_config_exits(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ZC_ENV", "prod")
        monkeypatch.setattr(worker, "ALLOWED_DOMAINS", "")
        monkeypatch.setattr(worker, "ENCRYPTION_KEY", "")
        monkeypatch.setattr(worker, "FASAH_BASE_URL", "")
        with pytest.raises(SystemExit):
            worker.validate_prod_config()

    def test_prod_complete_config_ok(self, monkeypatch) -> None:
        monkeypatch.setattr(worker, "ZC_ENV", "prod")
        monkeypatch.setattr(worker, "ALLOWED_DOMAINS", "*.fasah.gov.sa")
        monkeypatch.setattr(worker, "ENCRYPTION_KEY", "c29tZS1rZXk=")
        monkeypatch.setattr(worker, "FASAH_BASE_URL", "https://fasah.gov.sa")
        worker.validate_prod_config()  # must not raise
