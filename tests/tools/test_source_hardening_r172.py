"""R172 C4 — atomic source writes + deny-check path normalisation.

Writer: every byte-changing write goes through same-directory temp -> write ->
flush -> fsync -> ``os.replace``. An interruption before the rename leaves the
original bytes intact, leaves no temp file behind, is reported as an
``io_error`` refusal (data, not exception), and does NOT poison the next CAS
write against the original digest.

Reader + writer deny-check: the relative path is normalised BEFORE fnmatch so
spelling tricks cannot slip a credential file past the denylist:
zero-width / invisible code points stripped, NTFS alternate-data-stream suffix
(``:stream``) dropped, trailing dots and spaces dropped, casefolded. The raw
path is still checked too (C1's explicit case variants stay: belt and braces).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from core.contracts.source_write import SourceWriteOp, SourceWriteRefusalCode
from core.tools.source_reader import (
    DEFAULT_DENIED_PATTERNS,
    SourceReader,
    SourceReadRefused,
    is_denied,
    normalize_deny_path,
)
from core.tools.source_writer import SourceWriter

ZWJ = "\u200d"
ZWSP = "\u200b"
BOM = "\ufeff"
SOFT_HYPHEN = "\u00ad"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


# --- normaliser (pure) --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (".ENV", ".env"),
        (".Env.local", ".env.local"),
        (".env::$DATA", ".env"),
        (".env:hidden", ".env"),
        (".env.", ".env"),
        (".env ", ".env"),
        (".env. . ", ".env"),
        (f".e{ZWJ}nv", ".env"),
        (f"{ZWSP}.env{BOM}", ".env"),
        (f".e{SOFT_HYPHEN}nv", ".env"),
        ("nested/.ENV.production", "nested/.env.production"),
        ("Server.KEY", "server.key"),
        ("pkg/mod.py", "pkg/mod.py"),
        (".git/config", ".git/config"),
    ],
)
def test_normalize_deny_path(raw: str, expected: str) -> None:
    assert normalize_deny_path(raw) == expected


def test_normalize_is_idempotent() -> None:
    raw = f"nested/.E{ZWJ}NV::$DATA. "
    once = normalize_deny_path(raw)
    assert normalize_deny_path(once) == once


def test_is_denied_checks_raw_and_normalised() -> None:
    # raw match (pattern spelled exactly)
    assert is_denied(".env", DEFAULT_DENIED_PATTERNS)
    # normalised match only
    assert is_denied(".ENV", DEFAULT_DENIED_PATTERNS)
    assert is_denied(f".e{ZWJ}nv", DEFAULT_DENIED_PATTERNS)
    assert is_denied(".env::$DATA", DEFAULT_DENIED_PATTERNS)
    # not denied
    assert not is_denied("pkg/mod.py", DEFAULT_DENIED_PATTERNS)
    assert not is_denied("environment.py", DEFAULT_DENIED_PATTERNS)


# --- reader: variants are denied with DEFAULT patterns only (no C1 list) ------

VARIANTS = [
    ".ENV",
    ".Env.local",
    ".env::$DATA",
    ".env.",
    ".env ",
    f".e{ZWJ}nv",
    "nested/.ENV.production",
    "Server.KEY",
]


def _plant(repo: Path, rel: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("SECRET=1\n", encoding="utf-8")


@pytest.mark.parametrize("rel", VARIANTS)
def test_reader_refuses_normalised_variants(repo: Path, rel: str) -> None:
    _plant(repo, rel)
    reader = SourceReader(repo)  # DEFAULT_DENIED_PATTERNS only — no C1 case patch
    with pytest.raises(SourceReadRefused, match="denied by policy"):
        reader.read_file(rel)


def test_reader_listing_and_search_hide_variants(repo: Path) -> None:
    for rel in VARIANTS:
        _plant(repo, rel)
    reader = SourceReader(repo)
    files = reader.list_files()["files"]
    assert isinstance(files, list)
    assert files == ["pkg/mod.py"], files
    hits = reader.search("SECRET", glob="**/*")["matches"]
    assert hits == []


def test_reader_default_patterns_unchanged() -> None:
    # C4 changes the CHECK, not the LIST (C1's list lives in core/tools/denied_paths.py).
    assert len(DEFAULT_DENIED_PATTERNS) == 13


# --- writer: deny normalisation ------------------------------------------------


@pytest.mark.parametrize("rel", VARIANTS)
def test_writer_refuses_normalised_variants(repo: Path, rel: str) -> None:
    writer = SourceWriter(root=repo)
    out = writer.write(op=SourceWriteOp.CREATE, path=rel, content="SECRET=1\n")
    assert out["ok"] is False
    assert out["code"] == SourceWriteRefusalCode.PATH_DENIED.value
    assert not (repo / rel).exists()
    assert writer.ops_used == 0


# --- writer: atomicity ---------------------------------------------------------


def test_overwrite_is_atomic_on_interrupted_replace(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = repo / "pkg" / "mod.py"
    before = target.read_bytes()
    writer = SourceWriter(root=repo)

    real_replace = os.replace

    def boom(*a: object, **k: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(os, "replace", boom)
    out = writer.write(
        op=SourceWriteOp.OVERWRITE,
        path="pkg/mod.py",
        content="x = 2\n",
        expected_sha256=_sha(before),
    )
    monkeypatch.setattr(os, "replace", real_replace)

    assert out["ok"] is False
    assert out["code"] == SourceWriteRefusalCode.IO_ERROR.value
    assert target.read_bytes() == before, "original bytes must be intact"
    assert not list((repo / "pkg").glob(".*.tmp")), "no temp file left behind"
    assert writer.ops_used == 0, "a failed write does not consume an op"

    # subsequent CAS write against the ORIGINAL digest still succeeds
    out2 = writer.write(
        op=SourceWriteOp.OVERWRITE,
        path="pkg/mod.py",
        content="x = 2\n",
        expected_sha256=_sha(before),
    )
    assert out2["ok"] is True
    assert target.read_text(encoding="utf-8") == "x = 2\n"
    assert out2["previous_sha256"] == _sha(before)
    assert writer.ops_used == 1


def test_create_is_atomic_on_interrupted_replace(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = SourceWriter(root=repo)

    def boom(*a: object, **k: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(os, "replace", boom)
    out = writer.write(op=SourceWriteOp.CREATE, path="pkg/new.py", content="y = 1\n")
    assert out["ok"] is False and out["code"] == SourceWriteRefusalCode.IO_ERROR.value
    assert not (repo / "pkg" / "new.py").exists()
    assert not list((repo / "pkg").glob(".*.tmp"))


def test_overwrite_preserves_file_mode(repo: Path) -> None:
    target = repo / "pkg" / "mod.py"
    target.chmod(0o755)
    before = target.read_bytes()
    out = SourceWriter(root=repo).write(
        op=SourceWriteOp.OVERWRITE,
        path="pkg/mod.py",
        content="x = 3\n",
        expected_sha256=_sha(before),
    )
    assert out["ok"] is True
    assert (target.stat().st_mode & 0o777) == 0o755


def test_create_honours_umask_not_0600(repo: Path) -> None:
    old = os.umask(0o022)
    try:
        out = SourceWriter(root=repo).write(
            op=SourceWriteOp.CREATE, path="pkg/plain.py", content="z = 1\n"
        )
    finally:
        os.umask(old)
    assert out["ok"] is True
    assert ((repo / "pkg" / "plain.py").stat().st_mode & 0o777) == 0o644


def test_writer_never_leaves_temp_files_on_success(repo: Path) -> None:
    writer = SourceWriter(root=repo)
    assert writer.write(op=SourceWriteOp.CREATE, path="pkg/a.py", content="a\n")["ok"] is True
    sha = _sha(b"a\n")
    assert (
        writer.write(op=SourceWriteOp.OVERWRITE, path="pkg/a.py", content="b\n", expected_sha256=sha)[
            "ok"
        ]
        is True
    )
    names = sorted(p.name for p in (repo / "pkg").iterdir())
    assert names == ["a.py", "mod.py"]
