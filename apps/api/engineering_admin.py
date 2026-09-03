"""Admin seam over the SHARED engineering capability (ADR-0012 §4).

Admin does NOT run tools here. Admin (a) sees status, (b) issues/revokes
bounded authorization tickets, (c) grants engineering WRITE permissions to a
tenant. Every act rides the ONE firewall + ONE ledger the agent runtime uses;
nothing generic lives in this module — it is a thin translation of HTTP into
the shared core/composition calls.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from pydantic import Field

from core.audit.ports import AuditLogPort
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.engineering import EngineeringAct, EngineeringAuthorization
from core.engineering.errors import AuthorizationRefused
from core.engineering.tools import (
    ENGINEERING_READ_PERMISSIONS,
    ENGINEERING_WRITE_PERMISSIONS,
    EngineeringBundle,
)
from core.security.firewall import CapabilityFirewall


class IssueAuthorizationRequest(ContractModel):
    acts: Annotated[list[EngineeringAct], Field(min_length=1, max_length=8)]
    uses: Annotated[int, Field(ge=1, le=1_000)] = 1
    ttl_minutes: Annotated[int, Field(ge=1, le=24 * 60)] = 60
    note: BoundedStr | None = None


class GrantRequest(ContractModel):
    tenant_id: UUID
    permissions: Annotated[list[BoundedStr], Field(min_length=1, max_length=8)]


@dataclass(frozen=True)
class EngineeringAdminSurface:
    """Composition hands ONE of these when AGENT_WORKSPACE_ROOT is configured."""

    bundle: EngineeringBundle
    firewall: CapabilityFirewall
    remote: str
    commands: tuple[str, ...]
    #: Composition-owned write-grant decision (deny-by-default vocabulary).
    grant_writes: Callable[[CapabilityFirewall, UUID, frozenset[str]], frozenset[str]]
    #: R167-A D-09: a grant mutates ANOTHER tenant's policy — must-audit (20 §9
    #: ``security_policy_changed``). None ⇒ composition did not bind audit.
    audit: AuditLogPort | None = None

    def status(self, tenant_id: UUID) -> JsonObject:
        policy = self.firewall.policy_for(tenant_id)
        granted = sorted(policy.granted_permissions) if policy else []
        return {
            "configured": True,
            "workspace_root": self.bundle.workspace_label,
            "remote": self.remote,
            "commands": list(self.commands),
            "read_permissions": sorted(ENGINEERING_READ_PERMISSIONS),
            "write_permissions": sorted(ENGINEERING_WRITE_PERMISSIONS),
            "tenant_granted": granted,
            "acts": [act.value for act in EngineeringAct],
            "authorizations": [_ticket(t) for t in self.bundle.ledger.list_for_tenant(tenant_id)],
        }

    def issue(
        self, tenant_id: UUID, actor_id: UUID, body: IssueAuthorizationRequest
    ) -> EngineeringAuthorization:
        return self.bundle.ledger.issue(
            tenant_id=tenant_id,
            workspace=self.bundle.workspace_label,
            acts=body.acts,
            issued_by=actor_id,
            uses=body.uses,
            ttl=timedelta(minutes=body.ttl_minutes),
            note=body.note,
        )

    def revoke(self, tenant_id: UUID, actor_id: UUID, authorization_id: UUID) -> JsonObject:
        try:
            revoked = self.bundle.ledger.revoke(tenant_id, authorization_id, actor_id=actor_id)
        except AuthorizationRefused as exc:
            return {"revoked": False, "reason": exc.reason}
        return _ticket(revoked)

    def grant(
        self,
        body: GrantRequest,
        *,
        actor_id: UUID | None = None,
        actor_tenant_id: UUID | None = None,
    ) -> JsonObject:
        permissions = frozenset(str(p) for p in body.permissions)
        granted = self.grant_writes(self.firewall, body.tenant_id, permissions)
        if self.audit is not None:
            # Row lands under the TARGET tenant (whose policy changed); the
            # acting admin's identity rides actor_id + actor_tenant_id.
            self.audit.append(
                AuditEvent(
                    tenant_id=body.tenant_id,
                    event_type=AuditEventType.SECURITY_POLICY_CHANGED,
                    actor_id=actor_id,
                    details={
                        "surface": "engineering_grant",
                        "actor_tenant_id": str(actor_tenant_id) if actor_tenant_id else None,
                        "permissions": sorted(permissions),
                        "granted_permissions": sorted(granted),
                        "outcome": "granted",
                    },
                )
            )
        return {"tenant_id": str(body.tenant_id), "granted_permissions": sorted(granted)}


def _ticket(ticket: EngineeringAuthorization) -> JsonObject:
    return ticket.model_dump(mode="json")


__all__ = [
    "EngineeringAdminSurface",
    "GrantRequest",
    "IssueAuthorizationRequest",
]
