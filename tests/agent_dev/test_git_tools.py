"""R169 A5/A6 — git tools through the dev surface with a FAKE transport.

Live GitHub is NOT EVALUATED here; the transport is a port and these tests
prove the policy layer: tenant-scoped bindings, per-binding path jail,
last-moment token resolution that never leaks, PublishMode enforcement, and
protected-branch refusal with a pull-request fallback suggestion.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from apps.agent_dev.git_tools import (
    GIT_TOOL_NAMES,
    PERM_GIT_COMMIT,
    PERM_GIT_FETCH,
    PERM_GIT_PUBLISH,
    PERM_GIT_STATUS,
    BindingLookupRefused,
    GitToolset,
    NothingToCommit,
    ProtectedBranchRejected,
    RemoteRejected,
    RepoBindingRegistry,
    TransportError,
    jail_path,
)
from apps.agent_dev.surface import (
    DEV_TOOL_NAMES,
    DevAgentSurface,
    build_dev_surface,
    dev_tenant_policy,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.publish_mode import PublishMode
from core.contracts.repo_binding import GitOperation, GitRefusalCode, RepoBinding
from core.contracts.tools import ApprovalRequirement
from core.secrets.memory import InMemorySecretManager
from core.security.firewall import CapabilityFirewall
from core.usage.memory import InMemoryUsageAccounting

TENANT = uuid4()
OTHER_TENANT = uuid4()
TOKEN = "ghp_FAKE_TOKEN_NEVER_LEAKS_0123456789abcdef"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@dataclass
class FakeTransport:
    """Records calls; behaviour driven by flags. Never stores the token."""

    protected_branches: set[str] = field(default_factory=set)
    reject_push: bool = False
    fail_fetch: bool = False
    empty_commit: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)
    tokens_seen: list[str] = field(default_factory=list)
    pushed_branches: list[str] = field(default_factory=list)

    async def fetch(self, binding: RepoBinding, *, token: str) -> str | None:
        self.calls.append(("fetch", str(binding.id)))
        self.tokens_seen.append(token)
        if self.fail_fetch:
            raise TransportError("network unreachable")
        return "abc123"

    async def status(self, binding: RepoBinding):  # type: ignore[no-untyped-def]
        from core.contracts.repo_binding import GitStatusResult

        self.calls.append(("status", str(binding.id)))
        return GitStatusResult(
            binding_id=str(binding.id), branch=binding.branch, head="abc123", clean=True
        )

    async def diff_summary(self, binding: RepoBinding) -> str:
        self.calls.append(("diff", str(binding.id)))
        return "1 file changed"

    async def commit(self, binding: RepoBinding, *, message: str, paths: Sequence[str]) -> str:
        self.calls.append(("commit", ",".join(paths)))
        if self.empty_commit:
            raise NothingToCommit("nothing to commit")
        return "deadbeef"

    async def push(self, binding: RepoBinding, *, branch: str, token: str) -> None:
        self.calls.append(("push", branch))
        self.tokens_seen.append(token)
        if branch in self.protected_branches:
            raise ProtectedBranchRejected(f"branch {branch} is protected")
        if self.reject_push:
            raise RemoteRejected("non-fast-forward")
        self.pushed_branches.append(branch)

    async def open_pull_request(
        self, binding: RepoBinding, *, work_branch: str, title: str, token: str
    ) -> str:
        self.calls.append(("pr", work_branch))
        self.tokens_seen.append(token)
        return f"https://github.com/example/repo/pull/42?head={work_branch}"


@dataclass
class World:
    surface: DevAgentSurface
    toolset: GitToolset
    transport: FakeTransport
    bindings: RepoBindingRegistry
    secrets: InMemorySecretManager
    audit: InMemoryAuditLog
    binding: RepoBinding
    other_binding: RepoBinding
    foreign_binding: RepoBinding


def make_world(
    tmp_path: Path,
    *,
    transport: FakeTransport | None = None,
    allowed: frozenset[PublishMode] | None = None,
    git_granted: bool = True,
) -> World:
    transport = transport or FakeTransport()
    secrets = InMemorySecretManager()
    ref = secrets.store(TENANT, TOKEN)
    foreign_ref = secrets.store(OTHER_TENANT, "other-token")
    bindings = RepoBindingRegistry()
    root_a = tmp_path / "repo_a"
    root_b = tmp_path / "repo_b"
    root_a.mkdir()
    root_b.mkdir()
    kwargs: dict[str, object] = {}
    if allowed is not None:
        kwargs["allowed_modes"] = allowed
    binding = bindings.register(
        RepoBinding(
            tenant_id=TENANT,
            remote_url="https://github.com/example/repo.git",
            branch="main",
            local_root=str(root_a),
            credential_ref=ref,
            **kwargs,  # type: ignore[arg-type]
        )
    )
    other_binding = bindings.register(
        RepoBinding(
            tenant_id=TENANT,
            remote_url="https://github.com/example/other.git",
            branch="main",
            local_root=str(root_b),
            credential_ref=ref,
        )
    )
    foreign_binding = bindings.register(
        RepoBinding(
            tenant_id=OTHER_TENANT,
            remote_url="https://github.com/foreign/repo.git",
            branch="main",
            local_root=str(tmp_path / "foreign"),
            credential_ref=foreign_ref,
        )
    )
    toolset = GitToolset(tenant_id=TENANT, bindings=bindings, transport=transport, secrets=secrets)
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(TENANT, dev_tenant_policy(write=True, git=git_granted))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="dev", task_units_limit=100)
    audit = InMemoryAuditLog()
    surface = build_dev_surface(
        root=root_a, tenant_id=TENANT, firewall=firewall, audit=audit, usage=usage, git=toolset
    )
    return World(
        surface,
        toolset,
        transport,
        bindings,
        secrets,
        audit,
        binding,
        other_binding,
        foreign_binding,
    )


def publish(
    world: World, mode: str | None = None, binding: RepoBinding | None = None, **extra: object
):  # type: ignore[no-untyped-def]
    args: dict[str, object] = {"binding_id": str((binding or world.binding).id), **extra}
    if mode is not None:
        args["mode"] = mode
    return run(world.surface.call(PERM_GIT_PUBLISH, args, approval_state="approved"))


# --- composition -----------------------------------------------------------------


def test_git_tools_join_registry_with_expected_approval(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    names = {t.name for t in world.surface.registry.list_all()}
    assert names == set(DEV_TOOL_NAMES) | set(GIT_TOOL_NAMES)
    reg = world.surface.registry
    ids = world.surface.tool_ids
    assert reg.get(ids[PERM_GIT_FETCH]).approval_policy == {
        PERM_GIT_FETCH: ApprovalRequirement.NONE
    }
    assert reg.get(ids[PERM_GIT_STATUS]).approval_policy == {
        PERM_GIT_STATUS: ApprovalRequirement.NONE
    }
    assert reg.get(ids[PERM_GIT_COMMIT]).approval_policy == {
        PERM_GIT_COMMIT: ApprovalRequirement.BEFORE_ACTION
    }
    assert reg.get(ids[PERM_GIT_PUBLISH]).approval_policy == {
        PERM_GIT_PUBLISH: ApprovalRequirement.BEFORE_ACTION
    }


def test_surface_without_git_is_unchanged(tmp_path: Path) -> None:
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(TENANT, dev_tenant_policy(write=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="dev", task_units_limit=10)
    surface = build_dev_surface(
        root=tmp_path, tenant_id=TENANT, firewall=firewall, audit=InMemoryAuditLog(), usage=usage
    )
    assert set(surface.tool_ids) == set(DEV_TOOL_NAMES)
    assert surface.git is None


def test_toolset_tenant_must_match_surface(tmp_path: Path) -> None:
    toolset = GitToolset(
        tenant_id=OTHER_TENANT,
        bindings=RepoBindingRegistry(),
        transport=FakeTransport(),
        secrets=InMemorySecretManager(),
    )
    usage = InMemoryUsageAccounting()
    with pytest.raises(ValueError, match="tenant"):
        build_dev_surface(
            root=tmp_path,
            tenant_id=TENANT,
            firewall=CapabilityFirewall(),
            audit=InMemoryAuditLog(),
            usage=usage,
            git=toolset,
        )


def test_git_permissions_not_granted_is_firewall_deny(tmp_path: Path) -> None:
    world = make_world(tmp_path, git_granted=False)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    assert record.status == "refused"
    assert record.gate_decision.reason == "firewall_deny"
    assert world.transport.calls == []


# --- fetch / status ----------------------------------------------------------------


def test_fetch_resolves_token_at_last_moment_and_never_returns_it(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    assert record.status == "succeeded"
    assert record.result == {
        "ok": True,
        "binding_id": str(world.binding.id),
        "remote_head": "abc123",
    }
    assert world.transport.tokens_seen == [TOKEN]
    assert TOKEN not in repr(record)
    for event in world.audit.read(TENANT):
        assert TOKEN not in repr(event.details)
        assert world.binding.credential_ref not in repr(event.details)


def test_fetch_unknown_binding_is_typed_refusal(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(uuid4())}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == GitRefusalCode.BINDING_UNKNOWN.value
    assert world.transport.calls == []


def test_fetch_foreign_tenant_binding_is_tenant_mismatch(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.foreign_binding.id)}))
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.BINDING_TENANT_MISMATCH.value
    assert world.transport.calls == []
    assert "other-token" not in repr(record)


def test_fetch_unresolvable_credential_is_typed_refusal(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.secrets.revoke(TENANT, world.binding.credential_ref)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.CREDENTIAL_UNRESOLVED.value
    assert world.transport.calls == []


def test_fetch_transport_error_is_data_not_exception(tmp_path: Path) -> None:
    world = make_world(tmp_path, transport=FakeTransport(fail_fetch=True))
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.TRANSPORT_ERROR.value


def test_fetch_invalid_arguments(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_FETCH, {"binding_id": "not-a-uuid"}))
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.VALIDATION_ERROR.value


def test_status_returns_typed_result(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_STATUS, {"binding_id": str(world.binding.id)}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is True
    assert record.result["branch"] == "main"
    assert record.result["clean"] is True


# --- commit + path jail ------------------------------------------------------------


def test_commit_requires_approval(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            {"binding_id": str(world.binding.id), "message": "m", "paths": ["a.py"]},
        )
    )
    assert record.status == "refused"
    assert record.gate_decision.reason == "tool_approval_required:before_action"


def test_commit_relative_paths_inside_binding(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            {"binding_id": str(world.binding.id), "message": "m", "paths": ["a.py", "src/b.py"]},
            approval_state="approved",
        )
    )
    assert record.status == "succeeded"
    assert record.result == {
        "ok": True,
        "binding_id": str(world.binding.id),
        "sha": "deadbeef",
        "files": 2,
    }
    assert world.transport.calls[-1] == ("commit", "a.py,src/b.py")


def test_commit_path_from_binding_x_refused_under_binding_y(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    path_in_a = str(Path(world.binding.local_root) / "core" / "engine.py")
    record = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            {"binding_id": str(world.other_binding.id), "message": "m", "paths": [path_in_a]},
            approval_state="approved",
        )
    )
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == GitRefusalCode.PATH_OUTSIDE_BINDING.value
    assert record.result["binding_id"] == str(world.other_binding.id)
    assert not any(c[0] == "commit" for c in world.transport.calls)


@pytest.mark.parametrize("path", ["../repo_b/x.py", "/etc/passwd", "a/../../x.py"])
def test_commit_traversal_refused(tmp_path: Path, path: str) -> None:
    world = make_world(tmp_path)
    record = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            {"binding_id": str(world.binding.id), "message": "m", "paths": [path]},
            approval_state="approved",
        )
    )
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.PATH_OUTSIDE_BINDING.value


def test_jail_path_admits_absolute_inside_root_and_normalises(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    inside = str(Path(world.binding.local_root) / "src" / "./x" / ".." / "y.py")
    assert jail_path(world.binding, inside) == "src/y.py"
    assert jail_path(world.binding, "src/../z.py") == "z.py"
    with pytest.raises(BindingLookupRefused) as exc:
        jail_path(world.other_binding, inside)
    assert exc.value.code is GitRefusalCode.PATH_OUTSIDE_BINDING


def test_commit_nothing_to_commit_is_data(tmp_path: Path) -> None:
    world = make_world(tmp_path, transport=FakeTransport(empty_commit=True))
    record = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            {"binding_id": str(world.binding.id), "message": "m", "paths": ["a.py"]},
            approval_state="approved",
        )
    )
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.NOTHING_TO_COMMIT.value


# --- publish modes -------------------------------------------------------------------


def test_publish_requires_approval(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = run(world.surface.call(PERM_GIT_PUBLISH, {"binding_id": str(world.binding.id)}))
    assert record.status == "refused"
    assert record.gate_decision.reason == "tool_approval_required:before_action"
    assert world.transport.calls == []


def test_publish_default_mode_is_pull_request(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world)
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is True
    assert record.result["mode"] == "pull_request"
    assert record.result["pushed"] is True
    assert record.result["branch"] != "main"
    assert record.result["pull_request_url"].startswith("https://github.com/")
    assert world.transport.pushed_branches == [record.result["branch"]]
    assert ("pr", record.result["branch"]) in world.transport.calls


def test_publish_pull_request_honours_work_branch_and_title(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, work_branch="feature/x", title="Add X")
    assert record.result is not None
    assert record.result["branch"] == "feature/x"
    assert "feature/x" in record.result["pull_request_url"]


def test_publish_pull_request_work_branch_equal_to_bound_branch_is_invalid_ref(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    record = publish(world, work_branch="main")
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.INVALID_REF.value
    assert world.transport.pushed_branches == []


def test_publish_invalid_ref_name(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, work_branch="bad..name")
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.INVALID_REF.value


def test_publish_dry_run_touches_nothing(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, mode="dry_run")
    assert record.result is not None
    assert record.result["mode"] == "dry_run"
    assert record.result["pushed"] is False
    assert record.result["diff_summary"] == "1 file changed"
    assert world.transport.tokens_seen == []
    assert world.transport.pushed_branches == []


def test_publish_local_commit_only_touches_no_remote(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, mode="local_commit_only")
    assert record.result is not None
    assert record.result["mode"] == "local_commit_only"
    assert record.result["pushed"] is False
    assert world.transport.tokens_seen == []


def test_direct_push_refused_by_default_with_suggestion(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, mode="direct_push")
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == GitRefusalCode.PUBLISH_MODE_NOT_ALLOWED.value
    assert record.result["suggested_mode"] == "pull_request"
    assert world.transport.tokens_seen == []
    assert world.transport.pushed_branches == []


def test_direct_push_allowed_when_binding_opts_in(tmp_path: Path) -> None:
    world = make_world(tmp_path, allowed=frozenset(PublishMode))
    record = publish(world, mode="direct_push")
    assert record.result is not None
    assert record.result["ok"] is True
    assert record.result["mode"] == "direct_push"
    assert record.result["branch"] == "main"
    assert world.transport.pushed_branches == ["main"]


def test_direct_push_protected_branch_suggests_pull_request(tmp_path: Path) -> None:
    world = make_world(
        tmp_path,
        transport=FakeTransport(protected_branches={"main"}),
        allowed=frozenset(PublishMode),
    )
    record = publish(world, mode="direct_push")
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == GitRefusalCode.REMOTE_REJECTED_PROTECTED_BRANCH.value
    assert record.result["suggested_mode"] == "pull_request"
    assert world.transport.pushed_branches == []


def test_remote_rejected_non_protection_reason(tmp_path: Path) -> None:
    world = make_world(tmp_path, transport=FakeTransport(reject_push=True))
    record = publish(world)
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.REMOTE_REJECTED.value
    assert record.result["suggested_mode"] is None


def test_mode_not_in_binding_allowed_set(tmp_path: Path) -> None:
    world = make_world(tmp_path, allowed=frozenset({PublishMode.DRY_RUN}))
    record = publish(world, mode="pull_request")
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.PUBLISH_MODE_NOT_ALLOWED.value
    assert record.result["suggested_mode"] is None


def test_publish_unknown_mode_is_validation_error(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    record = publish(world, mode="force_push")
    assert record.result is not None
    assert record.result["code"] == GitRefusalCode.VALIDATION_ERROR.value


# --- audit + trace ----------------------------------------------------------------------


def test_publish_audit_event_carries_mode_and_no_secrets(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    publish(world, mode="dry_run")
    publish(world, mode="direct_push")
    publish(world)
    events = world.audit.read(TENANT, event_type=AuditEventType.TOOL_CALL)
    assert [e.details["mode"] for e in events] == ["dry_run", "direct_push", "pull_request"]
    assert all(e.details["status"] == "succeeded" for e in events)
    for event in events:
        assert TOKEN not in repr(event.details)


def test_non_publish_audit_events_have_no_mode(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    run(world.surface.call("source.read", {"action": "list_files"}))
    events = world.audit.read(TENANT, event_type=AuditEventType.TOOL_CALL)
    assert len(events) == 2
    assert all("mode" not in e.details for e in events)


def test_one_audit_event_per_attempt_including_refusals(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    run(world.surface.call(PERM_GIT_PUBLISH, {"binding_id": str(world.binding.id)}))  # refused
    publish(world, mode="direct_push")  # data refusal
    publish(world)  # success
    events = world.audit.read(TENANT, event_type=AuditEventType.TOOL_CALL)
    assert [e.details["status"] for e in events] == ["refused", "succeeded", "succeeded"]
    assert world.audit.count(TENANT) == 3


def test_execution_trace_records_every_git_attempt(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    run(world.surface.call(PERM_GIT_FETCH, {"binding_id": str(world.binding.id)}))
    publish(world, mode="direct_push")
    publish(world)
    trace = world.toolset.trace
    assert [t.operation for t in trace] == [
        GitOperation.FETCH,
        GitOperation.PUBLISH,
        GitOperation.PUBLISH,
    ]
    assert trace[1].ok is False
    assert trace[1].code is GitRefusalCode.PUBLISH_MODE_NOT_ALLOWED
    assert trace[1].mode is PublishMode.DIRECT_PUSH
    assert trace[2].ok is True
    assert trace[2].mode is PublishMode.PULL_REQUEST
    assert all(t.binding_id == str(world.binding.id) for t in trace)
    assert TOKEN not in repr(trace)


def test_registry_list_for_tenant_is_scoped(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    ids = {b.id for b in world.bindings.list_for_tenant(TENANT)}
    assert ids == {world.binding.id, world.other_binding.id}
    assert world.foreign_binding.id not in ids


def test_secret_manager_repr_never_exposes_token(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    assert TOKEN not in repr(world.secrets)
    assert TOKEN not in repr(world.binding)
