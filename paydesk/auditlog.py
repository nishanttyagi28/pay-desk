"""Append-only desk events for the auditor timeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class AuditLog:
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def record(self, kind: str, *, actor: str, invoice_id: str | None = None, **detail: Any) -> dict:
        event = {
            "id": len(self._events) + 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "actor": actor,
            "invoice_id": invoice_id,
            "detail": detail,
        }
        self._events.append(event)
        return event

    def list(self, invoice_id: str | None = None) -> list[dict]:
        if invoice_id is None:
            return list(reversed(self._events))
        return list(reversed([e for e in self._events if e["invoice_id"] == invoice_id]))

    def clear(self) -> None:
        self._events.clear()
