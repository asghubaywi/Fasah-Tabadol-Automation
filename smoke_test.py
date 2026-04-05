#!/usr/bin/env python3
"""
smoke_test.py — Pipeline Readiness Smoke Test
اختبار جاهزية خط الأنابيب

Validates that ALL 5 pipeline stages can actually execute — not just that
the code exists, but that runtime dependencies are in place.

Usage:
    python smoke_test.py
    python smoke_test.py --fix   # Attempt to install missing dependencies

Exit codes:
    0 = All stages ready
    1 = One or more stages have blocking issues
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))


def _c(ok: bool) -> str:
    return "✅" if ok else "❌"


def _w(msg: str) -> str:
    return f"⚠️  {msg}"


class SmokeTestReport:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.blocking: int = 0

    def check(self, stage: str, name: str, ok: bool, detail: str = "",
              blocking: bool = True, fix: str = "") -> bool:
        self.checks.append({
            "stage": stage, "name": name, "ok": ok,
            "detail": detail, "blocking": blocking, "fix": fix,
        })
        if not ok and blocking:
            self.blocking += 1
        return ok

    def print_report(self) -> None:
        print("\n" + "=" * 70)
        print("  FASAH-TABADOL PIPELINE — SMOKE TEST REPORT")
        print("=" * 70)

        current_stage = ""
        for c in self.checks:
            if c["stage"] != current_stage:
                current_stage = c["stage"]
                print(f"\n{'─' * 60}")
                print(f"  {current_stage}")
                print(f"{'─' * 60}")
            status = _c(c["ok"])
            print(f"  {status} {c['name']}")
            if c["detail"]:
                print(f"     {c['detail']}")
            if not c["ok"] and c["fix"]:
                print(f"     🔧 Fix: {c['fix']}")

        print(f"\n{'=' * 70}")
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c["ok"])
        print(f"  Result: {passed}/{total} checks passed", end="")
        if self.blocking > 0:
            print(f"  |  {self.blocking} BLOCKING issue(s)")
        else:
            print("  |  ALL CLEAR 🎉")
        print("=" * 70 + "\n")


def main() -> None:
    fix_mode = "--fix" in sys.argv
    report = SmokeTestReport()

    # ══════════════════════════════════════════════════════════════════════
    # Stage 1: Input (Tabadol CSV)
    # ══════════════════════════════════════════════════════════════════════

    # Check sample CSV exists
    sample = PROJECT_ROOT / "examples" / "sample_declarations.csv"
    report.check("Stage 1: Input (Tabadol CSV)",
                 "Sample CSV exists", sample.exists(),
                 str(sample), fix="Create examples/sample_declarations.csv")

    # Check workspace directories
    workspace = PROJECT_ROOT / "workspace"
    inbox = workspace / "inbox"
    report.check("Stage 1: Input (Tabadol CSV)",
                 "workspace/inbox/ exists", inbox.exists(),
                 str(inbox),
                 fix="mkdir -p workspace/inbox workspace/outbox workspace/audit")

    if fix_mode and not inbox.exists():
        for d in ["inbox", "outbox", "outbox/browser_tasks",
                   "outbox/browser_results", "audit", "state"]:
            (workspace / d).mkdir(parents=True, exist_ok=True)
        print("  🔧 Created workspace directories")

    # ══════════════════════════════════════════════════════════════════════
    # Stage 2: Processing (Parse + Compliance)
    # ══════════════════════════════════════════════════════════════════════

    # Rust engine binary
    release_bin = PROJECT_ROOT / "target" / "release" / "fasah-engine"
    debug_bin = PROJECT_ROOT / "target" / "debug" / "fasah-engine"
    engine_exists = release_bin.exists() or debug_bin.exists()
    engine_path = str(release_bin if release_bin.exists() else debug_bin)
    report.check("Stage 2: Processing (Parse + Compliance)",
                 "fasah-engine binary exists", engine_exists,
                 engine_path if engine_exists else "NOT FOUND",
                 blocking=False,  # Python fallback available
                 fix="cargo build --release")

    # Test Rust engine parse with sample CSV
    if engine_exists and sample.exists():
        try:
            result = subprocess.run(
                [engine_path, "parse", str(sample)],
                capture_output=True, text=True, timeout=10,
            )
            parse_ok = result.returncode == 0
            parse_out = json.loads(result.stdout) if parse_ok else {}
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Rust parse runs on sample CSV", parse_ok,
                         f"{parse_out.get('valid_records', 0)} valid records" if parse_ok
                         else result.stderr[:100])
        except Exception as exc:
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Rust parse runs on sample CSV", False, str(exc))
    else:
        report.check("Stage 2: Processing (Parse + Compliance)",
                      "Rust parse runs on sample CSV", False,
                      "Binary or sample CSV missing", blocking=False)

    # Test Python fallback parser
    try:
        from pipeline.fallback_parser import parse_csv
        if sample.exists():
            result = parse_csv(sample)
            fb_ok = result["valid_records"] > 0
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Python fallback parser works", fb_ok,
                         f"{result['valid_records']} valid records")
        else:
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Python fallback parser works", False,
                         "Sample CSV missing")
    except Exception as exc:
        report.check("Stage 2: Processing (Parse + Compliance)",
                     "Python fallback parser works", False, str(exc))

    # Test compliance check
    try:
        from pipeline.fallback_compliance import check_compliance
        if sample.exists():
            from pipeline.fallback_parser import parse_file
            parse_result = parse_file(sample)
            compliance_result = check_compliance(parse_result)
            cc_ok = compliance_result["total_checked"] > 0
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Compliance checker works", cc_ok,
                         f"checked={compliance_result['total_checked']}, "
                         f"approved={compliance_result['approved']}, "
                         f"rejected={compliance_result['rejected']}")
        else:
            report.check("Stage 2: Processing (Parse + Compliance)",
                         "Compliance checker works", False, "Sample CSV missing")
    except Exception as exc:
        report.check("Stage 2: Processing (Parse + Compliance)",
                     "Compliance checker works", False, str(exc))

    # Rules file
    rules = PROJECT_ROOT / "config" / "fasah_rules.yaml"
    report.check("Stage 2: Processing (Parse + Compliance)",
                 "fasah_rules.yaml exists", rules.exists(), str(rules))

    # ══════════════════════════════════════════════════════════════════════
    # Stage 3: Decision (Verdict Routing)
    # ══════════════════════════════════════════════════════════════════════

    # Test that orchestrator imports cleanly
    try:
        from pipeline.orchestrator import process_file, _dispatch_browser_task
        report.check("Stage 3: Decision (Verdict Routing)",
                     "Orchestrator module loads", True)
    except Exception as exc:
        report.check("Stage 3: Decision (Verdict Routing)",
                     "Orchestrator module loads", False, str(exc))

    # Check browser_tasks schema
    schema = PROJECT_ROOT / "schemas" / "fasah_task.schema.json"
    report.check("Stage 3: Decision (Verdict Routing)",
                 "Task schema exists", schema.exists(), str(schema))

    # ══════════════════════════════════════════════════════════════════════
    # Stage 4: Execution (Fasah Browser)
    # ══════════════════════════════════════════════════════════════════════

    # Playwright installed?
    try:
        import playwright
        pw_installed = True
        pw_version = getattr(playwright, "__version__", "unknown")
    except ImportError:
        pw_installed = False
        pw_version = "NOT INSTALLED"

    report.check("Stage 4: Execution (Fasah Browser)",
                 "Playwright package installed", pw_installed,
                 f"version: {pw_version}",
                 fix="pip install playwright && playwright install chromium")

    if fix_mode and not pw_installed:
        print("  🔧 Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"],
                       capture_output=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True)
        print("  🔧 Playwright installed")

    # Chromium browser downloaded?
    if pw_installed:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=10,
            )
            # If dry-run says nothing to install, it's already there
            chromium_ready = "already installed" in result.stdout.lower() or result.returncode == 0
        except Exception:
            chromium_ready = False

        # More reliable check: look for browser binary
        try:
            from playwright._impl._driver import compute_driver_executable
            driver = compute_driver_executable()
            chromium_ready = Path(driver).exists()
        except Exception:
            pass

        report.check("Stage 4: Execution (Fasah Browser)",
                     "Chromium browser available", chromium_ready,
                     fix="playwright install chromium")
    else:
        report.check("Stage 4: Execution (Fasah Browser)",
                     "Chromium browser available", False,
                     "Playwright not installed", fix="pip install playwright && playwright install chromium")

    # FASAH_BASE_URL
    base_url = os.environ.get("FASAH_BASE_URL", "")
    env_file = PROJECT_ROOT / ".env"
    if not base_url and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("FASAH_BASE_URL="):
                base_url = line.split("=", 1)[1].strip()
    report.check("Stage 4: Execution (Fasah Browser)",
                 "FASAH_BASE_URL configured", bool(base_url),
                 base_url or "NOT SET",
                 blocking=False,
                 fix="cp .env.example .env && edit FASAH_BASE_URL")

    # Worker module loads
    try:
        # Don't actually import worker (it initializes logging/dirs),
        # just verify the file is syntactically valid
        result = subprocess.run(
            [sys.executable, "-c",
             "import ast; ast.parse(open('src/browser/worker.py').read()); print('OK')"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=5,
        )
        report.check("Stage 4: Execution (Fasah Browser)",
                     "worker.py syntax valid", result.stdout.strip() == "OK")
    except Exception as exc:
        report.check("Stage 4: Execution (Fasah Browser)",
                     "worker.py syntax valid", False, str(exc))

    # ══════════════════════════════════════════════════════════════════════
    # Stage 5: Verification
    # ══════════════════════════════════════════════════════════════════════

    try:
        from pipeline.verification import VerificationEngine, VerificationStatus
        engine = VerificationEngine()
        rec = engine.verify("SMOKE-TEST-001", "approve", "Approved - Released")
        v_ok = rec.status == VerificationStatus.MATCH
        report.check("Stage 5: Verification",
                     "VerificationEngine works", v_ok,
                     f"status={rec.status.value}")
    except Exception as exc:
        report.check("Stage 5: Verification",
                     "VerificationEngine works", False, str(exc))

    # ══════════════════════════════════════════════════════════════════════
    # Tests
    # ══════════════════════════════════════════════════════════════════════

    # Rust tests
    try:
        result = subprocess.run(
            ["cargo", "test", "--quiet"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60,
        )
        rust_tests_ok = result.returncode == 0
        # Extract count from output
        for line in result.stderr.splitlines():
            if "test result" in line:
                report.check("Tests",
                             "Rust tests pass", rust_tests_ok, line.strip())
                break
        else:
            report.check("Tests", "Rust tests pass", rust_tests_ok,
                         result.stderr[-100:] if not rust_tests_ok else "all passed")
    except Exception as exc:
        report.check("Tests", "Rust tests pass", False, str(exc))

    # Python tests
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=60,
        )
        py_tests_ok = result.returncode == 0
        last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        report.check("Tests",
                     "Python tests pass", py_tests_ok, last_line)
    except Exception as exc:
        report.check("Tests", "Python tests pass", False, str(exc))

    # ── Print report ─────────────────────────────────────────────────────
    report.print_report()
    sys.exit(0 if report.blocking == 0 else 1)


if __name__ == "__main__":
    main()
