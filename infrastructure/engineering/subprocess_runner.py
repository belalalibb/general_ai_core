"""Subprocess adapter for ``CommandRunnerPort`` — spawns ONLY admitted commands."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from asyncio.subprocess import DEVNULL, PIPE

from core.contracts.engineering import MAX_COMMAND_OUTPUT_BYTES, CommandResult
from core.engineering.command import AdmittedCommand


def _cap(blob: bytes) -> tuple[str, bool]:
    truncated = len(blob) > MAX_COMMAND_OUTPUT_BYTES
    text = blob[:MAX_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return text, truncated


class SubprocessCommandRunner:
    """No shell, scrubbed env, own session, hard kill on timeout, capped output."""

    async def run(self, command: AdmittedCommand) -> CommandResult:
        env = {k: os.environ[k] for k in command.env_allowlist if k in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *command.argv,
                cwd=str(command.cwd),
                env=env,
                stdin=DEVNULL,
                stdout=PIPE,
                stderr=PIPE,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            return CommandResult(
                argv=list(command.argv),
                exit_code=None,
                stderr=f"spawn failed: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), command.timeout_ms / 1000)
        except TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
            out, err = await proc.communicate()
        stdout, out_trunc = _cap(out)
        stderr, err_trunc = _cap(err)
        return CommandResult(
            argv=list(command.argv),
            exit_code=None if timed_out else proc.returncode,
            timed_out=timed_out,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=out_trunc,
            stderr_truncated=err_trunc,
        )
