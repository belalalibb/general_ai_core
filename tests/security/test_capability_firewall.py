"""Capability Firewall skeleton tests (MVP Phase 2, 41 §41).

Verifies the deterministic deny-by-default evaluator over the 20 §4
decision contract: DENY unless explicitly granted; REQUIRE_APPROVAL for
approval-gated permissions without approval (20 §8); ALLOW_WITH_LIMIT for
limit-bounded grants; tenant policy never leaks across tenants (20 §6).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.contracts.security import (
    ActorKind,
    FirewallDecision,
    FirewallDecisionInput,
)
from core.security import CapabilityFirewall, TenantPolicy


def _request(
    tenant_id: UUID,
    *,
    permission: str = "github.pr.create",
    entitlement: str = "github_write",
    approval_state: str | None = None,
) -> FirewallDecisionInput:
    return FirewallDecisionInput.model_validate(
        {
            "actor": "user",
            "tenant_id": str(tenant_id),
            "permission": permission,
            "resource": "repo:owner/name",
            "scope": "project",
            "entitlement": entitlement,
            "approval_state": approval_state,
            "risk_level": "medium",
        }
    )


@pytest.fixture()
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture()
def firewall() -> CapabilityFirewall:
    return CapabilityFirewall()


class TestDenyByDefault:
    def test_unknown_tenant_denied(self, firewall: CapabilityFirewall, tenant_id: UUID) -> None:
        assert firewall.decide(_request(tenant_id)) is FirewallDecision.DENY

    def test_empty_policy_denied(self, firewall: CapabilityFirewall, tenant_id: UUID) -> None:
        firewall.set_tenant_policy(tenant_id, TenantPolicy())
        assert firewall.decide(_request(tenant_id)) is FirewallDecision.DENY

    def test_permission_granted_but_entitlement_missing_denied(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(granted_permissions=frozenset({"github.pr.create"})),
        )
        assert firewall.decide(_request(tenant_id)) is FirewallDecision.DENY

    def test_entitlement_held_but_permission_missing_denied(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(granted_entitlements=frozenset({"github_write"})),
        )
        assert firewall.decide(_request(tenant_id)) is FirewallDecision.DENY

    def test_approval_never_bypasses_grants(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        """approved + ungranted is still DENY (no approval-as-grant)."""
        firewall.set_tenant_policy(tenant_id, TenantPolicy())
        request = _request(tenant_id, approval_state="approved")
        assert firewall.decide(request) is FirewallDecision.DENY


class TestExplicitAllow:
    def test_full_grant_allows(self, firewall: CapabilityFirewall, tenant_id: UUID) -> None:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({"github.pr.create"}),
                granted_entitlements=frozenset({"github_write"}),
            ),
        )
        assert firewall.decide(_request(tenant_id)) is FirewallDecision.ALLOW

    def test_decision_is_deterministic(self, firewall: CapabilityFirewall, tenant_id: UUID) -> None:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({"github.pr.create"}),
                granted_entitlements=frozenset({"github_write"}),
            ),
        )
        results = {firewall.decide(_request(tenant_id)) for _ in range(10)}
        assert results == {FirewallDecision.ALLOW}

    def test_system_actor_follows_same_policy(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        """20 §1: authority is policy-driven for user AND system actors."""
        firewall.set_tenant_policy(tenant_id, TenantPolicy())
        request = FirewallDecisionInput(
            actor=ActorKind.SYSTEM,
            tenant_id=tenant_id,
            permission="github.pr.create",
            resource="repo:owner/name",
            scope="project",
            entitlement="github_write",
            risk_level="medium",
        )
        assert firewall.decide(request) is FirewallDecision.DENY


class TestApprovalGate:
    @pytest.fixture()
    def gated_firewall(self, firewall: CapabilityFirewall, tenant_id: UUID) -> CapabilityFirewall:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({"github.pr.merge"}),
                granted_entitlements=frozenset({"github_write"}),
                approval_gated_permissions=frozenset({"github.pr.merge"}),
            ),
        )
        return firewall

    def test_unapproved_requires_approval(
        self, gated_firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        """20 §8: PR merge class requires approval — null state must gate."""
        request = _request(tenant_id, permission="github.pr.merge")
        assert gated_firewall.decide(request) is FirewallDecision.REQUIRE_APPROVAL

    def test_approved_allows(self, gated_firewall: CapabilityFirewall, tenant_id: UUID) -> None:
        request = _request(tenant_id, permission="github.pr.merge", approval_state="approved")
        assert gated_firewall.decide(request) is FirewallDecision.ALLOW


class TestAllowWithLimit:
    def test_limited_permission_allows_with_limit(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({"model.invoke"}),
                granted_entitlements=frozenset({"model_use"}),
                limited_permissions=frozenset({"model.invoke"}),
            ),
        )
        request = _request(tenant_id, permission="model.invoke", entitlement="model_use")
        assert firewall.decide(request) is FirewallDecision.ALLOW_WITH_LIMIT

    def test_approval_gate_evaluated_before_limit(
        self, firewall: CapabilityFirewall, tenant_id: UUID
    ) -> None:
        """Most-restrictive-first: gated + limited + unapproved => REQUIRE_APPROVAL."""
        firewall.set_tenant_policy(
            tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({"terminal.exec"}),
                granted_entitlements=frozenset({"terminal_use"}),
                approval_gated_permissions=frozenset({"terminal.exec"}),
                limited_permissions=frozenset({"terminal.exec"}),
            ),
        )
        request = _request(tenant_id, permission="terminal.exec", entitlement="terminal_use")
        assert firewall.decide(request) is FirewallDecision.REQUIRE_APPROVAL
        approved = _request(
            tenant_id,
            permission="terminal.exec",
            entitlement="terminal_use",
            approval_state="approved",
        )
        assert firewall.decide(approved) is FirewallDecision.ALLOW_WITH_LIMIT


class TestTenantIsolation:
    def test_grants_do_not_leak_across_tenants(self, firewall: CapabilityFirewall) -> None:
        """20 §6: tenant A's grants never authorize tenant B."""
        tenant_a, tenant_b = uuid4(), uuid4()
        firewall.set_tenant_policy(
            tenant_a,
            TenantPolicy(
                granted_permissions=frozenset({"github.pr.create"}),
                granted_entitlements=frozenset({"github_write"}),
            ),
        )
        assert firewall.decide(_request(tenant_a)) is FirewallDecision.ALLOW
        assert firewall.decide(_request(tenant_b)) is FirewallDecision.DENY
