"""
checkpoint.py — Checkpoint/resume system for the pipeline orchestrator.
نظام نقاط التفتيش والاستئناف لمنسق خطوط الأنابيب

Persists processing state after each file so the orchestrator can resume
from where it left off after a crash or intentional restart.

Checkpoint JSON on disk:
{
    "version": 1,
    "created_at": "<iso>",
    "updated_at": "<iso>",
    "current_file": "<name>" | null,
    "processed_files": {
        "<name>": {"sha256": "...", "ts": "...", "status": "ok|failed", "error"?: "..."}
    },
    "verdicts_dispatched": <int>,
    "in_flight": {
        "<name>": {"step": "parse|check|dispatch", "started_at": "<iso>"}
    }
}

Usage:
    ckpt = PipelineCheckpoint(inbox_dir)
    ckpt.mark_in_flight("foo.csv", "parse")
    ...
    ckpt.mark_complete("foo.csv", sha256, verdicts_count=3)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("fasah.checkpoint")

_CHECKPOINT_FILENAME = ".pipeline_checkpoint.json"
_VERSION = 1


class PipelineCheckpoint:
    """
    Atomic checkpoint writer for pipeline orchestrator progress.

    كاتب نقاط التفتيش الذري لتقدم منسق خط الأنابيب.
    """

    def __init__(self, checkpoint_dir: Path) -> None:
        self._path = checkpoint_dir / _CHECKPOINT_FILENAME
        self._state: dict[str, Any] = self._load()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        """Load existing checkpoint or return a fresh empty state."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                n = len(state.get("processed_files", {}))
                log.info(
                    "Checkpoint loaded from %s (%d file(s) previously processed).",
                    self._path, n,
                )
                return state
            except (json.JSONDecodeError, OSError) as exc:
                log.warning(
                    "Cannot load checkpoint '%s': %s — starting fresh.",
                    self._path, exc,
                )

        return {
            "version": _VERSION,
            "created_at": _now(),
            "updated_at": _now(),
            "current_file": None,
            "processed_files": {},
            "verdicts_dispatched": 0,
            "in_flight": {},
        }

    # ── Saving ────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """Atomically write checkpoint to disk via tmp-then-rename."""
        self._state["updated_at"] = _now()
        try:
            checkpoint_dir = self._path.parent
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(checkpoint_dir), suffix=".checkpoint.tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2, ensure_ascii=False)
                Path(tmp_path).rename(self._path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            log.warning("Cannot save checkpoint: %s", exc)

    # ── Public API ────────────────────────────────────────────────────────────

    def mark_in_flight(self, filename: str, step: str) -> None:
        """
        Record that *filename* is actively being processed at *step*.

        تسجيل أن الملف قيد المعالجة الفعلية في الخطوة المحددة.
        """
        self._state["current_file"] = filename
        self._state.setdefault("in_flight", {})[filename] = {
            "step": step,
            "started_at": _now(),
        }
        self._save()

    def mark_step(self, filename: str, step: str) -> None:
        """Update the current step for an already in-flight file."""
        if filename in self._state.get("in_flight", {}):
            self._state["in_flight"][filename]["step"] = step
            self._save()

    def mark_complete(
        self, filename: str, sha256: str, verdicts_count: int = 0
    ) -> None:
        """
        Record successful completion of *filename*.

        تسجيل الاكتمال الناجح للملف.
        """
        self._state["current_file"] = None
        self._state.get("in_flight", {}).pop(filename, None)
        self._state.setdefault("processed_files", {})[filename] = {
            "sha256": sha256,
            "ts": _now(),
            "status": "ok",
        }
        self._state["verdicts_dispatched"] = (
            int(self._state.get("verdicts_dispatched", 0)) + verdicts_count
        )
        self._save()

    def mark_failed(self, filename: str, error: str) -> None:
        """
        Record that *filename* failed processing.

        تسجيل فشل معالجة الملف.
        """
        self._state["current_file"] = None
        self._state.get("in_flight", {}).pop(filename, None)
        self._state.setdefault("processed_files", {})[filename] = {
            "ts": _now(),
            "status": "failed",
            "error": error[:500],  # cap error length
        }
        self._save()

    def was_processed(self, filename: str) -> bool:
        """Return True if *filename* was successfully processed in a previous run."""
        entry = self._state.get("processed_files", {}).get(filename)
        return entry is not None and entry.get("status") == "ok"

    def get_in_flight(self) -> dict[str, Any]:
        """
        Return files that were in-flight at the last checkpoint.

        إرجاع الملفات التي كانت قيد المعالجة عند آخر نقطة تفتيش.

        These may be partially processed and should be re-evaluated on resume.
        """
        return dict(self._state.get("in_flight", {}))

    def clear(self) -> None:
        """Reset checkpoint to empty state. مسح نقطة التفتيش."""
        self._state = {
            "version": _VERSION,
            "created_at": _now(),
            "updated_at": _now(),
            "current_file": None,
            "processed_files": {},
            "verdicts_dispatched": 0,
            "in_flight": {},
        }
        self._save()
        log.info("Checkpoint cleared.")

    def summary(self) -> dict[str, Any]:
        """Return summary statistics for the health dashboard."""
        processed = self._state.get("processed_files", {})
        ok = sum(1 for v in processed.values() if v.get("status") == "ok")
        failed = sum(1 for v in processed.values() if v.get("status") == "failed")
        return {
            "checkpoint_file": str(self._path),
            "current_file": self._state.get("current_file"),
            "files_ok": ok,
            "files_failed": failed,
            "verdicts_dispatched": self._state.get("verdicts_dispatched", 0),
            "in_flight": list(self._state.get("in_flight", {}).keys()),
            "updated_at": self._state.get("updated_at"),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
