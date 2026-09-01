"""AGENT_SOURCE_ROOT composition seam — mandate §9 wiring.

Pins: absent/blank/invalid env = no source tools (platform still boots);
valid directory = the three R0 tools appear in the /v1/agent tools list;
the helper never raises at composition time.
"""

from __future__ import annotations

from pathlib import Path

from apps.composition.runtime import _source_reader


class TestSourceReaderSeam:
    def test_blank_env_yields_none(self) -> None:
        assert _source_reader("") is None
        assert _source_reader("   ") is None

    def test_missing_directory_yields_none_never_raises(self) -> None:
        assert _source_reader("/definitely/not/a/real/dir") is None

    def test_file_path_yields_none(self, tmp_path: Path) -> None:
        target = tmp_path / "afile.txt"
        target.write_text("x")
        assert _source_reader(str(target)) is None

    def test_valid_directory_yields_jailed_reader(self, tmp_path: Path) -> None:
        reader = _source_reader(str(tmp_path))
        assert reader is not None
        assert reader.root == tmp_path.resolve()
