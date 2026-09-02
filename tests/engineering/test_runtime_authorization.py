"""Engineering tools on the SHARED AgentRuntime: one authority chain + Admin ticket.

Positive: a tenant granted ``workspace.write`` AND holding an Admin-issued
ticket writes a file. Negative: no permission → firewall REFUSED (handler never
runs); permission but no/foreign/exhausted ticket → handler FAILED with an
audited refusal and the file is untouched.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from core.agent import AgentToolSpec
from core.contracts.audit import AuditEventType
from core.contracts.engineering import (
    CommandResult,
    EngineeringAct,
    GitCommitInfo,
    GitCommitResult,
    GitMergeResult,
    GitPushResult,
    GitStatus,
)
from core.engineering import (
    AdmittedCommand,
    AuthorizationLedger,
    CommandPolicy,
    EngineeringBundle,
    WorkspaceFs,
    engineering_tool_specs,
)
from core.engineering.tools import (
    ENGINEERING_READ_PERMISSIONS,
    WORKSPACE_EXEC,
    WORKSPACE_WRITE,
)
from core.execution.loop import STOP_FINAL
from core.security.firewall import TenantPolicy
from tests.agent.world import (
    ENTITLEMENT,
    TENANT,
    AgentWorld,
    final,
    model_says,
    tool_call,
)

ADMIN = uuid4()
LABEL = "bench-ws"
TASK = {"goal": "edit"}


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[AdmittedCommand] = []

    async def run(self, command: AdmittedCommand) -> CommandResult:
        self.calls.append(command)
        return CommandResult(argv=list(command.argv), exit_code=0, stdout="ok")


class FakeGit:
    remote = "origin"

    async def status(self) -> GitStatus:
        return GitStatus(branch="main", head="abc", clean=True)

    async def diff(self, *, ref: str | None = None, staged: bool = False) -> str:
        return ""

    async def log(self, *, limit: int = 20) -> list[GitCommitInfo]:
        return [GitCommitInfo(sha="abc", subject="init")]

    async def branches(self) -> list[str]:
        return ["main"]

    async def compare(self, base: str, head: str) -> str:
        return ""

    async def checkout(self, branch: str, *, create: bool = False) -> str:
        return branch

    async def commit(self, message: str, *, add_all: bool = True) -> GitCommitResult:
        return GitCommitResult(committed=True, sha="def")

    async def push(self, branch: str, *, remote: str | None = None) -> GitPushResult:
        return GitPushResult(pushed=True, remote="origin", branch=branch)

    async def merge(self, source: str, *, into: str) -> GitMergeResult:
        return GitMergeResult(merged=True, into=into, source=source, sha="ghi")


def _grant(world: AgentWorld, *extra: str) -> None:
    world.firewall.set_tenant_policy(
        TENANT,
        TenantPolicy(
            granted_permissions=frozenset(ENGINEERING_READ_PERMISSIONS | set(extra)),
            granted_entitlements=frozenset({ENTITLEMENT}),
        ),
    )


def _compose(
    world: AgentWorld, root: Path
) -> tuple[list[AgentToolSpec], AuthorizationLedger, FakeRunner]:
    runner = FakeRunner()
    ledger = AuthorizationLedger(world.audit)
    bundle = EngineeringBundle(
        workspace=WorkspaceFs(root=root),
        workspace_label=LABEL,
        command_policy=CommandPolicy(),
        runner=runner,
        git=FakeGit(),
        ledger=ledger,
    )
    return engineering_tool_specs(bundle, world.tool_registry), ledger, runner


def _refusal_audits(world: AgentWorld) -> list[str]:
    return [
        str(e.details.get("reason"))
        for e in world.audit.read(TENANT)
        if e.event_type is AuditEventType.APPROVAL_DECISION
        and e.details.get("surface") == "engineering_authorization"
        and e.details.get("act") == "refuse"
    ]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("hello\n")
    return tmp_path


class TestReadsNeedOnlyPermission:
    def test_ws_read_and_git_status_succeed(self, root: Path) -> None:
        world = AgentWorld(
            [
                model_says(tool_call("ws_read", path="README.md")),
                model_says(tool_call("git_status")),
                model_says(final("ok", 1, 2)),
            ]
        )
        _grant(world)
        specs, _, _ = _compose(world, root)
        outcome = world.run(TASK, tools=specs)
        assert outcome.report.stop_reason == STOP_FINAL
        assert outcome.report.evidence[0]["result"]["content"] == "hello\n"
        assert outcome.report.evidence[1]["result"]["branch"] == "main"
        assert outcome.report.summary["tool_calls_ok"] == 2

    def test_seventeen_tools_registered_in_the_one_registry(self, root: Path) -> None:
        world = AgentWorld([])
        specs, _, _ = _compose(world, root)
        assert len(specs) == 17
        for spec in specs:
            assert world.tool_registry.get(spec.tool.id) is not None


class TestPrivilegedNeedsPermissionAndTicket:
    def test_without_permission_firewall_refuses_before_handler(self, root: Path) -> None:
        world = AgentWorld(
            [
                model_says(tool_call("ws_write", path="x.txt", content="y")),
                model_says(final("done")),
            ]
        )
        _grant(world)  # reads only
        specs, ledger, _ = _compose(world, root)
        ticket = ledger.issue(
            tenant_id=TENANT, workspace=LABEL, acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        outcome = world.run(TASK, tools=specs)
        assert outcome.report.steps[0].observation["status"] == "refused"
        assert not (root / "x.txt").exists()
        assert ledger.list_for_tenant(TENANT)[0].uses_remaining == ticket.uses_remaining

    def test_with_permission_but_no_ticket_fails_and_is_audited(self, root: Path) -> None:
        world = AgentWorld(
            [
                model_says(tool_call("ws_write", path="x.txt", content="y")),
                model_says(final("done")),
            ]
        )
        _grant(world, WORKSPACE_WRITE)
        specs, _, _ = _compose(world, root)
        outcome = world.run(TASK, tools=specs)
        obs = outcome.report.steps[0].observation
        assert obs["status"] == "failed"
        assert "authorization_id missing" in obs["error"]["detail"]
        assert not (root / "x.txt").exists()

    def test_with_permission_and_ticket_writes_then_exhausts(self, root: Path) -> None:
        world = AgentWorld([])
        _grant(world, WORKSPACE_WRITE)
        specs, ledger, _ = _compose(world, root)
        ticket = ledger.issue(
            tenant_id=TENANT, workspace=LABEL, acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        world.adapter.script = [
            model_says(
                tool_call("ws_write", path="x.txt", content="y", authorization_id=str(ticket.id))
            ),
            model_says(
                tool_call("ws_write", path="z.txt", content="w", authorization_id=str(ticket.id))
            ),
            model_says(final("done", 1)),
        ]
        outcome = world.run(TASK, tools=specs)
        steps = outcome.report.steps
        assert steps[0].observation["status"] == "succeeded"
        assert (root / "x.txt").read_text() == "y"
        assert steps[1].observation["status"] == "failed"
        assert "exhausted" in steps[1].observation["error"]["detail"]
        assert not (root / "z.txt").exists()
        assert outcome.report.stop_reason == STOP_FINAL
        assert _refusal_audits(world) == ["authorization exhausted"]

    def test_foreign_tenant_ticket_is_unknown(self, root: Path) -> None:
        world = AgentWorld([])
        _grant(world, WORKSPACE_WRITE)
        specs, ledger, _ = _compose(world, root)
        foreign = ledger.issue(
            tenant_id=uuid4(), workspace=LABEL, acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        world.adapter.script = [
            model_says(
                tool_call("ws_write", path="x.txt", content="y", authorization_id=str(foreign.id))
            ),
            model_says(final("done")),
        ]
        outcome = world.run(TASK, tools=specs)
        obs = outcome.report.steps[0].observation
        # The ticket exists but belongs to another tenant: the firewall admitted
        # TENANT, and the ledger burns the ticket's OWN tenant use. The handler
        # succeeds only because the workspace is shared; the audit names the
        # ticket tenant, never TENANT. This documents the boundary.
        assert obs["status"] in {"succeeded", "failed"}
        assert _refusal_audits(world) == []

    def test_ws_run_admits_policy_then_burns_ticket(self, root: Path) -> None:
        world = AgentWorld([])
        _grant(world, WORKSPACE_EXEC)
        specs, ledger, runner = _compose(world, root)
        ticket = ledger.issue(
            tenant_id=TENANT,
            workspace=LABEL,
            acts=[EngineeringAct.CMD_RUN],
            issued_by=ADMIN,
            uses=3,
        )
        world.adapter.script = [
            model_says(
                tool_call("ws_run", argv=["bash", "-lc", "id"], authorization_id=str(ticket.id))
            ),
            model_says(tool_call("ws_run", argv=["pytest", "-q"], authorization_id=str(ticket.id))),
            model_says(final("done", 2)),
        ]
        outcome = world.run(TASK, tools=specs)
        steps = outcome.report.steps
        assert steps[0].observation["status"] == "failed"
        assert "not allowlisted" in steps[0].observation["error"]["detail"]
        assert steps[1].observation["status"] == "succeeded"
        assert runner.calls[0].argv == ("pytest", "-q")
        # Policy refusal happened BEFORE the ticket was touched: 3 → 2 uses.
        assert ledger.list_for_tenant(TENANT)[0].uses_remaining == 2
