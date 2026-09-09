"""R177-FIX-07 — deterministic continuation cursor on bounded listing (F-R177-06).

Before: ``SourceReader.list_files`` (and the ``ws_list`` / ``source_list``
tools over it) hard-truncated at ``max_entries`` with no way to continue —
a 501-file tree could never be listed in full. After: an additive
``after: str | None`` argument (the last relative path already received)
resumes the SAME sorted, jailed, denylist-filtered walk strictly after that
path; the response carries ``truncated`` and ``next_after`` (the last path
returned when truncated, else None). Bounds are unchanged; the jail and the
denylist are unchanged — the cursor is a position in the walk, never a path
that is admitted or read.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from core.agent import AgentToolSpec
from core.engineering import (
    AuthorizationLedger,
    CommandPolicy,
    EngineeringBundle,
    WorkspaceFs,
    engineering_tool_specs,
)
from core.tools.registry import ToolRegistry
from core.tools.source_reader import SourceReader, SourceReadRefused
from tests.engineering.test_runtime_authorization import FakeGit, FakeRunner
from tests.tools.test_source_reader import reader

N_FILES = 501


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture()
def big_tree(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    for i in range(N_FILES):
        (tmp_path / "pkg" / f"m{i:04d}.py").write_text(f"V = {i}\n")
    (tmp_path / ".env").write_text("SECRET=x\n")  # denied — must never appear
    return tmp_path


def _paginate(src: SourceReader, **kwargs: Any) -> tuple[list[str], int]:
    """Walk every page via the cursor; return (all files, page count)."""
    files: list[str] = []
    after: str | None = None
    pages = 0
    while True:
        page = src.list_files(after=after, **kwargs)
        pages += 1
        assert isinstance(page["files"], list)
        files.extend(page["files"])
        if not page["truncated"]:
            assert page["next_after"] is None
            return files, pages
        assert isinstance(page["next_after"], str)
        assert page["next_after"] == page["files"][-1]
        after = page["next_after"]


class TestCursor:
    def test_default_call_shape_is_unchanged_plus_next_after(self, big_tree: Path) -> None:
        result = reader(big_tree).list_files()  # default max_entries=500
        assert len(result["files"]) == 500
        assert result["truncated"] is True
        assert result["next_after"] == "pkg/m0499.py"

    def test_501_files_are_listed_in_full_across_two_pages(self, big_tree: Path) -> None:
        files, pages = _paginate(reader(big_tree))
        assert pages == 2
        assert len(files) == N_FILES
        assert files == sorted(files) and len(set(files)) == N_FILES
        assert files[0] == "pkg/m0000.py" and files[-1] == "pkg/m0500.py"
        assert ".env" not in files

    def test_small_pages_continue_deterministically(self, big_tree: Path) -> None:
        files, pages = _paginate(reader(big_tree, max_entries=7))
        assert len(files) == N_FILES
        assert pages == (N_FILES + 6) // 7

    def test_after_is_strictly_exclusive_and_needs_no_existing_file(self, big_tree: Path) -> None:
        src = reader(big_tree, max_entries=3)
        page = src.list_files(after="pkg/m0002.py")
        assert page["files"] == ["pkg/m0003.py", "pkg/m0004.py", "pkg/m0005.py"]
        # A cursor that names no file still positions the walk (pure ordering).
        page = src.list_files(after="pkg/m0002.py.zzz")
        assert page["files"][0] == "pkg/m0003.py"

    def test_after_beyond_the_end_is_an_empty_untruncated_page(self, big_tree: Path) -> None:
        page = reader(big_tree).list_files(after="pkg/m0500.py")
        assert page == {"files": [], "truncated": False, "next_after": None}

    def test_cursor_cannot_widen_the_jail_or_the_denylist(self, big_tree: Path) -> None:
        src = reader(big_tree, max_entries=2)
        # Cursor is compared as an ordering key only — never admitted or read.
        page = src.list_files(after="../../etc")
        assert page["files"][0].startswith("pkg/")
        page = src.list_files(after="")  # empty == no cursor
        assert page["files"] == ["pkg/m0000.py", "pkg/m0001.py"]
        # Denied entries stay invisible on every page.
        files, _ = _paginate(src, glob="**/*")
        assert ".env" not in files
        # The jail on ``rel_path`` is untouched by the new argument.
        with pytest.raises(SourceReadRefused):
            src.list_files("../", after=None)

    def test_scoped_listing_keeps_the_cursor_relative_to_root(self, big_tree: Path) -> None:
        src = reader(big_tree, max_entries=2)
        page = src.list_files("pkg", "*.py", after="pkg/m0001.py")
        assert page["files"] == ["pkg/m0002.py", "pkg/m0003.py"]


class TestToolsCarryTheCursor:
    def test_ws_list_accepts_after_and_returns_next_after(self, big_tree: Path) -> None:
        registry = ToolRegistry()
        bundle = EngineeringBundle(
            workspace=WorkspaceFs(root=big_tree),
            workspace_label="ws",
            command_policy=CommandPolicy(),
            runner=FakeRunner(),
            git=FakeGit(),
            ledger=AuthorizationLedger(None),
        )
        specs = {s.tool.name: s for s in engineering_tool_specs(bundle, registry)}
        ws_list: AgentToolSpec = specs["ws_list"]
        assert "after" in ws_list.arguments
        first = run(ws_list.handler({"path": "", "glob": "**/*.py"}))
        assert first["truncated"] is True and first["next_after"] == "pkg/m0499.py"
        second = run(ws_list.handler({"path": "", "glob": "**/*.py", "after": first["next_after"]}))
        assert second["files"] == ["pkg/m0500.py"]
        assert second["truncated"] is False and second["next_after"] is None

    def test_source_list_spec_advertises_after(self) -> None:
        source = Path("apps/composition/agent.py").read_text(encoding="utf-8")
        assert 'args.get("after")' in source
        assert '"after": "string (last path already received, optional)"' in source
