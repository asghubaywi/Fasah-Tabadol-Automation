"""
health_check.py — Browser worker health monitor.
مراقب صحة عامل المتصفح

Tracks task-level metrics to detect browser crashes, hung operations,
and persistent portal unavailability.

Detects:
  - Consecutive task failures beyond a configurable threshold
    (likely browser crash or portal down)
  - Tasks that have been in-flight longer than a timeout
    (likely hung Playwright call)
  - RSS memory growth (Linux only via /proc/self/status)

Usage:
    monitor = BrowserHealthMonitor()
    monitor.on_task_start("task-123")
    ...
    monitor.on_task_success("task-123")
    # or
    monitor.on_task_failure("task-123", error="browser crashed")
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("fasah.browser.health")


class BrowserHealthMonitor:
    """
    Thread-safe health tracker for the browser worker.

    متتبع الصحة الآمن للخيوط لعامل المتصفح.

    Args:
        max_consecutive_failures: Alert threshold for consecutive failures.
        task_timeout_secs:        Seconds before an in-flight task is considered stuck.
    """

    def __init__(
        self,
        max_consecutive_failures: int = 5,
        task_timeout_secs: float = 300.0,
    ) -> None:
        self.max_consecutive_failures = max_consecutive_failures
        self.task_timeout_secs = task_timeout_secs

        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._total_tasks = 0
        self._successful_tasks = 0
        self._failed_tasks = 0
        self._skipped_tasks = 0
        self._current_task: str | None = None
        self._task_start_time: float | None = None
        self._started_at = datetime.now(timezone.utc).isoformat()

    # ── Event callbacks ───────────────────────────────────────────────────────

    def on_task_start(self, task_id: str) -> None:
        """Call when a task begins processing."""
        with self._lock:
            self._current_task = task_id
            self._task_start_time = time.monotonic()
            self._total_tasks += 1

    def on_task_success(self, task_id: str) -> None:
        """Call when a task completes successfully."""
        with self._lock:
            self._consecutive_failures = 0
            self._successful_tasks += 1
            self._current_task = None
            self._task_start_time = None

    def on_task_failure(self, task_id: str, error: str = "") -> None:
        """
        Call when a task fails. Logs an alert if the threshold is reached.

        استدعاء عند فشل مهمة. يُسجل تنبيهاً عند تجاوز الحد المسموح.
        """
        with self._lock:
            self._consecutive_failures += 1
            self._failed_tasks += 1
            self._current_task = None
            self._task_start_time = None
            consecutive = self._consecutive_failures

        log.warning(
            "[BrowserHealth] Task '%s' failed (consecutive=%d/%d): %s",
            task_id, consecutive, self.max_consecutive_failures, error,
        )

        if consecutive >= self.max_consecutive_failures:
            log.error(
                "[BrowserHealth] ALERT: %d consecutive failures — "
                "browser may be crashed or portal unreachable. "
                "Consider restarting the worker.",
                consecutive,
            )

    def on_task_skip(self, task_id: str) -> None:
        """Call when a task is skipped (duplicate or locked)."""
        with self._lock:
            self._skipped_tasks += 1

    def reset_failure_count(self) -> None:
        """Manually reset the consecutive-failure counter after a browser restart."""
        with self._lock:
            self._consecutive_failures = 0
        log.info("[BrowserHealth] Consecutive failure counter reset.")

    # ── Health queries ────────────────────────────────────────────────────────

    def is_task_stuck(self) -> bool:
        """Return True if the current task has exceeded *task_timeout_secs*."""
        with self._lock:
            if self._task_start_time is None:
                return False
            return (time.monotonic() - self._task_start_time) > self.task_timeout_secs

    def is_browser_likely_crashed(self) -> bool:
        """Return True if consecutive failures have reached the alert threshold."""
        with self._lock:
            return self._consecutive_failures >= self.max_consecutive_failures

    def get_memory_mb(self) -> float | None:
        """
        Get process RSS in MB from /proc/self/status (Linux only).

        قراءة ذاكرة العملية من /proc/self/status (Linux فقط).
        """
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        return kb / 1024.0
        except (OSError, ValueError, IndexError):
            pass
        return None

    def status(self) -> dict[str, Any]:
        """Return a serialisable health snapshot for the dashboard."""
        with self._lock:
            stuck = False
            elapsed: float | None = None
            if self._task_start_time is not None:
                elapsed = round(time.monotonic() - self._task_start_time, 1)
                stuck = elapsed > self.task_timeout_secs

            healthy = (
                self._consecutive_failures < self.max_consecutive_failures
                and not stuck
            )

            return {
                "healthy": healthy,
                "consecutive_failures": self._consecutive_failures,
                "max_consecutive_failures": self.max_consecutive_failures,
                "total_tasks": self._total_tasks,
                "successful_tasks": self._successful_tasks,
                "failed_tasks": self._failed_tasks,
                "skipped_tasks": self._skipped_tasks,
                "current_task": self._current_task,
                "task_elapsed_secs": elapsed,
                "task_stuck": stuck,
                "memory_mb": self.get_memory_mb(),
                "started_at": self._started_at,
            }
