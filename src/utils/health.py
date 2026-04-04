"""
health.py — System health dashboard for Fasah-Tabadol-Automation.
لوحة صحة النظام لأتمتة فسح-تبادل

Reports which components are healthy / degraded / failed, active
fallback modes, disk space, and pipeline checkpoint statistics.

CLI usage:
    python -m src.utils.health               # one-shot report
    python -m src.utils.health --json        # machine-readable JSON
    python -m src.utils.health --watch 30    # refresh every 30 s

Exit codes:
    0  — all healthy
    1  — at least one component degraded (warnings)
    2  — at least one component failed (errors)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path bootstrap ────────────────────────────────────────────────────────────
_MODULE_DIR = Path(__file__).parent
_PROJECT_ROOT = _MODULE_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


# ── Individual component checks ───────────────────────────────────────────────

def _check_rust_engine() -> dict[str, Any]:
    """
    Check whether the fasah-engine binary exists and responds.

    فحص وجود وعمل ثنائي fasah-engine.
    """
    env_bin = os.environ.get("FASAH_ENGINE_BIN")
    release = _PROJECT_ROOT / "target" / "release" / "fasah-engine"
    debug = _PROJECT_ROOT / "target" / "debug" / "fasah-engine"

    if env_bin:
        binary = Path(env_bin)
    elif release.exists():
        binary = release
    elif debug.exists():
        binary = debug
    else:
        return {
            "status": "failed",
            "detail": "Binary not found — build with: cargo build --release",
        }

    if not binary.exists():
        return {"status": "failed", "detail": f"Binary missing: {binary}"}

    try:
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return {
                "status": "healthy",
                "detail": f"Binary at {binary}",
                "version": result.stdout.strip() or result.stderr.strip(),
            }
        return {
            "status": "degraded",
            "detail": f"Binary exists but --version returned exit {result.returncode}",
        }
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


def _check_playwright() -> dict[str, Any]:
    """
    Check whether Playwright and Chromium are installed.

    فحص توافر Playwright وChromium.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "status": "failed",
            "detail": "playwright not installed — run: pip install playwright",
        }

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            path = pw.chromium.executable_path
            if path and Path(path).exists():
                return {"status": "healthy", "detail": f"Chromium at {path}"}
            return {
                "status": "failed",
                "detail": "Chromium not installed — run: playwright install chromium",
            }
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


def _check_config() -> dict[str, Any]:
    """
    Check that config files are present and readable.

    فحص وجود وإمكانية قراءة ملفات الإعداد.
    """
    config_path = Path(
        os.environ.get(
            "AGENT_CONFIG",
            str(_PROJECT_ROOT / "config" / "agent_fasah.yaml"),
        )
    )
    rules_path = Path(
        os.environ.get(
            "FASAH_RULES",
            str(_PROJECT_ROOT / "config" / "fasah_rules.yaml"),
        )
    )

    issues: list[str] = []
    if not config_path.exists():
        issues.append(f"agent config not found: {config_path}")
    if not rules_path.exists():
        issues.append(
            f"rules file not found: {rules_path} (fallback defaults will be used)"
        )

    if not issues:
        return {"status": "healthy", "detail": f"Config: {config_path}"}
    if len(issues) == 1 and "rules" in issues[0]:
        return {"status": "degraded", "detail": issues[0]}
    return {"status": "failed", "detail": "; ".join(issues)}


def _check_workspace() -> dict[str, Any]:
    """
    Check workspace directories and available disk space.

    فحص مجلدات مساحة العمل والمساحة المتاحة على القرص.
    """
    workspace = _PROJECT_ROOT / "workspace"
    missing = [
        str(d)
        for d in [workspace / "inbox", workspace / "outbox", workspace / "audit"]
        if not d.exists()
    ]
    if missing:
        return {
            "status": "degraded",
            "detail": f"Directories not yet created (auto-created on start): {missing}",
        }

    try:
        import shutil

        free_bytes = shutil.disk_usage(str(workspace)).free
        free_gb = free_bytes / (1024 ** 3)
        if free_gb < 0.5:
            return {
                "status": "degraded",
                "detail": f"Low disk space: {free_gb:.2f} GB free — audit/output writes may fail",
            }
        return {
            "status": "healthy",
            "detail": f"Workspace: {workspace} ({free_gb:.1f} GB free)",
        }
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


def _check_audit_logger() -> dict[str, Any]:
    """
    Verify the audit log directory is writable.

    التحقق من إمكانية الكتابة في مجلد سجل التدقيق.
    """
    audit_dir = _PROJECT_ROOT / "workspace" / "audit"
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        probe = audit_dir / ".health_write_probe"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"status": "healthy", "detail": f"Writable: {audit_dir}"}
    except OSError as exc:
        return {"status": "failed", "detail": f"Audit dir not writable: {exc}"}


def _check_degradation_manager() -> dict[str, Any]:
    """
    Read the in-process degradation manager (if running in the same process).

    قراءة مدير التدهور داخل العملية.

    When called from the CLI (separate process) this will always show healthy
    because the manager state is not persisted to disk.
    """
    try:
        from utils.degradation import get_manager

        mgr = get_manager()
        summary = mgr.summary()
        degraded = [
            k for k, v in summary["components"].items()
            if v["status"] != "healthy"
        ]
        detail = (
            f"Degraded components: {degraded}" if degraded else "All components healthy"
        )
        return {
            "status": summary["overall"],
            "detail": detail,
            "components": summary["components"],
        }
    except Exception as exc:
        return {"status": "degraded", "detail": f"Cannot read degradation state: {exc}"}


def _check_checkpoint() -> dict[str, Any]:
    """
    Inspect the pipeline checkpoint file.

    فحص ملف نقطة تفتيش خط الأنابيب.
    """
    checkpoint_file = (
        _PROJECT_ROOT / "workspace" / "inbox" / ".pipeline_checkpoint.json"
    )
    if not checkpoint_file.exists():
        return {
            "status": "healthy",
            "detail": "No checkpoint on disk (first run or after clear)",
        }

    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        in_flight = state.get("in_flight", {})
        ok = sum(
            1 for v in state.get("processed_files", {}).values()
            if v.get("status") == "ok"
        )
        failed = sum(
            1 for v in state.get("processed_files", {}).values()
            if v.get("status") == "failed"
        )

        if in_flight:
            return {
                "status": "degraded",
                "detail": (
                    f"In-flight files from previous run: {list(in_flight.keys())} "
                    f"(will be re-processed on next start)"
                ),
                "in_flight": list(in_flight.keys()),
            }

        return {
            "status": "healthy",
            "detail": (
                f"Files ok={ok} failed={failed} "
                f"verdicts_dispatched={state.get('verdicts_dispatched', 0)}"
            ),
        }
    except Exception as exc:
        return {"status": "degraded", "detail": f"Cannot read checkpoint: {exc}"}


# ── Report builder ────────────────────────────────────────────────────────────

def get_health_report() -> dict[str, Any]:
    """
    Build and return the full system health report.

    بناء وإرجاع تقرير الصحة الكامل للنظام.
    """
    checks: dict[str, dict[str, Any]] = {
        "rust_engine": _check_rust_engine(),
        "playwright_browser": _check_playwright(),
        "config_files": _check_config(),
        "workspace_filesystem": _check_workspace(),
        "audit_logger": _check_audit_logger(),
        "degradation_manager": _check_degradation_manager(),
        "pipeline_checkpoint": _check_checkpoint(),
    }

    statuses = [c["status"] for c in checks.values()]
    if "failed" in statuses:
        overall = "failed"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


# ── Renderer ──────────────────────────────────────────────────────────────────

_STATUS_LABEL = {"healthy": "OK  ", "degraded": "WARN", "failed": "FAIL"}


def print_health_report(report: dict[str, Any]) -> None:
    """Pretty-print the health report to stdout."""
    width = 62
    print()
    print("=" * width)
    print("  Fasah-Tabadol-Automation — System Health Dashboard")
    print(f"  {report['timestamp']}")
    print("=" * width)

    overall = report["overall"]
    label = _STATUS_LABEL.get(overall, "????")
    print(f"\n  Overall status:  [{label}]  {overall.upper()}\n")
    print(f"  {'Component':<35} {'Status':<8}  Detail")
    print("  " + "-" * (width - 2))

    for name, check in report["checks"].items():
        status = check["status"]
        icon = _STATUS_LABEL.get(status, "????")
        detail = check.get("detail", "")
        # Truncate detail for terminal width
        max_detail = width - 50
        if len(detail) > max_detail:
            detail = detail[:max_detail] + "…"
        print(f"  {name:<35} [{icon}]  {detail}")

    print("\n" + "=" * width + "\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """
    Entry point for: python -m src.utils.health
    نقطة الدخول لأمر: python -m src.utils.health
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Fasah-Tabadol-Automation system health check"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument(
        "--watch",
        metavar="SECS",
        type=int,
        help="Refresh report every N seconds (Ctrl-C to stop)",
    )
    args = parser.parse_args()

    def run_once() -> dict[str, Any]:
        report = get_health_report()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_health_report(report)
        return report

    if args.watch:
        try:
            while True:
                report = run_once()
                time.sleep(args.watch)
        except KeyboardInterrupt:
            pass
        sys.exit(0)
    else:
        report = run_once()
        if report["overall"] == "failed":
            sys.exit(2)
        elif report["overall"] == "degraded":
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
