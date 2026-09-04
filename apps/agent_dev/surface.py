"""Development-agent composition root (R169 A3).

This module composes a *separate* tool surface for the development agent.
It reuses the core tool fabric (``ToolRegistry`` / ``ToolCallGate`` /
``ToolExecutor``) and the R169 source engines, but it is NOT wired into the
admin agent: ``apps/admin_agent`` keeps its closed registry and permission
classes (INV-7). Every refusal surfaces as typed data (INV-2), either as a
``ToolCallRecord`` with ``status="refused"`` or as a handler payload with
``ok=False`` and a machine-readable ``code``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError

from core.contracts.approval_binding import ApprovalBindingRefusal, ApprovalBindingRefusalCode
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.errors import ErrorCode
from core.contracts.security import ActorKind, FirewallDecision, FirewallDecisionInput
from core.contracts.tools import ApprovalRequirement, Tool, ToolLocation, ToolStatus
from core.identity.devices import DeviceRegistry
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.tools.checkpoint import CheckpointManager, checkpointed_write_handler
from core.tools.denied_paths import DENIED_PATH_PATTERNS
from core.tools.executor import ToolCallRecord, ToolExecutor
from core.tools.gate import ToolCallDecision, ToolCallGate
from core.tools.payload_binding import (
    NonCanonicalPayload,
    check_payload_binding,
    payload_hash,
)
from core.tools.registry import ToolRegistry
from core.tools.source_reader import SourceReader, SourceReadRefused
from core.tools.source_writer import SourceWriter, source_write_handler

from .git_tools import (
    GIT_PERMISSIONS,
    PERM_GIT_COMMIT,
    PERM_GIT_PUBLISH,
    GitToolset,
    mode_recording_audit,
)

if TYPE_CHECKING:
    from core.audit.ports import AuditLogPort
    from core.usage.ports import UsageAccountingPort

PERM_SOURCE_READ = "source.read"
PERM_SOURCE_WRITE = "source.write"
DEV_ENTITLEMENT = "dev_agent"
DEV_TOOL_NAMES: tuple[str, ...] = (PERM_SOURCE_READ, PERM_SOURCE_WRITE)
DEV_TOOL_VERSION = "r169.1"
DEV_RESOURCE = "repo:local"
DEV_SCOPE = "project"
DEV_RISK_LEVEL = "medium"

# R172 C6: write-class permissions whose approval is bound to the payload hash
# when the composition enables ``payload_binding``. Read-class calls are never
# bound. Closed set; extending it is an owner decision.
PAYLOAD_BOUND_PERMISSIONS: frozenset[str] = frozenset(
    {PERM_SOURCE_WRITE, PERM_GIT_COMMIT, PERM_GIT_PUBLISH}
)

ReadAction = Literal["read_file", "list_files", "search"]


class SourceReadRequest(ContractModel):
    """Typed arguments for the ``source.read`` tool."""

    action: ReadAction
    path: str = ""
    glob: BoundedStr | None = None
    text: BoundedStr | None = Field(default=None)


def _validation_refusal(error: ValidationError, path: object) -> JsonObject:
    reason = "; ".join(
        f"{'.'.join(str(loc) for loc in item['loc'])}: {item['msg']}" for item in error.errors()
    )
    return {"ok": False, "code": "validation_error", "reason": reason, "path": str(path)}


def source_read_handler(reader: SourceReader) -> Callable[[JsonObject], Awaitable[JsonObject]]:
    """Build the executor handler for ``source.read``.

    Read refusals raised by the jail are converted into ``ok=False`` payloads
    with ``code="read_refused"`` so that content never leaks via exceptions.
    """

    async def handle(arguments: JsonObject) -> JsonObject:
        try:
            request = SourceReadRequest.model_validate(arguments)
        except ValidationError as error:
            return _validation_refusal(error, arguments.get("path", ""))
        try:
            if request.action == "read_file":
                payload = reader.read_file(request.path)
            elif request.action == "list_files":
                payload = (
                    reader.list_files(request.path, request.glob)
                    if request.glob is not None
                    else reader.list_files(request.path)
                )
            else:
                if request.text is None:
                    return {
                        "ok": False,
                        "code": "validation_error",
                        "reason": "text: required for action 'search'",
                        "path": request.path,
                    }
                payload = (
                    reader.search(request.text, request.path, request.glob)
                    if request.glob is not None
                    else reader.search(request.text, request.path)
                )
        except SourceReadRefused as exc:
            return {"ok": False, "code": "read_refused", "reason": str(exc), "path": request.path}
        result: JsonObject = {"ok": True, "action": request.action, "path": request.path}
        result.update(payload)
        return result

    return handle


def dev_tenant_policy(*, write: bool, git: bool = False) -> TenantPolicy:
    """Tenant policy granting the dev-agent entitlement plus read (and optionally write/git)."""
    granted = {PERM_SOURCE_READ}
    if write:
        granted.add(PERM_SOURCE_WRITE)
    if git:
        granted |= GIT_PERMISSIONS
    return TenantPolicy(
        granted_permissions=frozenset(granted),
        granted_entitlements=frozenset({DEV_ENTITLEMENT}),
    )


def _dev_tools() -> tuple[Tool, Tool]:
    read_tool = Tool(
        id=uuid4(),
        name=PERM_SOURCE_READ,
        version=DEV_TOOL_VERSION,
        location=ToolLocation.SERVER,
        permissions=[PERM_SOURCE_READ],
        approval_policy={PERM_SOURCE_READ: ApprovalRequirement.NONE},
        status=ToolStatus.ACTIVE,
    )
    write_tool = Tool(
        id=uuid4(),
        name=PERM_SOURCE_WRITE,
        version=DEV_TOOL_VERSION,
        location=ToolLocation.SERVER,
        permissions=[PERM_SOURCE_WRITE],
        approval_policy={PERM_SOURCE_WRITE: ApprovalRequirement.BEFORE_ACTION},
        status=ToolStatus.ACTIVE,
    )
    return read_tool, write_tool


@dataclass(frozen=True)
class DevAgentSurface:
    """Composed development-agent surface (separate from the admin agent)."""

    tenant_id: UUID
    root: Path
    registry: ToolRegistry
    gate: ToolCallGate
    executor: ToolExecutor
    reader: SourceReader
    writer: SourceWriter
    tool_ids: dict[str, UUID]
    git: GitToolset | None = None
    checkpoints: CheckpointManager | None = None
    payload_binding: bool = False
    audit: AuditLogPort | None = None

    def request(
        self,
        permission: str,
        *,
        tenant_id: UUID | None = None,
        approval_state: Literal["approved"] | None = None,
    ) -> FirewallDecisionInput:
        return FirewallDecisionInput(
            actor=ActorKind.USER,
            tenant_id=tenant_id or self.tenant_id,
            permission=permission,
            resource=DEV_RESOURCE,
            scope=DEV_SCOPE,
            entitlement=DEV_ENTITLEMENT,
            approval_state=approval_state,
            risk_level=DEV_RISK_LEVEL,
        )

    async def call(
        self,
        tool_name: str,
        arguments: JsonObject,
        *,
        tenant_id: UUID | None = None,
        approval_state: Literal["approved"] | None = None,
        actor_id: UUID | None = None,
        approved_payload_hash: str | None = None,
    ) -> ToolCallRecord:
        """Execute a named dev tool through the gate + executor.

        Raises ``KeyError`` for tool names not composed into this surface.

        R172 C6 (opt-in, ``payload_binding=True`` at composition): for a
        write-class permission (``PAYLOAD_BOUND_PERMISSIONS``) called under
        ``approval_state="approved"``, ``arguments`` are canonicalised and
        their sha256 compared against ``approved_payload_hash`` BEFORE the
        gate. A missing hash, a mismatch, or a non-canonicalisable payload
        yields a refused ``ToolCallRecord`` carrying a typed
        ``ApprovalBindingRefusal`` in ``error_detail`` (hashes only, never
        the payload). The gate itself is unchanged and remains non-binding
        (owner decision). Default ``payload_binding=False`` is byte-identical
        to pre-C6 behaviour.
        """
        tool_id = self.tool_ids[tool_name]
        permission = str(self.registry.get(tool_id).permissions[0])
        request = self.request(permission, tenant_id=tenant_id, approval_state=approval_state)
        if (
            self.payload_binding
            and permission in PAYLOAD_BOUND_PERMISSIONS
            and approval_state == "approved"
        ):
            code = check_payload_binding(payload=arguments, approved_hash=approved_payload_hash)
            if code is not None:
                return self._refuse_payload_binding(
                    tool_id=tool_id,
                    request=request,
                    arguments=arguments,
                    approved_hash=approved_payload_hash,
                    code=code,
                    actor_id=actor_id,
                )
        return await self.executor.execute(
            tool_id=tool_id,
            request=request,
            arguments=arguments,
            actor_id=actor_id,
        )

    def _refuse_payload_binding(
        self,
        *,
        tool_id: UUID,
        request: FirewallDecisionInput,
        arguments: JsonObject,
        approved_hash: str | None,
        code: ApprovalBindingRefusalCode,
        actor_id: UUID | None,
    ) -> ToolCallRecord:
        """Build the executor-shaped refusal for a payload-binding failure.

        Mirrors ``ToolExecutor`` for a gate refusal: ``status="refused"``,
        ``gate_decision`` REQUIRE_APPROVAL naming the check, error code
        ``tool_approval_required``, and exactly one ``TOOL_CALL`` audit event.
        """
        try:
            actual: str | None = payload_hash(arguments)
        except NonCanonicalPayload:
            actual = None
        refusal = ApprovalBindingRefusal(
            code=code,
            permission=request.permission,
            approved_hash=approved_hash,
            payload_hash=actual,
            reason=_BINDING_REASONS[code],
        )
        decision = ToolCallDecision(
            admitted=False,
            decision=FirewallDecision.REQUIRE_APPROVAL,
            reason=code.value,
        )
        call_id = uuid4()
        error = ErrorCode.TOOL_APPROVAL_REQUIRED.value
        error_detail = refusal.model_dump_json()
        record = ToolCallRecord(
            call_id=call_id,
            tool_id=tool_id,
            tenant_id=request.tenant_id,
            permission=request.permission,
            status="refused",
            gate_decision=decision,
            result=None,
            error=error,
            error_detail=error_detail,
        )
        if self.audit is not None:
            self.audit.append(
                AuditEvent(
                    tenant_id=request.tenant_id,
                    event_type=AuditEventType.TOOL_CALL,
                    actor_id=actor_id,
                    details={
                        "call_id": str(call_id),
                        "tool_id": str(tool_id),
                        "permission": request.permission,
                        "status": "refused",
                        "gate_decision": decision.decision.value,
                        "gate_reason": code.value,
                        "error": error,
                        "error_detail": error_detail,
                    },
                )
            )
        return record


_BINDING_REASONS: dict[ApprovalBindingRefusalCode, str] = {
    ApprovalBindingRefusalCode.APPROVAL_HASH_REQUIRED: (
        "write-class call under approved state must present the approved payload hash"
    ),
    ApprovalBindingRefusalCode.APPROVAL_PAYLOAD_MISMATCH: (
        "submitted arguments do not match the payload the approval was granted for"
    ),
    ApprovalBindingRefusalCode.PAYLOAD_NOT_CANONICALISABLE: (
        "arguments contain values without a canonical JSON form (floats / non-JSON)"
    ),
}


def build_dev_surface(
    *,
    root: Path,
    tenant_id: UUID,
    firewall: CapabilityFirewall,
    audit: AuditLogPort,
    usage: UsageAccountingPort,
    devices: DeviceRegistry | None = None,
    reader: SourceReader | None = None,
    writer: SourceWriter | None = None,
    git: GitToolset | None = None,
    checkpoints: CheckpointManager | None = None,
    payload_binding: bool = False,
) -> DevAgentSurface:
    """Compose the dev-agent surface over ``root`` using the core tool fabric.

    When a ``GitToolset`` is supplied (R169 A5) its four ``git.*`` tools join
    the registry and the audit port is wrapped so the publish ``mode`` lands in
    the executor's single ``TOOL_CALL`` event (A6). Absent ``git`` the surface
    is exactly the A3 surface.

    R172 C5: when a ``CheckpointManager`` is supplied the ``source.write``
    handler snapshots the pre-apply content and seals/marks-partial after the
    write (result gains ``checkpoint_id`` on success). Absent ``checkpoints``
    the plain handler is used and the result shape is unchanged.

    R172 C6: ``payload_binding=True`` binds approvals of write-class calls to
    the sha256 of the canonical arguments (see ``DevAgentSurface.call``). The
    default ``False`` keeps the pre-C6 behaviour byte-identical; the gate is
    not modified either way (owner decision, pinned by test).
    """
    # R172 C1: the composed surface uses the hardened denylist; bare primitives
    # keep their defaults (callers may still inject their own reader/writer).
    if reader is None:
        reader = SourceReader(root, denied_patterns=DENIED_PATH_PATTERNS)
    if writer is None:
        writer = SourceWriter(root, denied_patterns=DENIED_PATH_PATTERNS)
    read_tool, write_tool = _dev_tools()
    registry = ToolRegistry()
    registry.register(read_tool)
    registry.register(write_tool)
    handlers: dict[UUID, Callable[[JsonObject], Awaitable[JsonObject]]] = {
        read_tool.id: source_read_handler(reader),
        write_tool.id: (
            checkpointed_write_handler(writer, checkpoints)
            if checkpoints is not None
            else source_write_handler(writer)
        ),
    }
    tool_ids = {read_tool.name: read_tool.id, write_tool.name: write_tool.id}
    if git is not None:
        if git.tenant_id != tenant_id:
            msg = "GitToolset tenant does not match the dev surface tenant"
            raise ValueError(msg)
        for tool in git.tools():
            registry.register(tool)
            tool_ids[tool.name] = tool.id
        handlers.update(git.handlers())
        audit = mode_recording_audit(audit)
    gate = ToolCallGate(
        tools=registry,
        firewall=firewall,
        devices=devices if devices is not None else DeviceRegistry(),
    )
    executor = ToolExecutor(gate=gate, handlers=handlers, audit=audit, usage=usage)
    return DevAgentSurface(
        tenant_id=tenant_id,
        root=writer.root,
        registry=registry,
        gate=gate,
        executor=executor,
        reader=reader,
        writer=writer,
        tool_ids=tool_ids,
        git=git,
        checkpoints=checkpoints,
        payload_binding=payload_binding,
        audit=audit,
    )
