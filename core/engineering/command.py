"""Bounded command execution PORT + admission policy (ADR-0012 §2).

Core owns the RULES; the process-spawning adapter lives in
``infrastructure/engineering`` (core purity — no subprocess here).

- ``argv[0]`` must be in the composition ALLOWLIST (basename match, no
  shell; relative executable paths are refused outright).
- ``cwd`` is workspace-relative and must resolve inside the jail.
- ``timeout_ms`` is capped by the contract (≤120 s) and by the policy.
- Only ``env_allowlist`` variables pass through — credentials never leak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from core.contracts.engineering import MAX_COMMAND_TIMEOUT_MS, CommandRequest, CommandResult
from core.engineering.errors import CommandRefused
from core.engineering.workspace import WorkspaceFs

DEFAULT_COMMAND_ALLOWLIST: tuple[str, ...] = ("python3", "pytest", "ruff")
DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


@dataclass(frozen=True)
class AdmittedCommand:
    """A command AFTER admission — what the adapter is allowed to spawn."""

    argv: tuple[str, ...]
    cwd: Path
    timeout_ms: int
    env_allowlist: tuple[str, ...]


class CommandRunnerPort(Protocol):
    """Spawn one admitted command; the command's own failure is a RESULT."""

    async def run(self, command: AdmittedCommand) -> CommandResult: ...


@dataclass(frozen=True)
class CommandPolicy:
    """Composition DATA: what may run, where, for how long."""

    allowlist: tuple[str, ...] = DEFAULT_COMMAND_ALLOWLIST
    env_allowlist: tuple[str, ...] = DEFAULT_ENV_ALLOWLIST
    max_timeout_ms: int = MAX_COMMAND_TIMEOUT_MS
    denied_arguments: tuple[str, ...] = field(default=("-c", "--command"))

    def admit(self, workspace: WorkspaceFs, request: CommandRequest) -> AdmittedCommand:
        head = request.argv[0]
        if "/" in head and not Path(head).is_absolute():
            raise CommandRefused(f"relative executable path refused: {head}")
        if Path(head).name not in self.allowlist:
            raise CommandRefused(f"executable not allowlisted: {head}")
        for arg in request.argv[1:]:
            if arg in self.denied_arguments:
                raise CommandRefused(f"argument denied by policy: {arg}")
        cwd = workspace.root
        if request.cwd:
            cwd = workspace.admit(request.cwd)
            if not cwd.is_dir():
                raise CommandRefused(f"cwd is not a directory: {request.cwd}")
        timeout = min(request.timeout_ms, self.max_timeout_ms, MAX_COMMAND_TIMEOUT_MS)
        return AdmittedCommand(
            argv=tuple(request.argv),
            cwd=cwd,
            timeout_ms=timeout,
            env_allowlist=self.env_allowlist,
        )


__all__ = [
    "DEFAULT_COMMAND_ALLOWLIST",
    "DEFAULT_ENV_ALLOWLIST",
    "AdmittedCommand",
    "CommandPolicy",
    "CommandRunnerPort",
]
