#!/usr/bin/env python3
"""
worker.py — Fasah Browser Worker (Playwright Edition)
======================================================
Playwright-based browser worker for automating Fasah portal interactions.

Picks up task JSON files from the inbox (browser_tasks/), executes the
fasah_search_inspect_v1 playbook, and writes result bundles to the outbox
(browser_results/).

All Gates (9–13) are preserved. All ENV-driven config is identical.

Architecture:
  orchestrator  --[task JSON]--> browser_tasks/  --[this worker]--> browser_results/
                                                                  \\-> state/processed/
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WORKER_VERSION = "1.1.0-pw"  # 1.1: added health monitor + retry
POLL_INTERVAL_SEC = int(os.environ.get("ZC_POLL_INTERVAL", "3"))

# ── Default paths resolve relative to project root ────────────────────────────
_WORKER_DIR = Path(__file__).parent
_PROJECT_ROOT = _WORKER_DIR.parent.parent
_WORKSPACE = _PROJECT_ROOT / "workspace"

INBOX_DIR = Path(os.environ.get("ZC_INBOX", str(_WORKSPACE / "outbox" / "browser_tasks")))
OUTBOX_DIR = Path(os.environ.get("ZC_OUTBOX", str(_WORKSPACE / "outbox" / "browser_results")))
STATE_DIR = Path(os.environ.get("ZC_STATE", str(_WORKSPACE / "state")))
LOG_DIR = Path(os.environ.get("ZC_LOG_DIR", str(_WORKSPACE / "state" / "logs" / "browser_worker")))
PROCESSED_DIR = STATE_DIR / "processed"
LOCKS_DIR = STATE_DIR / "locks"

# Environment-driven config
ZC_ENV = os.environ.get("ZC_ENV", "dev")
ALLOWED_DOMAINS = os.environ.get("AGENT_BROWSER_ALLOWED_DOMAINS", "")
ENCRYPTION_KEY = os.environ.get("AGENT_BROWSER_ENCRYPTION_KEY", "")
SESSION_NAME = os.environ.get("AGENT_BROWSER_SESSION_NAME", "fasah_default")
FASAH_BASE_URL = os.environ.get("FASAH_BASE_URL", "")

# Session storage directory for persistent login
SESSION_STORAGE_DIR = Path(os.environ.get(
    "ZC_SESSION_STORAGE", "/var/lib/zeroclaw/fasah/state/sessions"
))

# Regex for safe relative out_dir names
_SAFE_DIRNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Playwright timeouts (ms)
PW_NAV_TIMEOUT = int(os.environ.get("ZC_PW_NAV_TIMEOUT", "60000"))
PW_ACTION_TIMEOUT = int(os.environ.get("ZC_PW_ACTION_TIMEOUT", "30000"))

# ---------------------------------------------------------------------------
# [Gate 9] Output limits
# ---------------------------------------------------------------------------
MAX_ARTIFACTS_PER_TASK = int(os.environ.get("ZC_MAX_ARTIFACTS", "20"))
MAX_ARTIFACT_BYTES = int(os.environ.get("ZC_MAX_ARTIFACT_BYTES", str(20 * 1024 * 1024)))
MAX_OUTDIR_BYTES = int(os.environ.get("ZC_MAX_OUTDIR_BYTES", str(50 * 1024 * 1024)))

# ---------------------------------------------------------------------------
# [Gate 11] Blocked actions — hard deny regardless of policy
# ---------------------------------------------------------------------------
V1_BLOCKED_ACTIONS = frozenset({"download", "upload"})

# ---------------------------------------------------------------------------
# [Gate 13] Structured error codes
# ---------------------------------------------------------------------------
class ErrorCode:
    POLICY_OUTDIR_INVALID     = "E_POLICY_OUTDIR_INVALID"
    BASE_URL_MISSING_PROD     = "E_BASE_URL_MISSING_PROD"
    BROWSER_TIMEOUT           = "E_BROWSER_TIMEOUT"
    ELEMENT_NOT_FOUND         = "E_ELEMENT_NOT_FOUND"
    NETWORK_BLOCKED           = "E_NETWORK_BLOCKED"
    AUTH_REQUIRED             = "E_AUTH_REQUIRED"
    TASK_JSON_INVALID         = "E_TASK_JSON_INVALID"
    UNKNOWN_PLAYBOOK          = "E_UNKNOWN_PLAYBOOK"
    TRANSCRIPT_WRITE_FAIL     = "E_TRANSCRIPT_WRITE_FAIL"
    HASH_COMPUTE_FAIL         = "E_HASH_COMPUTE_FAIL"
    MANIFEST_WRITE_FAIL       = "E_MANIFEST_WRITE_FAIL"
    BUNDLE_WRITE_FAIL         = "E_BUNDLE_WRITE_FAIL"
    ARTIFACT_LIMIT_EXCEEDED   = "E_ARTIFACT_LIMIT_EXCEEDED"
    ARTIFACT_TOO_LARGE        = "E_ARTIFACT_TOO_LARGE"
    OUTDIR_SIZE_EXCEEDED      = "E_OUTDIR_SIZE_EXCEEDED"
    BLOCKED_ACTION_V1         = "E_BLOCKED_ACTION_V1"
    DUPLICATE_TASK            = "E_DUPLICATE_TASK"
    PROD_CONFIG_MISSING       = "E_PROD_CONFIG_MISSING"
    NAV_FAILED                = "E_NAV_FAILED"
    SEARCH_FAILED             = "E_SEARCH_FAILED"
    STATUS_EXTRACT_FAILED     = "E_STATUS_EXTRACT_FAILED"
    NO_RESULTS                = "E_NO_RESULTS"
    BROWSER_LAUNCH_FAIL       = "E_BROWSER_LAUNCH_FAIL"
    DOMAIN_NOT_ALLOWED        = "E_DOMAIN_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "worker.log"),
    ],
)
log = logging.getLogger("fasah_worker")

# ── Health monitor (module-level singleton) ───────────────────────────────────
from browser.health_check import BrowserHealthMonitor  # noqa: E402

_HEALTH = BrowserHealthMonitor(
    max_consecutive_failures=int(os.environ.get("ZC_MAX_CONSECUTIVE_FAILURES", "5")),
    task_timeout_secs=float(os.environ.get("ZC_TASK_TIMEOUT_SECS", "300")),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dir_total_bytes(directory: Path) -> int:
    total = 0
    if directory.exists():
        for f in directory.iterdir():
            if f.is_file():
                total += f.stat().st_size
    return total


# ---------------------------------------------------------------------------
# [Gate 10] Prod startup validation
# ---------------------------------------------------------------------------
def validate_prod_config() -> None:
    if ZC_ENV != "prod":
        return
    missing: list[str] = []
    if not ALLOWED_DOMAINS:
        missing.append("AGENT_BROWSER_ALLOWED_DOMAINS")
    if not ENCRYPTION_KEY or ENCRYPTION_KEY.startswith("<"):
        missing.append("AGENT_BROWSER_ENCRYPTION_KEY")
    if not FASAH_BASE_URL:
        missing.append("FASAH_BASE_URL")
    if missing:
        log.error(
            "FAIL-CLOSED [%s]: PROD mode requires: %s",
            ErrorCode.PROD_CONFIG_MISSING, ", ".join(missing),
        )
        sys.exit(1)
    log.info("PROD config validated.")


# ---------------------------------------------------------------------------
# [Gate 9] Output limit enforcement
# ---------------------------------------------------------------------------
class OutputLimitError(Exception):
    def __init__(self, error_code: str, detail: str):
        self.error_code = error_code
        self.detail = detail
        super().__init__(f"[{error_code}] {detail}")


def check_artifact_limits(artifacts: list[dict], out_dir: Path) -> None:
    if len(artifacts) > MAX_ARTIFACTS_PER_TASK:
        raise OutputLimitError(
            ErrorCode.ARTIFACT_LIMIT_EXCEEDED,
            f"Artifact count {len(artifacts)} exceeds limit {MAX_ARTIFACTS_PER_TASK}",
        )
    for art in artifacts:
        art_path = Path(art["path"])
        if art_path.exists():
            size = art_path.stat().st_size
            if size > MAX_ARTIFACT_BYTES:
                raise OutputLimitError(
                    ErrorCode.ARTIFACT_TOO_LARGE,
                    f"Artifact '{art['name']}' is {size} bytes, limit is {MAX_ARTIFACT_BYTES}",
                )
    total = dir_total_bytes(out_dir)
    if total > MAX_OUTDIR_BYTES:
        raise OutputLimitError(
            ErrorCode.OUTDIR_SIZE_EXCEEDED,
            f"Output directory total {total} bytes exceeds limit {MAX_OUTDIR_BYTES}",
        )


# ---------------------------------------------------------------------------
# [Gate 11] Domain allowlist enforcement
# ---------------------------------------------------------------------------
def is_domain_allowed(url: str) -> bool:
    """Check if a URL's domain is in the allowlist. Returns True if no allowlist set."""
    if not ALLOWED_DOMAINS:
        return True
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""
    for pattern in ALLOWED_DOMAINS.split(","):
        pattern = pattern.strip()
        if not pattern:
            continue
        if pattern.startswith("*."):
            # Wildcard: *.fasah.gov.sa matches sub.fasah.gov.sa
            suffix = pattern[1:]  # .fasah.gov.sa
            if hostname.endswith(suffix) or hostname == pattern[2:]:
                return True
        else:
            if hostname == pattern:
                return True
    return False


# ---------------------------------------------------------------------------
# [Gate 12] Idempotency
# ---------------------------------------------------------------------------
_TERMINAL_STATUSES = frozenset({"FOUND", "NOT_FOUND"})


def is_duplicate_task(task_id: str) -> bool:
    bundle_path = OUTBOX_DIR / task_id / "bundle.json"
    if not bundle_path.exists():
        return False
    try:
        with open(bundle_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        status = existing.get("status", "")
        if status in _TERMINAL_STATUSES:
            log.info("[%s] task_id=%s already terminal (status=%s) — skipping.",
                     ErrorCode.DUPLICATE_TASK, task_id, status)
            return True
    except (json.JSONDecodeError, OSError):
        pass
    return False


def acquire_task_lock(task_id: str) -> int | None:
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCKS_DIR / f"{task_id}.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o640)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        meta = json.dumps({
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        os.write(fd, (meta + "\n").encode())
        os.fsync(fd)
        return fd
    except (OSError, BlockingIOError):
        log.warning("[%s] task_id=%s already locked.", ErrorCode.DUPLICATE_TASK, task_id)
        return None


def release_task_lock(fd: int, task_id: str) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass
    try:
        (LOCKS_DIR / f"{task_id}.lock").unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------
def resolve_base_url(task: dict[str, Any]) -> str:
    if ZC_ENV == "prod" and FASAH_BASE_URL:
        log.info("PROD mode: using FASAH_BASE_URL from ENV (ignoring task.params.base_url)")
        return FASAH_BASE_URL
    return task["params"]["base_url"]


def resolve_out_dir(task: dict[str, Any]) -> Path:
    raw = task["outputs"]["out_dir"]
    clean = raw.strip().lstrip("/")
    basename = Path(clean).name
    if not _SAFE_DIRNAME_RE.match(basename):
        raise ValueError(f"Invalid out_dir '{raw}': must match [a-zA-Z0-9_-]{{1,128}}")
    resolved = OUTBOX_DIR / basename
    log.info("Resolved out_dir: %s → %s", raw, resolved)
    return resolved


# ---------------------------------------------------------------------------
# Transcript logger
# ---------------------------------------------------------------------------
class TranscriptLogger:
    def __init__(self, path: Path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")
        self._closed = False

    def log(self, event: str, data: dict[str, Any] | None = None):
        if self._closed:
            return
        entry = {"ts": now_iso(), "event": event}
        if data:
            entry["data"] = data
        self._fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self):
        if not self._closed:
            self._fh.close()
            self._closed = True


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------
def _make_result(
    status: str,
    *,
    error_code: str | None = None,
    error_detail: str | None = None,
    record_url: str | None = None,
    current_status: str | None = None,
    artifacts: list[dict] | None = None,
    hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "error_code": error_code,
        "error_detail": error_detail,
        "record_url": record_url,
        "current_status": current_status,
        "artifacts": artifacts or [],
        "hashes": hashes or {},
    }


# ---------------------------------------------------------------------------
# Canonical manifest
# ---------------------------------------------------------------------------
def write_canonical_manifest(hashes: dict[str, str], out_dir: Path) -> Path:
    manifest_path = out_dir / "sha256sum.txt"
    lines = []
    for filename in sorted(hashes.keys()):
        hex_digest = hashes[filename].removeprefix("sha256:")
        lines.append(f"{hex_digest}  {filename}")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# Playwright browser automation
# ---------------------------------------------------------------------------
def run_playwright_search(
    base_url: str,
    query: str,
    out_dir: Path,
    transcript: TranscriptLogger,
) -> dict[str, Any]:
    """
    Execute the fasah_search_inspect_v1 playbook using Playwright directly.
    Returns a result dict compatible with _make_result().
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

    artifacts: list[dict] = []
    hashes: dict[str, str] = {}

    # [Gate 11] Domain check before launching browser
    if not is_domain_allowed(base_url):
        return _make_result("TRANSIENT_FAIL",
            error_code=ErrorCode.DOMAIN_NOT_ALLOWED,
            error_detail=f"Domain not in allowlist: {base_url}")

    session_dir = SESSION_STORAGE_DIR / SESSION_NAME
    session_dir.mkdir(parents=True, exist_ok=True)
    storage_state = session_dir / "state.json"

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:
            log.error("[%s] Cannot launch browser: %s", ErrorCode.BROWSER_LAUNCH_FAIL, exc)
            return _make_result("TRANSIENT_FAIL",
                error_code=ErrorCode.BROWSER_LAUNCH_FAIL,
                error_detail=str(exc))

        try:
            # Reuse session if available (login persistence)
            ctx_args: dict[str, Any] = {
                "locale": "ar-SA",
                "viewport": {"width": 1280, "height": 720},
                "user_agent": f"ZeroClaw-FasahWorker/{WORKER_VERSION}",
            }
            if storage_state.exists():
                ctx_args["storage_state"] = str(storage_state)
                log.info("Reusing session from: %s", storage_state)

            context = browser.new_context(**ctx_args)

            # [Gate 11] Block downloads at browser level
            context.set_default_timeout(PW_ACTION_TIMEOUT)

            page = context.new_page()

            # ── Step 1: Navigate ──────────────────────────────
            # For Fasah SPA: go directly to Request List page (skip home)
            SEARCH_ROUTE = "/en/authorized-employee/requests"
            nav_url = base_url.rstrip("/") + SEARCH_ROUTE
            transcript.log("step", {"name": "navigate", "url": nav_url})
            try:
                response = page.goto(nav_url, wait_until="domcontentloaded", timeout=PW_NAV_TIMEOUT)
            except PwTimeout:
                _screenshot_safe(page, out_dir / "timeout_nav.png", artifacts, hashes)
                return _make_result("TRANSIENT_FAIL",
                    error_code=ErrorCode.BROWSER_TIMEOUT,
                    error_detail="Navigation timed out",
                    artifacts=artifacts, hashes=hashes)

            # Wait for Angular SPA to bootstrap and render
            ANGULAR_SETTLE_MS = int(os.environ.get("ZC_ANGULAR_SETTLE_MS", "8000"))
            page.wait_for_timeout(ANGULAR_SETTLE_MS)

            if response and response.status in (401, 403):
                _screenshot_safe(page, out_dir / "auth_fail.png", artifacts, hashes)
                transcript.log("auth_fail", {"status": response.status})
                return _make_result("AUTH_FAIL",
                    error_code=ErrorCode.AUTH_REQUIRED,
                    error_detail=f"HTTP {response.status}",
                    artifacts=artifacts, hashes=hashes)

            # Check if redirected to login page (SSO redirect to faseh-auth.sfda.gov.sa)
            current_url = page.url.lower()
            page_text_sample = (page.text_content("body") or "")[:2000].lower()
            login_indicators = ["login", "signin", "تسجيل الدخول", "دخول", "username", "password"]
            if any(ind in current_url or ind in page_text_sample for ind in login_indicators):
                _screenshot_safe(page, out_dir / "login_page.png", artifacts, hashes)
                transcript.log("auth_fail", {"reason": "login page detected", "url": page.url})
                return _make_result("AUTH_FAIL",
                    error_code=ErrorCode.AUTH_REQUIRED,
                    error_detail="Redirected to login page — session expired or not set",
                    artifacts=artifacts, hashes=hashes)

            transcript.log("navigate_ok", {"url": page.url})

            # [Gate 9]
            check_artifact_limits(artifacts, out_dir)

            # ── Step 2: Search ────────────────────────────────
            transcript.log("step", {"name": "search", "query": query})

            # Find search input — Fasah-specific selectors first, then generic fallbacks
            search_selectors = [
                # Fasah backoffice: Request List page
                '#requestNumberSearch',
                '#customsDeclarationNumberSearch',
                '#certificateNumber',
                '#searchKey',
                # Generic fallbacks
                'input[type="search"]',
                'input[name*="search" i]',
                'input[id*="search" i]',
                'input[placeholder*="بحث"]',
                'input[placeholder*="search" i]',
                'input[aria-label*="بحث"]',
                'input[aria-label*="search" i]',
                '[role="searchbox"]',
            ]

            search_input = None
            for sel in search_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        search_input = el
                        transcript.log("search_input_found", {"selector": sel})
                        break
                except Exception:
                    continue

            if not search_input:
                _screenshot_safe(page, out_dir / "no_search_input.png", artifacts, hashes)
                transcript.log("outcome", {"result": "NEEDS_HUMAN", "reason": "search input not found"})
                return _make_result("NEEDS_HUMAN",
                    error_code=ErrorCode.ELEMENT_NOT_FOUND,
                    error_detail="Cannot locate search input on page",
                    artifacts=artifacts, hashes=hashes)

            # Type query
            search_input.click()
            search_input.fill("")
            search_input.fill(query)

            # Find and click search button
            search_btn_selectors = [
                'button[type="submit"]',
                'button:has-text("بحث")',
                'button:has-text("Search")',
                'input[type="submit"]',
                'button:has-text("Find")',
                '[role="button"]:has-text("بحث")',
            ]

            clicked = False
            for sel in search_btn_selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        clicked = True
                        transcript.log("search_btn_clicked", {"selector": sel})
                        break
                except Exception:
                    continue

            if not clicked:
                # Fallback: press Enter
                search_input.press("Enter")
                transcript.log("search_submit", {"method": "Enter key"})

            # Wait for Angular to re-render search results
            page.wait_for_timeout(5000)

            # Screenshot search results
            _screenshot_safe(page, out_dir / "search_results.png", artifacts, hashes)

            # [Gate 9]
            check_artifact_limits(artifacts, out_dir)

            # ── Step 3: Analyse results ───────────────────────
            body_text = (page.text_content("body") or "")[:5000]
            body_lower = body_text.lower()

            no_results_indicators = [
                "لا توجد نتائج", "no results", "لم يتم العثور",
                "0 results", "no records", "لا يوجد",
            ]

            if any(ind in body_lower for ind in no_results_indicators):
                # Save evidence
                nr_path = out_dir / "no_results.txt"
                nr_path.write_text(body_text[:2000], encoding="utf-8")
                transcript.log("outcome", {"result": "NOT_FOUND"})
                return _make_result("NOT_FOUND",
                    error_code=ErrorCode.NO_RESULTS,
                    error_detail=f"No results for query: {query}",
                    artifacts=artifacts, hashes=hashes)

            # ── Step 4: Click first result ────────────────────
            result_selectors = [
                "table tbody tr:first-child a",
                "table tbody tr:first-child td:first-child",
                ".search-result a:first-of-type",
                ".result-item a:first-of-type",
                "a[href*='detail']",
                "a[href*='view']",
            ]

            result_clicked = False
            for sel in result_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        result_clicked = True
                        transcript.log("result_clicked", {"selector": sel})
                        break
                except Exception:
                    continue

            if not result_clicked:
                # Try clicking first table row
                try:
                    rows = page.query_selector_all("table tbody tr")
                    if rows:
                        rows[0].click()
                        result_clicked = True
                        transcript.log("result_clicked", {"selector": "first table row"})
                except Exception:
                    pass

            if result_clicked:
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except PwTimeout:
                    log.warning("networkidle timeout on detail page — continuing")

                # Screenshot detail page
                _screenshot_safe(page, out_dir / "detail_page.png", artifacts, hashes)

                # Record URL
                record_url = page.url
                (out_dir / "record_url.txt").write_text(record_url, encoding="utf-8")

                # Extract status
                status_text = _extract_status_text(page)
                if status_text:
                    (out_dir / "status.txt").write_text(status_text, encoding="utf-8")

                transcript.log("outcome", {
                    "result": "FOUND",
                    "current_status": status_text,
                    "record_url": record_url,
                })
                return _make_result("FOUND",
                    record_url=record_url,
                    current_status=status_text,
                    artifacts=artifacts, hashes=hashes)
            else:
                # Got results but couldn't click into detail
                transcript.log("outcome", {"result": "NEEDS_HUMAN", "reason": "cannot click result"})
                return _make_result("NEEDS_HUMAN",
                    error_code=ErrorCode.STATUS_EXTRACT_FAILED,
                    error_detail="Search returned results but could not navigate to detail",
                    artifacts=artifacts, hashes=hashes)

            # Save session for reuse
            try:
                context.storage_state(path=str(storage_state))
            except Exception:
                pass

        except PwTimeout as exc:
            log.error("[%s] Browser timeout: %s", ErrorCode.BROWSER_TIMEOUT, exc)
            return _make_result("TRANSIENT_FAIL",
                error_code=ErrorCode.BROWSER_TIMEOUT,
                error_detail=str(exc),
                artifacts=artifacts, hashes=hashes)
        except Exception as exc:
            log.exception("Browser automation error")
            return _make_result("TRANSIENT_FAIL",
                error_code=ErrorCode.SEARCH_FAILED,
                error_detail=str(exc),
                artifacts=artifacts, hashes=hashes)
        finally:
            try:
                # Always try to save session before closing
                context.storage_state(path=str(storage_state))
            except Exception:
                pass
            browser.close()


def _screenshot_safe(
    page: Any,
    path: Path,
    artifacts: list[dict],
    hashes: dict[str, str],
) -> None:
    """Take a screenshot, add to artifacts. Non-fatal on failure."""
    try:
        page.screenshot(path=str(path), full_page=True)
        artifacts.append({"name": path.stem, "path": str(path), "type": "screenshot"})
        hashes[path.name] = sha256_file(path)
    except Exception as exc:
        log.warning("Screenshot failed (non-fatal): %s", exc)


def _extract_status_text(page: Any) -> str | None:
    """Try multiple strategies to extract the current status from a detail page."""
    strategies = [
        # Strategy 1: Look for labeled status fields
        lambda: _try_label_value(page, ["الحالة", "حالة الطلب", "Status", "الحالة الحالية"]),
        # Strategy 2: Look for status badge/chip elements
        lambda: _try_css(page, ".status, .badge, .chip, [class*='status'], [class*='badge']"),
        # Strategy 3: Look for specific data attributes
        lambda: _try_css(page, "[data-status], [data-state]"),
    ]
    for strategy in strategies:
        try:
            result = strategy()
            if result and result.strip():
                return result.strip()[:500]
        except Exception:
            continue
    return None


def _try_label_value(page: Any, labels: list[str]) -> str | None:
    """Find a label element and return its sibling/next value."""
    for label in labels:
        try:
            # Try: label followed by value in next sibling
            el = page.query_selector(f'text="{label}"')
            if el:
                parent = el.evaluate_handle("el => el.parentElement")
                text = parent.evaluate("el => el.textContent") or ""
                # Remove the label itself
                value = text.replace(label, "").strip().strip(":").strip()
                if value:
                    return value
        except Exception:
            continue
    return None


def _try_css(page: Any, selector: str) -> str | None:
    """Try a CSS selector and return first visible element's text."""
    try:
        el = page.query_selector(selector)
        if el and el.is_visible():
            return el.text_content()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Playbook: fasah_search_inspect_v1
# ---------------------------------------------------------------------------
def playbook_fasah_search_inspect_v1(
    task: dict[str, Any],
    out_dir: Path,
    transcript: TranscriptLogger,
) -> dict[str, Any]:
    base_url = resolve_base_url(task)
    query = task["params"]["query"]

    transcript.log("playbook_start", {
        "playbook": "fasah_search_inspect_v1",
        "base_url": base_url,
        "base_url_source": "env" if (ZC_ENV == "prod" and FASAH_BASE_URL) else "task",
        "query": query,
        "blocked_actions": sorted(V1_BLOCKED_ACTIONS),
        "engine": "playwright",
    })

    return run_playwright_search(base_url, query, out_dir, transcript)


# ---------------------------------------------------------------------------
# Task processor (identical to original — all Gates preserved)
# ---------------------------------------------------------------------------
PLAYBOOKS = {
    "fasah_search_inspect_v1": playbook_fasah_search_inspect_v1,
}

# Backward-compatible aliases — maps legacy/short names to canonical playbook.
# Alias resolution is logged for auditability.
PLAYBOOK_ALIASES: dict[str, str] = {
    "search_application_status": "fasah_search_inspect_v1",
    "fasah_search":              "fasah_search_inspect_v1",
}


def _resolve_playbook(raw_name: str) -> str:
    """Return canonical playbook name, resolving aliases if needed."""
    if raw_name in PLAYBOOKS:
        return raw_name
    canonical = PLAYBOOK_ALIASES.get(raw_name)
    if canonical:
        log.info("Playbook alias resolved: %s → %s", raw_name, canonical)
        return canonical
    return raw_name  # let caller raise E_UNKNOWN_PLAYBOOK


def process_task(task_path: Path) -> None:
    """
    Load and execute one task file, updating the health monitor throughout.

    تحميل وتنفيذ ملف مهمة واحد مع تحديث مراقب الصحة.
    """
    log.info("Processing task: %s", task_path.name)

    # ── Graceful skip if browser is in a bad state ────────────────────────────
    if _HEALTH.is_browser_likely_crashed():
        log.warning(
            "[DEGRADED] Skipping task %s — browser health monitor reports "
            "%d consecutive failures (browser may be crashed). "
            "Restart the worker to reset.",
            task_path.name, _HEALTH._consecutive_failures,
        )
        _HEALTH.on_task_skip(task_path.stem)
        return

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            task = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("FAIL-CLOSED [%s]: %s: %s", ErrorCode.TASK_JSON_INVALID, task_path.name, exc)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(PROCESSED_DIR / f"{task_path.stem}.ERROR{task_path.suffix}"))
        return

    task_id = task["task_id"]
    playbook_name = _resolve_playbook(task["playbook"])

    if is_duplicate_task(task_id):
        log.info("Skipping duplicate task %s.", task_id)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(PROCESSED_DIR / task_path.name))
        _HEALTH.on_task_skip(task_id)
        return

    lock_fd = acquire_task_lock(task_id)
    if lock_fd is None:
        return

    _HEALTH.on_task_start(task_id)
    try:
        _process_task_locked(task_path, task, task_id, playbook_name)
        _HEALTH.on_task_success(task_id)
    except Exception as exc:
        _HEALTH.on_task_failure(task_id, str(exc))
        raise
    finally:
        release_task_lock(lock_fd, task_id)


def _process_task_locked(
    task_path: Path, task: dict, task_id: str, playbook_name: str,
) -> None:
    try:
        out_dir = resolve_out_dir(task)
    except ValueError as exc:
        log.error("FAIL-CLOSED [%s]: %s", ErrorCode.POLICY_OUTDIR_INVALID, exc)
        _write_error_bundle(task_id, OUTBOX_DIR, ErrorCode.POLICY_OUTDIR_INVALID, str(exc))
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(PROCESSED_DIR / f"{task_path.stem}.ERROR{task_path.suffix}"))
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    transcript: TranscriptLogger | None = None
    try:
        transcript_path = out_dir / "transcript.jsonl"
        transcript = TranscriptLogger(transcript_path)
        transcript.log("task_loaded", {"task_id": task_id, "playbook": playbook_name})
    except OSError as exc:
        log.error("FAIL-CLOSED [%s]: %s", ErrorCode.TRANSCRIPT_WRITE_FAIL, exc)
        _write_error_bundle(task_id, OUTBOX_DIR, ErrorCode.TRANSCRIPT_WRITE_FAIL, str(exc))
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(task_path), str(PROCESSED_DIR / task_path.name))
        return

    started_at = now_iso()
    result: dict[str, Any]

    try:
        if playbook_name not in PLAYBOOKS:
            raise ValueError(f"Unknown playbook: {playbook_name}")
        result = PLAYBOOKS[playbook_name](task, out_dir, transcript)
    except OutputLimitError as exc:
        log.error("FAIL-CLOSED [%s]: %s", exc.error_code, exc.detail)
        transcript.log("output_limit_exceeded", {"error_code": exc.error_code})
        result = _make_result("TRANSIENT_FAIL", error_code=exc.error_code, error_detail=exc.detail)
    except ValueError as exc:
        log.error("[%s]: %s", ErrorCode.UNKNOWN_PLAYBOOK, exc)
        result = _make_result("TRANSIENT_FAIL", error_code=ErrorCode.UNKNOWN_PLAYBOOK, error_detail=str(exc))
    except Exception as exc:
        log.exception("Task %s failed", task_id)
        result = _make_result("TRANSIENT_FAIL", error_code=ErrorCode.SEARCH_FAILED, error_detail=str(exc))

    finished_at = now_iso()

    transcript.close()
    if transcript_path.exists():
        result["artifacts"].append({"name": "transcript", "path": str(transcript_path), "type": "transcript"})
        try:
            result["hashes"]["transcript.jsonl"] = sha256_file(transcript_path)
        except OSError as exc:
            log.error("FAIL-CLOSED [%s]: %s", ErrorCode.HASH_COMPUTE_FAIL, exc)
            result["status"] = "TRANSIENT_FAIL"
            result["error_code"] = ErrorCode.HASH_COMPUTE_FAIL

    # [Gate 9] Final check
    try:
        check_artifact_limits(result["artifacts"], out_dir)
    except OutputLimitError as exc:
        result["status"] = "TRANSIENT_FAIL"
        result["error_code"] = exc.error_code

    # Canonical manifest
    try:
        if result["hashes"]:
            manifest_path = write_canonical_manifest(result["hashes"], out_dir)
            result["hashes"]["sha256sum.txt"] = sha256_file(manifest_path)
    except OSError as exc:
        log.error("FAIL-CLOSED [%s]: %s", ErrorCode.MANIFEST_WRITE_FAIL, exc)
        result["status"] = "TRANSIENT_FAIL"
        result["error_code"] = ErrorCode.MANIFEST_WRITE_FAIL

    # Build bundle
    bundle: dict[str, Any] = {
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": result["status"],
        "error_code": result.get("error_code"),
        "error_detail": result.get("error_detail"),
        "record_url": result.get("record_url"),
        "current_status": result.get("current_status"),
        "artifacts": result["artifacts"],
        "hashes": result["hashes"],
        "manifest_ref": "sha256sum.txt",
        "tool_versions": {
            "playwright": "bundled",
            "python": sys.version.split()[0],
            "worker_script": WORKER_VERSION,
        },
    }

    # Write bundle
    try:
        bundle_path = out_dir / "bundle.json"
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)
        log.info("Bundle written: %s (status=%s)", bundle_path, result["status"])
    except OSError as exc:
        log.error("FAIL-CLOSED [%s]: %s", ErrorCode.BUNDLE_WRITE_FAIL, exc)
        return

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(task_path), str(PROCESSED_DIR / task_path.name))
    log.info("Task moved to processed: %s", task_path.name)


def _write_error_bundle(task_id: str, out_dir: Path, error_code: str, detail: str) -> None:
    bundle = {
        "task_id": task_id, "started_at": now_iso(), "finished_at": now_iso(),
        "status": "TRANSIENT_FAIL", "error_code": error_code, "error_detail": detail,
        "artifacts": [], "hashes": {}, "manifest_ref": None,
    }
    try:
        d = out_dir / task_id
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "bundle.json", "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)
    except OSError:
        log.error("FAIL-CLOSED [%s]: Cannot write error bundle for %s", ErrorCode.BUNDLE_WRITE_FAIL, task_id)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def ensure_directories():
    for d in [INBOX_DIR, OUTBOX_DIR, STATE_DIR, PROCESSED_DIR, LOCKS_DIR, LOG_DIR, SESSION_STORAGE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def main():
    log.info("=" * 60)
    log.info("Fasah Browser Worker v%s (Playwright)", WORKER_VERSION)
    log.info("Environment: %s", ZC_ENV)
    log.info("Inbox:  %s", INBOX_DIR)
    log.info("Outbox: %s", OUTBOX_DIR)
    log.info("Poll interval: %ds", POLL_INTERVAL_SEC)
    log.info("V1 blocked actions: %s", sorted(V1_BLOCKED_ACTIONS))
    if ZC_ENV == "prod" and FASAH_BASE_URL:
        log.info("PROD base_url override active")
    log.info("=" * 60)

    validate_prod_config()
    ensure_directories()

    _HEALTH.reset_failure_count()  # fresh start on each launch
    _poll_count = 0

    while True:
        try:
            task_files = sorted(INBOX_DIR.glob("*.json"))
            if task_files:
                log.info("Found %d task(s) in inbox", len(task_files))
                for tf in task_files:
                    try:
                        process_task(tf)
                    except Exception:
                        log.exception("Unhandled error processing %s", tf.name)

            # Log health summary every 20 poll cycles (~1 min at default 3s interval)
            _poll_count += 1
            if _poll_count % 20 == 0:
                h = _HEALTH.status()
                log.info(
                    "[Health] tasks total=%d ok=%d failed=%d skipped=%d "
                    "consecutive_failures=%d healthy=%s",
                    h["total_tasks"], h["successful_tasks"],
                    h["failed_tasks"], h["skipped_tasks"],
                    h["consecutive_failures"], h["healthy"],
                )

            time.sleep(POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            log.info("Shutting down (SIGINT).")
            break
        except Exception:
            log.exception("Unhandled error in main loop")
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
