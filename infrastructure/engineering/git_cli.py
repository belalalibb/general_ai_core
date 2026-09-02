"""Git CLI adapter for ``GitPort`` — every call goes through the CommandRunnerPort."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.contracts.engineering import (
    CommandResult,
    GitCommitInfo,
    GitCommitResult,
    GitMergeResult,
    GitPushResult,
    GitStatus,
)
from core.engineering.command import AdmittedCommand, CommandRunnerPort
from core.engineering.errors import GitRefused
from core.engineering.git import validate_ref

_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
_MAX_LOG = 200
_MAX_MESSAGE = 2000
_MAX_STDERR = 500


@dataclass(frozen=True)
class GitCli:
    """Runs ``git`` in ``root`` with a fixed identity and NO credential helper."""

    root: Path
    runner: CommandRunnerPort
    remote_name: str = "origin"
    author_name: str = "platform-agent"
    author_email: str = "platform-agent@localhost"
    git_executable: str = "git"

    @property
    def remote(self) -> str:
        return self.remote_name

    async def _git(self, *args: str, timeout_ms: int = 60_000) -> CommandResult:
        argv = (
            self.git_executable,
            "-c",
            f"user.name={self.author_name}",
            "-c",
            f"user.email={self.author_email}",
            "-c",
            "credential.helper=",
            *args,
        )
        return await self.runner.run(
            AdmittedCommand(argv=argv, cwd=self.root, timeout_ms=timeout_ms, env_allowlist=_ENV)
        )

    async def _out(self, *args: str) -> str:
        result = await self._git(*args)
        if result.exit_code != 0:
            raise GitRefused(f"git {args[0]} failed: {result.stderr.strip()[:_MAX_STDERR]}")
        return result.stdout

    async def status(self) -> GitStatus:
        branch = (await self._out("rev-parse", "--abbrev-ref", "HEAD")).strip()
        head_result = await self._git("rev-parse", "HEAD")
        head = head_result.stdout.strip() if head_result.exit_code == 0 else None
        porcelain = await self._out("status", "--porcelain")
        entries = [line for line in porcelain.splitlines() if line.strip()]
        return GitStatus(branch=branch, head=head, clean=not entries, entries=entries)

    async def diff(self, *, ref: str | None = None, staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if ref is not None:
            args.append(validate_ref(ref))
        return await self._out(*args)

    async def log(self, *, limit: int = 20) -> list[GitCommitInfo]:
        count = max(1, min(limit, _MAX_LOG))
        text = await self._out("log", f"-n{count}", "--pretty=format:%H%x1f%s")
        commits: list[GitCommitInfo] = []
        for line in text.splitlines():
            sha, _, subject = line.partition("\x1f")
            if sha:
                commits.append(GitCommitInfo(sha=sha, subject=subject))
        return commits

    async def branches(self) -> list[str]:
        text = await self._out("branch", "--format=%(refname:short)")
        return [line.strip() for line in text.splitlines() if line.strip()]

    async def compare(self, base: str, head: str) -> str:
        return await self._out("diff", f"{validate_ref(base)}...{validate_ref(head)}")

    async def checkout(self, branch: str, *, create: bool = False) -> str:
        target = validate_ref(branch)
        args = ["checkout", "-b", target] if create else ["checkout", target]
        result = await self._git(*args)
        if result.exit_code != 0:
            raise GitRefused(f"checkout failed: {result.stderr.strip()[:_MAX_STDERR]}")
        return target

    async def commit(self, message: str, *, add_all: bool = True) -> GitCommitResult:
        if add_all:
            added = await self._git("add", "-A")
            if added.exit_code != 0:
                return GitCommitResult(committed=False, reason=added.stderr.strip()[:_MAX_STDERR])
        committed = await self._git("commit", "-m", message[:_MAX_MESSAGE])
        if committed.exit_code != 0:
            reason = (committed.stderr or committed.stdout).strip()[:_MAX_STDERR]
            return GitCommitResult(committed=False, reason=reason)
        sha = (await self._out("rev-parse", "HEAD")).strip()
        return GitCommitResult(committed=True, sha=sha)

    async def push(self, branch: str, *, remote: str | None = None) -> GitPushResult:
        target = validate_ref(branch)
        remote_name = remote or self.remote_name
        if remote_name != self.remote_name:
            return GitPushResult(
                pushed=False, remote=remote_name, branch=target, reason="remote_not_configured"
            )
        result = await self._git(
            "push", remote_name, f"{target}:{target}", timeout_ms=120_000
        )
        if result.exit_code != 0:
            return GitPushResult(
                pushed=False,
                remote=remote_name,
                branch=target,
                reason=result.stderr.strip()[:_MAX_STDERR] or "push failed",
            )
        return GitPushResult(pushed=True, remote=remote_name, branch=target)

    async def merge(self, source: str, *, into: str) -> GitMergeResult:
        src, dst = validate_ref(source), validate_ref(into)
        switched = await self._git("checkout", dst)
        if switched.exit_code != 0:
            return GitMergeResult(
                merged=False, into=dst, source=src, reason=switched.stderr.strip()[:_MAX_STDERR]
            )
        merged = await self._git("merge", "--no-edit", src)
        if merged.exit_code != 0:
            unmerged = await self._git("diff", "--name-only", "--diff-filter=U")
            conflicts = [line for line in unmerged.stdout.splitlines() if line.strip()]
            await self._git("merge", "--abort")
            reason = "conflicts" if conflicts else (merged.stderr or merged.stdout).strip()[:_MAX_STDERR]
            return GitMergeResult(
                merged=False, into=dst, source=src, conflicts=conflicts, reason=reason
            )
        sha = (await self._out("rev-parse", "HEAD")).strip()
        return GitMergeResult(merged=True, into=dst, source=src, sha=sha)
