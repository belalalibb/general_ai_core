"""R172 C6 — approval payload binding ABOVE the gate (HARVEST row 6).

Owner decision pinned here: ``core/tools/gate.py`` stays string-state only
(``approval_state == "approved"`` admits) and is NOT edited. The binding lives
in the dev surface: when ``build_dev_surface(..., payload_binding=True)`` the
surface canonicalises the call ``arguments`` (sorted keys, fixed separators,
UTF-8, floats rejected), hashes them with sha256 and compares against the
caller-supplied ``approved_payload_hash`` for the write-class permissions
``source.write`` / ``git.commit`` / ``git.publish``. A missing or mismatched
hash is refused as typed data BEFORE the gate and BEFORE any handler runs.
The default (``payload_binding=False``) is byte-identical to the pre-C6
surface so every existing ``approval_state="approved"`` caller stays green.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from apps.agent_dev.git_tools import (
    PERM_GIT_COMMIT,
    PERM_GIT_PUBLISH,
    GitToolset,
    RepoBindingRegistry,
)
from apps.agent_dev.surface import (
    PAYLOAD_BOUND_PERMISSIONS,
    PERM_SOURCE_READ,
    PERM_SOURCE_WRITE,
    DevAgentSurface,
    build_dev_surface,
    dev_tenant_policy,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.approval_binding import ApprovalBindingRefusal, ApprovalBindingRefusalCode
from core.contracts.audit import AuditEventType
from core.contracts.errors import ErrorCode
from core.contracts.repo_binding import RepoBinding
from core.contracts.security import FirewallDecision
from core.secrets.memory import InMemorySecretManager
from core.security.firewall import CapabilityFirewall
from core.tools.gate import ToolCallGate
from core.tools.payload_binding import (
    NonCanonicalPayload,
    canonical_json,
    check_payload_binding,
    payload_hash,
)
from core.usage.memory import InMemoryUsageAccounting
from tests.agent_dev.test_git_tools import FakeTransport

TENANT = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@dataclass
class World:
    surface: DevAgentSurface
    audit: InMemoryAuditLog
    transport: FakeTransport
    binding: RepoBinding
    root: Path


def make_world(tmp_path: Path, *, payload_binding: bool) -> World:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "core").mkdir()
    (root / "core" / "engine.py").write_text("x = 1\n")
    secrets = InMemorySecretManager()
    ref = secrets.store(TENANT, "ghp_" + "F" * 36)
    bindings = RepoBindingRegistry()
    binding = bindings.register(
        RepoBinding(
            tenant_id=TENANT,
            remote_url="https://github.com/example/repo.git",
            branch="main",
            local_root=str(root),
            credential_ref=ref,
        )
    )
    transport = FakeTransport()
    toolset = GitToolset(tenant_id=TENANT, bindings=bindings, transport=transport, secrets=secrets)
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(TENANT, dev_tenant_policy(write=True, git=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="dev", task_units_limit=100)
    audit = InMemoryAuditLog()
    surface = build_dev_surface(
        root=root,
        tenant_id=TENANT,
        firewall=firewall,
        audit=audit,
        usage=usage,
        git=toolset,
        payload_binding=payload_binding,
    )
    return World(surface=surface, audit=audit, transport=transport, binding=binding, root=root)


def write_args(path: str, content: str) -> dict[str, Any]:
    return {"op": "create", "path": path, "content": content}


def tool_call_events(audit: InMemoryAuditLog) -> list[dict[str, Any]]:
    return [
        e.details
        for e in audit.read(TENANT, limit=1000)
        if e.event_type is AuditEventType.TOOL_CALL
    ]


# --------------------------------------------------------------------------- #
# canonicalisation primitives
# --------------------------------------------------------------------------- #


def test_canonical_json_sorted_keys_compact_utf8() -> None:
    out = canonical_json({"b": 1, "a": {"z": [1, 2], "y": "é"}})
    assert isinstance(out, bytes)
    assert out == '{"a":{"y":"é","z":[1,2]},"b":1}'.encode()


def test_canonical_json_is_key_order_independent() -> None:
    one = {"op": "create", "path": "a.py", "content": "x", "meta": {"k": 1, "j": 2}}
    two = {"meta": {"j": 2, "k": 1}, "content": "x", "path": "a.py", "op": "create"}
    assert canonical_json(one) == canonical_json(two)
    assert payload_hash(one) == payload_hash(two)
    assert len(payload_hash(one)) == 64


def test_canonical_json_rejects_floats_recursively() -> None:
    with pytest.raises(NonCanonicalPayload):
        canonical_json({"a": 1.5})
    with pytest.raises(NonCanonicalPayload):
        canonical_json({"a": {"b": [1, float("nan")]}})
    # bools and ints are fine
    assert canonical_json({"t": True, "n": 0}) == b'{"n":0,"t":true}'


def test_canonical_json_rejects_non_json_types() -> None:
    with pytest.raises(NonCanonicalPayload):
        canonical_json({"a": {1, 2}})


def test_check_payload_binding_verdicts() -> None:
    payload = write_args("core/a.py", "x")
    good = payload_hash(payload)
    assert check_payload_binding(payload=payload, approved_hash=good) is None
    assert (
        check_payload_binding(payload=payload, approved_hash=None)
        is ApprovalBindingRefusalCode.APPROVAL_HASH_REQUIRED
    )
    assert (
        check_payload_binding(payload=payload, approved_hash="0" * 64)
        is ApprovalBindingRefusalCode.APPROVAL_PAYLOAD_MISMATCH
    )
    assert (
        check_payload_binding(payload={"f": 1.0}, approved_hash=good)
        is ApprovalBindingRefusalCode.PAYLOAD_NOT_CANONICALISABLE
    )


# --------------------------------------------------------------------------- #
# owner-decision pins
# --------------------------------------------------------------------------- #


def test_gate_admit_has_no_payload_parameter_pin() -> None:
    """The gate stays string-state only — binding is a surface concern (owner decision)."""
    params = set(inspect.signature(ToolCallGate.admit).parameters)
    assert params == {"self", "tool_id", "request", "device_id"}


def test_default_surface_admits_any_payload_under_approved_state(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=False)
    assert world.surface.payload_binding is False
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE, write_args("core/new.py", "y = 2\n"), approval_state="approved"
        )
    )
    assert rec.status == "succeeded"
    assert (world.root / "core" / "new.py").read_text() == "y = 2\n"


def test_scope_is_exactly_the_three_write_class_permissions() -> None:
    assert PAYLOAD_BOUND_PERMISSIONS == frozenset(
        {PERM_SOURCE_WRITE, PERM_GIT_COMMIT, PERM_GIT_PUBLISH}
    )


# --------------------------------------------------------------------------- #
# binding enabled
# --------------------------------------------------------------------------- #


def _assert_refusal(rec: Any, code: ApprovalBindingRefusalCode) -> ApprovalBindingRefusal:
    assert rec.status == "refused"
    assert rec.gate_decision.admitted is False
    assert rec.gate_decision.decision is FirewallDecision.REQUIRE_APPROVAL
    assert rec.gate_decision.reason == code.value
    assert rec.error == ErrorCode.TOOL_APPROVAL_REQUIRED.value
    assert rec.error_detail is not None
    refusal = ApprovalBindingRefusal.model_validate_json(rec.error_detail)
    assert refusal.code is code
    return refusal


def test_missing_hash_on_write_is_refused_before_gate(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    assert world.surface.payload_binding is True
    args = write_args("core/new.py", "y = 2\n")
    rec = run(world.surface.call(PERM_SOURCE_WRITE, args, approval_state="approved"))
    refusal = _assert_refusal(rec, ApprovalBindingRefusalCode.APPROVAL_HASH_REQUIRED)
    assert refusal.permission == PERM_SOURCE_WRITE
    assert refusal.approved_hash is None
    assert refusal.payload_hash == payload_hash(args)
    assert not (world.root / "core" / "new.py").exists()
    events = tool_call_events(world.audit)
    assert len(events) == 1
    assert events[0]["status"] == "refused"
    assert events[0]["gate_reason"] == "approval_hash_required"
    assert events[0]["call_id"] == str(rec.call_id)


def test_mismatched_hash_is_refused_as_approval_payload_mismatch(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    approved = write_args("core/new.py", "y = 2\n")
    substituted = write_args("core/new.py", "import os; os.system('rm -rf /')\n")
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE,
            substituted,
            approval_state="approved",
            approved_payload_hash=payload_hash(approved),
        )
    )
    refusal = _assert_refusal(rec, ApprovalBindingRefusalCode.APPROVAL_PAYLOAD_MISMATCH)
    assert refusal.approved_hash == payload_hash(approved)
    assert refusal.payload_hash == payload_hash(substituted)
    assert not (world.root / "core" / "new.py").exists()
    assert len(tool_call_events(world.audit)) == 1


def test_correct_hash_admits_write(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    args = write_args("core/new.py", "y = 2\n")
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE,
            args,
            approval_state="approved",
            approved_payload_hash=payload_hash(args),
        )
    )
    assert rec.status == "succeeded"
    assert (world.root / "core" / "new.py").read_text() == "y = 2\n"
    assert len(tool_call_events(world.audit)) == 1


def test_key_order_of_arguments_does_not_break_binding(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    original = write_args("core/new.py", "y = 2\n")
    reordered = {"content": "y = 2\n", "path": "core/new.py", "op": "create"}
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE,
            reordered,
            approval_state="approved",
            approved_payload_hash=payload_hash(original),
        )
    )
    assert rec.status == "succeeded"


def test_float_payload_is_refused_as_not_canonicalisable(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    args = {**write_args("core/new.py", "y\n"), "w": 1.5}
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE, args, approval_state="approved", approved_payload_hash="0" * 64
        )
    )
    refusal = _assert_refusal(rec, ApprovalBindingRefusalCode.PAYLOAD_NOT_CANONICALISABLE)
    assert refusal.payload_hash is None
    assert not (world.root / "core" / "new.py").exists()


def test_non_write_class_is_unaffected_when_binding_enabled(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    args = {"action": "read_file", "path": "core/engine.py"}
    rec = run(world.surface.call(PERM_SOURCE_READ, args))
    assert rec.status == "succeeded"
    rec2 = run(world.surface.call(PERM_SOURCE_READ, args, approved_payload_hash="0" * 64))
    assert rec2.status == "succeeded"


def test_unapproved_write_still_falls_through_to_gate(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    args = write_args("core/new.py", "y\n")
    rec = run(world.surface.call(PERM_SOURCE_WRITE, args, approved_payload_hash=payload_hash(args)))
    assert rec.status == "refused"
    assert rec.gate_decision.reason == "tool_approval_required:before_action"
    assert rec.error == ErrorCode.TOOL_APPROVAL_REQUIRED.value


def test_git_commit_and_publish_are_bound(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    bid = str(world.binding.id)
    approved = {"binding_id": bid, "message": "feat: engine", "paths": ["core/engine.py"]}
    swapped = {"binding_id": bid, "message": "feat: engine", "paths": ["core/engine.py", ".env"]}
    rec = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            swapped,
            approval_state="approved",
            approved_payload_hash=payload_hash(approved),
        )
    )
    _assert_refusal(rec, ApprovalBindingRefusalCode.APPROVAL_PAYLOAD_MISMATCH)
    assert world.transport.calls == []
    rec = run(
        world.surface.call(
            PERM_GIT_COMMIT,
            approved,
            approval_state="approved",
            approved_payload_hash=payload_hash(approved),
        )
    )
    assert rec.status == "succeeded"
    assert world.transport.calls == [("commit", "core/engine.py")]

    pub = {"binding_id": bid, "mode": "pull_request"}
    rec = run(world.surface.call(PERM_GIT_PUBLISH, pub, approval_state="approved"))
    _assert_refusal(rec, ApprovalBindingRefusalCode.APPROVAL_HASH_REQUIRED)
    assert world.transport.tokens_seen == []
    rec = run(
        world.surface.call(
            PERM_GIT_PUBLISH,
            pub,
            approval_state="approved",
            approved_payload_hash=payload_hash(pub),
        )
    )
    assert rec.status == "succeeded"


def test_refusal_detail_is_json_data_without_arguments_echo(tmp_path: Path) -> None:
    world = make_world(tmp_path, payload_binding=True)
    sentinel = "SECRET_CONTENT_MUST_NOT_ECHO"
    rec = run(
        world.surface.call(
            PERM_SOURCE_WRITE, write_args("core/new.py", sentinel), approval_state="approved"
        )
    )
    assert rec.error_detail is not None
    assert sentinel not in rec.error_detail
    assert json.loads(rec.error_detail)["code"] == "approval_hash_required"
