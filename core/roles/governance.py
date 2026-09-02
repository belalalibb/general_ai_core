"""Role governance — 41 §15 (FINAL Phase 12): system vs custom role control.

Authority (41 §15 verbatim): "System Roles: admin-controlled. Custom
Roles: user/project created." and "Security: a Custom Role never grants
permissions."

Recorded derivations (the doc states rules, not an interface):

- Scope split — 03 §6 RoleScope has four values; SYSTEM is the one 41 §15
  places under admin control; TENANT/USER/PROJECT are the custom side
  ("user/project created"; TENANT rides with the custom side because it
  is tenant-created, not platform-admin-created — the only reading that
  leaves no scope ungoverned; recorded, and trivially re-partitionable
  as data).
- The gate answers "may THIS actor register a role of THIS scope?" as an
  explicit decision naming the refusing rule (11 §14 posture). It does
  not authenticate the actor — ``is_admin`` arrives resolved from the
  identity layer (same seam posture as apps/api).
- "A Custom Role never grants permissions" is enforced at TWO layers:
  (1) universally by the contract itself (03 §8: ``capabilities_
  requested`` is never a grant — verbatim in core/contracts/roles.py);
  (2) here as REGISTRATION data hygiene — a custom role that arrives
  REQUESTING capabilities is admitted (requesting is legal, 03 §8) but
  the decision records the requests so the Capability Firewall layer
  sees exactly what was asked; nothing here or anywhere in Core turns a
  request into a grant. NO invented restriction: 41 §15 forbids
  GRANTING, not requesting — refusing custom-role requests outright
  would contradict 03 §8.
- Deny-by-default (41 §1 rule 9): unknown/unmapped scope refuses; the
  non-admin default refuses SYSTEM registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.contracts.roles import Role, RoleScope
from core.roles.registry import RoleRegistry

# 41 §15 partition: admin-controlled vs user/project-created (recorded above).
SYSTEM_SCOPES: frozenset[RoleScope] = frozenset({RoleScope.SYSTEM})
CUSTOM_SCOPES: frozenset[RoleScope] = frozenset(
    {RoleScope.TENANT, RoleScope.USER, RoleScope.PROJECT}
)


@dataclass(frozen=True)
class RoleAdmissionDecision:
    """Explicit admit/refuse outcome — refusals name the rule (11 §14)."""

    admitted: bool
    reason: str | None = None
    capabilities_requested: tuple[str, ...] = field(default_factory=tuple)


class RoleGovernance:
    """Registration gate over a :class:`RoleRegistry` (41 §15 control split)."""

    def __init__(self, registry: RoleRegistry) -> None:
        self._registry = registry

    def evaluate(self, role: Role, *, is_admin: bool) -> RoleAdmissionDecision:
        """Answer 41 §15's control question without writing anything."""
        if role.scope in SYSTEM_SCOPES:
            if not is_admin:
                return RoleAdmissionDecision(admitted=False, reason="system_role_requires_admin")
        elif role.scope not in CUSTOM_SCOPES:  # pragma: no cover — closed enum
            return RoleAdmissionDecision(admitted=False, reason="scope_ungoverned")
        return RoleAdmissionDecision(
            admitted=True,
            capabilities_requested=tuple(role.capabilities_requested),
        )

    def register(self, role: Role, *, is_admin: bool) -> RoleAdmissionDecision:
        """Evaluate, then register on admit (refusal writes nothing)."""
        decision = self.evaluate(role, is_admin=is_admin)
        if decision.admitted:
            self._registry.register(role)
        return decision
