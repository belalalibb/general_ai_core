"""T-IMPL-063 tests: tool registry + call gate (FINAL Phase 14, 41 §17).

Exit-list mapping (14 §10, tool-domain items; skill items closed at
T-IMPL-062, verified by name, not redone):

- "tool permission denied by default" ->
  test_undeclared_permission_denied, test_ungranted_permission_denied,
  test_unknown_tenant_denied_through_gate (+ pre-existing firewall suite
  by name: test_unknown_tenant_denied / test_empty_policy_denied).
- "tool approval flow" -> test_approval_required_then_approved_allows,
  test_declared_permission_without_policy_entry_requires_approval,
  test_tool_approval_tightens_a_firewall_allow,
  test_firewall_approval_gate_still_binds_when_tool_relaxes.
- "client device revoked" -> test_client_tool_with_revoked_device_denied
  (+ trusted-device admit, missing-device denied, unknown-device denied,
  hybrid same rule, server needs none).
- "github write requires approval" ->
  test_github_write_requires_approval_by_default (the 14 §4 example
  manifest: commit.create before_action / pr.merge always / repo.read none).
- "skill cannot bypass tool policy" ->
  test_gate_has_no_skill_input (structural: admit() signature carries no
  skill parameter — no channel exists) + pre-existing
  test_selected_skill_tools_remain_inert_data (by name, not redone).
- 41 §17 "every Tool Call passes through the Capability Firewall" ->
  test_firewall_deny_is_final (tool policy can never loosen it) +
  test_gate_consults_firewall_exactly_once.
- 14 §1 "Tool is never trusted by default" -> test_disabled_tool_denied,
  test_registry_selects_active_only (+ contract default DISABLED,
  pre-existing test_manifest_defaults_are_deny_by_default by name).
- 41 §17 client-runtime closed set -> test_client_runtime_kinds_verbatim.

Hermetic: in-memory registries, injected clock — zero I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from core.contracts.security import ActorKind, FirewallDecision, FirewallDecisionInput
from core.contracts.tools import ClientRuntimeKind, Tool
from core.identity.devices import DeviceRegistry
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.tools import (
    DuplicateToolRegistration,
    ToolCallGate,
    ToolNotRegistered,
    ToolNotSelectable,
    ToolRegistry,
)

TENANT = uuid4()
PERM_READ = "github.repo.read"
PERM_COMMIT = "github.commit.create"
PERM_MERGE = "github.pr.merge"


def make_tool(
    *,
    location: str = "server",
    status: str = "active",
    permissions: list[str] | None = None,
    approval_policy: dict[str, str] | None = None,
) -> Tool:
    return Tool.model_validate(
        {
            "id": uuid4(),
            "name": "GitHub",
            "version": "1.0.0",
            "location": location,
            "permissions": (
                permissions
                if permissions is not None
                else [PERM_READ, PERM_COMMIT, PERM_MERGE]
            ),
            "approval_policy": (
                approval_policy
                if approval_policy is not None
                # The 14 §4 example, verbatim values.
                else {
                    PERM_READ: "none",
                    PERM_COMMIT: "before_action",
                    PERM_MERGE: "always",
                }
            ),
            "status": status,
        }
    )


def make_request(
    *,
    permission: str = PERM_READ,
    tenant_id: UUID = TENANT,
    approval_state: str | None = None,
) -> FirewallDecisionInput:
    return FirewallDecisionInput(
        actor=ActorKind.USER,
        tenant_id=tenant_id,
        permission=permission,
        resource="repo:owner/name",
        scope="project",
        entitlement="github_write",
        approval_state=approval_state,  # type: ignore[arg-type]
        risk_level="medium",
    )


def granting_firewall(
    *,
    tenant_id: UUID = TENANT,
    permissions: frozenset[str] = frozenset({PERM_READ, PERM_COMMIT, PERM_MERGE}),
    approval_gated: frozenset[str] = frozenset(),
) -> CapabilityFirewall:
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(
        tenant_id,
        TenantPolicy(
            granted_permissions=permissions,
            granted_entitlements=frozenset({"github_write"}),
            approval_gated_permissions=approval_gated,
        ),
    )
    return firewall


def make_gate(
    tool: Tool,
    *,
    firewall: CapabilityFirewall | None = None,
    devices: DeviceRegistry | None = None,
) -> ToolCallGate:
    registry = ToolRegistry()
    registry.register(tool)
    return ToolCallGate(
        tools=registry,
        firewall=firewall if firewall is not None else granting_firewall(),
        devices=devices if devices is not None else DeviceRegistry(),
    )


# --- registry ------------------------------------------------------------------------


def test_register_get_and_duplicate_rejected() -> None:
    registry = ToolRegistry()
    tool = make_tool()
    registry.register(tool)
    assert registry.get(tool.id).id == tool.id
    with pytest.raises(DuplicateToolRegistration):
        registry.register(tool)


def test_unknown_tool_raises_not_registered() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotRegistered):
        registry.get(uuid4())


def test_registry_selects_active_only() -> None:
    """14 §1: disabled tools are loadable-but-never-callable."""
    registry = ToolRegistry()
    active = make_tool()
    disabled = make_tool(status="disabled")
    registry.register(active)
    registry.register(disabled)
    assert registry.select(active.id).id == active.id
    with pytest.raises(ToolNotSelectable) as exc:
        registry.select(disabled.id)
    assert exc.value.status == "disabled"
    assert [t.id for t in registry.list_selectable()] == [active.id]
    assert len(registry.list_all()) == 2


# --- gate: deny-by-default ------------------------------------------------------------


def test_disabled_tool_denied() -> None:
    tool = make_tool(status="disabled")
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request())
    assert not decision.admitted
    assert decision.decision is FirewallDecision.DENY
    assert decision.reason == "tool_not_selectable:disabled"


def test_undeclared_permission_denied() -> None:
    """A call naming a permission the tool never declared is refused."""
    tool = make_tool(permissions=[PERM_READ], approval_policy={PERM_READ: "none"})
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_MERGE))
    assert not decision.admitted
    assert decision.reason == f"permission_undeclared:{PERM_MERGE}"


def test_ungranted_permission_denied() -> None:
    """Declared by the tool but not granted by the firewall -> DENY."""
    tool = make_tool()
    firewall = granting_firewall(permissions=frozenset({PERM_COMMIT}))
    gate = make_gate(tool, firewall=firewall)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_READ))
    assert not decision.admitted
    assert decision.reason == "firewall_deny"


def test_unknown_tenant_denied_through_gate() -> None:
    tool = make_tool()
    gate = make_gate(tool)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(tenant_id=uuid4())
    )
    assert not decision.admitted
    assert decision.decision is FirewallDecision.DENY


# --- gate: approval flow (14 §4 example semantics) -------------------------------------


def test_github_write_requires_approval_by_default() -> None:
    """14 §8/§10: commit.create (before_action) unapproved -> REQUIRE_APPROVAL."""
    tool = make_tool()
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_COMMIT))
    assert not decision.admitted
    assert decision.decision is FirewallDecision.REQUIRE_APPROVAL
    assert decision.reason == "tool_approval_required:before_action"


def test_approval_required_then_approved_allows() -> None:
    tool = make_tool()
    gate = make_gate(tool)
    unapproved = gate.admit(
        tool_id=tool.id, request=make_request(permission=PERM_MERGE)
    )
    assert unapproved.decision is FirewallDecision.REQUIRE_APPROVAL
    approved = gate.admit(
        tool_id=tool.id,
        request=make_request(permission=PERM_MERGE, approval_state="approved"),
    )
    assert approved.admitted
    assert approved.decision is FirewallDecision.ALLOW


def test_read_with_approval_none_allows_without_approval() -> None:
    """repo.read: approval_policy 'none' -> ALLOW with no approval_state."""
    tool = make_tool()
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_READ))
    assert decision.admitted
    assert decision.decision is FirewallDecision.ALLOW


def test_declared_permission_without_policy_entry_requires_approval() -> None:
    """Deny-by-default: absent approval_policy entry resolves to ALWAYS."""
    tool = make_tool(permissions=[PERM_READ], approval_policy={})
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_READ))
    assert not decision.admitted
    assert decision.reason == "tool_approval_required:always"


def test_tool_approval_tightens_a_firewall_allow() -> None:
    """Firewall says ALLOW; the tool's own policy still gates (14 §4)."""
    tool = make_tool()  # merge: always
    firewall = granting_firewall()  # no firewall-side approval gate
    gate = make_gate(tool, firewall=firewall)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_MERGE))
    assert decision.decision is FirewallDecision.REQUIRE_APPROVAL


def test_firewall_approval_gate_still_binds_when_tool_relaxes() -> None:
    """Tool policy 'none' can never LOOSEN a firewall approval gate."""
    tool = make_tool(permissions=[PERM_READ], approval_policy={PERM_READ: "none"})
    firewall = granting_firewall(approval_gated=frozenset({PERM_READ}))
    gate = make_gate(tool, firewall=firewall)
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_READ))
    assert not decision.admitted
    assert decision.decision is FirewallDecision.REQUIRE_APPROVAL
    assert decision.reason == "firewall_requires_approval"


def test_firewall_deny_is_final() -> None:
    """41 §17: no tool-side policy loosens a firewall DENY — approved or not."""
    tool = make_tool(permissions=[PERM_READ], approval_policy={PERM_READ: "none"})
    firewall = CapabilityFirewall()  # no tenant policy at all
    gate = make_gate(tool, firewall=firewall)
    decision = gate.admit(
        tool_id=tool.id,
        request=make_request(permission=PERM_READ, approval_state="approved"),
    )
    assert not decision.admitted
    assert decision.decision is FirewallDecision.DENY


# --- gate: device trust (14 §6/§9, client/hybrid tools) --------------------------------


def trusted_device(devices: DeviceRegistry) -> UUID:
    device = devices.pair(tenant_id=TENANT, user_id=uuid4(), name="laptop")
    devices.trust(device.id)
    return device.id


def test_server_tool_needs_no_device() -> None:
    tool = make_tool(location="server")
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request())
    assert decision.admitted


def test_client_tool_without_device_denied() -> None:
    """14 §9: 'Client tool runs on server by assumption' is forbidden."""
    tool = make_tool(location="client")
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request())
    assert not decision.admitted
    assert decision.reason == "device_required:client"


def test_client_tool_with_trusted_device_admitted() -> None:
    tool = make_tool(location="client")
    devices = DeviceRegistry(clock=lambda: datetime(2026, 8, 28, tzinfo=UTC))
    device_id = trusted_device(devices)
    gate = make_gate(tool, devices=devices)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(), device_id=device_id
    )
    assert decision.admitted


def test_client_tool_with_revoked_device_denied() -> None:
    """14 §10 'client device revoked': revocation kills tool access."""
    tool = make_tool(location="client")
    devices = DeviceRegistry(clock=lambda: datetime(2026, 8, 28, tzinfo=UTC))
    device_id = trusted_device(devices)
    devices.revoke(device_id)
    gate = make_gate(tool, devices=devices)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(), device_id=device_id
    )
    assert not decision.admitted
    assert decision.reason == "device_not_trusted"


def test_client_tool_with_merely_paired_device_denied() -> None:
    """Paired-but-untrusted is not usable (41 §1 rule 9)."""
    tool = make_tool(location="client")
    devices = DeviceRegistry(clock=lambda: datetime(2026, 8, 28, tzinfo=UTC))
    device = devices.pair(tenant_id=TENANT, user_id=uuid4(), name="laptop")
    gate = make_gate(tool, devices=devices)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(), device_id=device.id
    )
    assert not decision.admitted
    assert decision.reason == "device_not_trusted"


def test_client_tool_with_unknown_device_denied() -> None:
    tool = make_tool(location="client")
    gate = make_gate(tool)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(), device_id=uuid4()
    )
    assert not decision.admitted
    assert decision.reason == "device_unknown"


def test_foreign_tenant_device_behaves_as_unknown() -> None:
    """Anti-enumeration parity (20 §6): a foreign-tenant device id is
    indistinguishable from an absent one."""
    tool = make_tool(location="client")
    devices = DeviceRegistry(clock=lambda: datetime(2026, 8, 28, tzinfo=UTC))
    foreign = devices.pair(tenant_id=uuid4(), user_id=uuid4(), name="other")
    devices.trust(foreign.id)
    gate = make_gate(tool, devices=devices)
    decision = gate.admit(
        tool_id=tool.id, request=make_request(), device_id=foreign.id
    )
    assert not decision.admitted
    assert decision.reason == "device_unknown"


def test_hybrid_tool_follows_the_client_device_rule() -> None:
    tool = make_tool(location="hybrid")
    gate = make_gate(tool)
    decision = gate.admit(tool_id=tool.id, request=make_request())
    assert not decision.admitted
    assert decision.reason == "device_required:hybrid"


# --- structural guarantees --------------------------------------------------------------


def test_gate_has_no_skill_input() -> None:
    """03 §8/14 §9 'skill cannot bypass tool policy': structurally, the
    gate's admission surface carries NO skill parameter — no channel
    exists through which a requiring skill could alter the verdict."""
    import inspect

    params = set(inspect.signature(ToolCallGate.admit).parameters)
    assert params == {"self", "tool_id", "request", "device_id"}
    source = inspect.getsource(ToolCallGate)
    assert "skill" not in source.lower()


def test_gate_consults_firewall_exactly_once() -> None:
    """41 §17: the firewall is consulted on every admitted path — once."""
    tool = make_tool()
    calls: list[FirewallDecisionInput] = []

    class CountingFirewall(CapabilityFirewall):
        def decide(self, request: FirewallDecisionInput) -> FirewallDecision:
            calls.append(request)
            return super().decide(request)

    firewall = CountingFirewall()
    firewall.set_tenant_policy(
        TENANT,
        TenantPolicy(
            granted_permissions=frozenset({PERM_READ}),
            granted_entitlements=frozenset({"github_write"}),
        ),
    )
    registry = ToolRegistry()
    registry.register(tool)
    gate = ToolCallGate(tools=registry, firewall=firewall, devices=DeviceRegistry())
    decision = gate.admit(tool_id=tool.id, request=make_request(permission=PERM_READ))
    assert decision.admitted
    assert len(calls) == 1


def test_unknown_tool_id_raises_not_registered() -> None:
    """Absent tool = caller error (raise), not a policy verdict."""
    gate = ToolCallGate(
        tools=ToolRegistry(), firewall=granting_firewall(), devices=DeviceRegistry()
    )
    with pytest.raises(ToolNotRegistered):
        gate.admit(tool_id=uuid4(), request=make_request())


def test_client_runtime_kinds_verbatim() -> None:
    """41 §17 client-runtime list — closed set, verbatim (snake_case)."""
    assert {k.value for k in ClientRuntimeKind} == {
        "browser",
        "filesystem",
        "terminal",
        "ide",
        "local_project",
    }


def test_gate_executes_nothing_and_imports_no_io() -> None:
    """The gate decides admission only — zero transport/execution code."""
    import inspect

    import core.tools.errors as errors_mod
    import core.tools.gate as gate_mod
    import core.tools.registry as registry_mod

    for mod in (gate_mod, registry_mod, errors_mod):
        source = inspect.getsource(mod)
        for banned in ("httpx", "requests", "urllib", "socket", "subprocess", "aiohttp"):
            assert banned not in source, f"{mod.__name__} references {banned}"
