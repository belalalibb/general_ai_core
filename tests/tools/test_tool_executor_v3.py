"""Phase V3 tests: the ToolExecutor — single gated execution path (X²-2).

Frozen-definition mapping (roadmap V3, verbatim clauses):

- "(1) requires a gate ALLOW verdict" ->
  test_denied_call_never_reaches_handler,
  test_approval_required_refused_as_data,
  test_unknown_tool_raises_not_registered (caller defect stays loud),
  test_execute_has_no_verdict_injection_channel (structural: the signature
  carries no decision/verdict parameter — no bypass channel exists),
  test_executor_surface_is_execute_only.
- "(2) dispatches to handlers registered at composition" ->
  test_admitted_call_dispatches_with_arguments,
  test_admitted_tool_without_handler_is_loud,
  test_handlers_snapshot_frozen_at_construction.
- "(3) normalizes results/errors as data" ->
  test_success_result_is_data, test_handler_exception_contained_as_data,
  test_refusal_carries_gate_reason_verbatim.
- "(4) audits + accounts" ->
  test_every_attempt_emits_exactly_one_tool_call_audit_event,
  test_success_settles_reservation, test_handler_failure_fails_reservation,
  test_budget_refusal_never_reaches_handler,
  test_refused_call_reserves_nothing.

Hermetic: in-memory gate/audit/usage, zero I/O.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.audit import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.base import JsonObject
from core.contracts.usage import UsageLedgerStatus
from core.identity.devices import DeviceRegistry
from core.tools import (
    ToolCallGate,
    ToolCallRecord,
    ToolExecutor,
    ToolHandlerNotBound,
    ToolNotRegistered,
    ToolRegistry,
)
from core.usage import InMemoryUsageAccounting
from tests.tools.test_tool_fabric import (
    PERM_COMMIT,
    PERM_READ,
    TENANT,
    granting_firewall,
    make_request,
    make_tool,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class _Recorder:
    """Handler double: records invocations, returns/raises per script."""

    def __init__(
        self,
        *,
        result: JsonObject | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[JsonObject] = []
        self._result = result if result is not None else {"ok": True}
        self._error = error

    async def __call__(self, arguments: JsonObject) -> JsonObject:
        self.calls.append(arguments)
        if self._error is not None:
            raise self._error
        return self._result


def make_world(
    *,
    tool: Any = None,
    handler: _Recorder | None = None,
    firewall: Any = None,
    budget: float = 100.0,
) -> tuple[ToolExecutor, Any, _Recorder, InMemoryAuditLog, InMemoryUsageAccounting]:
    tool = tool if tool is not None else make_tool()
    handler = handler if handler is not None else _Recorder()
    registry = ToolRegistry()
    registry.register(tool)
    gate = ToolCallGate(
        tools=registry,
        firewall=firewall if firewall is not None else granting_firewall(),
        devices=DeviceRegistry(),
    )
    audit = InMemoryAuditLog()
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="test", task_units_limit=budget)
    executor = ToolExecutor(
        gate=gate,
        handlers={tool.id: handler},
        audit=audit,
        usage=usage,
    )
    return executor, tool, handler, audit, usage


# --- (1) gate verdict required, structurally -----------------------------------------


def test_denied_call_never_reaches_handler() -> None:
    """An undeclared permission is refused as data; the handler stays cold."""
    tool = make_tool(permissions=[PERM_READ])
    executor, tool, handler, _, _ = make_world(tool=tool)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),
            arguments={"x": 1},
        )
    )
    assert isinstance(record, ToolCallRecord)
    assert record.status == "refused"
    assert record.succeeded is False
    assert record.error == "capability_denied"
    assert handler.calls == []


def test_approval_required_refused_as_data() -> None:
    """14 §4 approval requirement surfaces as tool_approval_required."""
    executor, tool, handler, _, _ = make_world()
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),  # before_action
            arguments={},
        )
    )
    assert record.status == "refused"
    assert record.error == "tool_approval_required"
    assert record.gate_decision.reason is not None
    assert record.gate_decision.reason.startswith("tool_approval_required")
    assert handler.calls == []


def test_unknown_tool_raises_not_registered() -> None:
    """Unknown tool id = caller defect (gate posture), never a verdict."""
    executor, _, _, _, _ = make_world()
    with pytest.raises(ToolNotRegistered):
        run(
            executor.execute(
                tool_id=uuid4(), request=make_request(), arguments={}
            )
        )


def test_execute_has_no_verdict_injection_channel() -> None:
    """Structural bypass-proofing (same posture as the gate's no-skill-input):

    execute() exposes no parameter that could carry a pre-made decision or
    skip admission — the executor calls the gate itself, unconditionally.
    """
    params = set(inspect.signature(ToolExecutor.execute).parameters)
    assert params == {
        "self",
        "tool_id",
        "request",
        "arguments",
        "device_id",
        "actor_id",
        "estimated_units",
    }


def test_executor_surface_is_execute_only() -> None:
    """No second execution API exists that could route around the gate."""
    public = {n for n in dir(ToolExecutor) if not n.startswith("_")}
    assert public == {"execute"}


# --- (2) composition-bound dispatch ---------------------------------------------------


def test_admitted_call_dispatches_with_arguments() -> None:
    handler = _Recorder(result={"answer": 42})
    executor, tool, handler, _, _ = make_world(handler=handler)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(),
            arguments={"query": "state of the repo"},
        )
    )
    assert record.status == "succeeded"
    assert handler.calls == [{"query": "state of the repo"}]


def test_admitted_tool_without_handler_is_loud() -> None:
    """Admitted-but-unwired = composition defect, raises (never silent)."""
    tool = make_tool()
    registry = ToolRegistry()
    registry.register(tool)
    executor = ToolExecutor(
        gate=ToolCallGate(
            tools=registry, firewall=granting_firewall(), devices=DeviceRegistry()
        ),
        handlers={},
        audit=InMemoryAuditLog(),
        usage=InMemoryUsageAccounting(),
    )
    with pytest.raises(ToolHandlerNotBound):
        run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))


def test_handlers_snapshot_frozen_at_construction() -> None:
    """Mutating the source mapping after construction changes nothing."""
    tool = make_tool()
    handler = _Recorder()
    source: dict[UUID, Any] = {tool.id: handler}
    registry = ToolRegistry()
    registry.register(tool)
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="test", task_units_limit=10.0)
    executor = ToolExecutor(
        gate=ToolCallGate(
            tools=registry, firewall=granting_firewall(), devices=DeviceRegistry()
        ),
        handlers=source,
        audit=InMemoryAuditLog(),
        usage=usage,
    )
    source.clear()  # composition mapping mutated after the fact
    record = run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    assert record.status == "succeeded"  # executor kept its own copy


# --- (3) normalization as data --------------------------------------------------------


def test_success_result_is_data() -> None:
    handler = _Recorder(result={"content": "done", "files": ["a.py"]})
    executor, tool, _, _, _ = make_world(handler=handler)
    record = run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    assert record.succeeded is True
    assert record.result == {"content": "done", "files": ["a.py"]}
    assert record.error is None
    assert record.tenant_id == TENANT
    assert record.permission == PERM_READ


def test_handler_exception_contained_as_data() -> None:
    handler = _Recorder(error=RuntimeError("upstream exploded"))
    executor, tool, _, _, _ = make_world(handler=handler)
    record = run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    assert record.status == "failed"
    assert record.error == "execution_failed"
    assert record.error_detail == "RuntimeError: upstream exploded"
    assert record.result is None


def test_refusal_carries_gate_reason_verbatim() -> None:
    tool = make_tool(status="disabled")
    executor, tool, _, _, _ = make_world(tool=tool)
    record = run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    assert record.status == "refused"
    assert record.gate_decision.admitted is False
    assert record.gate_decision.reason == "tool_not_selectable:disabled"
    assert record.error_detail == "tool_not_selectable:disabled"


# --- (4) audit + accounting -----------------------------------------------------------


def test_every_attempt_emits_exactly_one_tool_call_audit_event() -> None:
    """Refused, failed, and succeeded attempts each audit exactly once."""
    # succeeded
    executor, tool, _, audit, _ = make_world()
    run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    events = audit.read(tenant_id=TENANT)
    assert len(events) == 1
    assert events[0].event_type is AuditEventType.TOOL_CALL
    assert events[0].details["status"] == "succeeded"
    assert events[0].details["tool_id"] == str(tool.id)

    # refused
    executor, tool, _, audit, _ = make_world(tool=make_tool(status="disabled"))
    run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    events = audit.read(tenant_id=TENANT)
    assert len(events) == 1
    assert events[0].details["status"] == "refused"
    assert events[0].details["gate_reason"] == "tool_not_selectable:disabled"

    # failed
    executor, tool, _, audit, _ = make_world(
        handler=_Recorder(error=ValueError("bad"))
    )
    run(executor.execute(tool_id=tool.id, request=make_request(), arguments={}))
    events = audit.read(tenant_id=TENANT)
    assert len(events) == 1
    assert events[0].details["status"] == "failed"
    assert events[0].details["error"] == "execution_failed"


def test_success_settles_reservation() -> None:
    executor, tool, _, _, usage = make_world()
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(),
            arguments={},
            estimated_units=3.0,
        )
    )
    entry = usage.get(record.call_id)
    assert entry.status is UsageLedgerStatus.SETTLED
    assert entry.units_settled == 3.0


def test_handler_failure_fails_reservation() -> None:
    executor, tool, _, _, usage = make_world(handler=_Recorder(error=OSError("io")))
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(),
            arguments={},
            estimated_units=2.0,
        )
    )
    assert record.status == "failed"
    entry = usage.get(record.call_id)
    assert entry.status is UsageLedgerStatus.FAILED


def test_budget_refusal_never_reaches_handler() -> None:
    """03 §7: a denied reservation must never reach the handler."""
    executor, tool, handler, audit, _ = make_world(budget=1.0)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(),
            arguments={},
            estimated_units=5.0,
        )
    )
    assert record.status == "refused"
    assert record.error == "entitlement_exceeded"
    assert handler.calls == []
    events = audit.read(tenant_id=TENANT)
    assert len(events) == 1  # the refusal is still audited
    assert events[0].details["error"] == "entitlement_exceeded"


def test_refused_call_reserves_nothing() -> None:
    """A gate refusal leaves the ledger untouched — no hold, no residue."""
    executor, tool, _, _, usage = make_world(tool=make_tool(status="disabled"))
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(),
            arguments={},
            estimated_units=5.0,
        )
    )
    assert record.status == "refused"
    with pytest.raises(Exception):  # noqa: B017 — any lookup miss is fine
        usage.get(record.call_id)
