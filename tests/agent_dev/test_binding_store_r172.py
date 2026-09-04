"""R172 C2 — persistent, fail-closed, tenant-scoped repo-binding store.

Durability: same-directory temp -> flush -> fsync -> os.replace, file 0o600,
dir 0o700, path refused inside any protected working tree. Load is
fail-closed: missing / unreadable / malformed / invalid records are skipped
and REPORTED, never raised into the tool path, never partially resurrected.
INV-3: only ``credential_ref`` is serialised — the token bytes never touch disk.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from apps.agent_dev.git_tools import BindingLookupRefused, RepoBindingRegistry
from core.contracts.binding_store import BindingStoreDocument, BindingStoreLoadReport
from core.contracts.publish_mode import PublishMode
from core.contracts.repo_binding import GitRefusalCode, RepoBinding
from core.secrets.memory import InMemorySecretManager
from core.tools.binding_store import BindingStoreRefused, JsonBindingStore

TENANT = UUID("00000000-0000-0000-0000-00000000c201")
OTHER = UUID("00000000-0000-0000-0000-00000000c202")
TOKEN = "ghp_" + "Z" * 36  # synthetic; must never appear in the store bytes


def _binding(tenant: UUID = TENANT, *, ref: str = "credref_x", root: str = "/tmp/repo") -> RepoBinding:
    return RepoBinding(
        tenant_id=tenant,
        remote_url="https://github.com/example/repo.git",
        branch="main",
        local_root=root,
        credential_ref=ref,
        allowed_modes=frozenset({PublishMode.PULL_REQUEST, PublishMode.DIRECT_PUSH}),
        label="demo",
    )


def _store(tmp_path: Path, **kw: object) -> JsonBindingStore:
    return JsonBindingStore(tmp_path / "state" / "bindings.json", **kw)  # type: ignore[arg-type]


# --- durability -------------------------------------------------------------


def test_save_creates_dir_0700_and_file_0600(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.save([_binding()])
    d = tmp_path / "state"
    f = d / "bindings.json"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert not list(d.glob("*.tmp*")), "temp file must be replaced, not left behind"


def test_save_is_atomic_on_interrupted_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    first = _binding()
    store.save([first])
    before = (tmp_path / "state" / "bindings.json").read_bytes()

    real_replace = os.replace

    def boom(*a: object, **k: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(BindingStoreRefused):
        store.save([first, _binding(ref="credref_y")])
    monkeypatch.setattr(os, "replace", real_replace)

    assert (tmp_path / "state" / "bindings.json").read_bytes() == before
    report = store.load()
    assert [b.id for b in report.bindings] == [first.id]


def test_round_trip_preserves_every_field(tmp_path: Path) -> None:
    store = _store(tmp_path)
    b = _binding()
    store.save([b])
    report = store.load()
    assert isinstance(report, BindingStoreLoadReport)
    assert report.bindings == (b,)
    assert report.skipped == ()
    assert report.bindings[0].allowed_modes == b.allowed_modes


def test_store_refuses_path_inside_protected_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(BindingStoreRefused, match="inside a protected working tree"):
        JsonBindingStore(repo / ".dev" / "bindings.json", outside_of=(repo,))
    # sibling path is fine
    JsonBindingStore(tmp_path / "state" / "bindings.json", outside_of=(repo,))


# --- fail-closed load -------------------------------------------------------


def test_load_missing_file_is_empty_not_error(tmp_path: Path) -> None:
    report = _store(tmp_path).load()
    assert report.bindings == ()
    assert report.skipped == ()
    assert report.source_state == "missing"


def test_load_malformed_json_skips_everything_and_reports(tmp_path: Path) -> None:
    p = tmp_path / "state" / "bindings.json"
    p.parent.mkdir(mode=0o700)
    p.write_text("{not json", encoding="utf-8")
    report = _store(tmp_path).load()
    assert report.bindings == ()
    assert report.source_state == "malformed"
    assert report.skipped and report.skipped[0].reason.startswith("malformed")


def test_load_skips_invalid_record_keeps_valid_ones(tmp_path: Path) -> None:
    good = _binding()
    doc = BindingStoreDocument(version=1, bindings=(good,)).model_dump(mode="json")
    bad = dict(doc["bindings"][0])
    bad["remote_url"] = "ftp://not-https"  # fails RemoteUrl pattern
    bad["id"] = str(uuid4())
    doc["bindings"].append(bad)
    doc["bindings"].append({"garbage": True})
    p = tmp_path / "state" / "bindings.json"
    p.parent.mkdir(mode=0o700)
    p.write_text(json.dumps(doc), encoding="utf-8")

    report = _store(tmp_path).load()
    assert [b.id for b in report.bindings] == [good.id]
    assert len(report.skipped) == 2
    assert {s.index for s in report.skipped} == {1, 2}
    assert report.source_state == "partial"


def test_load_unknown_version_skips_all(tmp_path: Path) -> None:
    p = tmp_path / "state" / "bindings.json"
    p.parent.mkdir(mode=0o700)
    p.write_text(json.dumps({"version": 99, "bindings": []}), encoding="utf-8")
    report = _store(tmp_path).load()
    assert report.bindings == ()
    assert report.source_state == "malformed"


def test_load_unreadable_file_reports_not_raises(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores file modes")
    p = tmp_path / "state" / "bindings.json"
    p.parent.mkdir(mode=0o700)
    p.write_text("{}", encoding="utf-8")
    p.chmod(0)
    try:
        report = _store(tmp_path).load()
    finally:
        p.chmod(0o600)
    assert report.bindings == ()
    assert report.source_state == "unreadable"


# --- INV-3 ------------------------------------------------------------------


def test_serialised_bytes_contain_ref_never_token(tmp_path: Path) -> None:
    secrets = InMemorySecretManager()
    ref = secrets.store(TENANT, TOKEN)
    store = _store(tmp_path)
    store.save([_binding(ref=ref)])
    raw = (tmp_path / "state" / "bindings.json").read_bytes()
    assert ref.encode() in raw
    assert TOKEN.encode() not in raw
    assert b"ghp_" not in raw


# --- registry integration ---------------------------------------------------


def test_registry_without_store_is_unchanged() -> None:
    reg = RepoBindingRegistry()
    b = reg.register(_binding())
    assert reg.get(b.id, tenant_id=TENANT) == b
    assert reg.load_report is None


def test_registry_with_store_persists_and_survives_restart(tmp_path: Path) -> None:
    store = _store(tmp_path)
    reg1 = RepoBindingRegistry(store=store)
    b = reg1.register(_binding())
    # "process restart": brand-new registry over the same file
    reg2 = RepoBindingRegistry(store=JsonBindingStore(tmp_path / "state" / "bindings.json"))
    assert reg2.get(b.id, tenant_id=TENANT) == b
    assert reg2.load_report is not None and reg2.load_report.source_state == "ok"


def test_tenant_scoping_survives_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    reg1 = RepoBindingRegistry(store=store)
    b = reg1.register(_binding())
    reg2 = RepoBindingRegistry(store=JsonBindingStore(tmp_path / "state" / "bindings.json"))
    with pytest.raises(BindingLookupRefused) as ei:
        reg2.get(b.id, tenant_id=OTHER)
    assert ei.value.code is GitRefusalCode.BINDING_TENANT_MISMATCH
    with pytest.raises(BindingLookupRefused) as ei2:
        reg2.get(uuid4(), tenant_id=OTHER)
    assert ei2.value.code is GitRefusalCode.BINDING_UNKNOWN
    assert reg2.list_for_tenant(OTHER) == []
    assert [x.id for x in reg2.list_for_tenant(TENANT)] == [b.id]


def test_registry_never_resurrects_partial_store(tmp_path: Path) -> None:
    good = _binding()
    doc = BindingStoreDocument(version=1, bindings=(good,)).model_dump(mode="json")
    doc["bindings"].append({"garbage": True})
    p = tmp_path / "state" / "bindings.json"
    p.parent.mkdir(mode=0o700)
    p.write_text(json.dumps(doc), encoding="utf-8")
    reg = RepoBindingRegistry(store=JsonBindingStore(p))
    assert reg.load_report is not None
    assert reg.load_report.source_state == "partial"
    assert reg.get(good.id, tenant_id=TENANT) == good
    # the garbage record does not exist in any form
    assert len(reg.list_for_tenant(TENANT)) == 1
    # a subsequent register re-saves only valid records; garbage is gone from disk
    reg.register(_binding(ref="credref_2", root="/tmp/other"))
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert len(on_disk["bindings"]) == 2
    assert all("garbage" not in r for r in on_disk["bindings"])
