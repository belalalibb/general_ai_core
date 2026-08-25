"""Audit-log port (dependency-inversion boundary; MVP Phase 3, 41 §42).

Spec anchors:

- 41 §42 deliverable: "basic audit logs".
- 20 §9: the must-audit event set (closed enum in core/contracts/audit.py).
- 20 §6 tenant isolation: reads are tenant-scoped; there is deliberately
  NO cross-tenant or global read operation on this port.
- Append-only posture: the port exposes ``append`` and tenant-scoped reads
  ONLY — no update, no delete, no truncate. Tamper-resistance by design;
  retention/archival is an infrastructure policy of the real binding
  (later slice), never an API of core.

Design decisions (recorded here, mirroring the storage/secrets ports):

- ``tenant_id`` is an explicit parameter on every read, and appended
  events carry their own ``tenant_id`` — isolation at the boundary.
- Reads return events in chronological order (``occurred_at``, then
  insertion order for equal timestamps) so audit review is deterministic.
- Admin-change integrity rule (21 §8) is validated at append time:
  admin config publish/rollback events MUST carry an AdminChangeRecord,
  and non-admin events must NOT — enforced by the binding, tested.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.contracts.audit import AuditEvent, AuditEventType


class AuditLogPort(Protocol):
    """Append-only, tenant-scoped audit log (20 §9, 41 §42)."""

    def append(self, event: AuditEvent) -> AuditEvent:
        """Persist one immutable audit event; returns the stored event.

        Raises ``InvalidAuditEvent`` if the 21 §8 admin-change integrity
        rule is violated (admin event without record / record on a
        non-admin event).
        """
        ...

    def read(
        self,
        tenant_id: UUID,
        event_type: AuditEventType | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Return ``tenant_id``'s events, chronological, optionally filtered.

        ``limit`` keeps the newest N of the (filtered) result. Never
        returns another tenant's events.
        """
        ...

    def count(self, tenant_id: UUID) -> int:
        """Number of events recorded for ``tenant_id``."""
        ...
