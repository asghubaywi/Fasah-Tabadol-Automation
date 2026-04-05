"""
resilient_audit.py — Non-blocking audit logger with in-memory buffer fallback.
مسجل التدقيق غير الحاجب مع احتياطي ذاكرة التخزين المؤقت

Extends AuditLogger so that disk failures never block the pipeline:

  1. On failure → event is placed in a thread-safe in-memory deque.
  2. On the next write attempt → buffered events are flushed first.
  3. If the deque is full → oldest events are silently dropped
     (deque handles this automatically via maxlen) and a stderr warning
     is printed.
  4. On every failure and recovery → a message is printed to stderr.
  5. Never raises — calling code can always proceed.

Usage:
    from utils.resilient_audit import ResilientAuditLogger
    audit = ResilientAuditLogger("agent_fasah", audit_dir)
    audit.record("AgentStarted", ...)
"""
from __future__ import annotations

import collections
import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.audit import AuditLogger

log = logging.getLogger("fasah.resilient_audit")

_DEFAULT_MAX_BUFFER = 500


class ResilientAuditLogger(AuditLogger):
    """
    Drop-in replacement for AuditLogger that never blocks on I/O failure.

    بديل مباشر لـ AuditLogger لا يتوقف عند فشل الإدخال/الإخراج.

    All public methods are thread-safe.
    """

    def __init__(
        self,
        agent_id: str,
        audit_dir: Path | str,
        max_buffer: int = _DEFAULT_MAX_BUFFER,
    ) -> None:
        super().__init__(agent_id, audit_dir)
        # maxlen ensures oldest events are automatically dropped when full
        self._buffer: collections.deque[str] = collections.deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        self._write_failures = 0
        self._buffered_total = 0
        self._dropped_total = 0

    # ── Public interface ──────────────────────────────────────────────────────

    def record(
        self,
        action: str,
        subject: str,
        tool: str,
        outcome: str,
        data: dict[str, Any] | None = None,
        risk_level: str = "low",
    ) -> None:
        """
        Append one audit event. Never raises.

        إضافة حدث تدقيق واحد. لا يُطلق استثناءات أبداً.
        """
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "action": action,
            "subject": subject,
            "tool": tool,
            "outcome": outcome,
            "risk_level": risk_level,
            "data": data or {},
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        try:
            with self._lock:
                self._write_line(line)
        except Exception as exc:
            # Honour the "never raises" contract even for unexpected errors
            print(
                f"[audit] WARN: unexpected error in record(): {exc}",
                file=sys.stderr,
            )

    def flush(self) -> None:
        """
        Attempt to flush all buffered events to disk.

        محاولة تفريغ جميع الأحداث المخزنة مؤقتاً إلى القرص.
        """
        with self._lock:
            self._flush_buffer()

    def stats(self) -> dict[str, Any]:
        """Return buffer statistics for the health dashboard."""
        with self._lock:
            return {
                "buffered": len(self._buffer),
                "buffered_total": self._buffered_total,
                "dropped_total": self._dropped_total,
                "write_failures": self._write_failures,
            }

    # ── Internal helpers (must hold self._lock) ───────────────────────────────

    def _write_line(self, line: str) -> None:
        """Try to write *line*; on failure buffer it. Must hold _lock."""
        # Flush any previously buffered events first so ordering is preserved
        if self._buffer:
            self._flush_buffer()

        try:
            with open(self._log_path(), "a", encoding="utf-8") as fh:
                fh.write(line)
            # Recovery: reset failure counter after a successful write
            if self._write_failures > 0:
                log.info(
                    "[ResilientAudit] Disk write recovered after %d failure(s).",
                    self._write_failures,
                )
                self._write_failures = 0
        except OSError as exc:
            self._write_failures += 1
            prev_len = len(self._buffer)
            self._buffer.append(line)
            new_len = len(self._buffer)
            self._buffered_total += 1

            if new_len < prev_len + 1:
                # deque was full — an old event was dropped automatically
                self._dropped_total += 1
                if self._dropped_total == 1 or self._dropped_total % 100 == 0:
                    print(
                        f"[audit] WARN: in-memory buffer full — "
                        f"oldest events are being dropped "
                        f"(total dropped={self._dropped_total})",
                        file=sys.stderr,
                    )

            print(
                f"[audit] WARN: disk write failed "
                f"(failure #{self._write_failures}): {exc} — "
                f"event buffered in memory ({new_len} event(s) pending)",
                file=sys.stderr,
            )

    def _flush_buffer(self) -> None:
        """Attempt to drain _buffer to disk. Must hold _lock."""
        if not self._buffer:
            return
        try:
            with open(self._log_path(), "a", encoding="utf-8") as fh:
                count = len(self._buffer)
                while self._buffer:
                    fh.write(self._buffer.popleft())
            log.info("[ResilientAudit] Flushed %d buffered event(s) to disk.", count)
        except OSError:
            pass  # leave events in buffer; will retry on next write
