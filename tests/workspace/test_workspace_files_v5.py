"""Phase V5 chunk 1: workspace file surface over ObjectStoragePort.

Frozen-definition mapping (roadmap V5, verbatim clauses):

- "over ObjectStoragePort (files, listing, manifests)" ->
  round-trip / head / delete / list / manifest tests over the EXISTING
  InMemoryObjectStorage binding — the primitive owns no storage.
- tenant isolation (20 §6, port posture preserved) ->
  test_cross_tenant_read_is_absent.
- workspace namespacing (two workspaces of ONE tenant) ->
  test_workspaces_of_same_tenant_are_disjoint.
- P7 path discipline -> the validate_path refusal matrix (traversal,
  absolute, backslash, control chars, empty segments) BEFORE any storage
  call.
- P6 manifest-is-derived -> test_manifest_reflects_live_storage.

Hermetic — in-memory storage, zero I/O.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.storage import InMemoryObjectStorage, ObjectNotFound
from core.workspace import (
    InvalidWorkspacePath,
    WorkspaceFile,
    WorkspaceFiles,
    validate_path,
)

TENANT = uuid4()
WS = uuid4()


def make_files() -> WorkspaceFiles:
    return WorkspaceFiles(InMemoryObjectStorage())


# --- files over the port -------------------------------------------------------------


def test_put_get_round_trip() -> None:
    files = make_files()
    stored = files.put(TENANT, WS, "docs/readme.md", b"# hi", "text/markdown")
    assert isinstance(stored, WorkspaceFile)
    assert stored.workspace_id == WS
    assert stored.path == "docs/readme.md"
    assert stored.size_bytes == 4
    assert stored.content_type == "text/markdown"
    assert files.get(TENANT, WS, "docs/readme.md") == b"# hi"


def test_overwrite_allowed() -> None:
    files = make_files()
    files.put(TENANT, WS, "a.txt", b"one", "text/plain")
    files.put(TENANT, WS, "a.txt", b"two", "text/plain")
    assert files.get(TENANT, WS, "a.txt") == b"two"


def test_head_returns_metadata_without_payload() -> None:
    files = make_files()
    files.put(TENANT, WS, "img.png", b"\x89PNG", "image/png")
    meta = files.head(TENANT, WS, "img.png")
    assert meta.size_bytes == 4
    assert meta.content_type == "image/png"


def test_delete_then_absent() -> None:
    files = make_files()
    files.put(TENANT, WS, "tmp.bin", b"x", "application/octet-stream")
    files.delete(TENANT, WS, "tmp.bin")
    with pytest.raises(ObjectNotFound):
        files.get(TENANT, WS, "tmp.bin")


def test_absent_file_raises_object_not_found() -> None:
    """P1: the port's own anti-enumeration error, no parallel taxonomy."""
    files = make_files()
    with pytest.raises(ObjectNotFound):
        files.head(TENANT, WS, "never/existed.txt")
    with pytest.raises(ObjectNotFound):
        files.delete(TENANT, WS, "never/existed.txt")


# --- isolation -------------------------------------------------------------------------


def test_cross_tenant_read_is_absent() -> None:
    """20 §6 — the port's tenant scoping is preserved verbatim."""
    files = make_files()
    files.put(TENANT, WS, "secret.txt", b"data", "text/plain")
    with pytest.raises(ObjectNotFound):
        files.get(uuid4(), WS, "secret.txt")


def test_workspaces_of_same_tenant_are_disjoint() -> None:
    """The ws/{id}/ namespace keeps sibling workspaces apart."""
    files = make_files()
    other_ws = uuid4()
    files.put(TENANT, WS, "file.txt", b"mine", "text/plain")
    with pytest.raises(ObjectNotFound):
        files.get(TENANT, other_ws, "file.txt")
    assert files.list_paths(TENANT, other_ws) == ()


# --- listing + manifest -----------------------------------------------------------------


def test_list_paths_returns_workspace_relative_paths() -> None:
    files = make_files()
    files.put(TENANT, WS, "a/one.txt", b"1", "text/plain")
    files.put(TENANT, WS, "a/two.txt", b"2", "text/plain")
    files.put(TENANT, WS, "b/three.txt", b"3", "text/plain")
    assert sorted(files.list_paths(TENANT, WS)) == [
        "a/one.txt",
        "a/two.txt",
        "b/three.txt",
    ]
    assert sorted(files.list_paths(TENANT, WS, prefix="a/")) == [
        "a/one.txt",
        "a/two.txt",
    ]


def test_manifest_reflects_live_storage() -> None:
    """P6: the manifest is DERIVED from storage, never a stored claim."""
    files = make_files()
    files.put(TENANT, WS, "x.txt", b"xxxx", "text/plain")
    files.put(TENANT, WS, "y.txt", b"yy", "text/plain")
    manifest = files.manifest(TENANT, WS)
    assert manifest.workspace_id == WS
    assert {f.path for f in manifest.files} == {"x.txt", "y.txt"}
    assert manifest.total_bytes == 6
    # deletion is immediately visible — no stored manifest to drift
    files.delete(TENANT, WS, "x.txt")
    assert {f.path for f in files.manifest(TENANT, WS).files} == {"y.txt"}


def test_empty_workspace_manifest() -> None:
    files = make_files()
    manifest = files.manifest(TENANT, WS)
    assert manifest.files == ()
    assert manifest.total_bytes == 0


# --- P7 path discipline ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "reason_part"),
    [
        ("", "non-empty"),
        ("/etc/passwd", "must be relative"),
        ("a/../b", "'..' is not allowed"),
        ("..", "'..' is not allowed"),
        ("a/./b", "'.' is not allowed"),
        ("a//b", "empty path segment"),
        ("a/b/", "empty path segment"),
        ("a\\b", "backslash"),
        ("a\x00b", "control characters"),
        ("a\nb", "control characters"),
    ],
)
def test_invalid_paths_refused_named(path: str, reason_part: str) -> None:
    with pytest.raises(InvalidWorkspacePath) as exc:
        validate_path(path)
    assert reason_part in str(exc.value)


def test_invalid_path_never_reaches_storage() -> None:
    """A refused path must not touch the port (P7 — refuse pre-I/O)."""

    class ExplodingStorage:
        def __getattr__(self, name: str) -> object:
            raise AssertionError("storage must not be touched")

    files = WorkspaceFiles(ExplodingStorage())  # type: ignore[arg-type]
    for op in (
        lambda: files.put(TENANT, WS, "../up", b"", "text/plain"),
        lambda: files.get(TENANT, WS, "/abs"),
        lambda: files.head(TENANT, WS, "a//b"),
        lambda: files.delete(TENANT, WS, "a\\b"),
        lambda: files.list_paths(TENANT, WS, prefix=".."),
    ):
        with pytest.raises(InvalidWorkspacePath):
            op()


def test_valid_paths_accepted_verbatim() -> None:
    for path in ("a.txt", "a/b/c.tar.gz", "with space.md", "unicode-ملف.txt"):
        assert validate_path(path) == path
