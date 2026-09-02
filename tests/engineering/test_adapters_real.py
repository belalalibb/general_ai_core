"""REAL adapters: SubprocessCommandRunner spawns processes; GitCli drives a real repo.

No mocks: a temporary git repository with a bare remote proves commit → push →
merge (including a conflict that is aborted cleanly).
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from core.contracts.engineering import CommandRequest
from core.engineering import CommandPolicy, GitRefused, WorkspaceFs
from infrastructure.engineering import GitCli, SubprocessCommandRunner

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _git(cwd: Path, *args: str) -> str:
    return _run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *args], cwd)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "work"
    bare = tmp_path / "remote.git"
    work.mkdir()
    _git(tmp_path, "init", "--bare", "-q", str(bare))
    _git(work, "init", "-q", "-b", "main")
    (work / "README.md").write_text("hello\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "main")
    return work, bare


class TestSubprocessRunner:
    def test_runs_allowlisted_python_and_captures_output(self, tmp_path: Path) -> None:
        ws = WorkspaceFs(root=tmp_path)
        (tmp_path / "hello.py").write_text("print('hi from ws')\n")
        policy = CommandPolicy(allowlist=(Path(sys.executable).name, "python3"))
        admitted = policy.admit(ws, CommandRequest(argv=[sys.executable, "hello.py"]))
        result = asyncio.run(SubprocessCommandRunner().run(admitted))
        assert result.exit_code == 0
        assert result.stdout.strip() == "hi from ws"
        assert result.timed_out is False

    def test_timeout_kills_and_reports(self, tmp_path: Path) -> None:
        ws = WorkspaceFs(root=tmp_path)
        (tmp_path / "sleep.py").write_text("import time\ntime.sleep(30)\n")
        policy = CommandPolicy(allowlist=(Path(sys.executable).name, "python3"))
        admitted = policy.admit(
            ws, CommandRequest(argv=[sys.executable, "sleep.py"], timeout_ms=300)
        )
        result = asyncio.run(SubprocessCommandRunner().run(admitted))
        assert result.timed_out is True
        assert result.exit_code is None
        assert result.duration_ms < 10_000

    def test_env_is_scrubbed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_TOKEN", "leak")
        ws = WorkspaceFs(root=tmp_path)
        (tmp_path / "env.py").write_text("import os\nprint(os.environ.get('SECRET_TOKEN'))\n")
        policy = CommandPolicy(allowlist=(Path(sys.executable).name, "python3"))
        admitted = policy.admit(ws, CommandRequest(argv=[sys.executable, "env.py"]))
        result = asyncio.run(SubprocessCommandRunner().run(admitted))
        assert result.stdout.strip() == "None"

    def test_spawn_failure_is_data(self, tmp_path: Path) -> None:
        ws = WorkspaceFs(root=tmp_path)
        policy = CommandPolicy(allowlist=("definitely-missing-binary",))
        admitted = policy.admit(ws, CommandRequest(argv=["definitely-missing-binary"]))
        result = asyncio.run(SubprocessCommandRunner().run(admitted))
        assert result.exit_code is None
        assert "spawn failed" in result.stderr


class TestGitCli:
    def test_status_log_branches_diff(self, repo: tuple[Path, Path]) -> None:
        work, _ = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        status = asyncio.run(git.status())
        assert status.branch == "main" and status.clean and status.head
        assert asyncio.run(git.log(limit=5))[0].subject == "init"
        assert asyncio.run(git.branches()) == ["main"]
        (work / "README.md").write_text("changed\n")
        assert "+changed" in asyncio.run(git.diff())
        assert asyncio.run(git.status()).clean is False

    def test_commit_push_merge_roundtrip(self, repo: tuple[Path, Path]) -> None:
        work, bare = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        asyncio.run(git.checkout("base", create=True))  # marker for compare()
        asyncio.run(git.checkout("main"))
        assert asyncio.run(git.checkout("feat/x", create=True)) == "feat/x"
        (work / "feat.txt").write_text("feature\n")
        committed = asyncio.run(git.commit("feat: add feat.txt"))
        assert committed.committed and committed.sha
        pushed = asyncio.run(git.push("feat/x"))
        assert pushed.pushed and pushed.remote == "origin"
        assert "feat/x" in _git(bare, "branch", "--format=%(refname:short)")
        merged = asyncio.run(git.merge("feat/x", into="main"))
        assert merged.merged and merged.sha and merged.conflicts == []
        assert (work / "feat.txt").exists()
        assert "feat.txt" in asyncio.run(git.compare("base", "main"))

    def test_nothing_to_commit_is_data_not_exception(self, repo: tuple[Path, Path]) -> None:
        work, _ = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        result = asyncio.run(git.commit("noop"))
        assert result.committed is False and result.reason

    def test_merge_conflict_is_aborted_and_reported(self, repo: tuple[Path, Path]) -> None:
        work, _ = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        asyncio.run(git.checkout("conflict", create=True))
        (work / "README.md").write_text("theirs\n")
        asyncio.run(git.commit("theirs"))
        asyncio.run(git.checkout("main"))
        (work / "README.md").write_text("ours\n")
        asyncio.run(git.commit("ours"))
        result = asyncio.run(git.merge("conflict", into="main"))
        assert result.merged is False
        assert result.reason == "conflicts"
        assert result.conflicts == ["README.md"]
        # Aborted cleanly: tree is back to `ours`, no MERGE_HEAD.
        assert (work / "README.md").read_text() == "ours\n"
        assert asyncio.run(git.status()).clean is True

    def test_push_to_unconfigured_remote_refused_as_data(self, repo: tuple[Path, Path]) -> None:
        work, _ = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        result = asyncio.run(git.push("main", remote="upstream"))
        assert result.pushed is False and result.reason == "remote_not_configured"

    def test_invalid_ref_refused_before_spawn(self, repo: tuple[Path, Path]) -> None:
        work, _ = repo
        git = GitCli(root=work, runner=SubprocessCommandRunner())
        with pytest.raises(GitRefused):
            asyncio.run(git.checkout("--upload-pack=evil"))
