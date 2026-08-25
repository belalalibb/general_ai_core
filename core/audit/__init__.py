"""Audit-log abstraction (MVP Phase 3, 41 §42 "basic audit logs").

Public surface: the audit-log port, its errors, and the in-memory binding.
The AuditEvent contract itself lives in ``core.contracts.audit`` (contracts
are the single source of truth for schemas). Real PostgreSQL-backed audit
storage arrives in ``infrastructure/`` later behind the same port.
"""

from core.audit.errors import AuditError, InvalidAuditEvent
from core.audit.memory import InMemoryAuditLog
from core.audit.ports import AuditLogPort

__all__ = [
    "AuditError",
    "AuditLogPort",
    "InMemoryAuditLog",
    "InvalidAuditEvent",
]
