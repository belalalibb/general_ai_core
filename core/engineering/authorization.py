"""Admin-issued, bounded, consumable authorizations (ADR-0012 §2/§4).

    Admin issues ticket ─► ledger stores it (APPROVAL_DECISION audit, act=issue)
    agent proposes act with authorization_id ─► ledger.consume(...)
        ├─ covered → one use burned (APPROVAL_DECISION, act=consume)
        └─ refused → AuthorizationRefused DATA (APPROVAL_DECISION, act=refuse)

Bounded on every axis: tenant, workspace label, act set, uses, expiry,
revocation. No new audit event types — act detail rides ``details``.
Storage is an in-process dict (same dev/test posture as the R3 in-memory
proposal store); a durable port is a future adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NoReturn
from uuid import UUID

from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject, utc_now
from core.contracts.engineering import EngineeringAct, EngineeringAuthorization
from core.engineering.errors import AuthorizationRefused

#: Hard ceiling on a ticket's lifetime (composition may only shorten).
MAX_TTL = timedelta(hours=24)


class AuthorizationLedger:
    """Issue / revoke / consume engineering authorizations (tenant-scoped)."""

    def __init__(
        self,
        audit: AuditLogPort,
        *,
        clock: Callable[[], datetime] = utc_now,
        max_ttl: timedelta = MAX_TTL,
    ) -> None:
        self._audit = audit
        self._clock = clock
        self._max_ttl = min(max_ttl, MAX_TTL)
        self._tickets: dict[UUID, EngineeringAuthorization] = {}

    def issue(
        self,
        *,
        tenant_id: UUID,
        workspace: str,
        acts: list[EngineeringAct],
        issued_by: UUID,
        uses: int = 1,
        ttl: timedelta | None = None,
        note: str | None = None,
    ) -> EngineeringAuthorization:
        now = self._clock()
        lifetime = self._max_ttl if ttl is None else min(ttl, self._max_ttl)
        if lifetime <= timedelta(0):
            raise AuthorizationRefused("ttl must be positive")
        ticket = EngineeringAuthorization(
            tenant_id=tenant_id,
            workspace=workspace,
            acts=sorted(set(acts), key=str),
            uses_remaining=uses,
            expires_at=now + lifetime,
            issued_by=issued_by,
            issued_at=now,
            note=note,
        )
        self._tickets[ticket.id] = ticket
        self._record(ticket, actor_id=issued_by, act="issue")
        return ticket

    def revoke(
        self, tenant_id: UUID, authorization_id: UUID, *, actor_id: UUID
    ) -> EngineeringAuthorization:
        ticket = self._tickets.get(authorization_id)
        if ticket is None or ticket.tenant_id != tenant_id:
            raise AuthorizationRefused("authorization unknown")
        revoked = ticket.model_copy(update={"revoked": True})
        self._tickets[ticket.id] = revoked
        self._record(revoked, actor_id=actor_id, act="revoke")
        return revoked

    def list_for_tenant(self, tenant_id: UUID) -> list[EngineeringAuthorization]:
        return sorted(
            (t for t in self._tickets.values() if t.tenant_id == tenant_id),
            key=lambda t: t.issued_at,
        )

    def consume(
        self,
        *,
        tenant_id: UUID,
        workspace: str,
        act: EngineeringAct,
        authorization_id: UUID | None,
        actor_id: UUID | None,
        detail: JsonObject | None = None,
    ) -> EngineeringAuthorization:
        """Burn one use of a covering ticket or refuse (both audited)."""
        if authorization_id is None:
            self._refuse(tenant_id, act, None, actor_id, "authorization_id missing", detail)
        ticket = self._tickets.get(authorization_id)
        # Absent and foreign-tenant are indistinguishable (20 §6).
        if ticket is None or ticket.tenant_id != tenant_id:
            self._refuse(
                tenant_id, act, authorization_id, actor_id, "authorization unknown", detail
            )
        reason: str | None = None
        if ticket.revoked:
            reason = "authorization revoked"
        elif ticket.workspace != workspace:
            reason = "authorization is for another workspace"
        elif act not in ticket.acts:
            reason = f"authorization does not cover act {act.value}"
        elif ticket.uses_remaining <= 0:
            reason = "authorization exhausted"
        elif self._clock() >= ticket.expires_at:
            reason = "authorization expired"
        if reason is not None:
            self._refuse(tenant_id, act, authorization_id, actor_id, reason, detail)
        burned = ticket.model_copy(update={"uses_remaining": ticket.uses_remaining - 1})
        self._tickets[ticket.id] = burned
        self._record(
            burned,
            actor_id=actor_id,
            act="consume",
            extra={"engineering_act": act.value, **(detail or {})},
        )
        return burned

    def consume_ticket(
        self,
        *,
        authorization_id: UUID | None,
        workspace: str,
        act: EngineeringAct,
        actor_id: UUID | None = None,
        detail: JsonObject | None = None,
    ) -> EngineeringAuthorization:
        """Consume by ticket id alone (tenant derived FROM the ticket).

        Used by tool handlers, which receive only the model's arguments: the
        tenant's permission was already decided by the ONE firewall before the
        handler ran, so the ticket binds the remaining axes (workspace, act,
        uses, expiry, revocation). An unknown id is audited under the NIL
        tenant so the refusal is still evidence.
        """
        ticket = self._tickets.get(authorization_id) if authorization_id else None
        if ticket is None:
            reason = "authorization_id missing" if authorization_id is None else "authorization unknown"
            self._refuse(UUID(int=0), act, authorization_id, actor_id, reason, detail)
        return self.consume(
            tenant_id=ticket.tenant_id,
            workspace=workspace,
            act=act,
            authorization_id=authorization_id,
            actor_id=actor_id,
            detail=detail,
        )

    def _refuse(
        self,
        tenant_id: UUID,
        act: EngineeringAct,
        authorization_id: UUID | None,
        actor_id: UUID | None,
        reason: str,
        detail: JsonObject | None,
    ) -> NoReturn:
        self._audit.append(
            AuditEvent(
                tenant_id=tenant_id,
                event_type=AuditEventType.APPROVAL_DECISION,
                actor_id=actor_id,
                details={
                    "surface": "engineering_authorization",
                    "act": "refuse",
                    "engineering_act": act.value,
                    "authorization_id": str(authorization_id) if authorization_id else None,
                    "reason": reason,
                    **(detail or {}),
                },
            )
        )
        raise AuthorizationRefused(reason)

    def _record(
        self,
        ticket: EngineeringAuthorization,
        *,
        actor_id: UUID | None,
        act: str,
        extra: JsonObject | None = None,
    ) -> None:
        self._audit.append(
            AuditEvent(
                tenant_id=ticket.tenant_id,
                event_type=AuditEventType.APPROVAL_DECISION,
                actor_id=actor_id,
                details={
                    "surface": "engineering_authorization",
                    "act": act,
                    "authorization_id": str(ticket.id),
                    "workspace": ticket.workspace,
                    "acts": [a.value for a in ticket.acts],
                    "uses_remaining": ticket.uses_remaining,
                    "expires_at": ticket.expires_at.isoformat(),
                    "revoked": ticket.revoked,
                    **(extra or {}),
                },
            )
        )


__all__ = ["MAX_TTL", "AuthorizationLedger"]
