"""In-memory audit log (MVP Phase 3 skeleton binding, 41 §42).

Satisfies :class:`~core.audit.ports.AuditLogPort` against process memory —
same skeleton discipline as the Phase 2/3 in-memory bindings: the real
PostgreSQL-backed audit log arrives later behind the same port.

Append-only mechanics: events are stored in an internal list that no public
method mutates except ``append``; AuditEvent itself is a frozen contract, so
stored records cannot be altered in place either.

Isolation mechanics (20 §6): reads filter strictly on ``tenant_id``; there
is no operation that can return another tenant's events.
"""

from __future__ import annotations

from uuid import UUID

from core.audit.errors import InvalidAuditEvent
from core.contracts.audit import ADMIN_CHANGE_EVENT_TYPES, AuditEvent, AuditEventType


class InMemoryAuditLog:
    """Process-memory implementation of ``AuditLogPort``."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> AuditEvent:
        is_admin = event.event_type in ADMIN_CHANGE_EVENT_TYPES
        if is_admin and event.admin_change is None:
            raise InvalidAuditEvent(f"{event.event_type} requires an AdminChangeRecord (21 §8)")
        if not is_admin and event.admin_change is not None:
            raise InvalidAuditEvent(f"{event.event_type} must not carry an AdminChangeRecord")
        self._events.append(event)
        return event

    def read(
        self,
        tenant_id: UUID,
        event_type: AuditEventType | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        selected = [
            event
            for event in self._events
            if event.tenant_id == tenant_id
            and (event_type is None or event.event_type == event_type)
        ]
        # Chronological; Python's stable sort preserves insertion order
        # for equal timestamps.
        selected.sort(key=lambda event: event.occurred_at)
        if limit is not None:
            selected = selected[-limit:]
        return tuple(selected)

    def count(self, tenant_id: UUID) -> int:
        return sum(1 for event in self._events if event.tenant_id == tenant_id)

    def __repr__(self) -> str:
        return f"InMemoryAuditLog(events={len(self._events)})"
