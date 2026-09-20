"""R192 G1 (H5/H10) — governed project inspection: tenant → RepoBinding → remote trust
→ credential_ref → SecretManager (last moment) → read-only GitHub inspection.

RED first: ``BoundProjectInspector`` does not exist yet. Written against the SAME
authorities ``GitToolset`` already uses (``RepoBindingRegistry.get(tenant_id=)``,
``RemoteTrustPort.is_trusted``, ``SecretManagerPort.resolve``) so no second trust /
credential / binding system is introduced. ZERO live network: ``httpx.MockTransport``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from apps.agent_dev.git_tools import BindingLookupRefused, RepoBindingRegistry
from apps.agent_dev.project_inspector import BoundProjectInspector, GitHubProjectInspector
from core.agent.app_factory import (
    APP_FACTORY_CAPABILITY_NAME,
    AppFactoryCapability,
    ProjectInventory,
)
from core.agent.general import GeneralAgentRequest, PlanRefused
from core.contracts.repo_binding import GitRefusalCode, RepoBinding
from core.secrets.memory import InMemorySecretManager

REMOTE = "https://github.com/acme/shop.git"


class _Trust:
    def __init__(self, trusted: bool, *, raise_on_call: bool = False) -> None:
        self.trusted = trusted
        self.raise_on_call = raise_on_call
        self.calls: list[tuple[UUID, str]] = []

    def is_trusted(self, tenant_id: UUID, remote_url: str) -> bool:
        self.calls.append((tenant_id, remote_url))
        if self.raise_on_call:
            raise RuntimeError("trust registry fault")
        return self.trusted


class _Secrets(InMemorySecretManager):
    """Records resolve() calls so ordering (trust BEFORE secret) is provable."""

    def __init__(self) -> None:
        super().__init__()
        self.resolves: list[tuple[UUID, str]] = []

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        self.resolves.append((tenant_id, credential_ref))
        return super().resolve(tenant_id, credential_ref)


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
                    "tree": [
                        {"path": "pyproject.toml", "type": "blob"},
                        {"path": "src/app.py", "type": "blob"},
                    ],
                },
            )
        return httpx.Response(404, json={"message": "nope"})

    return httpx.MockTransport(handler), seen


def _world(
    tmp_path: Path, *, trusted: bool = True, with_secret: bool = True, trust: Any = None
) -> dict[str, Any]:
    tenant = uuid4()
    secrets = _Secrets()
    ref = secrets.store(tenant, "ghp_SECRET_never_leaks") if with_secret else "cred/missing"
    binding = RepoBinding(
        tenant_id=tenant,
        remote_url=REMOTE,
        branch="main",
        local_root=str(tmp_path),
        credential_ref=ref,
        label="shop",
    )
    registry = RepoBindingRegistry()
    registry.register(binding)
    transport, seen = _github()
    inspector = GitHubProjectInspector(transport=transport)
    trust_port = trust if trust is not None else _Trust(trusted)
    bound = BoundProjectInspector(
        inspector, tenant_id=tenant, bindings=registry, trust=trust_port, secrets=secrets
    )
    return {
        "tenant": tenant,
        "binding": binding,
        "registry": registry,
        "secrets": secrets,
        "trust": trust_port,
        "seen": seen,
        "bound": bound,
    }


class TestGovernedPath:
    def test_happy_path_uses_binding_identity_and_never_leaks_the_token(
        self, tmp_path: Path
    ) -> None:
        w = _world(tmp_path)
        inventory = w["bound"].inspect_binding(w["binding"].id)
        assert isinstance(inventory, ProjectInventory)
        assert inventory.remote_url == REMOTE and inventory.branch == "main"
        assert inventory.head_sha == "c0ffee" and inventory.file_count == 2
        # ordering: trust consulted, then ONE secret resolve, then HTTP with that token
        assert w["trust"].calls == [(w["tenant"], REMOTE)]
        assert w["secrets"].resolves == [(w["tenant"], w["binding"].credential_ref)]
        assert [r.method for r in w["seen"]] == ["GET", "GET"]
        assert all(
            r.headers["Authorization"] == "Bearer ghp_SECRET_never_leaks" for r in w["seen"]
        )
        assert "ghp_SECRET" not in inventory.model_dump_json()
        assert "ghp_SECRET" not in repr(w["bound"])

    def test_untrusted_remote_is_refused_before_secret_resolve_and_before_network(
        self, tmp_path: Path
    ) -> None:
        w = _world(tmp_path, trusted=False)
        with pytest.raises(BindingLookupRefused) as info:
            w["bound"].inspect_binding(w["binding"].id)
        assert info.value.code is GitRefusalCode.REMOTE_NOT_TRUSTED
        assert w["secrets"].resolves == []  # trust BEFORE credential — same as GitToolset
        assert w["seen"] == []

    def test_trust_registry_fault_fails_closed(self, tmp_path: Path) -> None:
        w = _world(tmp_path, trust=_Trust(True, raise_on_call=True))
        with pytest.raises(BindingLookupRefused) as info:
            w["bound"].inspect_binding(w["binding"].id)
        assert info.value.code is GitRefusalCode.REMOTE_NOT_TRUSTED
        assert w["secrets"].resolves == [] and w["seen"] == []

    def test_foreign_tenant_binding_is_refused_as_tenant_mismatch(self, tmp_path: Path) -> None:
        w = _world(tmp_path)
        other = BoundProjectInspector(
            GitHubProjectInspector(transport=_github()[0]),
            tenant_id=uuid4(),
            bindings=w["registry"],
            trust=w["trust"],
            secrets=w["secrets"],
        )
        with pytest.raises(BindingLookupRefused) as info:
            other.inspect_binding(w["binding"].id)
        assert info.value.code is GitRefusalCode.BINDING_TENANT_MISMATCH
        assert w["trust"].calls == [] and w["secrets"].resolves == []

    def test_unknown_binding_is_refused(self, tmp_path: Path) -> None:
        w = _world(tmp_path)
        with pytest.raises(BindingLookupRefused) as info:
            w["bound"].inspect_binding(uuid4())
        assert info.value.code is GitRefusalCode.BINDING_UNKNOWN
        assert w["seen"] == []

    def test_unresolvable_credential_is_typed_and_never_reaches_network(
        self, tmp_path: Path
    ) -> None:
        w = _world(tmp_path, with_secret=False)
        with pytest.raises(BindingLookupRefused) as info:
            w["bound"].inspect_binding(w["binding"].id)
        assert info.value.code is GitRefusalCode.CREDENTIAL_UNRESOLVED
        assert "cred/missing" not in str(info.value) or "ghp_" not in str(info.value)
        assert w["seen"] == []

    def test_no_trust_registry_preserves_pre_r172_behaviour(self, tmp_path: Path) -> None:
        w = _world(tmp_path)
        bound = BoundProjectInspector(
            GitHubProjectInspector(transport=_github()[0]),
            tenant_id=w["tenant"],
            bindings=w["registry"],
            trust=None,
            secrets=w["secrets"],
        )
        assert bound.inspect_binding(w["binding"].id).head_sha == "c0ffee"


class TestAppFactoryConsumesTheGovernedPort:
    def test_capability_resolves_inventory_by_binding_id_through_the_port(
        self, tmp_path: Path
    ) -> None:
        w = _world(tmp_path)
        capability = AppFactoryCapability(inspector=None, binding_inspector=w["bound"])
        contribution = capability.contribute(
            GeneralAgentRequest(
                ask="x",
                capability=APP_FACTORY_CAPABILITY_NAME,
                context={"binding_id": str(w["binding"].id)},
            )
        )
        assert contribution.template_ref == "app_factory.plan@1"
        assert any("c0ffee" in n for n in contribution.notes)
        assert not any("ghp_SECRET" in n for n in contribution.notes)

    def test_binding_refusals_surface_as_plan_refusals_with_the_typed_code(
        self, tmp_path: Path
    ) -> None:
        w = _world(tmp_path, trusted=False)
        capability = AppFactoryCapability(inspector=None, binding_inspector=w["bound"])
        with pytest.raises(PlanRefused, match="remote_not_trusted"):
            capability.contribute(
                GeneralAgentRequest(
                    ask="x",
                    capability=APP_FACTORY_CAPABILITY_NAME,
                    context={"binding_id": str(w["binding"].id)},
                )
            )
        assert w["secrets"].resolves == []

    def test_malformed_binding_id_is_refused_without_lookup(self, tmp_path: Path) -> None:
        w = _world(tmp_path)
        capability = AppFactoryCapability(inspector=None, binding_inspector=w["bound"])
        with pytest.raises(PlanRefused, match="binding_id"):
            capability.contribute(
                GeneralAgentRequest(
                    ask="x", capability=APP_FACTORY_CAPABILITY_NAME, context={"binding_id": "zzz"}
                )
            )
        assert w["trust"].calls == [] and w["seen"] == []

    def test_binding_id_without_a_bound_inspector_is_refused_loudly(self) -> None:
        capability = AppFactoryCapability(inspector=None)
        with pytest.raises(PlanRefused, match="project inspector"):
            capability.contribute(
                GeneralAgentRequest(
                    ask="x",
                    capability=APP_FACTORY_CAPABILITY_NAME,
                    context={"binding_id": str(uuid4())},
                )
            )
