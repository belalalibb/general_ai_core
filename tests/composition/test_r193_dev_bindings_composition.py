"""R193 — production composition of the governed REST-Git engineering path (P-R192-04).

RED first: ``apps.composition.dev_bindings`` does not exist yet.

What is proven (R193-DEC-01 i–vii):
(i)   env unset ⇒ composition inert: ``build_dev_bindings`` returns None; the default
      runtime profile keeps ``/v1/dev`` absent and offers no REST-git tools
      (extends the IMPL-024 pin instead of inverting it).
(ii)  env set ⇒ the EXISTING read-only ``/v1/dev/bindings/{id}/publish-modes`` resolves
      200 for the caller's own binding and the SAME typed 404 for foreign/unknown ids.
(iii) JSON stores round-trip across two compositions over the same state dir — the
      only durability claimed.
(iv)  untrusted remote ⇒ ``remote_not_trusted`` BEFORE any ``secrets.resolve`` and
      BEFORE any HTTP (``httpx.MockTransport`` — ZERO live calls).
(v)   ``git.commit`` / ``git.publish`` stay ``BEFORE_ACTION`` in the composed tools;
      ``git.fetch`` / ``git.status`` / the inspector stay ``NONE``.
(vi)  state dir inside the platform checkout ⇒ boot-time refusal (ADR-0009 §14).
(vii) tool handlers refuse outside a bound run; inside ``bind_run_tenant`` they act
      for THAT tenant only — foreign binding ⇒ ``binding_tenant_mismatch``; the token
      never appears in outputs.

No admin-only path. No new isolation model: tenant scope is the admitted caller at
every lookup (``RepoBindingRegistry.get(tenant_id=)``, ``RemoteTrustPort``,
``SecretManagerPort``) — exactly as ``GitToolset`` / ``repo_map`` already do.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from apps.agent_dev.git_tools import (
    PERM_GIT_COMMIT,
    PERM_GIT_FETCH,
    PERM_GIT_PUBLISH,
    PERM_GIT_STATUS,
    RepoBindingRegistry,
)
from apps.agent_dev.http import DEV_ROUTER_PREFIX
from apps.api.run_context import bind_run_tenant
from apps.composition.dev_bindings import (
    ENV_DEV_STATE_DIR,
    PERM_PROJECT_INSPECT,
    DevBindingsComposition,
    DevStateDirRefused,
    build_dev_bindings,
)
from apps.composition.runtime import DEV_DEMO_PRINCIPAL_ENV, build_runtime_profile
from core.contracts.remote_trust import RemoteTrustGrant
from core.contracts.repo_binding import GitRefusalCode, RepoBinding
from core.contracts.tools import ApprovalRequirement
from core.secrets.memory import InMemorySecretManager
from core.tools.remote_trust import RemoteTrustRegistry

REMOTE = "https://github.com/acme/shop.git"
SECRET = "ghp_R193_never_leaks"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _github() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/repos/acme/shop/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "c0ffee", "type": "commit"}})
        if path == "/repos/acme/shop/git/trees/c0ffee":
            return httpx.Response(
                200,
                json={
                    "sha": "c0ffee",
                    "truncated": False,
                    "tree": [{"path": "pyproject.toml", "type": "blob"}],
                },
            )
        return httpx.Response(404, json={"message": "nope"})

    return httpx.MockTransport(handler), seen


class _Secrets(InMemorySecretManager):
    def __init__(self) -> None:
        super().__init__()
        self.resolves: list[tuple[UUID, str]] = []

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        self.resolves.append((tenant_id, credential_ref))
        return super().resolve(tenant_id, credential_ref)


def _binding(root: Path, tenant: UUID, ref: str) -> RepoBinding:
    (root / "wt").mkdir(parents=True, exist_ok=True)
    return RepoBinding(
        tenant_id=tenant,
        remote_url=REMOTE,
        branch="main",
        local_root=str(root / "wt"),
        credential_ref=ref,
        label="shop",
    )


def _grant(tenant: UUID) -> RemoteTrustGrant:
    return RemoteTrustGrant(
        tenant_id=tenant,
        remote_url=REMOTE,
        trusted=True,
        granted_by="operator",
        granted_at=datetime.now(UTC),
    )


def _compose(tmp_path: Path, **kw: Any) -> tuple[DevBindingsComposition, list[httpx.Request]]:
    transport, seen = _github()
    secrets = kw.pop("secrets", _Secrets())
    comp = build_dev_bindings(
        {ENV_DEV_STATE_DIR: str(tmp_path / "state")},
        secrets=secrets,
        transport=transport,
        **kw,
    )
    assert comp is not None
    return comp, seen


def _spec(comp: DevBindingsComposition, name: str) -> Any:
    return next(s for s in comp.tool_specs if s.name == name)


# ------------------------------------------------------------------ (i) inert when unset


class TestInertWhenUnset:
    def test_builder_returns_none_without_env(self) -> None:
        assert build_dev_bindings({}, secrets=InMemorySecretManager()) is None
        assert (
            build_dev_bindings({ENV_DEV_STATE_DIR: "   "}, secrets=InMemorySecretManager()) is None
        )

    def test_default_profile_keeps_dev_seam_inert(self) -> None:
        profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})
        assert profile.dev_bindings is None
        assert not any(p.startswith(DEV_ROUTER_PREFIX) for p in profile.app.openapi()["paths"])
        assert profile.agent is not None
        names = set(profile.agent.surface.catalog)
        assert PERM_GIT_FETCH not in names and PERM_PROJECT_INSPECT not in names


# ------------------------------------------------------------------ (vi) §14 refusal


class TestStateDirGuard:
    def test_state_dir_inside_platform_checkout_is_refused_at_boot(self) -> None:
        platform = Path(__file__).resolve().parents[2]
        with pytest.raises(DevStateDirRefused, match="14"):
            build_dev_bindings(
                {ENV_DEV_STATE_DIR: str(platform / "var" / "dev")},
                secrets=InMemorySecretManager(),
            )


# ------------------------------------------------------------------ (ii)(iii) served + durable


class TestServedRouteAndDurability:
    def test_profile_with_env_mounts_existing_read_router_tenant_scoped(
        self, tmp_path: Path
    ) -> None:
        env = {DEV_DEMO_PRINCIPAL_ENV: "1", ENV_DEV_STATE_DIR: str(tmp_path / "state")}
        profile = build_runtime_profile(environ=env)
        assert profile.dev_bindings is not None and profile.demo_principal is not None
        own = profile.dev_bindings.register(
            _binding(tmp_path, profile.demo_principal.tenant_id, "cred/own")
        )
        foreign = profile.dev_bindings.register(_binding(tmp_path, uuid4(), "cred/foreign"))

        async def get(path: str) -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=profile.app), base_url="http://t"
            ) as client:
                return await client.get(path)

        ok = _run(get(f"{DEV_ROUTER_PREFIX}/bindings/{own.id}/publish-modes"))
        assert ok.status_code == 200, ok.text
        assert ok.json()["default"] == "pull_request"
        for bad in (str(foreign.id), str(uuid4()), "not-a-uuid"):
            r = _run(get(f"{DEV_ROUTER_PREFIX}/bindings/{bad}/publish-modes"))
            assert r.status_code == 404 and r.json()["error"]["code"] == "validation_error"
        # the catalog now offers the REST-git tools + inspector (same catalog, one rule)
        assert profile.agent is not None
        names = set(profile.agent.surface.catalog)
        assert {
            PERM_GIT_FETCH,
            PERM_GIT_STATUS,
            PERM_GIT_COMMIT,
            PERM_GIT_PUBLISH,
            PERM_PROJECT_INSPECT,
        } <= names

    def test_bindings_and_trust_survive_a_second_composition(self, tmp_path: Path) -> None:
        tenant = uuid4()
        first, _ = _compose(tmp_path)
        binding = first.bindings.register(_binding(tmp_path, tenant, "cred/x"))
        first.trust.grant(_grant(tenant))
        second, _ = _compose(tmp_path)
        assert second.bindings.get(binding.id, tenant_id=tenant).remote_url == REMOTE
        assert second.trust.is_trusted(tenant, REMOTE) is True
        assert (tmp_path / "state" / "bindings.json").exists()
        assert (tmp_path / "state" / "remote_trust.json").exists()
        assert not any((tmp_path / "wt").glob("*.json"))  # never inside a working tree


# ------------------------------------------------------------------ (iv)(v)(vii) governed tools


class TestGovernedToolsAreTenantBound:
    def test_approval_requirements_are_preserved(self, tmp_path: Path) -> None:
        comp, _ = _compose(tmp_path)
        for name in (PERM_GIT_COMMIT, PERM_GIT_PUBLISH):
            assert _spec(comp, name).tool.approval_policy[name] is (
                ApprovalRequirement.BEFORE_ACTION
            )
        for read in (PERM_GIT_FETCH, PERM_GIT_STATUS, PERM_PROJECT_INSPECT):
            spec = _spec(comp, read)
            assert spec.tool.approval_policy[read] is ApprovalRequirement.NONE
            assert spec.permission == read

    def test_handler_refuses_outside_a_bound_run(self, tmp_path: Path) -> None:
        comp, seen = _compose(tmp_path)
        with pytest.raises(ValueError, match="no admitted tenant"):
            _run(_spec(comp, PERM_PROJECT_INSPECT).handler({"binding_id": str(uuid4())}))
        with pytest.raises(ValueError, match="no admitted tenant"):
            _run(_spec(comp, PERM_GIT_FETCH).handler({"binding_id": str(uuid4())}))
        assert seen == []

    def test_inspect_inside_bound_run_uses_callers_tenant_and_hides_token(
        self, tmp_path: Path
    ) -> None:
        secrets = _Secrets()
        tenant = uuid4()
        ref = secrets.store(tenant, SECRET)
        comp, seen = _compose(tmp_path, secrets=secrets)
        binding = comp.bindings.register(_binding(tmp_path, tenant, ref))
        comp.trust.grant(_grant(tenant))
        with bind_run_tenant(tenant):
            out = _run(_spec(comp, PERM_PROJECT_INSPECT).handler({"binding_id": str(binding.id)}))
        assert out["head_sha"] == "c0ffee" and out["remote_url"] == REMOTE
        assert SECRET not in json.dumps(out)
        assert secrets.resolves == [(tenant, ref)]
        assert [r.method for r in seen] == ["GET", "GET"]
        assert all(r.headers["Authorization"] == f"Bearer {SECRET}" for r in seen)

    def test_foreign_tenant_binding_is_refused_inside_a_bound_run(self, tmp_path: Path) -> None:
        secrets = _Secrets()
        owner, intruder = uuid4(), uuid4()
        comp, seen = _compose(tmp_path, secrets=secrets)
        binding = comp.bindings.register(_binding(tmp_path, owner, secrets.store(owner, SECRET)))
        comp.trust.grant(_grant(owner))
        with bind_run_tenant(intruder), pytest.raises(ValueError) as info:
            _run(_spec(comp, PERM_PROJECT_INSPECT).handler({"binding_id": str(binding.id)}))
        assert GitRefusalCode.BINDING_TENANT_MISMATCH.value in str(info.value)
        with bind_run_tenant(intruder):
            out = _run(_spec(comp, PERM_GIT_FETCH).handler({"binding_id": str(binding.id)}))
        assert out.get("code") == GitRefusalCode.BINDING_TENANT_MISMATCH.value
        assert secrets.resolves == [] and seen == []

    def test_untrusted_remote_refused_before_secret_and_before_network(
        self, tmp_path: Path
    ) -> None:
        secrets = _Secrets()
        tenant = uuid4()
        comp, seen = _compose(tmp_path, secrets=secrets)
        binding = comp.bindings.register(_binding(tmp_path, tenant, secrets.store(tenant, SECRET)))
        # no grant ⇒ untrusted (trust registry composed ⇒ deny by default)
        with bind_run_tenant(tenant):
            with pytest.raises(ValueError) as info:
                _run(_spec(comp, PERM_PROJECT_INSPECT).handler({"binding_id": str(binding.id)}))
            assert GitRefusalCode.REMOTE_NOT_TRUSTED.value in str(info.value)
            out = _run(_spec(comp, PERM_GIT_FETCH).handler({"binding_id": str(binding.id)}))
        assert out.get("code") == GitRefusalCode.REMOTE_NOT_TRUSTED.value
        assert secrets.resolves == [] and seen == []

    def test_git_fetch_inside_bound_run_reaches_remote_for_trusted_binding(
        self, tmp_path: Path
    ) -> None:
        secrets = _Secrets()
        tenant = uuid4()
        comp, seen = _compose(tmp_path, secrets=secrets)
        binding = comp.bindings.register(_binding(tmp_path, tenant, secrets.store(tenant, SECRET)))
        comp.trust.grant(_grant(tenant))
        with bind_run_tenant(tenant):
            out = _run(_spec(comp, PERM_GIT_FETCH).handler({"binding_id": str(binding.id)}))
        assert out.get("ok") is True and out.get("remote_head") == "c0ffee", out
        assert SECRET not in json.dumps(out)
        assert [r.method for r in seen] == ["GET"]
        assert isinstance(comp.trust, RemoteTrustRegistry)
        assert isinstance(comp.bindings, RepoBindingRegistry)
