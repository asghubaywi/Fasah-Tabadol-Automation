"""
degradation.py — Central degradation manager for the Fasah pipeline.
مدير التدهور المركزي لخط أنابيب فسح

Single source of truth for which components are healthy, degraded
(running with a Python fallback), or fully failed.

Usage:
    from utils.degradation import get_manager, Component
    mgr = get_manager()
    mgr.mark_degraded(Component.RUST_ENGINE, "Binary not found")
    if mgr.is_degraded(Component.RUST_ENGINE):
        result = python_fallback()
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any

log = logging.getLogger("fasah.degradation")


class ComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"   # Operating, but using a Python fallback
    FAILED = "failed"       # Not operating at all


class Component(Enum):
    RUST_ENGINE = "rust_engine"
    RUST_PARSER = "rust_parser"
    RUST_COMPLIANCE = "rust_compliance"
    BROWSER = "browser"
    PLAYWRIGHT = "playwright"
    AUDIT_LOGGER = "audit_logger"
    CONFIG_LOADER = "config_loader"
    FILESYSTEM = "filesystem"


class DegradationManager:
    """
    Thread-safe registry for component health and fallback modes.

    سجل آمن للخيوط لصحة المكونات وأوضاع الاحتياط.
    """

    def __init__(self) -> None:
        self._components: dict[Component, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._max_events = 200

    # ── Write operations ──────────────────────────────────────────────────────

    def mark_healthy(self, component: Component, detail: str = "") -> None:
        """
        Mark *component* as healthy (or recovered from degraded/failed).

        تحديد المكون على أنه سليم أو متعافٍ.
        """
        with self._lock:
            prev_status = self._components.get(component, {}).get("status")
            self._components[component] = {
                "status": ComponentStatus.HEALTHY,
                "detail": detail,
                "since": _now(),
            }
            if prev_status not in (None, ComponentStatus.HEALTHY):
                log.info(
                    "[Degradation] %s RECOVERED: %s", component.value, detail
                )
                self._append_event(component, ComponentStatus.HEALTHY, detail)

    def mark_degraded(self, component: Component, reason: str) -> None:
        """
        Mark *component* as degraded — operating with a Python fallback.

        تحديد المكون على أنه متدهور — يعمل بالنسخة الاحتياطية Python.
        """
        with self._lock:
            prev_status = self._components.get(component, {}).get("status")
            self._components[component] = {
                "status": ComponentStatus.DEGRADED,
                "reason": reason,
                "since": _now(),
            }
            if prev_status != ComponentStatus.DEGRADED:
                log.warning(
                    "[Degradation] %s DEGRADED: %s", component.value, reason
                )
                self._append_event(component, ComponentStatus.DEGRADED, reason)

    def mark_failed(self, component: Component, reason: str) -> None:
        """
        Mark *component* as failed — not operating.

        تحديد المكون على أنه فاشل — لا يعمل.
        """
        with self._lock:
            prev_status = self._components.get(component, {}).get("status")
            self._components[component] = {
                "status": ComponentStatus.FAILED,
                "reason": reason,
                "since": _now(),
            }
            if prev_status != ComponentStatus.FAILED:
                log.error(
                    "[Degradation] %s FAILED: %s", component.value, reason
                )
                self._append_event(component, ComponentStatus.FAILED, reason)

    # ── Read operations ───────────────────────────────────────────────────────

    def is_degraded(self, component: Component) -> bool:
        """Return True if component is DEGRADED or FAILED."""
        with self._lock:
            return self._components.get(component, {}).get("status") in (
                ComponentStatus.DEGRADED,
                ComponentStatus.FAILED,
            )

    def is_failed(self, component: Component) -> bool:
        """Return True if component is FAILED."""
        with self._lock:
            return (
                self._components.get(component, {}).get("status")
                == ComponentStatus.FAILED
            )

    def get_status(self, component: Component) -> ComponentStatus:
        """Return the current status of *component*."""
        with self._lock:
            return self._components.get(component, {}).get(
                "status", ComponentStatus.HEALTHY
            )

    def any_degraded(self) -> bool:
        """Return True if any component is not HEALTHY."""
        with self._lock:
            return any(
                info.get("status") != ComponentStatus.HEALTHY
                for info in self._components.values()
            )

    def summary(self) -> dict[str, Any]:
        """Return full status summary for the health dashboard."""
        with self._lock:
            components: dict[str, Any] = {}
            statuses = []
            for comp, info in self._components.items():
                status: ComponentStatus = info.get(
                    "status", ComponentStatus.HEALTHY
                )
                statuses.append(status)
                components[comp.value] = {
                    "status": status.value,
                    "since": info.get("since"),
                    "detail": info.get("detail") or info.get("reason", ""),
                }

            if any(s == ComponentStatus.FAILED for s in statuses):
                overall = "failed"
            elif any(s == ComponentStatus.DEGRADED for s in statuses):
                overall = "degraded"
            else:
                overall = "healthy"

            return {
                "overall": overall,
                "components": components,
                "recent_events": list(self._events[-10:]),
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _append_event(
        self,
        component: Component,
        status: ComponentStatus,
        detail: str,
    ) -> None:
        """Append to the internal event log. Must hold _lock."""
        self._events.append(
            {
                "ts": _now(),
                "component": component.value,
                "status": status.value,
                "detail": detail,
            }
        )
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]


# ── Module-level singleton ────────────────────────────────────────────────────

_manager: DegradationManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> DegradationManager:
    """Return (or lazily create) the process-wide DegradationManager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = DegradationManager()
        return _manager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
