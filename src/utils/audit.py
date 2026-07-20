"""
audit.py — Lightweight JSONL audit logger for Fasah-Tabadol-Automation.

Writes one JSON object per line to a daily audit file in audit_dir.
Replaces the ZeroClaw core_audit crate with a simple Python implementation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Appends structured audit events to a daily JSONL file.

    File path: <audit_dir>/<agent_id>_YYYY-MM-DD.jsonl
    """

    def __init__(self, agent_id: str, audit_dir: Path | str):
        self.agent_id = agent_id
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.audit_dir / f"{self.agent_id}_{today}.jsonl"

    def record(
        self,
        action: str,
        subject: str,
        tool: str,
        outcome: str,
        data: dict[str, Any] | None = None,
        risk_level: str = "low",
    ) -> None:
        """Append one audit event. Never raises — logs errors to stderr."""
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
        try:
            with open(self._log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            import sys
            print(f"[audit] WARN: failed to write audit entry: {exc}", file=sys.stderr)
