"""Tool call gate — Phase 14 Tool Fabric (T-IMPL-063).

Spec anchors:

- 41 §17 (verbatim): "Security: every Tool Call passes through the
  Capability Firewall." — the gate is that single mandatory path; there is
  NO tool-call admission API in core that skips it.
- 03 §8 (verbatim): "Tool calls require Capability Firewall approval." /
  "Skill can require Tools but cannot bypass Tool permissions."
- 14 §1: "Tool is never trusted by default." 14 §7: the ten-item check
  list. 14 §9 (forbidden): "Tool executes without Capability Firewall." /
  "Client tool runs on server by assumption." / "Skill grants security
  permissions." / "LLM decides final permission."
- 20 §4: FirewallDecisionInput / the closed decision set (pre-existing
  contract + CapabilityFirewall skeleton, MVP Phase 2 — reused, not
  rebuilt).

Recorded derivations (nothing invented silently):

- 14 §7 lists ten checks. Mapping against what EXISTS: identity / tenant /
  permission / entitlement / scope / approval policy arrive as
  FirewallDecisionInput fields and are decided by the EXISTING
  CapabilityFirewall (its evaluation order is already deny-by-default);
  resource ownership rides the ``resource`` input (ownership RESOLUTION is
  an infrastructure lookup, recorded not claimed). The gate ADDS the
  checks the firewall cannot know: tool status (14 §1), permission
  DECLARATION (a call naming a permission the tool never declared is a
  refusal — same posture as ToolManifest.approval_for), tool location vs
  device trust (14 §9 "Client tool runs on server by assumption" — a
  client/hybrid tool call must present a TRUSTED device), and the tool's
  OWN approval_policy (14 §4) composed WITH the firewall verdict.
- CHECK ORDER follows FIREWALL_CHECK_ORDER's spirit: cheap structural
  refusals (tool status, permission declared, device trust) run first and
  are DENY-equivalent (naming the failed check); the firewall then decides
  grants; tool approval policy tightens the verdict LAST — tightening
  only, never loosening: a firewall DENY stays DENY regardless of tool
  policy; a firewall ALLOW with an unmet tool approval requirement becomes
  REQUIRE_APPROVAL (most-restrictive-wins; both authorities must consent).
- SKILL CANNOT BYPASS (03 §8 / 14 §9): the gate takes NO skill parameter
  at all — there is no input through which a requiring skill could alter
  the verdict. Structural, tested.
- LLM NEVER DECIDES (14 §9): ActorKind is user|system only (20 §4 contract
  already excludes an llm actor); the gate adds no channel.
- DEVICE RULE: location=server needs no device; client/hybrid REQUIRE a
  device_id whose DeviceRegistry.is_usable is True (trusted only, 41 §1
  rule 9). A missing device for a client tool refuses — deny-by-default.
- Rate limit + audit (14 §7 items 9–10): the RATE LIMIT check binds
  through the EXISTING RateLimitPort at the composition root (the runtime
  AdmissionController already owns windowing); AUDIT emission belongs to
  the audit subsystem. The gate returns an explicit decision object so
  both can consume it; neither is silently claimed (41 §49).
- The gate is PURE apart from reads: it executes NOTHING. Tool execution
  (transport, sandboxing) is deployment/adapter territory — core decides
  admission only.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from core.contracts.security import FirewallDecision, FirewallDecisionInput
from core.contracts.tools import ApprovalRequirement, Tool, ToolLocation
from core.identity.devices import DeviceNotFound, DeviceRegistry
from core.security.firewall import CapabilityFirewall
from core.tools.errors import ToolFabricError, ToolNotSelectable
from core.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolCallDecision:
    """Explicit admit/refuse outcome for one tool call (11 §14).

    ``decision`` is the composed verdict in the closed 20 §4 set;
    ``admitted`` is True only for ALLOW / ALLOW_WITH_LIMIT. Refusals and
    approval requirements NAME the check that produced them.
    """

    admitted: bool
    decision: FirewallDecision
    reason: str | None = None


class ToolCallGate:
    """The single mandatory admission path for tool calls (41 §17)."""

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        firewall: CapabilityFirewall,
        devices: DeviceRegistry,
    ) -> None:
        self._tools = tools
        self._firewall = firewall
        self._devices = devices

    def admit(
        self,
        *,
        tool_id: UUID,
        request: FirewallDecisionInput,
        device_id: UUID | None = None,
    ) -> ToolCallDecision:
        """Decide one tool call. Executes nothing; every path is explicit.

        Unknown tool ids raise (ToolNotRegistered — absent is a caller
        error, not a policy verdict); every POLICY refusal returns a
        DENY/REQUIRE_APPROVAL decision naming the check.
        """
        # 1. Tool status (14 §1: never trusted by default; active only).
        try:
            tool = self._tools.select(tool_id)
        except ToolNotSelectable as exc:
            return ToolCallDecision(
                admitted=False,
                decision=FirewallDecision.DENY,
                reason=f"tool_not_selectable:{exc.status}",
            )

        # 2. Permission must be DECLARED by the tool (undeclared = refusal,
        #    same posture as ToolManifest.approval_for).
        if request.permission not in tool.permissions:
            return ToolCallDecision(
                admitted=False,
                decision=FirewallDecision.DENY,
                reason=f"permission_undeclared:{request.permission}",
            )

        # 3. Location vs device trust (14 §9: client tool never runs on
        #    server by assumption; trusted devices only).
        device_reason = self._check_device(tool, request.tenant_id, device_id)
        if device_reason is not None:
            return ToolCallDecision(
                admitted=False,
                decision=FirewallDecision.DENY,
                reason=device_reason,
            )

        # 4. Capability Firewall — EVERY call passes through (41 §17).
        verdict = self._firewall.decide(request)
        if verdict is FirewallDecision.DENY:
            return ToolCallDecision(admitted=False, decision=verdict, reason="firewall_deny")

        # 5. Tool approval policy (14 §4) — tightening only. A declared
        #    permission absent from approval_policy resolves to ALWAYS
        #    (deny-by-default, DEFAULT_APPROVAL_REQUIREMENT).
        needs_approval = tool.approval_policy.get(request.permission, ApprovalRequirement.ALWAYS)
        if needs_approval is not ApprovalRequirement.NONE and request.approval_state != "approved":
            return ToolCallDecision(
                admitted=False,
                decision=FirewallDecision.REQUIRE_APPROVAL,
                reason=f"tool_approval_required:{needs_approval.value}",
            )
        if verdict is FirewallDecision.REQUIRE_APPROVAL:
            # Firewall-side approval gate unmet (its own 20 §8 classes).
            return ToolCallDecision(
                admitted=False, decision=verdict, reason="firewall_requires_approval"
            )

        return ToolCallDecision(admitted=True, decision=verdict)

    # -- internals ------------------------------------------------------------------

    def _check_device(self, tool: Tool, tenant_id: UUID, device_id: UUID | None) -> str | None:
        """Device-trust rule for client/hybrid tools; None = check passed."""
        if tool.location is ToolLocation.SERVER:
            return None  # server tools carry no device requirement
        if device_id is None:
            return f"device_required:{tool.location.value}"
        try:
            usable = self._devices.is_usable(device_id, tenant_id=tenant_id)
        except DeviceNotFound:
            return "device_unknown"
        if not usable:
            return "device_not_trusted"
        return None


__all__ = ["ToolCallDecision", "ToolCallGate", "ToolFabricError"]
