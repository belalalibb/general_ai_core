"""R172 C3 — explicit remote trust, enforced before any credential is resolved.

A remote is untrusted until a named granter records ``trusted=True`` for
(tenant, remote_url). Revocation flips it back. Enforcement lives ONLY in
``GitToolset`` for ``git.fetch`` and ``git.publish`` (the two acts that reach
the network); ``git.status`` and ``git.commit`` are untouched. Refusal is
``GitRefusal`` data with the new ``remote_not_trusted`` code, and it happens
before ``secrets.resolve`` — the token is never touched for an untrusted remote.
"""

from __future__ import annotations

import asyncio
import json
import stat
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from apps.agent_dev.git_tools import (
    PERM_GIT_COMMIT,
    PERM_GIT_FETCH,
    PERM_GIT_PUBLISH,
    PERM_GIT_STATUS,
    GitToolset,
    RepoBindingRegistry,
)
from apps.agent_dev.surface import build_dev_surface, dev_tenant_policy
from core.audit.memory import InMemoryAuditLog
from core.contracts.publish_mode import PublishMode
from core.contracts.remote_trust import RemoteTrustGrant, TrustStoreDocument
from core.contracts.repo_binding import GitRefusalCode, GitStatusResult, RepoBinding
from core.secrets.memory import InMemorySecretManager
from core.security.firewall import CapabilityFirewall
from core.tools.remote_trust import JsonRemoteTrustStore, RemoteTrustRegistry
from core.usage.memory import InMemoryUsageAccounting

TENANT = UUID("00000000-0000-0000-0000-00000000c301")
OTHER = UUID("00000000-0000-0000-0000-00000000c302")
REMOTE = "https://github.com/example/repo.git"
OTHER_REMOTE = "https://github.com/example/other.git"
TOKEN = "ghp_" + "T" * 36
GRANTER = "owner@example.com"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class CountingSecrets(InMemorySecretManager):
    """Records every resolve so tests can prove it was never reached."""

    def __init__(self) -> None:
        super().__init__()
        self.resolve_calls = 0

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        self.resolve_calls += 1
        return super().resolve(tenant_id, credential_ref)


@dataclass
class Transport:
    calls: list[str] = field(default_factory=list)

    async def fetch(self, binding: RepoBinding, *, token: str) -> str | None:
        self.calls.append("fetch")
        return "abc123"

    async def status(self, binding: RepoBinding) -> GitStatusResult:
        self.calls.append("status")
        return GitStatusResult(
            binding_id=str(binding.id), branch=binding.branch, head="abc123", clean=False
        )

    async def diff_summary(self, binding: RepoBinding) -> str:
        self.calls.append("diff")
        return "1 file changed"

    async def commit(self, binding: RepoBinding, *, message: str, paths: Sequence[str]) -> str:
        self.calls.append("commit")
        return "deadbeef"

    async def push(self, binding: RepoBinding, *, branch: str, token: str) -> None:
        self.calls.append("push")

    async def open_pull_request(
        self, binding: RepoBinding, *, work_branch: str, title: str, token: str
    ) -> str:
        self.calls.append("pr")
        return "https://github.com/example/repo/pull/1"


@dataclass
class World:
    surface: Any
    toolset: GitToolset
    transport: Transport
    secrets: CountingSecrets
    trust: RemoteTrustRegistry
    binding: RepoBinding


def make_world(tmp_path: Path, *, trust: RemoteTrustRegistry | None) -> World:
    transport = Transport()
    secrets = CountingSecrets()
    ref = secrets.store(TENANT, TOKEN)
    bindings = RepoBindingRegistry()
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    binding = bindings.register(
        RepoBinding(
            tenant_id=TENANT,
            remote_url=REMOTE,
            branch="main",
            local_root=str(root),
            credential_ref=ref,
            allowed_modes=frozenset(
                {PublishMode.DRY_RUN, PublishMode.PULL_REQUEST, PublishMode.DIRECT_PUSH}
            ),
        )
    )
    kwargs: dict[str, object] = {}
    if trust is not None:
        kwargs["trust"] = trust
    toolset = GitToolset(
        tenant_id=TENANT,
        bindings=bindings,
        transport=transport,
        secrets=secrets,
        **kwargs,  # type: ignore[arg-type]
    )
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(TENANT, dev_tenant_policy(write=True, git=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(TENANT, plan="dev", task_units_limit=100)
    surface = build_dev_surface(
        root=root,
        tenant_id=TENANT,
        firewall=firewall,
        audit=InMemoryAuditLog(),
        usage=usage,
        git=toolset,
    )
    return World(surface, toolset, transport, secrets, trust or RemoteTrustRegistry(), binding)


def call(world: World, perm: str, **args: object) -> dict[str, Any]:
    payload: dict[str, object] = {"binding_id": str(world.binding.id), **args}
    return run(world.surface.call(perm, payload, approval_state="approved"))


def _grant(*, trusted: bool = True, tenant: UUID = TENANT, remote: str = REMOTE) -> RemoteTrustGrant:
    return RemoteTrustGrant(
        tenant_id=tenant,
        remote_url=remote,
        trusted=trusted,
        granted_by=GRANTER,
        granted_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


# --- contract ---------------------------------------------------------------


def test_refusal_code_exists_and_is_snake_case() -> None:
    assert GitRefusalCode.REMOTE_NOT_TRUSTED.value == "remote_not_trusted"


def test_trusted_string_true_is_rejected_by_contract() -> None:
    # "true" (string) must not coerce to True: strict bool.
    with pytest.raises(ValidationError):
        RemoteTrustGrant(
            tenant_id=TENANT,
            remote_url=REMOTE,
            trusted="true",  # type: ignore[arg-type]
            granted_by=GRANTER,
            granted_at=datetime.now(UTC),
        )


def test_grant_requires_https_remote_and_named_granter() -> None:
    with pytest.raises(ValidationError):
        RemoteTrustGrant(
            tenant_id=TENANT,
            remote_url="git@github.com:example/repo.git",
            trusted=True,
            granted_by=GRANTER,
            granted_at=datetime.now(UTC),
        )
    with pytest.raises(ValidationError):
        RemoteTrustGrant(
            tenant_id=TENANT,
            remote_url=REMOTE,
            trusted=True,
            granted_by="",
            granted_at=datetime.now(UTC),
        )


# --- registry semantics -----------------------------------------------------


def test_default_is_untrusted() -> None:
    reg = RemoteTrustRegistry()
    assert reg.is_trusted(TENANT, REMOTE) is False


def test_grant_then_trusted_per_tenant_and_per_remote() -> None:
    reg = RemoteTrustRegistry()
    reg.grant(_grant())
    assert reg.is_trusted(TENANT, REMOTE) is True
    assert reg.is_trusted(OTHER, REMOTE) is False, "trust is per tenant"
    assert reg.is_trusted(TENANT, OTHER_REMOTE) is False, "trust is per remote"


def test_revoke_makes_untrusted_and_records_revocation() -> None:
    reg = RemoteTrustRegistry()
    reg.grant(_grant())
    reg.revoke(TENANT, REMOTE, revoked_by="security@example.com")
    assert reg.is_trusted(TENANT, REMOTE) is False
    rec = reg.get(TENANT, REMOTE)
    assert rec is not None
    assert rec.revoked_by == "security@example.com"
    assert rec.revoked_at is not None


def test_grant_with_trusted_false_is_untrusted() -> None:
    reg = RemoteTrustRegistry()
    reg.grant(_grant(trusted=False))
    assert reg.is_trusted(TENANT, REMOTE) is False


def test_remote_url_normalisation_is_conservative() -> None:
    # Exact-string match only, apart from trailing whitespace: a scheme/host/case
    # variant is a DIFFERENT remote and stays untrusted.
    reg = RemoteTrustRegistry()
    reg.grant(_grant())
    assert reg.is_trusted(TENANT, REMOTE + "  ") is True
    assert reg.is_trusted(TENANT, "https://GitHub.com/example/repo.git") is False
    assert reg.is_trusted(TENANT, "https://github.com/example/repo") is False


# --- persistence (C2 durability reused) ---------------------------------------


def test_store_round_trip_modes_and_fail_closed(tmp_path: Path) -> None:
    store = JsonRemoteTrustStore(tmp_path / "state" / "trust.json")
    reg = RemoteTrustRegistry(store=store)
    reg.grant(_grant())
    d = tmp_path / "state"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE((d / "trust.json").stat().st_mode) == 0o600

    reg2 = RemoteTrustRegistry(store=JsonRemoteTrustStore(d / "trust.json"))
    assert reg2.is_trusted(TENANT, REMOTE) is True
    assert reg2.load_report is not None and reg2.load_report.source_state == "ok"

    # a corrupt record is skipped and reported; it never becomes trust
    doc = TrustStoreDocument(version=1, grants=(_grant(),)).model_dump(mode="json")
    doc["grants"].append({"tenant_id": str(OTHER), "remote_url": REMOTE, "trusted": "true"})
    (d / "trust.json").write_text(json.dumps(doc), encoding="utf-8")
    reg3 = RemoteTrustRegistry(store=JsonRemoteTrustStore(d / "trust.json"))
    assert reg3.load_report is not None and reg3.load_report.source_state == "partial"
    assert reg3.is_trusted(OTHER, REMOTE) is False
    assert reg3.is_trusted(TENANT, REMOTE) is True

    # malformed document -> nothing trusted
    (d / "trust.json").write_text("{nope", encoding="utf-8")
    reg4 = RemoteTrustRegistry(store=JsonRemoteTrustStore(d / "trust.json"))
    assert reg4.load_report is not None and reg4.load_report.source_state == "malformed"
    assert reg4.is_trusted(TENANT, REMOTE) is False


def test_store_refuses_path_inside_protected_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(Exception, match="inside a protected working tree"):
        JsonRemoteTrustStore(repo / ".dev" / "trust.json", outside_of=(repo,))


# --- enforcement in GitToolset -----------------------------------------------


def test_fetch_untrusted_refused_before_resolve(tmp_path: Path) -> None:
    world = make_world(tmp_path, trust=RemoteTrustRegistry())
    out = call(world, PERM_GIT_FETCH)
    assert out["ok"] is False
    assert out["code"] == "remote_not_trusted"
    assert out["binding_id"] == str(world.binding.id)
    assert world.secrets.resolve_calls == 0, "token must not be resolved for an untrusted remote"
    assert world.transport.calls == []
    assert TOKEN not in json.dumps(out)


def test_publish_untrusted_refused_before_resolve_all_network_modes(tmp_path: Path) -> None:
    for mode in ("pull_request", "direct_push"):
        world = make_world(tmp_path, trust=RemoteTrustRegistry())
        out = call(world, PERM_GIT_PUBLISH, mode=mode)
        assert out["ok"] is False, mode
        assert out["code"] == "remote_not_trusted", mode
        assert world.secrets.resolve_calls == 0, mode
        assert "push" not in world.transport.calls and "pr" not in world.transport.calls


def test_publish_dry_run_untrusted_is_also_refused(tmp_path: Path) -> None:
    # git.publish is refused as a whole for an untrusted remote — no partial acts.
    world = make_world(tmp_path, trust=RemoteTrustRegistry())
    out = call(world, PERM_GIT_PUBLISH, mode="dry_run")
    assert out["ok"] is False and out["code"] == "remote_not_trusted"
    assert world.transport.calls == []


def test_status_and_commit_untouched_by_trust(tmp_path: Path) -> None:
    world = make_world(tmp_path, trust=RemoteTrustRegistry())
    st = call(world, PERM_GIT_STATUS)
    assert st.get("ok", True) is not False and st["branch"] == "main"
    cm = call(world, PERM_GIT_COMMIT, message="msg", paths=["a.py"])
    assert cm.get("ok", True) is not False and cm["sha"] == "deadbeef"


def test_trusted_remote_proceeds_and_resolves_once(tmp_path: Path) -> None:
    trust = RemoteTrustRegistry()
    trust.grant(_grant())
    world = make_world(tmp_path, trust=trust)
    out = call(world, PERM_GIT_FETCH)
    assert out.get("ok", True) is not False and out["remote_head"] == "abc123"
    assert world.secrets.resolve_calls == 1
    pub = call(world, PERM_GIT_PUBLISH, mode="pull_request", work_branch="dev/x")
    assert pub.get("ok", True) is not False and pub["pushed"] is True


def test_revocation_takes_effect_immediately(tmp_path: Path) -> None:
    trust = RemoteTrustRegistry()
    trust.grant(_grant())
    world = make_world(tmp_path, trust=trust)
    assert call(world, PERM_GIT_FETCH).get("ok", True) is not False
    trust.revoke(TENANT, REMOTE, revoked_by=GRANTER)
    out = call(world, PERM_GIT_FETCH)
    assert out["ok"] is False and out["code"] == "remote_not_trusted"
    assert world.secrets.resolve_calls == 1


def test_foreign_tenant_grant_does_not_trust_this_tenant(tmp_path: Path) -> None:
    trust = RemoteTrustRegistry()
    trust.grant(_grant(tenant=OTHER))
    world = make_world(tmp_path, trust=trust)
    out = call(world, PERM_GIT_FETCH)
    assert out["ok"] is False and out["code"] == "remote_not_trusted"
    assert world.secrets.resolve_calls == 0


def test_trust_refusal_is_recorded_in_trace(tmp_path: Path) -> None:
    world = make_world(tmp_path, trust=RemoteTrustRegistry())
    call(world, PERM_GIT_FETCH)
    assert world.toolset.trace[-1].code is GitRefusalCode.REMOTE_NOT_TRUSTED
    assert world.toolset.trace[-1].ok is False


def test_without_trust_registry_behaviour_is_r169(tmp_path: Path) -> None:
    """Absent ``trust`` the toolset is exactly the R169 one (38 existing tests)."""
    world = make_world(tmp_path, trust=None)
    out = call(world, PERM_GIT_FETCH)
    assert out.get("ok", True) is not False and out["remote_head"] == "abc123"
    assert world.secrets.resolve_calls == 1
