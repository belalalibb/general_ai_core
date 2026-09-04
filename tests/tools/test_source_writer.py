"""R169 A2 — bounded SourceWriter: jail, denylist, caps, preconditions, audit."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.source_write import SourceWriteOp, SourceWriteRefusalCode
from core.tools.executor import ToolExecutor
from core.tools.source_reader import DEFAULT_DENIED_PATTERNS
from core.tools.source_writer import SourceWriter, source_write_handler
from core.usage.memory import InMemoryUsageAccounting
from tests.tools.test_tool_fabric import (
    PERM_COMMIT,
    PERM_READ,
    TENANT,
    make_gate,
    make_request,
    make_tool,
)

run = asyncio.run

ENGINE_SRC = "def route():\n    return 'decision'\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "core").mkdir(parents=True)
    (root / "core" / "engine.py").write_text(ENGINE_SRC, encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
    (root / "link_out").symlink_to(outside / "secret.txt")
    (root / "dir_out").symlink_to(outside, target_is_directory=True)
    return root


# --- construction & surface -------------------------------------------------


def test_root_must_be_directory(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        SourceWriter(root=f)


def test_denylist_shared_with_reader(repo: Path) -> None:
    assert SourceWriter(root=repo).denied_patterns == DEFAULT_DENIED_PATTERNS


def test_public_surface_is_minimal(repo: Path) -> None:
    public = {n for n in dir(SourceWriter(root=repo)) if not n.startswith("_")}
    assert public == {
        "root",
        "max_write_bytes",
        "max_ops",
        "denied_patterns",
        "write",
        "ops_used",
    }


# --- jail -------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", "/etc/passwd", "\\abs", "../x.py", "core/../../x.py"])
def test_non_relative_paths_refused(repo: Path, path: str) -> None:
    result = SourceWriter(root=repo).write(op="create", path=path, content="x")
    assert result["ok"] is False
    assert result["code"] == SourceWriteRefusalCode.PATH_NOT_RELATIVE


def test_symlink_file_escape_refused(repo: Path, tmp_path: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="overwrite", path="link_out", content="pwned", expected_sha256=sha("outside\n")
    )
    assert result["code"] == SourceWriteRefusalCode.PATH_OUTSIDE_ROOT
    assert (tmp_path / "outside" / "secret.txt").read_text() == "outside\n"


def test_symlink_dir_escape_refused(repo: Path, tmp_path: Path) -> None:
    result = SourceWriter(root=repo).write(op="create", path="dir_out/new.txt", content="x")
    assert result["code"] == SourceWriteRefusalCode.PATH_OUTSIDE_ROOT
    assert not (tmp_path / "outside" / "new.txt").exists()


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".git/hooks/pre-commit",
        "core/.git/x",
        ".env",
        ".env.local",
        "core/.env",
        "deploy/server.pem",
        "id_rsa.key",
    ],
)
def test_denylist_refused(repo: Path, path: str) -> None:
    result = SourceWriter(root=repo).write(op="create", path=path, content="x")
    assert result["code"] == SourceWriteRefusalCode.PATH_DENIED
    assert (repo / ".git" / "config").read_text() == "[core]\n"


def test_delete_root_itself_is_not_a_file(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="delete", path=".", expected_sha256=sha(""))
    assert result["code"] == SourceWriteRefusalCode.NOT_A_FILE


# --- caps -------------------------------------------------------------------


def test_byte_cap_refuses_oversize(repo: Path) -> None:
    w = SourceWriter(root=repo, max_write_bytes=8)
    ok = w.write(op="create", path="a.txt", content="12345678")
    assert ok["ok"] is True
    bad = w.write(op="create", path="b.txt", content="123456789")
    assert bad["code"] == SourceWriteRefusalCode.WRITE_TOO_LARGE
    assert not (repo / "b.txt").exists()


def test_byte_cap_counts_utf8_bytes(repo: Path) -> None:
    w = SourceWriter(root=repo, max_write_bytes=4)
    assert w.write(op="create", path="a.txt", content="éé")["ok"] is True
    bad = w.write(op="create", path="b.txt", content="ééé")
    assert bad["code"] == SourceWriteRefusalCode.WRITE_TOO_LARGE


def test_op_cap(repo: Path) -> None:
    w = SourceWriter(root=repo, max_ops=2)
    r1 = w.write(op="create", path="a.txt", content="1")
    assert r1["ops_remaining"] == 1
    r2 = w.write(op="create", path="b.txt", content="2")
    assert r2["ops_remaining"] == 0
    r3 = w.write(op="create", path="c.txt", content="3")
    assert r3["code"] == SourceWriteRefusalCode.OP_CAP_EXCEEDED
    assert not (repo / "c.txt").exists()
    assert w.ops_used == 2


def test_refusals_do_not_consume_ops(repo: Path) -> None:
    w = SourceWriter(root=repo, max_ops=1)
    w.write(op="create", path="../x", content="1")
    w.write(op="create", path=".env", content="1")
    w.write(op="overwrite", path="core/engine.py", content="1")
    assert w.ops_used == 0
    assert w.write(op="create", path="ok.txt", content="1")["ok"] is True


# --- create -----------------------------------------------------------------


def test_create_ok(repo: Path) -> None:
    content = "x = 1\ny=2\n"
    result = SourceWriter(root=repo).write(op="create", path="core/new.py", content=content)
    assert result["ok"] is True
    assert result["op"] == SourceWriteOp.CREATE
    assert result["path"] == "core/new.py"
    assert result["bytes_written"] == len(b"x = 1\ny=2\n") == 10
    assert result["sha256"] == sha(content)
    assert result["previous_sha256"] is None
    assert (repo / "core" / "new.py").read_text() == content


def test_create_makes_parents(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="create", path="a/b/c.txt", content="deep")
    assert result["ok"] is True
    assert (repo / "a" / "b" / "c.txt").read_text() == "deep"


def test_create_existing_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="create", path="core/engine.py", content="x")
    assert result["code"] == SourceWriteRefusalCode.FILE_EXISTS
    assert (repo / "core" / "engine.py").read_text() == ENGINE_SRC


def test_create_needs_content(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="create", path="core/new.py")
    assert result["code"] == SourceWriteRefusalCode.CONTENT_REQUIRED


# --- overwrite --------------------------------------------------------------


def test_overwrite_ok(repo: Path) -> None:
    new = "def route():\n    return 'other'\n"
    result = SourceWriter(root=repo).write(
        op="overwrite", path="core/engine.py", content=new, expected_sha256=sha(ENGINE_SRC)
    )
    assert result["ok"] is True
    assert result["op"] == SourceWriteOp.OVERWRITE
    assert result["previous_sha256"] == sha(ENGINE_SRC)
    assert result["sha256"] == sha(new)
    assert (repo / "core" / "engine.py").read_text() == new


def test_overwrite_mismatch_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="overwrite", path="core/engine.py", content="x", expected_sha256=sha("stale")
    )
    assert result["code"] == SourceWriteRefusalCode.PRECONDITION_MISMATCH
    assert (repo / "core" / "engine.py").read_text() == ENGINE_SRC


def test_overwrite_requires_precondition(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="overwrite", path="core/engine.py", content="x")
    assert result["code"] == SourceWriteRefusalCode.PRECONDITION_REQUIRED
    assert (repo / "core" / "engine.py").read_text() == ENGINE_SRC


def test_overwrite_missing_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="overwrite", path="core/nope.py", content="x", expected_sha256=sha("")
    )
    assert result["code"] == SourceWriteRefusalCode.FILE_MISSING


def test_overwrite_directory_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="overwrite", path="core", content="x", expected_sha256=sha("")
    )
    assert result["code"] == SourceWriteRefusalCode.NOT_A_FILE


def test_overwrite_needs_content(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="overwrite", path="core/engine.py", expected_sha256=sha(ENGINE_SRC)
    )
    assert result["code"] == SourceWriteRefusalCode.CONTENT_REQUIRED
    assert (repo / "core" / "engine.py").read_text() == ENGINE_SRC


# --- delete -----------------------------------------------------------------


def test_delete_ok(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="delete", path="core/engine.py", expected_sha256=sha(ENGINE_SRC)
    )
    assert result["ok"] is True
    assert result["op"] == SourceWriteOp.DELETE
    assert result["sha256"] is None
    assert result["previous_sha256"] == sha(ENGINE_SRC)
    assert result["bytes_written"] == 0
    assert not (repo / "core" / "engine.py").exists()


def test_delete_mismatch_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="delete", path="core/engine.py", expected_sha256=sha("stale")
    )
    assert result["code"] == SourceWriteRefusalCode.PRECONDITION_MISMATCH
    assert (repo / "core" / "engine.py").exists()


def test_delete_requires_precondition(repo: Path) -> None:
    result = SourceWriter(root=repo).write(op="delete", path="core/engine.py")
    assert result["code"] == SourceWriteRefusalCode.PRECONDITION_REQUIRED
    assert (repo / "core" / "engine.py").exists()


def test_delete_missing_refused(repo: Path) -> None:
    result = SourceWriter(root=repo).write(
        op="delete", path="core/nope.py", expected_sha256=sha("")
    )
    assert result["code"] == SourceWriteRefusalCode.FILE_MISSING


def test_refusal_codes_are_distinct() -> None:
    values = [c.value for c in SourceWriteRefusalCode]
    assert len(values) == 12
    assert len(set(values)) == 12


# --- executor / audit -------------------------------------------------------


def make_world(root: Path, *, permissions: list[str] | None = None):  # type: ignore[no-untyped-def]
    perms = permissions if permissions is not None else [PERM_COMMIT]
    tool = make_tool(
        permissions=perms,
        approval_policy={PERM_COMMIT: "none", PERM_READ: "none"},
    )
    gate = make_gate(tool)
    audit = InMemoryAuditLog()
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="test", task_units_limit=1_000.0)
    writer = SourceWriter(root=root)
    executor = ToolExecutor(
        gate=gate,
        handlers={tool.id: source_write_handler(writer)},
        audit=audit,
        usage=usage,
    )
    return tool, executor, audit, writer


def tool_call_events(audit: InMemoryAuditLog):  # type: ignore[no-untyped-def]
    return list(audit.read(TENANT, AuditEventType.TOOL_CALL))


def test_executor_admitted_write_is_audited_once(repo: Path) -> None:
    tool, executor, audit, _ = make_world(repo)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),
            arguments={"op": "create", "path": "core/x.py", "content": "x = 1\n"},
        )
    )
    assert record.status == "succeeded"
    assert record.result is not None and record.result["ok"] is True
    assert (repo / "core" / "x.py").read_text() == "x = 1\n"
    events = tool_call_events(audit)
    assert len(events) == 1
    assert events[0].details["status"] == "succeeded"
    assert events[0].details["tool_id"] == str(tool.id)


def test_executor_handler_refusal_is_data(repo: Path) -> None:
    tool, executor, audit, writer = make_world(repo)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),
            arguments={"op": "create", "path": ".git/hooks/pre-commit", "content": "evil"},
        )
    )
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "path_denied"
    assert not (repo / ".git" / "hooks").exists()
    assert writer.ops_used == 0
    assert len(tool_call_events(audit)) == 1


def test_executor_invalid_arguments_are_data(repo: Path) -> None:
    tool, executor, _, writer = make_world(repo)
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),
            arguments={"op": "rename", "path": "core/engine.py"},
        )
    )
    assert record.status == "succeeded"
    assert record.result is not None
    assert record.result["ok"] is False
    assert record.result["code"] == "validation_error"
    assert writer.ops_used == 0


def test_executor_gate_refusal_blocks_write(repo: Path) -> None:
    tool, executor, audit, writer = make_world(repo, permissions=[PERM_READ])
    record = run(
        executor.execute(
            tool_id=tool.id,
            request=make_request(permission=PERM_COMMIT),
            arguments={"op": "create", "path": "core/x.py", "content": "x"},
        )
    )
    assert record.status == "refused"
    assert not (repo / "core" / "x.py").exists()
    assert writer.ops_used == 0
    events = tool_call_events(audit)
    assert len(events) == 1
    assert events[0].details["status"] == "refused"
