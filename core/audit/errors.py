"""Audit-log error set (closed; MVP Phase 3, 41 §42)."""

from __future__ import annotations


class AuditError(Exception):
    """Base class for all audit-log errors."""


class InvalidAuditEvent(AuditError):
    """Event violates an audit integrity rule (e.g. 21 §8 admin-change
    record missing on an admin config publish/rollback event, or present
    on a non-admin event)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
