"""R172 C5 — checkpoint/undo around the dev-surface ``source.write`` apply path.

Model: before a write is applied the manager snapshots the target's bytes into a
content-addressed object store outside the working tree and records
``pre_sha256`` (``None`` when the file did not exist). After a successful write
the checkpoint is *sealed* with ``post_sha256`` (``None`` after a delete). A
refused or crashed apply leaves the checkpoint ``partial``.

Restore (typed data, never raises into the tool path):
  current == pre   -> ``noop``
  current == post  -> ``reverted`` (pre bytes written back atomically; pre None -> file deleted)
  otherwise        -> ``checkpoint_conflict`` refusal, file untouched
A missing/tampered blob is an ``object_store_corrupt`` refusal whose reason names the
"object store". Absent manager the surface is byte-identical to R169/C4.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import stat
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.agent_dev.surface import (
    PERM_SOURCE_WRITE,
    DevAgentSurface,
    build_dev_surface,
    dev_tenant_policy,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.checkpoint import CheckpointRefusalCode
from core.security.firewall import CapabilityFirewall
from core.tools.checkpoint import CheckpointManager, CheckpointRefused, CheckpointStore
from core.usage.memory import InMemoryUsageAccounting

TENANT = UUID("00000000-0000-0000-0000-00000000c501")
OLD = "x = 1\n"
NEW = "x = 2\n"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text(OLD, encoding="utf-8")
    (root / ".env").write_text("SECRET=do-not-snapshot\n", encoding="utf-8")
    return root


def make_manager(tmp_path: Path, repo: Path) -> CheckpointManager:
    store = CheckpointStore(tmp_path / "state" / "checkpoints", outside_of=(repo,))
    return CheckpointManager(root=repo, tenant_id=TENANT, store=store)


def make_surface(repo: Path, manager: CheckpointManager | None) -> DevAgentSurface:
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(TENANT, dev_tenant_policy(write=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="dev", task_units_limit=100)
    kwargs: dict[str, object] = {}
    if manager is not None:
        kwargs["checkpoints"] = manager
    return build_dev_surface(
        root=repo,
        tenant_id=TENANT,
        firewall=firewall,
        audit=InMemoryAuditLog(),
        usage=usage,
        **kwargs,  # type: ignore[arg-type]
    )


def write(surface: DevAgentSurface, **args: object) -> dict[str, Any]:
    record = run(surface.call(PERM_SOURCE_WRITE, dict(args), approval_state="approved"))
    assert record.status == "succeeded", (record.status, record.error, record.error_detail)
    assert record.result is not None
    return dict(record.result)


# --- happy path: snapshot, seal, restore -----------------------------------------


def test_overwrite_snapshots_pre_and_seals_post(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    assert out["ok"] is True
    cp = manager.get(UUID(out["checkpoint_id"]))
    assert cp is not None
    assert cp.tenant_id == TENANT
    assert cp.path == "pkg/mod.py"
    assert cp.pre_sha256 == sha(OLD)
    assert cp.post_sha256 == sha(NEW)
    assert cp.state == "sealed"
    assert cp.sealed_at is not None


def test_restore_reverts_when_current_equals_post(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    res = manager.restore(UUID(out["checkpoint_id"]))
    assert res["ok"] is True
    assert res["outcome"] == "reverted"
    assert res["restored_sha256"] == sha(OLD)
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == OLD


def test_restore_noop_when_current_equals_pre(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    (repo / "pkg" / "mod.py").write_text(OLD, encoding="utf-8")  # someone already undid it
    res = manager.restore(UUID(out["checkpoint_id"]))
    assert res["ok"] is True and res["outcome"] == "noop"
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == OLD


def test_restore_conflict_when_drifted_leaves_file_untouched(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    (repo / "pkg" / "mod.py").write_text("x = 3\n", encoding="utf-8")  # third-party edit
    res = manager.restore(UUID(out["checkpoint_id"]))
    assert res["ok"] is False
    assert res["code"] == CheckpointRefusalCode.CHECKPOINT_CONFLICT.value
    assert res["checkpoint_id"] == out["checkpoint_id"]
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 3\n"


def test_create_has_null_pre_and_restore_deletes(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="create", path="pkg/new.py", content=NEW)
    cp = manager.get(UUID(out["checkpoint_id"]))
    assert cp is not None and cp.pre_sha256 is None and cp.post_sha256 == sha(NEW)
    res = manager.restore(cp.id)
    assert res["ok"] is True and res["outcome"] == "reverted" and res["restored_sha256"] is None
    assert not (repo / "pkg" / "new.py").exists()


def test_delete_restore_recreates_bytes(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="delete", path="pkg/mod.py", expected_sha256=sha(OLD))
    assert not (repo / "pkg" / "mod.py").exists()
    cp = manager.get(UUID(out["checkpoint_id"]))
    assert cp is not None and cp.post_sha256 is None and cp.pre_sha256 == sha(OLD)
    res = manager.restore(cp.id)
    assert res["ok"] is True and res["outcome"] == "reverted"
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == OLD


# --- partial -----------------------------------------------------------------------


def test_refused_write_leaves_partial_checkpoint_restore_noop(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(
        surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha("stale")
    )
    assert out["ok"] is False and out["code"] == "precondition_mismatch"
    cps = manager.list()
    assert len(cps) == 1 and cps[0].state == "partial" and cps[0].post_sha256 is None
    res = manager.restore(cps[0].id)
    assert res["ok"] is True and res["outcome"] == "noop"


def test_partial_with_drift_is_conflict(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    cp = manager.begin("pkg/mod.py", op="overwrite")
    manager.mark_partial(cp.id)
    (repo / "pkg" / "mod.py").write_text("x = 9\n", encoding="utf-8")
    res = manager.restore(cp.id)
    assert res["ok"] is False and res["code"] == "checkpoint_conflict"


# --- durability / restart ------------------------------------------------------------


def test_simulated_restart_restores_from_disk(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    del manager, surface  # "process exit"

    reborn = make_manager(tmp_path, repo)
    assert reborn.load_report is not None and reborn.load_report.source_state == "ok"
    cp = reborn.get(UUID(out["checkpoint_id"]))
    assert cp is not None and cp.state == "sealed"
    res = reborn.restore(cp.id)
    assert res["ok"] is True and res["outcome"] == "reverted"
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == OLD


def test_store_modes_and_location_guard(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    manager.begin("pkg/mod.py", op="overwrite")
    d = tmp_path / "state" / "checkpoints"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    for p in d.rglob("*"):
        if p.is_dir():
            assert stat.S_IMODE(p.stat().st_mode) == 0o700, p
        else:
            assert stat.S_IMODE(p.stat().st_mode) == 0o600, p
    with pytest.raises(Exception, match="inside a protected working tree"):
        CheckpointStore(repo / ".dev" / "checkpoints", outside_of=(repo,))


def test_corrupt_object_store_is_typed_refusal(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(surface, op="overwrite", path="pkg/mod.py", content=NEW, expected_sha256=sha(OLD))
    blob = tmp_path / "state" / "checkpoints" / "objects" / sha(OLD)
    assert blob.is_file()
    blob.write_text("tampered", encoding="utf-8")
    res = manager.restore(UUID(out["checkpoint_id"]))
    assert res["ok"] is False
    assert res["code"] == CheckpointRefusalCode.OBJECT_STORE_CORRUPT.value
    assert "object store" in res["reason"]
    assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == NEW, "file untouched"


def test_malformed_index_fails_closed(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    manager.begin("pkg/mod.py", op="overwrite")
    (tmp_path / "state" / "checkpoints" / "checkpoints.json").write_text("{nope", encoding="utf-8")
    reborn = make_manager(tmp_path, repo)
    assert reborn.load_report is not None and reborn.load_report.source_state == "malformed"
    assert reborn.list() == []
    res = reborn.restore(uuid4())
    assert res["ok"] is False and res["code"] == "checkpoint_unknown"


def test_corrupt_index_record_skipped_not_resurrected(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    cp = manager.begin("pkg/mod.py", op="overwrite")
    idx = tmp_path / "state" / "checkpoints" / "checkpoints.json"
    doc = json.loads(idx.read_text(encoding="utf-8"))
    doc["checkpoints"].append({"id": str(uuid4()), "path": "pkg/mod.py", "state": "sealed"})
    idx.write_text(json.dumps(doc), encoding="utf-8")
    reborn = make_manager(tmp_path, repo)
    assert reborn.load_report is not None and reborn.load_report.source_state == "partial"
    assert [c.id for c in reborn.list()] == [cp.id]


# --- safety / composition -------------------------------------------------------------


def test_denied_path_is_never_snapshotted(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    surface = make_surface(repo, manager)
    out = write(
        surface, op="overwrite", path=".env", content="X=1\n", expected_sha256=sha("whatever")
    )
    assert out["ok"] is False and out["code"] == "path_denied"
    assert "checkpoint_id" not in out
    assert manager.list() == []
    objects = tmp_path / "state" / "checkpoints" / "objects"
    blobs = list(objects.iterdir()) if objects.exists() else []
    assert blobs == []
    with pytest.raises(CheckpointRefused):
        manager.begin(".env", op="overwrite")
    with pytest.raises(CheckpointRefused):
        manager.begin("../outside", op="overwrite")


def test_unknown_checkpoint_is_typed_refusal(tmp_path: Path, repo: Path) -> None:
    manager = make_manager(tmp_path, repo)
    res = manager.restore(uuid4())
    assert res["ok"] is False and res["code"] == "checkpoint_unknown"


def test_absent_manager_surface_is_identical(repo: Path) -> None:
    surface = make_surface(repo, None)
    assert surface.checkpoints is None
    out = write(surface, op="create", path="pkg/new.py", content=NEW)
    assert out["ok"] is True
    assert "checkpoint_id" not in out
    assert set(out) == {
        "ok",
        "op",
        "path",
        "bytes_written",
        "sha256",
        "previous_sha256",
        "ops_remaining",
    }
