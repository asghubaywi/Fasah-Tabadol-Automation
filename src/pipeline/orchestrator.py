"""
orchestrator.py — Fasah/Tabadol Pipeline Orchestrator
======================================================
محرك سير العمل لنظام فسح/تبادل

Polls inbox for CSV/JSON declaration files, runs them through the
fasah-engine (Rust) parse + compliance steps, then either:
  - Writes a browser task JSON for the browser worker, OR
  - Writes a tracking command directly to outbox.

Graceful degradation:
  - If Rust binary is missing/fails → Python fallback parser/compliance checker
  - If Rust engine trips circuit breaker → Python fallback until recovery
  - Checkpoint/resume: state saved after each file so a crashed run can resume
  - ResilientAuditLogger: buffers events in memory when disk writes fail

Usage:
    python src/pipeline/orchestrator.py
    AGENT_CONFIG=config/agent_fasah.yaml python src/pipeline/orchestrator.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── Project root resolution ───────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent

# Add src/ to import path for utils
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

# ── Configuration ─────────────────────────────────────────────────────────────
CONFIG_PATH = os.environ.get(
    "AGENT_CONFIG", str(_PROJECT_ROOT / "config" / "agent_fasah.yaml")
)
RULES_PATH = os.environ.get(
    "FASAH_RULES", str(_PROJECT_ROOT / "config" / "fasah_rules.yaml")
)

# Rust binary path — prefers release build, falls back to debug
_RELEASE_BIN = _PROJECT_ROOT / "target" / "release" / "fasah-engine"
_DEBUG_BIN = _PROJECT_ROOT / "target" / "debug" / "fasah-engine"
FASAH_ENGINE_BIN = os.environ.get(
    "FASAH_ENGINE_BIN",
    str(_RELEASE_BIN if _RELEASE_BIN.exists() else _DEBUG_BIN),
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fasah.orchestrator")

# ── Resilience: circuit breaker for the Rust engine ──────────────────────────
from pipeline.circuit_breaker import CircuitBreaker, CircuitOpenError  # noqa: E402
from pipeline import fallback_parser, fallback_compliance              # noqa: E402
from pipeline.checkpoint import PipelineCheckpoint                     # noqa: E402
from utils.degradation import get_manager as _get_degradation_manager, Component  # noqa: E402

_ENGINE_CIRCUIT = CircuitBreaker(
    name="rust_engine",
    failure_threshold=3,
    recovery_timeout=float(os.environ.get("ENGINE_CIRCUIT_TIMEOUT", "120")),
)


# ── Config loading ────────────────────────────────────────────────────────────

def load_config() -> dict[str, Any]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        log.info("Config loaded from %s", CONFIG_PATH)
        return cfg
    except OSError as e:
        log.warning("Cannot load config from %s: %s — using defaults", CONFIG_PATH, e)
        return {}


# ── Rust engine interface ─────────────────────────────────────────────────────

def run_engine(args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Call fasah-engine binary, return parsed JSON output.

    استدعاء ثنائي fasah-engine وإعادة نتيجة JSON المحللة.

    Raises FileNotFoundError if binary not found (run: cargo build --release).
    Raises RuntimeError on non-zero exit.
    """
    cmd = [FASAH_ENGINE_BIN] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        log.error(
            "fasah-engine binary not found at %s — "
            "build with: cargo build --release",
            FASAH_ENGINE_BIN,
        )
        raise
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"fasah-engine timed out after {timeout}s: {' '.join(args)}")

    if result.returncode != 0:
        raise RuntimeError(
            f"fasah-engine failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    return json.loads(result.stdout)


def run_engine_or_fallback_parse(file_path: Path) -> tuple[dict[str, Any], bool]:
    """
    Run ``fasah-engine parse`` through the circuit breaker.
    Falls back to the Python parser if Rust is unavailable.

    تشغيل أمر parse مع قاطع الدائرة، مع الرجوع إلى Python عند الفشل.

    Returns:
        (parse_result, used_fallback)
    """
    degradation = _get_degradation_manager()
    try:
        result = _ENGINE_CIRCUIT.call(run_engine, ["parse", str(file_path)])
        degradation.mark_healthy(Component.RUST_PARSER, "Rust parse succeeded")
        return result, False
    except CircuitOpenError as exc:
        log.warning(
            "[DEGRADED] Rust engine circuit OPEN for parse — using Python fallback (%s)",
            exc,
        )
        degradation.mark_degraded(Component.RUST_PARSER, str(exc))
    except FileNotFoundError:
        log.warning(
            "[DEGRADED] fasah-engine binary not found — using Python fallback parser"
        )
        degradation.mark_degraded(
            Component.RUST_PARSER, "Binary not found; using Python fallback"
        )
    except Exception as exc:
        log.warning(
            "[DEGRADED] Rust parse failed (%s) — using Python fallback parser", exc
        )
        degradation.mark_degraded(Component.RUST_PARSER, str(exc))

    return fallback_parser.parse_file(file_path), True


def run_engine_or_fallback_check(
    parse_result: dict[str, Any],
    tmp_records: Path,
) -> tuple[dict[str, Any], bool]:
    """
    Run ``fasah-engine check`` through the circuit breaker.
    Falls back to the Python compliance checker if Rust is unavailable.

    تشغيل أمر check مع قاطع الدائرة، مع الرجوع إلى Python عند الفشل.

    Returns:
        (compliance_result, used_fallback)
    """
    degradation = _get_degradation_manager()
    try:
        result = _ENGINE_CIRCUIT.call(
            run_engine, ["check", str(tmp_records), "--rules", RULES_PATH]
        )
        degradation.mark_healthy(Component.RUST_COMPLIANCE, "Rust check succeeded")
        return result, False
    except CircuitOpenError as exc:
        log.warning(
            "[DEGRADED] Rust engine circuit OPEN for check — using Python fallback (%s)",
            exc,
        )
        degradation.mark_degraded(Component.RUST_COMPLIANCE, str(exc))
    except FileNotFoundError:
        log.warning(
            "[DEGRADED] fasah-engine binary not found — using Python fallback compliance checker"
        )
        degradation.mark_degraded(
            Component.RUST_COMPLIANCE, "Binary not found; using Python fallback"
        )
    except Exception as exc:
        log.warning(
            "[DEGRADED] Rust check failed (%s) — using Python fallback compliance checker",
            exc,
        )
        degradation.mark_degraded(Component.RUST_COMPLIANCE, str(exc))

    return fallback_compliance.check_compliance(parse_result, RULES_PATH), True


# ── File utilities ────────────────────────────────────────────────────────────

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hashes(hashes_file: Path) -> set[str]:
    """Load known SHA-256 hashes from the ledger file."""
    known: set[str] = set()
    if hashes_file.exists():
        for line in hashes_file.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if parts and len(parts[0]) == 64:
                known.add(parts[0])
    return known


def append_hash(hashes_file: Path, sha256: str, filename: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with open(hashes_file, "a", encoding="utf-8") as f:
        f.write(f"{sha256} {filename} {ts}\n")


def move_safe(src: Path, dst: Path) -> None:
    """Move a file atomically; fall back to copy+delete on cross-device move."""
    try:
        src.rename(dst)
    except OSError:
        shutil.copy2(src, dst)
        src.unlink(missing_ok=True)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def process_file(
    file_path: Path,
    outbox_dir: Path,
    browser_tasks_dir: Path,
    audit: Any,
    checkpoint: "PipelineCheckpoint | None" = None,
) -> int:
    """
    Run parse → compliance → dispatch for a single declaration file.

    تشغيل التحليل ← الامتثال ← التوزيع لملف إعلان واحد.

    Returns the number of verdicts dispatched (for checkpoint tracking).
    """
    filename = file_path.name

    # ── Step 1: Parse ─────────────────────────────────────────────────────────
    log.info("Parsing %s", filename)
    if checkpoint:
        checkpoint.mark_in_flight(filename, "parse")

    parse_result, parse_fallback = run_engine_or_fallback_parse(file_path)

    audit.record(
        "ToolCompleted", "agent_fasah", "fasah_declaration_parse",
        "success" if not parse_fallback else "degraded",
        {
            "file": filename,
            "valid": parse_result.get("valid_records"),
            "invalid": parse_result.get("invalid_records"),
            "fallback": parse_fallback,
        },
    )

    records = parse_result.get("records", [])
    if not records:
        log.warning("No valid declarations in %s", filename)
        return 0

    # ── Step 2: Compliance Check ──────────────────────────────────────────────
    if checkpoint:
        checkpoint.mark_step(filename, "check")

    tmp_records = file_path.parent / f".tmp_records_{filename}.json"
    tmp_records.write_text(
        json.dumps(parse_result, ensure_ascii=False), encoding="utf-8"
    )
    try:
        log.info("Checking compliance for %d declaration(s) from %s", len(records), filename)
        compliance_result, check_fallback = run_engine_or_fallback_check(
            parse_result, tmp_records
        )
    finally:
        tmp_records.unlink(missing_ok=True)

    audit.record(
        "ToolCompleted", "agent_fasah", "fasah_compliance_check",
        "success" if not check_fallback else "degraded",
        {
            "file": filename,
            "approved": compliance_result.get("approved"),
            "held": compliance_result.get("held"),
            "rejected": compliance_result.get("rejected"),
            "fallback": check_fallback,
        },
    )

    # ── Step 3: Process Verdicts ──────────────────────────────────────────────
    if checkpoint:
        checkpoint.mark_step(filename, "dispatch")

    verdicts_count = 0
    for verdict in compliance_result.get("verdicts", []):
        decl_num = verdict.get("declaration_number", "UNKNOWN")
        action = verdict.get("action", "approve")
        risk_score = verdict.get("risk_score", 0)

        needs_browser = action in ("hold_pending_certificates", "escalate_high_value")

        if needs_browser:
            _dispatch_browser_task(
                decl_num, action, risk_score, browser_tasks_dir, audit
            )
        else:
            _write_tracking_command(
                decl_num, action, risk_score, outbox_dir
            )
        verdicts_count += 1

    return verdicts_count


def _dispatch_browser_task(
    decl_num: str,
    action: str,
    risk_score: int,
    browser_tasks_dir: Path,
    audit: Any,
) -> None:
    """Write a task envelope JSON for the browser worker."""
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:22]
    safe_decl = decl_num.replace("/", "_").replace("\\", "_").replace(" ", "_")
    task_id = f"fasah-{safe_decl}-{now_str}"
    fasah_url = os.environ.get("FASAH_BASE_URL", "https://fasah.gov.sa")

    task = {
        "task_id": task_id,
        "playbook": "fasah_search_inspect_v1",
        "params": {"base_url": fasah_url, "query": decl_num},
        "session_name": "fasah_agent",
        "outputs": {"out_dir": task_id},
    }

    # Atomic write
    tmp_task = browser_tasks_dir / f".tmp_{task_id}.json"
    final_task = browser_tasks_dir / f"{task_id}.json"
    tmp_task.write_text(
        json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp_task.rename(final_task)

    log.info(
        "Browser task dispatched: %s → %s (action=%s, risk=%d)",
        decl_num, task_id, action, risk_score,
    )
    audit.record(
        "ToolInvoked", "agent_fasah", "browser_dispatch", "success",
        {"task_id": task_id, "declaration": decl_num,
         "action": action, "risk_score": risk_score},
        risk_level="medium",
    )


def _write_tracking_command(
    decl_num: str,
    action: str,
    risk_score: int,
    outbox_dir: Path,
) -> None:
    """Write a tracking command JSON directly to outbox."""
    status_map = {
        "approve": "approved",
        "approve_with_conditions": "approved",
        "reject": "rejected",
        "reject_sanctioned": "rejected",
        "mandate_inspection": "held",
        "escalate_high_value": "held",
    }
    new_status = status_map.get(action, "checked")
    ts = datetime.now(timezone.utc).isoformat()
    ts_fmt = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = decl_num.replace("/", "_").replace("\\", "_").replace(" ", "_")

    cmd = {
        "command_type": "shipment_status_update",
        "declaration_number": decl_num,
        "status": new_status,
        "previous_status": "received",
        "timestamp": ts,
        "metadata": {
            "source": "compliance_check",
            "compliance_action": action,
            "risk_score": risk_score,
        },
    }
    out_file = outbox_dir / f"track_{safe}_{ts_fmt}.json"
    out_file.write_text(json.dumps(cmd, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Tracking command: %s → %s", decl_num, new_status)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = load_config()

    workspace = _PROJECT_ROOT / "workspace"
    inbox_dir = Path(cfg.get("inbox_dir", str(workspace / "inbox")))
    outbox_dir = Path(cfg.get("outbox_dir", str(workspace / "outbox")))
    audit_dir = Path(cfg.get("audit_dir", str(workspace / "audit")))
    poll_secs = int(cfg.get("poll_interval_secs", 15))

    processed_dir = inbox_dir / "processed"
    quarantine_dir = inbox_dir / "quarantine"
    browser_tasks_dir = outbox_dir / "browser_tasks"
    hashes_file = inbox_dir / ".processed_hashes"

    for d in [inbox_dir, outbox_dir, audit_dir, processed_dir, quarantine_dir, browser_tasks_dir]:
        d.mkdir(parents=True, exist_ok=True)

    from utils.resilient_audit import ResilientAuditLogger
    audit = ResilientAuditLogger("agent_fasah", audit_dir)

    audit.record(
        "AgentStarted", "agent_fasah", "agent_fasah", "success",
        {"inbox": str(inbox_dir), "outbox": str(outbox_dir),
         "engine": FASAH_ENGINE_BIN},
    )
    log.info(
        "Fasah orchestrator started | inbox=%s | poll=%ds | engine=%s",
        inbox_dir, poll_secs, FASAH_ENGINE_BIN,
    )

    # Surface a disabled sanction screen prominently (GAP-SEC-005): an empty
    # sanctioned_countries list means origin-sanction screening is effectively
    # OFF. Populating the list is a human/policy decision (GAP-HUM-007).
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as rf:
            _rules_doc = yaml.safe_load(rf) or {}
        if not _rules_doc.get("sanctioned_countries"):
            log.warning(
                "[POLICY] sanctioned_countries is EMPTY in %s — origin sanction "
                "screening is DISABLED until configured.", RULES_PATH,
            )
            audit.record(
                "PolicyWarning", "agent_fasah", "sanctions_screen", "disabled",
                {"rules_path": RULES_PATH}, risk_level="medium",
            )
    except OSError as exc:
        log.warning("Could not read rules file %s to verify sanctions list: %s",
                    RULES_PATH, exc)

    known_hashes = load_hashes(hashes_file)

    # ── Checkpoint: resume from where we left off ─────────────────────────────
    checkpoint = PipelineCheckpoint(inbox_dir)
    in_flight = checkpoint.get_in_flight()
    if in_flight:
        log.warning(
            "[RESUME] Found %d in-flight file(s) from previous run: %s — "
            "they will be re-processed.",
            len(in_flight), list(in_flight.keys()),
        )

    # Graceful shutdown on SIGINT / SIGTERM
    running = True

    def _stop(sig, frame):  # noqa: ARG001
        nonlocal running
        running = False
        log.info("Shutdown signal received — will stop after current cycle")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        files = [
            e for e in inbox_dir.iterdir()
            if e.is_file()
            and e.suffix.lower() in (".csv", ".json")
            and not e.name.startswith(".")
            and not e.name.startswith("tmp")
        ]

        for f in files:
            sha = compute_sha256(f)
            if sha in known_hashes:
                log.info("Duplicate %s — skipping", f.name)
                move_safe(f, processed_dir / f.name)
                continue

            try:
                verdicts = process_file(
                    f, outbox_dir, browser_tasks_dir, audit, checkpoint
                )
                known_hashes.add(sha)
                append_hash(hashes_file, sha, f.name)
                checkpoint.mark_complete(f.name, sha, verdicts)
                move_safe(f, processed_dir / f.name)
                log.info("Pipeline complete: %s (%d verdict(s))", f.name, verdicts)
            except Exception as exc:
                log.error("Pipeline failed for %s: %s — quarantining", f.name, exc)
                audit.record(
                    "ToolCompleted", "agent_fasah", "pipeline", "failure",
                    {"file": f.name, "error": str(exc)},
                    risk_level="medium",
                )
                checkpoint.mark_failed(f.name, str(exc))
                move_safe(f, quarantine_dir / f.name)

        if running:
            time.sleep(poll_secs)

    audit.record(
        "AgentStopped", "agent_fasah", "agent_fasah", "success",
        {"reason": "shutdown_signal"},
    )
    log.info("Fasah orchestrator stopped.")


if __name__ == "__main__":
    main()
