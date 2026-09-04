"""GitHub connectivity for the development agent (R169 A5/A6).

Every Git operation is a *typed tool call* that flows through the core tool
fabric (``ToolCallGate`` → ``ToolExecutor``). This module contributes:

* ``GitTransportPort`` — the only seam that touches a remote or a working
  tree. Production adapters live outside ``apps`` (INV-3); tests use a fake.
* ``RepoBindingRegistry`` — tenant-scoped lookup of ``RepoBinding`` records.
  Unknown or foreign-tenant bindings are refusals as data (INV-2).
* A per-binding *path jail*: a commit path is admitted only if it resolves
  inside the binding's ``local_root``. A path that belongs to binding X is
  refused when presented under binding Y (``path_outside_binding``).
* Credential hygiene: the token is resolved through
  ``SecretManagerPort.resolve(tenant_id, credential_ref)`` at the last
  possible moment, handed to the transport, and never copied into results,
  traces or audit details.
* ``PublishMode`` enforcement: the default is ``PULL_REQUEST``;
  ``DIRECT_PUSH`` is refused unless the binding explicitly allows it. A
  protected-branch rejection from the remote becomes
  ``remote_rejected_protected_branch`` with ``suggested_mode="pull_request"``.
* Observability: every publish attempt is appended to a typed execution
  trace, and the executor's single ``TOOL_CALL`` audit event is enriched with
  the ``mode`` via ``mode_recording_audit`` (no second event is emitted, so the
  one-event-per-attempt rule of ``ToolExecutor`` holds).

Nothing here widens the admin agent (INV-7): this is a separately composed
surface consumed by ``apps.agent_dev.surface``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError

from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import ContractModel, JsonObject, utc_now
from core.contracts.binding_store import BindingStoreLoadReport
from core.contracts.publish_mode import DEFAULT_PUBLISH_MODE, PublishMode
from core.contracts.repo_binding import (
    GitCommitRequest,
    GitCommitResult,
    GitFetchRequest,
    GitFetchResult,
    GitOperation,
    GitPublishRequest,
    GitPublishResult,
    GitRefusal,
    GitRefusalCode,
    GitStatusRequest,
    GitStatusResult,
    RepoBinding,
)
from core.contracts.tools import ApprovalRequirement, Tool, ToolLocation, ToolStatus
from core.engineering.errors import GitRefused
from core.engineering.git import validate_ref
from core.secrets.errors import SecretNotFound

if TYPE_CHECKING:
    from core.audit.ports import AuditLogPort
    from core.secrets.ports import SecretManagerPort

PERM_GIT_FETCH = "git.fetch"
PERM_GIT_STATUS = "git.status"
PERM_GIT_COMMIT = "git.commit"
PERM_GIT_PUBLISH = "git.publish"
GIT_TOOL_NAMES: tuple[str, ...] = (
    PERM_GIT_FETCH,
    PERM_GIT_STATUS,
    PERM_GIT_COMMIT,
    PERM_GIT_PUBLISH,
)
GIT_TOOL_VERSION = "r169.1"
GIT_PERMISSIONS: frozenset[str] = frozenset(GIT_TOOL_NAMES)

Handler = Callable[[JsonObject], Awaitable[JsonObject]]


# --- Transport seam -------------------------------------------------------------


class TransportError(Exception):
    """The transport could not complete the operation (network, auth, ...)."""


class RemoteRejected(TransportError):
    """The remote refused the push for a non-protection reason."""


class ProtectedBranchRejected(RemoteRejected):
    """The remote refused a push because the target branch is protected."""


class NothingToCommit(TransportError):
    """No staged change — a commit would be empty."""


class GitTransportPort(Protocol):
    """Binding-scoped Git operations. Implementations receive the resolved
    token only for remote-touching calls and must never persist it."""

    async def fetch(self, binding: RepoBinding, *, token: str) -> str | None: ...

    async def status(self, binding: RepoBinding) -> GitStatusResult: ...

    async def diff_summary(self, binding: RepoBinding) -> str: ...

    async def commit(self, binding: RepoBinding, *, message: str, paths: Sequence[str]) -> str: ...

    async def push(self, binding: RepoBinding, *, branch: str, token: str) -> None: ...

    async def open_pull_request(
        self, binding: RepoBinding, *, work_branch: str, title: str, token: str
    ) -> str: ...


# --- Binding registry (tenant-scoped) --------------------------------------------


class BindingStorePort(Protocol):
    """Durable backing for :class:`RepoBindingRegistry` (R172 C2)."""

    def load(self) -> BindingStoreLoadReport: ...

    def save(self, bindings: Iterable[RepoBinding]) -> None: ...


class BindingLookupRefused(Exception):
    """Typed lookup failure; converted to ``GitRefusal`` by the handlers."""

    def __init__(self, code: GitRefusalCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class RepoBindingRegistry:
    """In-memory registry of ``RepoBinding`` records keyed by id.

    ``get`` is tenant-scoped: a binding owned by another tenant is reported as
    ``binding_tenant_mismatch`` (never as "unknown", so audits can distinguish
    a cross-tenant probe from a typo).

    R172 C2: an optional ``store`` (``core.tools.binding_store.JsonBindingStore``)
    makes the registry durable. Valid records are loaded fail-closed at
    construction (``load_report`` says what was skipped); every ``register``
    re-saves the full valid set so bad on-disk records are dropped, never
    resurrected. Without a store the behaviour is byte-for-byte the R169 one.
    """

    def __init__(self, store: BindingStorePort | None = None) -> None:
        self._bindings: dict[UUID, RepoBinding] = {}
        self._store = store
        self.load_report: BindingStoreLoadReport | None = None
        if store is not None:
            report = store.load()
            self.load_report = report
            for binding in report.bindings:
                self._bindings[binding.id] = binding

    def register(self, binding: RepoBinding) -> RepoBinding:
        self._bindings[binding.id] = binding
        if self._store is not None:
            self._store.save(self._bindings.values())
        return binding

    def get(self, binding_id: UUID, *, tenant_id: UUID) -> RepoBinding:
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise BindingLookupRefused(
                GitRefusalCode.BINDING_UNKNOWN, f"binding not registered: {binding_id}"
            )
        if binding.tenant_id != tenant_id:
            raise BindingLookupRefused(
                GitRefusalCode.BINDING_TENANT_MISMATCH,
                f"binding {binding_id} belongs to another tenant",
            )
        return binding

    def list_for_tenant(self, tenant_id: UUID) -> list[RepoBinding]:
        return [b for b in self._bindings.values() if b.tenant_id == tenant_id]


# --- Path jail -------------------------------------------------------------------


def jail_path(binding: RepoBinding, raw: str) -> str:
    """Return ``raw`` relative to the binding root, or raise ``BindingLookupRefused``.

    Absolute paths are admitted only when they point inside ``local_root``.
    Traversal (``..``) that escapes the root is refused. Symlinks are not
    followed (the working tree may not exist yet); the check is lexical.
    """
    root = Path(binding.local_root)
    candidate = Path(raw)
    target = candidate if candidate.is_absolute() else root / candidate
    normalised = Path(*_normalise(target.parts))
    root_norm = Path(*_normalise(root.parts))
    if normalised != root_norm and root_norm not in normalised.parents:
        raise BindingLookupRefused(
            GitRefusalCode.PATH_OUTSIDE_BINDING,
            f"path escapes binding root: {raw}",
        )
    return normalised.relative_to(root_norm).as_posix()


def _normalise(parts: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if len(out) > 1 or (out and out[0] != "/"):
                out.pop()
            continue
        out.append(part)
    return out or ["."]


# --- Execution trace --------------------------------------------------------------


class GitTraceEntry(ContractModel):
    """One recorded Git operation attempt (typed execution trace)."""

    id: UUID
    at: datetime
    operation: GitOperation
    binding_id: str | None
    mode: PublishMode | None = None
    ok: bool
    code: GitRefusalCode | None = None


_CURRENT_MODE: contextvars.ContextVar[PublishMode | None] = contextvars.ContextVar(
    "agent_dev_git_publish_mode", default=None
)


class ModeRecordingAudit:
    """Audit decorator: copies the in-flight publish ``mode`` into the
    executor's ``TOOL_CALL`` event details. Exactly one event per attempt."""

    def __init__(self, inner: AuditLogPort) -> None:
        self._inner = inner

    def append(self, event: AuditEvent) -> AuditEvent:
        mode = _CURRENT_MODE.get()
        if mode is not None and event.event_type is AuditEventType.TOOL_CALL:
            details = dict(event.details)
            details["mode"] = mode.value
            event = event.model_copy(update={"details": details})
            _CURRENT_MODE.set(None)
        return self._inner.append(event)

    def read(
        self,
        tenant_id: UUID,
        event_type: AuditEventType | None = None,
        limit: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        return tuple(self._inner.read(tenant_id, event_type, limit))

    def count(self, tenant_id: UUID) -> int:
        return self._inner.count(tenant_id)


def mode_recording_audit(inner: AuditLogPort) -> ModeRecordingAudit:
    return ModeRecordingAudit(inner)


# --- Toolset ---------------------------------------------------------------------


def _refusal(
    code: GitRefusalCode,
    reason: str,
    binding_id: object = None,
    *,
    suggested_mode: PublishMode | None = None,
) -> JsonObject:
    payload = GitRefusal(
        code=code,
        reason=reason,
        binding_id=str(binding_id) if binding_id is not None else None,
        suggested_mode=suggested_mode,
    )
    return payload.model_dump(mode="json")


def _validation_error(error: ValidationError, binding_id: object) -> JsonObject:
    reason = "; ".join(
        f"{'.'.join(str(loc) for loc in item['loc'])}: {item['msg']}" for item in error.errors()
    )
    return _refusal(GitRefusalCode.VALIDATION_ERROR, reason, binding_id)


@dataclass
class GitToolset:
    """Tenant-scoped Git tools for one dev-agent surface."""

    tenant_id: UUID
    bindings: RepoBindingRegistry
    transport: GitTransportPort
    secrets: SecretManagerPort
    trace: list[GitTraceEntry] = field(default_factory=list)
    _tools: tuple[Tool, ...] = field(default_factory=tuple, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tools = tuple(
            Tool(
                id=uuid4(),
                name=name,
                version=GIT_TOOL_VERSION,
                location=ToolLocation.SERVER,
                permissions=[name],
                approval_policy={name: approval},
                status=ToolStatus.ACTIVE,
            )
            for name, approval in (
                (PERM_GIT_FETCH, ApprovalRequirement.NONE),
                (PERM_GIT_STATUS, ApprovalRequirement.NONE),
                (PERM_GIT_COMMIT, ApprovalRequirement.BEFORE_ACTION),
                (PERM_GIT_PUBLISH, ApprovalRequirement.BEFORE_ACTION),
            )
        )

    # -- composition -------------------------------------------------------------

    def tools(self) -> tuple[Tool, ...]:
        return self._tools

    def handlers(self) -> dict[UUID, Handler]:
        by_name: dict[str, Handler] = {
            PERM_GIT_FETCH: self.fetch,
            PERM_GIT_STATUS: self.status,
            PERM_GIT_COMMIT: self.commit,
            PERM_GIT_PUBLISH: self.publish,
        }
        return {tool.id: by_name[tool.name] for tool in self._tools}

    # -- helpers -----------------------------------------------------------------

    def _record(
        self,
        operation: GitOperation,
        binding_id: object,
        *,
        ok: bool,
        code: GitRefusalCode | None = None,
        mode: PublishMode | None = None,
    ) -> None:
        self.trace.append(
            GitTraceEntry(
                id=uuid4(),
                at=utc_now(),
                operation=operation,
                binding_id=str(binding_id) if binding_id is not None else None,
                mode=mode,
                ok=ok,
                code=code,
            )
        )

    def _binding(self, binding_id: UUID) -> RepoBinding:
        return self.bindings.get(binding_id, tenant_id=self.tenant_id)

    def _token(self, binding: RepoBinding) -> str:
        try:
            return self.secrets.resolve(self.tenant_id, binding.credential_ref)
        except SecretNotFound as exc:
            raise BindingLookupRefused(
                GitRefusalCode.CREDENTIAL_UNRESOLVED,
                f"credential_ref could not be resolved for binding {binding.id}",
            ) from exc

    # -- handlers ------------------------------------------------------------------

    async def fetch(self, arguments: JsonObject) -> JsonObject:
        op = GitOperation.FETCH
        try:
            request = GitFetchRequest.model_validate(arguments)
        except ValidationError as error:
            self._record(
                op, arguments.get("binding_id"), ok=False, code=GitRefusalCode.VALIDATION_ERROR
            )
            return _validation_error(error, arguments.get("binding_id"))
        try:
            binding = self._binding(request.binding_id)
            token = self._token(binding)
            head = await self.transport.fetch(binding, token=token)
        except BindingLookupRefused as exc:
            self._record(op, request.binding_id, ok=False, code=exc.code)
            return _refusal(exc.code, exc.reason, request.binding_id)
        except TransportError as exc:
            self._record(op, request.binding_id, ok=False, code=GitRefusalCode.TRANSPORT_ERROR)
            return _refusal(GitRefusalCode.TRANSPORT_ERROR, str(exc), request.binding_id)
        self._record(op, request.binding_id, ok=True)
        return GitFetchResult(binding_id=str(binding.id), remote_head=head).model_dump(mode="json")

    async def status(self, arguments: JsonObject) -> JsonObject:
        op = GitOperation.STATUS
        try:
            request = GitStatusRequest.model_validate(arguments)
        except ValidationError as error:
            self._record(
                op, arguments.get("binding_id"), ok=False, code=GitRefusalCode.VALIDATION_ERROR
            )
            return _validation_error(error, arguments.get("binding_id"))
        try:
            binding = self._binding(request.binding_id)
            result = await self.transport.status(binding)
        except BindingLookupRefused as exc:
            self._record(op, request.binding_id, ok=False, code=exc.code)
            return _refusal(exc.code, exc.reason, request.binding_id)
        except TransportError as exc:
            self._record(op, request.binding_id, ok=False, code=GitRefusalCode.TRANSPORT_ERROR)
            return _refusal(GitRefusalCode.TRANSPORT_ERROR, str(exc), request.binding_id)
        self._record(op, request.binding_id, ok=True)
        return result.model_dump(mode="json")

    async def commit(self, arguments: JsonObject) -> JsonObject:
        op = GitOperation.COMMIT
        try:
            request = GitCommitRequest.model_validate(arguments)
        except ValidationError as error:
            self._record(
                op, arguments.get("binding_id"), ok=False, code=GitRefusalCode.VALIDATION_ERROR
            )
            return _validation_error(error, arguments.get("binding_id"))
        try:
            binding = self._binding(request.binding_id)
            jailed = [jail_path(binding, p) for p in request.paths]
            sha = await self.transport.commit(binding, message=request.message, paths=jailed)
        except BindingLookupRefused as exc:
            self._record(op, request.binding_id, ok=False, code=exc.code)
            return _refusal(exc.code, exc.reason, request.binding_id)
        except NothingToCommit as exc:
            self._record(op, request.binding_id, ok=False, code=GitRefusalCode.NOTHING_TO_COMMIT)
            return _refusal(GitRefusalCode.NOTHING_TO_COMMIT, str(exc), request.binding_id)
        except TransportError as exc:
            self._record(op, request.binding_id, ok=False, code=GitRefusalCode.TRANSPORT_ERROR)
            return _refusal(GitRefusalCode.TRANSPORT_ERROR, str(exc), request.binding_id)
        self._record(op, request.binding_id, ok=True)
        return GitCommitResult(binding_id=str(binding.id), sha=sha, files=len(jailed)).model_dump(
            mode="json"
        )

    async def publish(self, arguments: JsonObject) -> JsonObject:
        op = GitOperation.PUBLISH
        try:
            request = GitPublishRequest.model_validate(arguments)
        except ValidationError as error:
            self._record(
                op, arguments.get("binding_id"), ok=False, code=GitRefusalCode.VALIDATION_ERROR
            )
            return _validation_error(error, arguments.get("binding_id"))
        mode = request.mode
        _CURRENT_MODE.set(mode)
        try:
            binding = self._binding(request.binding_id)
        except BindingLookupRefused as exc:
            self._record(op, request.binding_id, ok=False, code=exc.code, mode=mode)
            return _refusal(exc.code, exc.reason, request.binding_id)

        if not binding.mode_allowed(mode):
            suggested = DEFAULT_PUBLISH_MODE if binding.mode_allowed(DEFAULT_PUBLISH_MODE) else None
            self._record(
                op, binding.id, ok=False, code=GitRefusalCode.PUBLISH_MODE_NOT_ALLOWED, mode=mode
            )
            return _refusal(
                GitRefusalCode.PUBLISH_MODE_NOT_ALLOWED,
                f"publish mode {mode.value!r} is not enabled for binding {binding.id}",
                binding.id,
                suggested_mode=suggested,
            )

        try:
            result = await self._publish_in_mode(binding, request)
        except BindingLookupRefused as exc:
            self._record(op, binding.id, ok=False, code=exc.code, mode=mode)
            return _refusal(exc.code, exc.reason, binding.id)
        except GitRefused as exc:
            self._record(op, binding.id, ok=False, code=GitRefusalCode.INVALID_REF, mode=mode)
            return _refusal(GitRefusalCode.INVALID_REF, str(exc), binding.id)
        except ProtectedBranchRejected as exc:
            self._record(
                op,
                binding.id,
                ok=False,
                code=GitRefusalCode.REMOTE_REJECTED_PROTECTED_BRANCH,
                mode=mode,
            )
            return _refusal(
                GitRefusalCode.REMOTE_REJECTED_PROTECTED_BRANCH,
                str(exc),
                binding.id,
                suggested_mode=PublishMode.PULL_REQUEST,
            )
        except RemoteRejected as exc:
            self._record(op, binding.id, ok=False, code=GitRefusalCode.REMOTE_REJECTED, mode=mode)
            return _refusal(GitRefusalCode.REMOTE_REJECTED, str(exc), binding.id)
        except TransportError as exc:
            self._record(op, binding.id, ok=False, code=GitRefusalCode.TRANSPORT_ERROR, mode=mode)
            return _refusal(GitRefusalCode.TRANSPORT_ERROR, str(exc), binding.id)
        self._record(op, binding.id, ok=True, mode=mode)
        return result.model_dump(mode="json")

    async def _publish_in_mode(
        self, binding: RepoBinding, request: GitPublishRequest
    ) -> GitPublishResult:
        mode = request.mode
        if mode is PublishMode.DRY_RUN:
            summary = await self.transport.diff_summary(binding)
            return GitPublishResult(
                binding_id=str(binding.id),
                mode=mode,
                branch=binding.branch,
                pushed=False,
                diff_summary=summary,
            )
        if mode is PublishMode.LOCAL_COMMIT_ONLY:
            status = await self.transport.status(binding)
            return GitPublishResult(
                binding_id=str(binding.id),
                mode=mode,
                branch=status.branch,
                pushed=False,
                diff_summary=f"local head {status.head or '(none)'}; remote untouched",
            )
        if mode is PublishMode.PULL_REQUEST:
            work_branch = validate_ref(
                request.work_branch or f"dev/{str(binding.id)[:8]}/{uuid4().hex[:8]}"
            )
            if work_branch == binding.branch:
                raise GitRefused("work branch must differ from the bound branch")
            title = request.title or f"dev-agent: {work_branch}"
            token = self._token(binding)
            await self.transport.push(binding, branch=work_branch, token=token)
            url = await self.transport.open_pull_request(
                binding, work_branch=work_branch, title=title, token=token
            )
            return GitPublishResult(
                binding_id=str(binding.id),
                mode=mode,
                branch=work_branch,
                pushed=True,
                pull_request_url=url,
            )
        # DIRECT_PUSH — only reachable when the binding explicitly allows it.
        target = validate_ref(binding.branch)
        token = self._token(binding)
        await self.transport.push(binding, branch=target, token=token)
        return GitPublishResult(binding_id=str(binding.id), mode=mode, branch=target, pushed=True)


__all__ = [
    "GIT_PERMISSIONS",
    "GIT_TOOL_NAMES",
    "GIT_TOOL_VERSION",
    "PERM_GIT_COMMIT",
    "PERM_GIT_FETCH",
    "PERM_GIT_PUBLISH",
    "PERM_GIT_STATUS",
    "BindingLookupRefused",
    "GitToolset",
    "GitTraceEntry",
    "GitTransportPort",
    "ModeRecordingAudit",
    "NothingToCommit",
    "ProtectedBranchRejected",
    "RemoteRejected",
    "RepoBindingRegistry",
    "TransportError",
    "jail_path",
    "mode_recording_audit",
]
