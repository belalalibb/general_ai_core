"""Capability Firewall skeleton — deterministic deny-by-default evaluator.

Spec anchors:

- 20 §1: security boundaries enforced by deterministic platform code, not
  prompts; the LLM is untrusted for authority decisions (the contract layer
  already excludes an "llm" actor kind).
- 20 §4: decision inputs (``FirewallDecisionInput``) and the closed output
  set ``ALLOW | DENY | ALLOW_WITH_LIMIT | REQUIRE_APPROVAL``.
- 20 §8: approval-required action classes — for approval-gated permissions
  an unapproved request yields ``REQUIRE_APPROVAL``, never ALLOW.
- 20 §3 / 41 Phase 2 security list: deny-by-default — anything not
  explicitly granted is DENY.

Skeleton scope (MVP Phase 2, 41 §41 "capability firewall skeleton"):

- Policy state (which permissions/entitlements a tenant holds, which
  permissions are approval-gated or limit-bounded) is injected as in-memory
  ``TenantPolicy`` records. Admin-configurable catalogs, persistence, and
  audit emission are later-phase bindings.
- Evaluation order (most-restrictive-first, deny-by-default):

  1. tenant has no policy record            -> DENY
  2. permission not granted                 -> DENY
  3. entitlement not held                   -> DENY
  4. permission approval-gated + unapproved -> REQUIRE_APPROVAL
  5. permission limit-bounded               -> ALLOW_WITH_LIMIT
  6. otherwise                              -> ALLOW

  ``approval_state == "approved"`` never bypasses grant checks: an
  approved-but-ungranted request is still DENY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from core.contracts.security import FirewallDecision, FirewallDecisionInput


@dataclass(frozen=True)
class TenantPolicy:
    """In-memory grant/gate state for one tenant (skeleton policy source).

    - ``granted_permissions`` / ``granted_entitlements``: explicit grants;
      absence means DENY (deny-by-default).
    - ``approval_gated_permissions``: permissions in the 20 §8 approval
      classes; requests without ``approval_state == "approved"`` yield
      REQUIRE_APPROVAL.
    - ``limited_permissions``: permissions granted only with a quota/limit
      envelope; allowed requests yield ALLOW_WITH_LIMIT (limit enforcement
      itself is a later-phase concern).
    """

    granted_permissions: frozenset[str] = frozenset()
    granted_entitlements: frozenset[str] = frozenset()
    approval_gated_permissions: frozenset[str] = frozenset()
    limited_permissions: frozenset[str] = frozenset()


@dataclass
class CapabilityFirewall:
    """Deterministic deny-by-default evaluator (20 §4 skeleton)."""

    _policies: dict[UUID, TenantPolicy] = field(default_factory=dict)

    def set_tenant_policy(self, tenant_id: UUID, policy: TenantPolicy) -> None:
        """Install/replace the policy record for a tenant."""
        self._policies[tenant_id] = policy

    def policy_for(self, tenant_id: UUID) -> TenantPolicy | None:
        """The installed policy record (None ⇒ deny-by-default). Read-only."""
        return self._policies.get(tenant_id)

    def decide(self, request: FirewallDecisionInput) -> FirewallDecision:
        """Evaluate one request to exactly one explicit decision.

        Pure and deterministic: same input + same policy state => same
        decision. No implicit allow exists on any path.
        """
        policy = self._policies.get(request.tenant_id)
        if policy is None:
            return FirewallDecision.DENY
        if request.permission not in policy.granted_permissions:
            return FirewallDecision.DENY
        if request.entitlement not in policy.granted_entitlements:
            return FirewallDecision.DENY
        if (
            request.permission in policy.approval_gated_permissions
            and request.approval_state != "approved"
        ):
            return FirewallDecision.REQUIRE_APPROVAL
        if request.permission in policy.limited_permissions:
            return FirewallDecision.ALLOW_WITH_LIMIT
        return FirewallDecision.ALLOW
