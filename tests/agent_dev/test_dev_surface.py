"""R169 A4 — tests for the separate development-agent composition root."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.agent_dev.surface import (
    DEV_TOOL_NAMES,
    PERM_SOURCE_READ,
    PERM_SOURCE_WRITE,
    DevAgentSurface,
    SourceReadRequest,
    build_dev_surface,
    dev_tenant_policy,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.tools import ApprovalRequirement, ToolLocation, ToolStatus
from core.security.firewall import CapabilityFirewall
from core.tools.executor import ToolExecutor
from core.tools.gate import ToolCallGate
from core.tools.registry import ToolRegistry
from core.usage.memory import InMemoryUsageAccounting

TENANT = uuid4()
ENGINE_SRC = "def engine() -> str:\n    return 'r169-engine-marker'\n"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "engine.py").write_text(ENGINE_SRC)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")
    (tmp_path / ".env").write_text("SECRET=do-not-leak\n")
    return tmp_path


def make_surface(
    root: Path,
    *,
    tenant_id: UUID = TENANT,
    write: bool = True,
    audit: InMemoryAuditLog | None = None,
    budget: float | None = 100.0,
) -> DevAgentSurface:
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(tenant_id, dev_tenant_policy(write=write))
    usage = InMemoryUsageAccounting()
    if budget is not None:
        usage.configure_tenant(tenant_id, plan="dev", task_units_limit=budget)
    return build_dev_surface(
        root=root,
        tenant_id=tenant_id,
        firewall=firewall,
        audit=audit if audit is not None else InMemoryAuditLog(),
        usage=usage,
    )


def write_args(path: str, content: str) -> dict[str, object]:
    return {"op": "create", "path": path, "content": content}


# --- composition -----------------------------------------------------------


def test_surface_composes_core_fabric(repo: Path) -> None:
    surface = make_surface(repo)
    assert isinstance(surface.registry, ToolRegistry)
    assert isinstance(surface.gate, ToolCallGate)
    assert isinstance(surface.executor, ToolExecutor)
    assert surface.root == repo.resolve()
    assert surface.tenant_id == TENANT


def test_registry_holds_exactly_the_dev_tools(repo: Path) -> None:
    surface = make_surface(repo)
    names = sorted(tool.name for tool in surface.registry.list_all())
    assert names == sorted(DEV_TOOL_NAMES)
    assert set(surface.tool_ids) == set(DEV_TOOL_NAMES)


def test_tool_permissions_and_approval_policy(repo: Path) -> None:
    surface = make_surface(repo)
    read = surface.registry.get(surface.tool_ids[PERM_SOURCE_READ])
    write = surface.registry.get(surface.tool_ids[PERM_SOURCE_WRITE])
    assert list(read.permissions) == [PERM_SOURCE_READ]
    assert list(write.permissions) == [PERM_SOURCE_WRITE]
    assert read.approval_policy == {PERM_SOURCE_READ: ApprovalRequirement.NONE}
    assert write.approval_policy == {PERM_SOURCE_WRITE: ApprovalRequirement.BEFORE_ACTION}
    assert read.location is ToolLocation.SERVER
    assert write.status is ToolStatus.ACTIVE


def test_tool_ids_unique_and_disjoint_across_surfaces(repo: Path) -> None:
    a = make_surface(repo)
    b = make_surface(repo)
    assert len(set(a.tool_ids.values())) == len(DEV_TOOL_NAMES)
    assert set(a.tool_ids.values()).isdisjoint(b.tool_ids.values())


def test_dev_tenant_policy_grants() -> None:
    ro = dev_tenant_policy(write=False)
    rw = dev_tenant_policy(write=True)
    assert PERM_SOURCE_READ in ro.granted_permissions
    assert PERM_SOURCE_WRITE not in ro.granted_permissions
    assert {PERM_SOURCE_READ, PERM_SOURCE_WRITE} <= set(rw.granted_permissions)


def test_root_must_be_a_directory(repo: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        make_surface(repo / "core" / "engine.py")


# --- source.read -----------------------------------------------------------


def test_read_file_returns_content(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": "core/engine.py"}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is True
    assert record.result["content"] == ENGINE_SRC


def test_list_files_recursive_glob(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "list_files", "glob": "**/*.py"}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert any(str(f).endswith("core/engine.py") for f in record.result["files"])


def test_search_finds_marker(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "search", "text": "r169-engine-marker"}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert len(record.result["matches"]) >= 1


def test_read_denied_pattern_is_typed_refusal_without_content(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": ".env"}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "read_refused"
    assert "SECRET" not in repr(record.result)


@pytest.mark.parametrize("path", ["../x.py", "/etc/passwd", ".git/config", ""])
def test_read_jail_refuses_escapes(repo: Path, path: str) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": path}))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "read_refused"
    assert "content" not in record.result


@pytest.mark.parametrize(
    "arguments",
    [{"action": "delete", "path": "x"}, {"path": "x"}, {"action": "search"}],
)
def test_read_invalid_arguments_become_validation_error(
    repo: Path, arguments: dict[str, object]
) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_READ, arguments))
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "validation_error"


def test_source_read_request_defaults() -> None:
    request = SourceReadRequest(action="list_files")
    assert request.path == ""
    assert request.glob is None
    assert request.text is None


# --- source.write ----------------------------------------------------------


def test_write_without_approval_is_refused(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(surface.call(PERM_SOURCE_WRITE, write_args("new.py", "x = 1\n")))
    assert record.status == "refused"
    assert record.gate_decision.admitted is False
    assert record.gate_decision.reason == "tool_approval_required:before_action"
    assert not (repo / "new.py").exists()


def test_write_with_approval_succeeds(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(
        surface.call(PERM_SOURCE_WRITE, write_args("new.py", "x = 1\n"), approval_state="approved")
    )
    assert record.status == "succeeded"
    assert record.result is not None
    assert "sha256" in record.result
    assert (repo / "new.py").read_text() == "x = 1\n"
    assert surface.writer.ops_used == 1


def test_write_denied_pattern_is_typed_refusal(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(
        surface.call(
            PERM_SOURCE_WRITE,
            write_args(".git/hooks/pre-commit", "#!/bin/sh\n"),
            approval_state="approved",
        )
    )
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "path_denied"
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()


def test_write_not_granted_is_firewall_deny(repo: Path) -> None:
    surface = make_surface(repo, write=False)
    record = run(
        surface.call(PERM_SOURCE_WRITE, write_args("new.py", "x = 1\n"), approval_state="approved")
    )
    assert record.status == "refused"
    assert record.gate_decision.reason == "firewall_deny"


def test_unknown_tenant_is_firewall_deny(repo: Path) -> None:
    surface = make_surface(repo)
    record = run(
        surface.call(
            PERM_SOURCE_READ, {"action": "read_file", "path": "core/engine.py"}, tenant_id=uuid4()
        )
    )
    assert record.status == "refused"
    assert record.gate_decision.reason == "firewall_deny"


def test_gate_refuses_undeclared_permission(repo: Path) -> None:
    surface = make_surface(repo)
    decision = surface.gate.admit(
        tool_id=surface.tool_ids[PERM_SOURCE_READ],
        request=surface.request(PERM_SOURCE_WRITE),
    )
    assert decision.admitted is False
    assert decision.reason == f"permission_undeclared:{PERM_SOURCE_WRITE}"


def test_no_usage_entitlement_is_typed_budget_refusal(repo: Path) -> None:
    surface = make_surface(repo, budget=None)
    record = run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": "core/engine.py"}))
    assert record.status == "refused"
    assert record.gate_decision.admitted is True
    assert record.error == "entitlement_exceeded"


def test_unknown_tool_name_raises_key_error(repo: Path) -> None:
    surface = make_surface(repo)
    with pytest.raises(KeyError):
        run(surface.call("git.push", {}))


# --- audit -----------------------------------------------------------------


def test_audit_records_every_attempt(repo: Path) -> None:
    audit = InMemoryAuditLog()
    surface = make_surface(repo, audit=audit)
    run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": "core/engine.py"}))
    run(surface.call(PERM_SOURCE_WRITE, write_args("a.py", "a = 1\n"), approval_state="approved"))
    run(surface.call(PERM_SOURCE_WRITE, write_args("b.py", "b = 1\n")))
    events = audit.read(TENANT, event_type=AuditEventType.TOOL_CALL)
    assert [e.details["status"] for e in events] == ["succeeded", "succeeded", "refused"]
    assert events[-1].details["gate_reason"] == "tool_approval_required:before_action"
    assert {e.details["tool_id"] for e in events} <= {
        str(i) for i in surface.tool_ids.values()
    } | set(surface.tool_ids.values())


def test_audit_never_carries_content(repo: Path) -> None:
    audit = InMemoryAuditLog()
    surface = make_surface(repo, audit=audit)
    run(surface.call(PERM_SOURCE_READ, {"action": "read_file", "path": "core/engine.py"}))
    run(
        surface.call(
            PERM_SOURCE_WRITE,
            write_args("m.py", "marker = 'r169-write-marker'\n"),
            approval_state="approved",
        )
    )
    for event in audit.read(TENANT, event_type=AuditEventType.TOOL_CALL):
        blob = repr(event.details)
        assert "r169-engine-marker" not in blob
        assert "r169-write-marker" not in blob
        assert "content" not in event.details
