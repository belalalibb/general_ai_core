"""Tool Execution Runtime (MASTER VISION v2 roadmap, Phase V3 / X²-2).

The SINGLE execution path for tool calls. The frozen definition, verbatim:
"(1) requires a gate ALLOW verdict, (2) dispatches to handlers registered
at composition (handlers = apps/providers territory, never core),
(3) normalizes results/errors as data, (4) audits + accounts.
Security-critical: 'every call passes the gate' as a structural property."

Structural bypass-proofing mirrors the gate's no-skill-input posture
(41 §17): :meth:`ToolExecutor.execute` calls ``gate.admit(...)`` ITSELF and
exposes no parameter through which a caller could supply a pre-made verdict,
skip admission, or reach a handler directly — handlers are private state.
There is no other execution API on this class.

Normalization contract (P6 — evidence or silence; 11 §14 explainable
outcomes): every ATTEMPT on a registered tool resolves to a
:class:`ToolCallRecord` — refusals carry the gate's decision verbatim,
handler failures are contained as data (``error`` names the exception type;
provider-style internals never propagate). Only CALLER/COMPOSITION defects
raise: unknown tool (``ToolNotRegistered``, from the gate's registry) and
admitted-but-unbound handler (``ToolHandlerNotBound``) — those are wiring
bugs, not tool-call outcomes.

Audit + accounting (gate docstring, 41 §49: "The gate returns an explicit
decision object so both can consume it; neither is silently claimed"):
this executor IS that consumer. Exactly one ``TOOL_CALL`` audit event per
attempt (refused, failed, and succeeded alike — a refusal is evidence, not
silence), and the 03 §7 reserve→settle/fail lifecycle around the handler:
reserve BEFORE the handler runs (a budget denial must never reach a
handler, same rule the execution service enforces for providers), settle
on success, fail on handler error. Ports are the EXISTING core seams
(AuditLogPort, UsageAccountingPort) — no new contracts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject
from core.contracts.errors import ErrorCode
from core.tools.errors import ToolHandlerNotBound
from core.tools.gate import ToolCallDecision, ToolCallGate
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured

if TYPE_CHECKING:
    from core.audit.ports import AuditLogPort
    from core.contracts.security import FirewallDecisionInput
    from core.usage.ports import UsageAccountingPort

ToolHandler = Callable[[JsonObject], Awaitable[JsonObject]]
"""Composition-bound execution body for ONE tool (transport/sandboxing =
adapter territory, per the tool-fabric charter: the gate/executor never
own how a tool physically runs)."""


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool-call attempt normalized as data (P6; 11 §14).

    ``status`` is the closed three-way outcome:

    - ``"refused"``   — the gate did not admit; ``gate_decision.reason``
      names the check verbatim; ``error`` carries the unified error code
      (``capability_denied`` / ``tool_approval_required`` /
      ``entitlement_exceeded`` for a budget refusal).
    - ``"failed"``    — admitted, handler raised; ``error`` =
      ``execution_failed``, ``error_detail`` names the exception type +
      message as data (never re-raised).
    - ``"succeeded"`` — admitted, handler returned; ``result`` holds the
      handler's output verbatim.

    ``call_id`` keys the audit event and the usage-ledger entry so both
    subsystems tell the same story about the same attempt.
    """

    call_id: UUID
    tool_id: UUID
    tenant_id: UUID
    permission: str
    status: str
    gate_decision: ToolCallDecision
    result: JsonObject | None = None
    error: str | None = None
    error_detail: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"


class ToolExecutor:
    """The single tool execution path (V3 frozen definition).

    Handlers are injected ONCE at construction from the composition root and
    copied into a private immutable mapping — core never registers, mutates,
    or discovers handlers itself, and nothing outside can rebind them.
    """

    def __init__(
        self,
        *,
        gate: ToolCallGate,
        handlers: Mapping[UUID, ToolHandler],
        audit: AuditLogPort,
        usage: UsageAccountingPort,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._gate = gate
        self._handlers: dict[UUID, ToolHandler] = dict(handlers)
        self._audit = audit
        self._usage = usage
        self._id_factory = id_factory

    async def execute(
        self,
        *,
        tool_id: UUID,
        request: FirewallDecisionInput,
        arguments: JsonObject,
        device_id: UUID | None = None,
        actor_id: UUID | None = None,
        estimated_units: float = 0.0,
    ) -> ToolCallRecord:
        """Admit → dispatch → normalize → audit + account. No other path.

        Raises ``ToolNotRegistered`` for an unknown ``tool_id`` (caller
        defect, surfaced by the gate's registry read) and
        ``ToolHandlerNotBound`` when the gate admits a tool composition
        never wired (composition defect). Everything else is data.
        """
        call_id = self._id_factory()
        # (1) The gate verdict — unconditionally first, no bypass parameter.
        decision = self._gate.admit(tool_id=tool_id, request=request, device_id=device_id)
        if not decision.admitted:
            code = (
                ErrorCode.TOOL_APPROVAL_REQUIRED
                if (decision.reason or "").startswith(
                    ("tool_approval_required", "firewall_requires_approval")
                )
                else ErrorCode.CAPABILITY_DENIED
            )
            return self._conclude(
                call_id=call_id,
                tool_id=tool_id,
                request=request,
                decision=decision,
                actor_id=actor_id,
                status="refused",
                error=code.value,
                error_detail=decision.reason,
            )

        # (2) Composition-bound handler — checked BEFORE reserving so a
        # wiring bug never touches the tenant's budget.
        handler = self._handlers.get(tool_id)
        if handler is None:
            raise ToolHandlerNotBound(tool_id)

        # (4a) Reserve BEFORE the handler runs (03 §7): a budget denial is
        # a refusal as data — the handler must never see the call.
        try:
            self._usage.reserve(request.tenant_id, call_id, estimated_units)
        except (BudgetExceeded, EntitlementNotConfigured) as exc:
            return self._conclude(
                call_id=call_id,
                tool_id=tool_id,
                request=request,
                decision=decision,
                actor_id=actor_id,
                status="refused",
                error=ErrorCode.ENTITLEMENT_EXCEEDED.value,
                error_detail=str(exc),
            )

        # (3) Dispatch; normalize the outcome as data either way.
        try:
            result = await handler(dict(arguments))
        except Exception as exc:  # noqa: BLE001 — normalization IS the contract
            self._usage.fail(call_id)
            return self._conclude(
                call_id=call_id,
                tool_id=tool_id,
                request=request,
                decision=decision,
                actor_id=actor_id,
                status="failed",
                error=ErrorCode.EXECUTION_FAILED.value,
                error_detail=f"{type(exc).__name__}: {exc}",
            )
        self._usage.settle(call_id, estimated_units)
        return self._conclude(
            call_id=call_id,
            tool_id=tool_id,
            request=request,
            decision=decision,
            actor_id=actor_id,
            status="succeeded",
            result=result,
        )

    def _conclude(
        self,
        *,
        call_id: UUID,
        tool_id: UUID,
        request: FirewallDecisionInput,
        decision: ToolCallDecision,
        actor_id: UUID | None,
        status: str,
        result: JsonObject | None = None,
        error: str | None = None,
        error_detail: str | None = None,
    ) -> ToolCallRecord:
        """Build the record and emit its ONE audit event (4b)."""
        record = ToolCallRecord(
            call_id=call_id,
            tool_id=tool_id,
            tenant_id=request.tenant_id,
            permission=request.permission,
            status=status,
            gate_decision=decision,
            result=result,
            error=error,
            error_detail=error_detail,
        )
        details: JsonObject = {
            "call_id": str(call_id),
            "tool_id": str(tool_id),
            "permission": request.permission,
            "status": status,
            "gate_decision": decision.decision.value,
        }
        if decision.reason is not None:
            details["gate_reason"] = decision.reason
        if error is not None:
            details["error"] = error
        if error_detail is not None:
            details["error_detail"] = error_detail
        self._audit.append(
            AuditEvent(
                tenant_id=request.tenant_id,
                event_type=AuditEventType.TOOL_CALL,
                actor_id=actor_id,
                details=details,
            )
        )
        return record
