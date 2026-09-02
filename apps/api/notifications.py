"""NTF-1 — poll-based notification read-model (AA-3, doc C §5; doc A §12).

DESIGN (doc A §12 verbatim): six closed categories — SUCCESS · INFO ·
WARNING · ERROR · SECURITY · CHANGE. "A read-model over audit, not a new
event system": every notification is DERIVED from an existing record
(audit event / execution report / config-change record) at read time.

Honesty rules made structural:

- ZERO notifications exist without a backing record (criterion 4): the
  derivation is a pure function over the injected stores — there is no
  ``create_notification`` anywhere; nothing can mint one.
- Every notification carries an ``evidence`` link ``{kind, ref}`` naming
  its source record — the same citation vocabulary the agent uses.
- Deterministic ids (``exec:<uuid>``, ``audit:<uuid>``,
  ``change:<uuid>:<state>``) so acks survive repeated polls; ack state is
  process-local read/unread ONLY (the record itself is never touched).
- Poll-based v1 — no pub/sub, no delivery, no push (doc C §5 non-scope).

Category derivation (each category ← its source record type):

- SUCCESS  ← execution reports with status SUCCEEDED
- ERROR    ← execution reports with status FAILED
- INFO     ← config changes in VALIDATED state (awaiting the human publish)
- WARNING  ← config changes in REJECTED state (validation refused)
- SECURITY ← audit PERMISSION_DENIED / CROSS_TENANT_ACCESS_DENIED /
             SECURITY_POLICY_CHANGED
- CHANGE   ← audit ADMIN_CONFIG_PUBLISHED / ADMIN_CONFIG_ROLLED_BACK
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from apps.api.errors import error_response
from apps.api.store import ExecutionStorePort
from core.admin.service import AdminConfigService
from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEventType
from core.contracts.errors import ErrorCode
from core.contracts.execute import ExecutionStatus

if TYPE_CHECKING:
    from apps.api.app import Principal


class NotificationCategory(StrEnum):
    """Doc A §12 closed set, verbatim."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"
    CHANGE = "change"


#: SECURITY derives from exactly these audit event types (doc A §12).
SECURITY_EVENT_TYPES: frozenset[AuditEventType] = frozenset(
    {
        AuditEventType.PERMISSION_DENIED,
        AuditEventType.CROSS_TENANT_ACCESS_DENIED,
        AuditEventType.SECURITY_POLICY_CHANGED,
    }
)

#: CHANGE derives from exactly these audit event types (doc A §12).
CHANGE_EVENT_TYPES: frozenset[AuditEventType] = frozenset(
    {
        AuditEventType.ADMIN_CONFIG_PUBLISHED,
        AuditEventType.ADMIN_CONFIG_ROLLED_BACK,
    }
)


@dataclass(frozen=True)
class NotificationSources:
    """The EXISTING records notifications derive from — injected, never new."""

    audit: AuditLogPort
    # Structural port (same P2 widening as AgentToolSurface): notifications
    # only ever call ``.list(tenant_id)`` — both store bindings satisfy it.
    executions: ExecutionStorePort
    changes: AdminConfigService


@dataclass
class NotificationService:
    """Derive-on-read notification list + process-local ack state."""

    sources: NotificationSources
    _acked: set[tuple[UUID, str]] = field(default_factory=set)

    def list(self, tenant_id: UUID) -> list[dict[str, object]]:
        """All derivable notifications, newest-first, with read state."""
        rows: list[dict[str, object]] = []

        for event in self.sources.audit.read(tenant_id, limit=200):
            if event.event_type in SECURITY_EVENT_TYPES:
                category = NotificationCategory.SECURITY
            elif event.event_type in CHANGE_EVENT_TYPES:
                category = NotificationCategory.CHANGE
            else:
                continue
            rows.append(
                self._row(
                    tenant_id,
                    notification_id=f"audit:{event.id}",
                    category=category,
                    title=event.event_type.value,
                    occurred_at=event.occurred_at.isoformat(),
                    evidence={"kind": "audit_event", "ref": str(event.id)},
                )
            )

        for report in self.sources.executions.list(tenant_id):
            status = report.execution.status
            if status is ExecutionStatus.SUCCEEDED:
                category = NotificationCategory.SUCCESS
            elif status is ExecutionStatus.FAILED:
                category = NotificationCategory.ERROR
            else:
                continue
            rows.append(
                self._row(
                    tenant_id,
                    notification_id=f"exec:{report.execution.id}",
                    category=category,
                    title=f"execution {status.value}",
                    occurred_at=report.execution.created_at.isoformat(),
                    evidence={"kind": "execution", "ref": str(report.execution.id)},
                )
            )

        for change in self.sources.changes.list_changes(tenant_id):
            state = change.state.value
            if state == "validated":
                category = NotificationCategory.INFO
                title = f"change awaiting publish: {change.action.value}"
            elif state == "rejected":
                category = NotificationCategory.WARNING
                title = change.validation_result or "change rejected"
            else:
                continue
            rows.append(
                self._row(
                    tenant_id,
                    notification_id=f"change:{change.id}:{state}",
                    category=category,
                    title=title,
                    occurred_at=change.created_at.isoformat(),
                    evidence={"kind": "config_change", "ref": str(change.id)},
                )
            )

        rows.sort(key=lambda r: str(r["occurred_at"]), reverse=True)
        return rows

    def ack(self, tenant_id: UUID, notification_id: str) -> bool:
        """Mark read IFF the id is currently derivable — no phantom acks."""
        known = {str(row["id"]) for row in self.list(tenant_id)}
        if notification_id not in known:
            return False
        self._acked.add((tenant_id, notification_id))
        return True

    def _row(
        self,
        tenant_id: UUID,
        *,
        notification_id: str,
        category: NotificationCategory,
        title: str,
        occurred_at: str,
        evidence: dict[str, str],
    ) -> dict[str, object]:
        return {
            "id": notification_id,
            "category": category.value,
            "title": title[:512],
            "occurred_at": occurred_at,
            "evidence": evidence,
            "read": (tenant_id, notification_id) in self._acked,
        }


def create_notifications_router(
    service: NotificationService,
    *,
    resolve: Callable[[Request], Principal | JSONResponse],
) -> APIRouter:
    """GET list + POST ack — admin-gated, poll-based (doc C §5)."""
    router = APIRouter(prefix="/v1/admin/notifications")

    def _admit(request: Request) -> Principal | JSONResponse:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        if not caller.is_admin:
            return error_response(ErrorCode.UNAUTHORIZED, "Admin access required.")
        return caller

    @router.get("")
    async def list_notifications(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        rows = service.list(admitted.tenant_id)
        unread = sum(1 for row in rows if not row["read"])
        return JSONResponse(status_code=200, content={"notifications": rows, "unread": unread})

    @router.post("/{notification_id}/ack")
    async def ack_notification(request: Request, notification_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        if not service.ack(admitted.tenant_id, notification_id):
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown notification id.",
                http_status=404,
            )
        return JSONResponse(status_code=200, content={"acknowledged": notification_id})

    return router
