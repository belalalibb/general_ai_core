"""Unit tests: jailed WorkspaceFs, CommandPolicy admission, ref validation, ledger."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.engineering import ChangeSet, CommandRequest, EngineeringAct, FileChange
from core.engineering import (
    AuthorizationLedger,
    AuthorizationRefused,
    CommandPolicy,
    CommandRefused,
    GitRefused,
    WorkspaceFs,
    WorkspaceRefused,
    validate_ref,
)

TENANT = uuid4()
ADMIN = uuid4()


@pytest.fixture
def ws(tmp_path: Path) -> WorkspaceFs:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def f():\n    return 1\n")
    (tmp_path / "README.md").write_text("hello\n")
    return WorkspaceFs(root=tmp_path)


class TestWorkspaceJail:
    def test_read_list_search_reuse_source_reader(self, ws: WorkspaceFs) -> None:
        assert ws.reader.read_file("README.md")["content"] == "hello\n"
        listed = ws.reader.list_files("", "**/*.py")
        assert "src/app.py" in str(listed["files"])
        found = ws.reader.search("return 1", "", "**/*.py")
        assert found["matches"]

    def test_parent_traversal_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(WorkspaceRefused):
            ws.admit("../outside.txt")

    def test_absolute_path_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(WorkspaceRefused):
            ws.admit("/etc/passwd")

    def test_symlinked_directory_cannot_escape(self, ws: WorkspaceFs, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"outside-{uuid4().hex}"
        outside.mkdir()
        try:
            os.symlink(outside, ws.root / "escape")
            with pytest.raises(WorkspaceRefused, match="escapes"):
                ws.admit("escape/new.txt")
        finally:
            (ws.root / "escape").unlink()
            outside.rmdir()

    def test_denied_patterns_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(WorkspaceRefused, match="denied"):
            ws.admit(".env")

    def test_write_move_delete_roundtrip(self, ws: WorkspaceFs) -> None:
        created = ws.write_file("src/new.py", "x = 1\n")
        assert created == {"path": "src/new.py", "bytes": 6, "created": True}
        again = ws.write_file("src/new.py", "x = 2\n")
        assert again["created"] is False
        moved = ws.move_file("src/new.py", "src/renamed.py")
        assert moved == {"from": "src/new.py", "to": "src/renamed.py"}
        assert (ws.root / "src" / "renamed.py").read_text() == "x = 2\n"
        assert ws.delete_file("src/renamed.py") == {"path": "src/renamed.py", "deleted": True}
        assert not (ws.root / "src" / "renamed.py").exists()

    def test_write_cap_is_enforced(self, tmp_path: Path) -> None:
        small = WorkspaceFs(root=tmp_path, max_write_bytes=8)
        with pytest.raises(WorkspaceRefused, match="write cap"):
            small.write_file("big.txt", "0123456789")

    def test_change_set_is_atomic_on_failure(self, ws: WorkspaceFs) -> None:
        before = (ws.root / "README.md").read_text()
        change_set = ChangeSet(
            changes=[
                FileChange(kind="write", path="README.md", content="changed\n"),
                FileChange(kind="write", path="docs/new.md", content="new\n"),
                FileChange(kind="delete", path="src/missing.py"),  # fails -> rollback
            ]
        )
        result = ws.apply_change_set(change_set)
        assert result.applied is False
        assert result.rolled_back is True
        assert result.error
        assert (ws.root / "README.md").read_text() == before
        assert not (ws.root / "docs" / "new.md").exists()

    def test_change_set_applies_all(self, ws: WorkspaceFs) -> None:
        result = ws.apply_change_set(
            ChangeSet(
                changes=[
                    FileChange(kind="write", path="a.txt", content="a"),
                    FileChange(kind="move", path="a.txt", to_path="b.txt"),
                    FileChange(kind="delete", path="README.md"),
                ],
                reason="test",
            )
        )
        assert result.applied is True and result.operations == 3
        assert (ws.root / "b.txt").read_text() == "a"
        assert not (ws.root / "README.md").exists()


class TestCommandPolicy:
    def test_allowlisted_command_admitted_with_capped_timeout(self, ws: WorkspaceFs) -> None:
        policy = CommandPolicy(max_timeout_ms=5_000)
        admitted = policy.admit(ws, CommandRequest(argv=["python3", "-V"], timeout_ms=60_000))
        assert admitted.argv == ("python3", "-V")
        assert admitted.cwd == ws.root
        assert admitted.timeout_ms == 5_000

    def test_non_allowlisted_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(CommandRefused, match="not allowlisted"):
            CommandPolicy().admit(ws, CommandRequest(argv=["bash", "-lc", "id"]))

    def test_denied_argument_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(CommandRefused, match="denied"):
            CommandPolicy().admit(ws, CommandRequest(argv=["python3", "-c", "print(1)"]))

    def test_relative_executable_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(CommandRefused, match="relative"):
            CommandPolicy().admit(ws, CommandRequest(argv=["./python3"]))

    def test_cwd_outside_workspace_refused(self, ws: WorkspaceFs) -> None:
        with pytest.raises(WorkspaceRefused):
            CommandPolicy().admit(ws, CommandRequest(argv=["python3"], cwd="../"))


class TestValidateRef:
    @pytest.mark.parametrize("ref", ["main", "feat/x-1", "bench-main/r164", "v1.2.3"])
    def test_accepts(self, ref: str) -> None:
        assert validate_ref(ref) == ref

    @pytest.mark.parametrize(
        "ref", ["", "-rf", "a..b", "x/", "x.lock", "a b", "a~1", "a^", "a:b", "a?b", "a*", "a\\b"]
    )
    def test_refuses(self, ref: str) -> None:
        with pytest.raises(GitRefused):
            validate_ref(ref)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class TestAuthorizationLedger:
    def _ledger(self) -> tuple[AuthorizationLedger, InMemoryAuditLog, Clock]:
        audit = InMemoryAuditLog()
        clock = Clock()
        return AuthorizationLedger(audit, clock=clock), audit, clock

    def test_issue_consume_exhaust_audited(self) -> None:
        ledger, audit, _ = self._ledger()
        ticket = ledger.issue(
            tenant_id=TENANT, workspace="ws", acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        burned = ledger.consume_ticket(
            authorization_id=ticket.id, workspace="ws", act=EngineeringAct.FS_WRITE
        )
        assert burned.uses_remaining == 0
        with pytest.raises(AuthorizationRefused, match="exhausted"):
            ledger.consume_ticket(
                authorization_id=ticket.id, workspace="ws", act=EngineeringAct.FS_WRITE
            )
        acts = [
            e.details.get("act")
            for e in audit.read(TENANT)
            if e.event_type is AuditEventType.APPROVAL_DECISION
            and e.details.get("surface") == "engineering_authorization"
        ]
        assert acts == ["issue", "consume", "refuse"]

    def test_uncovered_act_and_other_workspace_refused(self) -> None:
        ledger, _, _ = self._ledger()
        ticket = ledger.issue(
            tenant_id=TENANT, workspace="ws", acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        with pytest.raises(AuthorizationRefused, match="does not cover"):
            ledger.consume_ticket(
                authorization_id=ticket.id, workspace="ws", act=EngineeringAct.GIT_PUSH
            )
        with pytest.raises(AuthorizationRefused, match="another workspace"):
            ledger.consume_ticket(
                authorization_id=ticket.id, workspace="other", act=EngineeringAct.FS_WRITE
            )

    def test_expired_and_revoked_refused(self) -> None:
        ledger, _, clock = self._ledger()
        ticket = ledger.issue(
            tenant_id=TENANT,
            workspace="ws",
            acts=[EngineeringAct.CMD_RUN],
            issued_by=ADMIN,
            uses=5,
            ttl=timedelta(minutes=5),
        )
        clock.now += timedelta(minutes=6)
        with pytest.raises(AuthorizationRefused, match="expired"):
            ledger.consume_ticket(
                authorization_id=ticket.id, workspace="ws", act=EngineeringAct.CMD_RUN
            )
        clock.now -= timedelta(minutes=6)
        ledger.revoke(TENANT, ticket.id, actor_id=ADMIN)
        with pytest.raises(AuthorizationRefused, match="revoked"):
            ledger.consume_ticket(
                authorization_id=ticket.id, workspace="ws", act=EngineeringAct.CMD_RUN
            )

    def test_missing_or_unknown_ticket_refused_and_audited_under_nil_tenant(self) -> None:
        ledger, audit, _ = self._ledger()
        with pytest.raises(AuthorizationRefused, match="missing"):
            ledger.consume_ticket(
                authorization_id=None, workspace="ws", act=EngineeringAct.FS_WRITE
            )
        with pytest.raises(AuthorizationRefused, match="unknown"):
            ledger.consume_ticket(
                authorization_id=uuid4(), workspace="ws", act=EngineeringAct.FS_WRITE
            )
        from uuid import UUID

        assert len(audit.read(UUID(int=0))) == 2

    def test_foreign_tenant_cannot_revoke(self) -> None:
        ledger, _, _ = self._ledger()
        ticket = ledger.issue(
            tenant_id=TENANT, workspace="ws", acts=[EngineeringAct.FS_WRITE], issued_by=ADMIN
        )
        with pytest.raises(AuthorizationRefused):
            ledger.revoke(uuid4(), ticket.id, actor_id=ADMIN)
        assert ledger.list_for_tenant(TENANT)[0].revoked is False

    def test_ttl_is_capped_at_max(self) -> None:
        ledger, _, clock = self._ledger()
        ticket = ledger.issue(
            tenant_id=TENANT,
            workspace="ws",
            acts=[EngineeringAct.FS_WRITE],
            issued_by=ADMIN,
            ttl=timedelta(days=30),
        )
        assert ticket.expires_at - clock.now == timedelta(hours=24)
