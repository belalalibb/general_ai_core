"""SourceReader — bounded read-only source inspection (mandate §9).

Pins: root jail (absolute / ``..`` / symlink escapes refused), denylist
(credential-shaped files + .git unreadable AND unlistable), byte-cap with
loud truncation, entry caps, literal (non-regex) search, and the
structural guarantee that the module has no write path.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from core.tools import source_reader as module
from core.tools.source_reader import SourceReader, SourceReadRefused


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("VALUE = 1\nneedle_here\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text("def test_a():\n    pass\n")
    (tmp_path / ".env").write_text("SECRET=x\n")
    (tmp_path / "server.key").write_text("PRIVATE\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("token=abc\n")
    (tmp_path / "big.txt").write_bytes(b"a" * 100)
    return tmp_path


def reader(root: Path, **kwargs: object) -> SourceReader:
    return SourceReader(root=root, **kwargs)  # type: ignore[arg-type]


class TestJail:
    def test_read_inside_root_succeeds(self, tree: Path) -> None:
        result = reader(tree).read_file("pkg/mod.py")
        assert result["path"] == "pkg/mod.py"
        assert "VALUE = 1" in str(result["content"])
        assert result["truncated"] is False

    def test_absolute_path_refused(self, tree: Path) -> None:
        with pytest.raises(SourceReadRefused):
            reader(tree).read_file("/etc/passwd")

    def test_dotdot_escape_refused(self, tree: Path) -> None:
        with pytest.raises(SourceReadRefused):
            reader(tree).read_file("../outside.txt")

    def test_symlink_escape_refused(self, tree: Path) -> None:
        outside = tree.parent / "outside-secret.txt"
        outside.write_text("secret")
        (tree / "link.txt").symlink_to(outside)
        with pytest.raises(SourceReadRefused):
            reader(tree).read_file("link.txt")

    def test_missing_file_refused_not_raised_raw(self, tree: Path) -> None:
        with pytest.raises(SourceReadRefused):
            reader(tree).read_file("pkg/absent.py")

    def test_non_directory_root_refused_at_construction(self, tree: Path) -> None:
        with pytest.raises(ValueError, match="not a directory"):
            reader(tree / "pkg" / "mod.py")


class TestDenylist:
    @pytest.mark.parametrize("path", [".env", "server.key", ".git/config"])
    def test_denied_files_unreadable(self, tree: Path, path: str) -> None:
        with pytest.raises(SourceReadRefused):
            reader(tree).read_file(path)

    def test_denied_files_not_listed(self, tree: Path) -> None:
        files = reader(tree).list_files()["files"]
        assert isinstance(files, list)
        assert ".env" not in files
        assert "server.key" not in files
        assert all(not name.startswith(".git") for name in files)

    def test_denied_files_not_searched(self, tree: Path) -> None:
        result = reader(tree).search("SECRET", glob="**/*")
        assert result["matches"] == []


class TestBounds:
    def test_byte_cap_truncates_loudly(self, tree: Path) -> None:
        result = reader(tree, max_file_bytes=10).read_file("big.txt")
        assert result["truncated"] is True
        assert len(str(result["content"])) == 10
        assert result["size_bytes"] == 100

    def test_listing_entry_cap(self, tree: Path) -> None:
        result = reader(tree, max_entries=1).list_files()
        files = result["files"]
        assert isinstance(files, list)
        assert len(files) == 1
        assert result["truncated"] is True

    def test_search_match_cap(self, tree: Path) -> None:
        result = reader(tree, max_entries=1).search("e", glob="**/*.py")
        matches = result["matches"]
        assert isinstance(matches, list)
        assert len(matches) == 1
        assert result["truncated"] is True


class TestSearch:
    def test_literal_match_with_line_numbers(self, tree: Path) -> None:
        result = reader(tree).search("needle_here")
        assert result["matches"] == [{"path": "pkg/mod.py", "line": 2, "text": "needle_here"}]

    def test_search_is_literal_not_regex(self, tree: Path) -> None:
        (tree / "pkg" / "lit.py").write_text("a.*b literal\n")
        assert reader(tree).search("a.*b")["matches"] != []
        assert reader(tree).search("axxb")["matches"] == []

    def test_empty_search_refused(self, tree: Path) -> None:
        with pytest.raises(SourceReadRefused):
            reader(tree).search("")


class TestReadOnlyStructure:
    def test_module_has_no_write_path(self) -> None:
        source = inspect.getsource(module)
        for token in (
            "write_text",
            "write_bytes",
            '"w"',
            "'w'",
            '"wb"',
            "unlink",
            "rmdir",
            "chmod",
        ):
            assert token not in source, f"write-capable token found: {token}"

    def test_public_surface_is_read_only(self) -> None:
        public = [n for n in dir(SourceReader) if not n.startswith("_")]
        # ``root`` has no class-level default, so it is instance-only data.
        assert sorted(public) == [
            "denied_patterns",
            "list_files",
            "max_entries",
            "max_file_bytes",
            "read_file",
            "search",
        ]
