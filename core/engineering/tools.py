"""Engineering tool specs — the ONLY way the agent touches a workspace (ADR-0012).

Every tool below is an ``AgentToolSpec`` admitted through the ONE authority
chain (``ToolRegistry → CapabilityFirewall → DeviceRegistry``). Read tools need
only the tenant permission; privileged tools additionally burn an Admin-issued
``EngineeringAuthorization`` ticket via ``AuthorizationLedger.consume_ticket``.
Nothing here is Admin-specific: any tenant with the permission may consume.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from core.agent.runtime import AgentToolSpec
from core.contracts.base import JsonObject
from core.contracts.engineering import (
    ChangeSet,
    CommandRequest,
    CommandResult,
    EngineeringAct,
)
from core.contracts.tools import Tool
from core.engineering.authorization import AuthorizationLedger
from core.engineering.command import CommandPolicy, CommandRunnerPort
from core.engineering.errors import EngineeringRefused
from core.engineering.git import GitPort, validate_ref
from core.engineering.workspace import WorkspaceFs
from core.tools.registry import ToolRegistry
from core.tools.source_reader import SourceReadRefused
from core.workspace.errors import InvalidWorkspacePath

WORKSPACE_READ = "workspace.read"
WORKSPACE_WRITE = "workspace.write"
WORKSPACE_EXEC = "workspace.exec"
GIT_READ = "git.read"
GIT_WRITE = "git.write"

ENGINEERING_PERMISSIONS = frozenset(
    {WORKSPACE_READ, WORKSPACE_WRITE, WORKSPACE_EXEC, GIT_READ, GIT_WRITE}
)
ENGINEERING_READ_PERMISSIONS = frozenset({WORKSPACE_READ, GIT_READ})
ENGINEERING_WRITE_PERMISSIONS = frozenset({WORKSPACE_WRITE, WORKSPACE_EXEC, GIT_WRITE})

AGENT_TOOLS_ENTITLEMENT = "agent.tools"
WORKSPACE_RESOURCE = "workspace:root"


@dataclass(frozen=True)
class EngineeringBundle:
    """Everything the engineering tools need, composed once by apps/composition."""

    workspace: WorkspaceFs
    workspace_label: str
    command_policy: CommandPolicy
    runner: CommandRunnerPort
    git: GitPort
    ledger: AuthorizationLedger


Handler = Callable[[JsonObject], Awaitable[JsonObject]]
ResultCheck = Callable[[JsonObject], str | None]


def _tool(name: str, permission: str) -> Tool:
    return Tool.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "location": "server",
            "permissions": [permission],
            "approval_policy": {permission: "none"},
            "status": "active",
        }
    )


def _refusals_as_errors(call: Handler) -> Handler:
    """Map domain refusals to ``ValueError`` so ToolExecutor records status=failed."""

    async def wrapped(args: JsonObject) -> JsonObject:
        try:
            return await call(args)
        except (EngineeringRefused, SourceReadRefused, InvalidWorkspacePath) as exc:
            raise ValueError(f"engineering refused: {exc}") from exc
        except ValidationError as exc:
            raise ValueError(f"engineering refused: invalid arguments: {exc}") from exc

    return wrapped


def _str(args: JsonObject, key: str, default: str = "") -> str:
    value = args.get(key, default)
    return value if isinstance(value, str) else default


def _bool(args: JsonObject, key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    return value if isinstance(value, bool) else default


def _int(args: JsonObject, key: str, default: int) -> int:
    value = args.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _uuid(args: JsonObject, key: str) -> UUID | None:
    value = args.get(key)
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _command_failed(result: JsonObject) -> str | None:
    if result.get("timed_out") is True:
        return "command timed out"
    code = result.get("exit_code")
    if code != 0:
        return f"command exited with {code}"
    return None


def _dump(model: BaseModel) -> JsonObject:
    return model.model_dump(mode="json")


def engineering_tool_specs(
    bundle: EngineeringBundle, registry: ToolRegistry
) -> list[AgentToolSpec]:
    """Register the engineering tools in the shared registry and return their specs."""

    ws = bundle.workspace
    git = bundle.git
    label = bundle.workspace_label

    def consume(args: JsonObject, act: EngineeringAct, detail: JsonObject) -> None:
        bundle.ledger.consume_ticket(
            authorization_id=_uuid(args, "authorization_id"),
            workspace=label,
            act=act,
            detail=detail,
        )

    # ---- reads -----------------------------------------------------------
    async def ws_read(args: JsonObject) -> JsonObject:
        return ws.reader.read_file(_str(args, "path"))

    async def ws_list(args: JsonObject) -> JsonObject:
        return ws.reader.list_files(_str(args, "path"), _str(args, "glob", "**/*"))

    async def ws_search(args: JsonObject) -> JsonObject:
        return ws.reader.search(
            _str(args, "text"), _str(args, "path"), _str(args, "glob", "**/*.py")
        )

    async def git_status(args: JsonObject) -> JsonObject:
        return _dump(await git.status())

    async def git_diff(args: JsonObject) -> JsonObject:
        ref = _str(args, "ref") or None
        text = await git.diff(ref=ref, staged=_bool(args, "staged"))
        return {"ref": ref, "staged": _bool(args, "staged"), "diff": text}

    async def git_log(args: JsonObject) -> JsonObject:
        entries = await git.log(limit=_int(args, "limit", 20))
        return {"commits": [_dump(entry) for entry in entries]}

    async def git_branches(args: JsonObject) -> JsonObject:
        return {"branches": await git.branches()}

    async def git_compare(args: JsonObject) -> JsonObject:
        base = validate_ref(_str(args, "base"))
        head = validate_ref(_str(args, "head"))
        return {"base": base, "head": head, "diff": await git.compare(base, head)}

    # ---- privileged (ticketed) -------------------------------------------
    # Policy FIRST, ticket SECOND (same order as ws_run): a jail/denylist
    # refusal must never cost the tenant an authorization use.
    async def ws_write(args: JsonObject) -> JsonObject:
        path = _str(args, "path")
        ws.admit(path)
        consume(args, EngineeringAct.FS_WRITE, {"op": "write", "path": path})
        return ws.write_file(path, _str(args, "content"))

    async def ws_move(args: JsonObject) -> JsonObject:
        path, to = _str(args, "path"), _str(args, "to_path")
        ws.admit(path)
        ws.admit(to)
        consume(args, EngineeringAct.FS_WRITE, {"op": "move", "path": path, "to_path": to})
        return ws.move_file(path, to)

    async def ws_delete(args: JsonObject) -> JsonObject:
        path = _str(args, "path")
        ws.admit(path)
        consume(args, EngineeringAct.FS_WRITE, {"op": "delete", "path": path})
        return ws.delete_file(path)

    async def ws_apply_changes(args: JsonObject) -> JsonObject:
        change_set = ChangeSet.model_validate(
            {"changes": args.get("changes", []), "reason": args.get("reason")}
        )
        for change in change_set.changes:
            ws.admit(change.path)
            if change.to_path is not None:
                ws.admit(change.to_path)
        consume(
            args,
            EngineeringAct.FS_WRITE,
            {"op": "apply_changes", "count": len(change_set.changes)},
        )
        return _dump(ws.apply_change_set(change_set))

    async def ws_run(args: JsonObject) -> JsonObject:
        payload: JsonObject = {"argv": args.get("argv", [])}
        if args.get("cwd") is not None:
            payload["cwd"] = args.get("cwd")
        if args.get("timeout_ms") is not None:
            payload["timeout_ms"] = args.get("timeout_ms")
        request = CommandRequest.model_validate(payload)
        admitted = bundle.command_policy.admit(ws, request)
        consume(args, EngineeringAct.CMD_RUN, {"argv": list(admitted.argv)})
        result: CommandResult = await bundle.runner.run(admitted)
        return _dump(result)

    async def git_checkout(args: JsonObject) -> JsonObject:
        branch = validate_ref(_str(args, "branch"))
        create = _bool(args, "create")
        consume(args, EngineeringAct.GIT_COMMIT, {"op": "checkout", "branch": branch})
        return {"branch": await git.checkout(branch, create=create), "created": create}

    async def git_commit(args: JsonObject) -> JsonObject:
        message = _str(args, "message").strip()
        if not message:
            raise ValueError("engineering refused: commit message required")
        consume(args, EngineeringAct.GIT_COMMIT, {"op": "commit"})
        return _dump(await git.commit(message, add_all=_bool(args, "add_all", True)))

    async def git_push(args: JsonObject) -> JsonObject:
        branch = validate_ref(_str(args, "branch"))
        consume(args, EngineeringAct.GIT_PUSH, {"branch": branch})
        return _dump(await git.push(branch))

    async def git_merge(args: JsonObject) -> JsonObject:
        source = validate_ref(_str(args, "source"))
        into = validate_ref(_str(args, "into"))
        consume(args, EngineeringAct.GIT_MERGE, {"source": source, "into": into})
        return _dump(await git.merge(source, into=into))

    ticket_arg: dict[str, str] = {
        "authorization_id": "string (UUID of an Admin-issued authorization)"
    }
    entries: list[tuple[str, str, str, str, dict[str, str], Handler, ResultCheck | None]] = [
        (
            "ws_read",
            WORKSPACE_READ,
            "low",
            "Read a UTF-8 text file inside the workspace.",
            {"path": "string (relative path)"},
            ws_read,
            None,
        ),
        (
            "ws_list",
            WORKSPACE_READ,
            "low",
            "List workspace files under a directory matching a glob.",
            {"path": "string (relative dir, default root)", "glob": "string (default '**/*')"},
            ws_list,
            None,
        ),
        (
            "ws_search",
            WORKSPACE_READ,
            "low",
            "Literal substring search across workspace files.",
            {
                "text": "string",
                "path": "string (relative dir, default root)",
                "glob": "string (default '**/*.py')",
            },
            ws_search,
            None,
        ),
        (
            "git_status",
            GIT_READ,
            "low",
            "Branch, HEAD and working-tree status.",
            {},
            git_status,
            None,
        ),
        (
            "git_diff",
            GIT_READ,
            "low",
            "Diff of the working tree (or against a ref / staged).",
            {"ref": "string (optional)", "staged": "boolean (optional)"},
            git_diff,
            None,
        ),
        (
            "git_log",
            GIT_READ,
            "low",
            "Recent commits.",
            {"limit": "integer (default 20, max 200)"},
            git_log,
            None,
        ),
        ("git_branches", GIT_READ, "low", "List local branches.", {}, git_branches, None),
        (
            "git_compare",
            GIT_READ,
            "low",
            "Diff between two refs (base...head).",
            {"base": "string", "head": "string"},
            git_compare,
            None,
        ),
        (
            "ws_write",
            WORKSPACE_WRITE,
            "medium",
            "Write a UTF-8 text file (requires authorization).",
            {"path": "string", "content": "string", **ticket_arg},
            ws_write,
            None,
        ),
        (
            "ws_move",
            WORKSPACE_WRITE,
            "medium",
            "Move/rename a file (requires authorization).",
            {"path": "string", "to_path": "string", **ticket_arg},
            ws_move,
            None,
        ),
        (
            "ws_delete",
            WORKSPACE_WRITE,
            "medium",
            "Delete a file (requires authorization).",
            {"path": "string", **ticket_arg},
            ws_delete,
            None,
        ),
        (
            "ws_apply_changes",
            WORKSPACE_WRITE,
            "medium",
            "Apply an atomic set of write/move/delete changes (requires authorization).",
            {
                "changes": "array of {kind: write|move|delete, path, content?, to_path?}",
                "reason": "string (optional)",
                **ticket_arg,
            },
            ws_apply_changes,
            None,
        ),
        (
            "ws_run",
            WORKSPACE_EXEC,
            "high",
            "Run an allow-listed command inside the workspace (requires authorization).",
            {
                "argv": "array of strings",
                "cwd": "string (optional relative dir)",
                "timeout_ms": "integer (optional, max 120000)",
                **ticket_arg,
            },
            ws_run,
            _command_failed,
        ),
        (
            "git_checkout",
            GIT_WRITE,
            "medium",
            "Checkout (optionally create) a branch (requires authorization).",
            {"branch": "string", "create": "boolean (optional)", **ticket_arg},
            git_checkout,
            None,
        ),
        (
            "git_commit",
            GIT_WRITE,
            "medium",
            "Stage and commit (requires authorization).",
            {"message": "string", "add_all": "boolean (default true)", **ticket_arg},
            git_commit,
            None,
        ),
        (
            "git_push",
            GIT_WRITE,
            "high",
            "Push a branch to the configured remote (requires authorization).",
            {"branch": "string", **ticket_arg},
            git_push,
            None,
        ),
        (
            "git_merge",
            GIT_WRITE,
            "high",
            "Merge source into target branch; aborts on conflicts (requires authorization).",
            {"source": "string", "into": "string", **ticket_arg},
            git_merge,
            None,
        ),
    ]

    specs: list[AgentToolSpec] = []
    for name, permission, risk, description, arguments, handler, verify in entries:
        tool = _tool(name, permission)
        registry.register(tool)
        specs.append(
            AgentToolSpec(
                tool=tool,
                handler=_refusals_as_errors(handler),
                permission=permission,
                resource=WORKSPACE_RESOURCE,
                entitlement=AGENT_TOOLS_ENTITLEMENT,
                description=description,
                arguments=arguments,
                risk_level=risk,
                verify_result=verify,
            )
        )
    return specs
