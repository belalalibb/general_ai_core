"""V8 chunk 2 — snapshot + patch algebra (ADR-0009).

Acceptance-criteria mapping (operator's 12-item list, this chunk's share):

- criterion 1 (proposed source changes are versioned) -> content-addressed
  snapshot ids + patch_hash version identity tests.
- criterion 5 groundwork (deterministic) -> same content = same id
  regardless of construction order; hash stability tests.
- criterion 8 groundwork (rollback is real) -> invert_patch round-trip law
  proven for every operation kind.

§14 posture asserted structurally here: the package namespace exposes no
write/push/secret capability of any kind (test_package_is_pure_values).
"""

from __future__ import annotations

import pytest

from core.sourcechange import (
    MalformedPatch,
    PatchNotApplicable,
    PatchOperation,
    PatchOpKind,
    SourcePatch,
    SourceSnapshot,
    apply_patch,
    invert_patch,
    patch_hash,
)
from core.workspace.errors import InvalidWorkspacePath


def _snapshot(**files: bytes) -> SourceSnapshot:
    return SourceSnapshot.from_files(
        {name.replace("__", "/").replace("_", "."): body for name, body in files.items()}
    )


BASE = SourceSnapshot.from_files(
    {
        "src/app.py": b"print('v1')\n",
        "src/util.py": b"def add(a, b):\n    return a + b\n",
        "README.md": b"# demo\n",
    }
)


# --- Snapshot identity (criterion 1: versioned) -----------------------------------


def test_snapshot_id_is_content_derived_and_order_independent() -> None:
    a = SourceSnapshot.from_files({"a.txt": b"one", "b.txt": b"two"})
    b = SourceSnapshot.from_files({"b.txt": b"two", "a.txt": b"one"})
    assert a.snapshot_id == b.snapshot_id
    assert len(a.snapshot_id) == 64  # sha256 hex


def test_snapshot_id_changes_with_content_and_with_path() -> None:
    base = SourceSnapshot.from_files({"a.txt": b"one"})
    other_content = SourceSnapshot.from_files({"a.txt": b"two"})
    other_path = SourceSnapshot.from_files({"b.txt": b"one"})
    assert base.snapshot_id != other_content.snapshot_id
    assert base.snapshot_id != other_path.snapshot_id


def test_snapshot_is_immutable_structurally() -> None:
    snap = SourceSnapshot.from_files({"a.txt": b"one"})
    with pytest.raises(TypeError):
        snap.files["a.txt"] = b"tampered"  # type: ignore[index]
    with pytest.raises(AttributeError):
        snap.snapshot_id = "forged"  # type: ignore[misc]


def test_snapshot_integrity_verification() -> None:
    assert BASE.verify_integrity() is True
    forged = SourceSnapshot(snapshot_id="0" * 64, files=BASE.files)
    assert forged.verify_integrity() is False


def test_snapshot_manifest_is_derived_evidence() -> None:
    manifest = BASE.manifest()
    assert [row[0] for row in manifest] == sorted(BASE.files)
    for path, content_hash, size in manifest:
        assert size == len(BASE.files[path])
        assert len(content_hash) == 64


def test_snapshot_paths_are_validated_p7() -> None:
    for bad in ("/abs.txt", "../up.txt", "a/../b.txt", "a\\b.txt", ""):
        with pytest.raises(InvalidWorkspacePath):
            SourceSnapshot.from_files({bad: b"x"})


# --- Patch shape rules (P7) ---------------------------------------------------------


def test_patch_operation_shape_rules_named() -> None:
    with pytest.raises(MalformedPatch):
        PatchOperation(kind=PatchOpKind.ADD_FILE, path="a.txt")  # no content
    with pytest.raises(MalformedPatch):
        PatchOperation(kind=PatchOpKind.MODIFY_FILE, path="a.txt")
    with pytest.raises(MalformedPatch):
        PatchOperation(
            kind=PatchOpKind.DELETE_FILE, path="a.txt", content=b"x"
        )  # delete carries no content
    with pytest.raises(InvalidWorkspacePath):
        PatchOperation(kind=PatchOpKind.ADD_FILE, path="../up.py", content=b"x")


def test_patch_refuses_empty_and_duplicate_paths() -> None:
    with pytest.raises(MalformedPatch):
        SourcePatch(operations=())
    op = PatchOperation(kind=PatchOpKind.ADD_FILE, path="a.txt", content=b"x")
    dup = PatchOperation(kind=PatchOpKind.DELETE_FILE, path="a.txt")
    with pytest.raises(MalformedPatch):
        SourcePatch(operations=(op, dup))


# --- Application semantics (pure, all-or-nothing) -----------------------------------


def test_apply_add_modify_delete() -> None:
    patch = SourcePatch(
        operations=(
            PatchOperation(
                kind=PatchOpKind.ADD_FILE, path="src/new.py", content=b"new\n"
            ),
            PatchOperation(
                kind=PatchOpKind.MODIFY_FILE, path="src/app.py", content=b"print('v2')\n"
            ),
            PatchOperation(kind=PatchOpKind.DELETE_FILE, path="README.md"),
        )
    )
    result = apply_patch(BASE, patch)
    assert result.files["src/new.py"] == b"new\n"
    assert result.files["src/app.py"] == b"print('v2')\n"
    assert "README.md" not in result.files
    # base is untouched (value semantics)
    assert BASE.files["src/app.py"] == b"print('v1')\n"
    assert "README.md" in BASE.files
    assert result.snapshot_id != BASE.snapshot_id


def test_apply_refusals_are_named_and_total() -> None:
    with pytest.raises(PatchNotApplicable, match="already exists"):
        apply_patch(
            BASE,
            SourcePatch(
                operations=(
                    PatchOperation(
                        kind=PatchOpKind.ADD_FILE, path="src/app.py", content=b"x"
                    ),
                )
            ),
        )
    for kind in (PatchOpKind.MODIFY_FILE, PatchOpKind.DELETE_FILE):
        content = b"x" if kind is PatchOpKind.MODIFY_FILE else None
        with pytest.raises(PatchNotApplicable, match="does not exist"):
            apply_patch(
                BASE,
                SourcePatch(
                    operations=(
                        PatchOperation(kind=kind, path="ghost.py", content=content),
                    )
                ),
            )


def test_apply_is_all_or_nothing() -> None:
    """One inapplicable op anywhere -> NOTHING is applied (P6)."""
    patch = SourcePatch(
        operations=(
            PatchOperation(
                kind=PatchOpKind.ADD_FILE, path="src/new.py", content=b"new\n"
            ),
            PatchOperation(kind=PatchOpKind.DELETE_FILE, path="ghost.py"),
        )
    )
    with pytest.raises(PatchNotApplicable):
        apply_patch(BASE, patch)
    # base unchanged and no partial snapshot observable anywhere
    assert "src/new.py" not in BASE.files
    assert BASE.verify_integrity()


def test_apply_is_deterministic() -> None:
    patch = SourcePatch(
        operations=(
            PatchOperation(
                kind=PatchOpKind.MODIFY_FILE, path="src/app.py", content=b"print('v2')\n"
            ),
        )
    )
    first = apply_patch(BASE, patch)
    second = apply_patch(BASE, patch)
    assert first.snapshot_id == second.snapshot_id
    assert first.manifest() == second.manifest()


# --- Version identity (criterion 7 substrate) ---------------------------------------


def test_patch_hash_binds_content_and_base() -> None:
    patch_a = SourcePatch(
        operations=(
            PatchOperation(kind=PatchOpKind.ADD_FILE, path="a.txt", content=b"one"),
        )
    )
    patch_b = SourcePatch(
        operations=(
            PatchOperation(kind=PatchOpKind.ADD_FILE, path="a.txt", content=b"two"),
        )
    )
    other_base = SourceSnapshot.from_files({"x.txt": b"x"})
    h = patch_hash(patch_a, BASE.snapshot_id)
    assert h == patch_hash(patch_a, BASE.snapshot_id)  # stable
    assert h != patch_hash(patch_b, BASE.snapshot_id)  # content-bound
    assert h != patch_hash(patch_a, other_base.snapshot_id)  # base-bound
    assert len(h) == 64


def test_patch_hash_is_operation_order_independent() -> None:
    """Per-path duplicate-free ops are order-independent — the hash agrees."""
    op1 = PatchOperation(kind=PatchOpKind.ADD_FILE, path="a.txt", content=b"one")
    op2 = PatchOperation(kind=PatchOpKind.DELETE_FILE, path="README.md")
    forward = SourcePatch(operations=(op1, op2))
    reverse = SourcePatch(operations=(op2, op1))
    assert patch_hash(forward, BASE.snapshot_id) == patch_hash(
        reverse, BASE.snapshot_id
    )
    assert (
        apply_patch(BASE, forward).snapshot_id
        == apply_patch(BASE, reverse).snapshot_id
    )


# --- Rollback law (criterion 8 substrate) --------------------------------------------


def test_invert_round_trip_every_kind() -> None:
    patch = SourcePatch(
        operations=(
            PatchOperation(
                kind=PatchOpKind.ADD_FILE, path="src/new.py", content=b"new\n"
            ),
            PatchOperation(
                kind=PatchOpKind.MODIFY_FILE, path="src/app.py", content=b"print('v2')\n"
            ),
            PatchOperation(kind=PatchOpKind.DELETE_FILE, path="README.md"),
        )
    )
    inverse = invert_patch(patch, BASE)
    patched = apply_patch(BASE, patch)
    restored = apply_patch(patched, inverse)
    assert restored.snapshot_id == BASE.snapshot_id
    assert dict(restored.files) == dict(BASE.files)


def test_invert_restores_exact_prior_content() -> None:
    patch = SourcePatch(
        operations=(
            PatchOperation(
                kind=PatchOpKind.MODIFY_FILE, path="src/util.py", content=b"changed\n"
            ),
        )
    )
    inverse = invert_patch(patch, BASE)
    (op,) = inverse.operations
    assert op.kind is PatchOpKind.MODIFY_FILE
    assert op.content == BASE.files["src/util.py"]


def test_invert_refuses_inapplicable_patch_named() -> None:
    ghost_delete = SourcePatch(
        operations=(PatchOperation(kind=PatchOpKind.DELETE_FILE, path="ghost.py"),)
    )
    with pytest.raises(PatchNotApplicable, match="does not exist"):
        invert_patch(ghost_delete, BASE)


# --- §14 structural posture -----------------------------------------------------------


def test_package_is_pure_values_no_io_capability() -> None:
    """The package namespace exposes NO write/push/secret capability.

    Structural check: nothing importable from core.sourcechange mentions
    remotes, credentials, or environment access — the sandbox incapability
    starts at the primitive layer (ADR-0009).
    """
    import core.sourcechange as pkg

    forbidden_fragments = ("push", "remote", "secret", "credential", "env")
    for name in pkg.__all__:
        lowered = name.lower()
        assert not any(fragment in lowered for fragment in forbidden_fragments)
    # And the module imports no IO/network machinery at all.
    import sys

    for module_name in (
        "core.sourcechange",
        "core.sourcechange.snapshot",
        "core.sourcechange.patch",
        "core.sourcechange.errors",
    ):
        module = sys.modules[module_name]
        source_names = set(vars(module))
        assert "subprocess" not in source_names
        assert "socket" not in source_names
        assert "os" not in source_names
