"""R172 C7 — the ``/v1/dev`` router must be *mounted* by ``create_app``.

Discovery D3 (``evidence/r172/discovery.md``): ``apps.agent_dev.http.create_dev_router``
existed since R169 A6 but no composition root ever called it, so
``GET /v1/dev/bindings/{binding_id}/publish-modes`` resolved on no served app.

This spec pins the closure:

* ``create_app(dev_bindings=RepoBindingRegistry)`` mounts the router (opt-in seam,
  same pattern as the other optional seams — production composition does NOT
  inject it, so the capability is honestly ``inert`` there).
* A new closed capability id ``dev.publish_modes`` derives from that seam.
* Unknown / malformed / foreign-tenant binding ids collapse to ONE typed 404 with
  no leak of the foreign binding's label, remote, branch or credential_ref.
* When the seam is absent the route is not in the table and the capability is inert.

Fail-first: every ``TestSeamComposed`` test and the capability-id tests fail on
``bde7276`` (``create_app() got an unexpected keyword argument 'dev_bindings'`` /
``dev.publish_modes`` not in ``CAPABILITY_IDS``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.agent_dev.git_tools import RepoBindingRegistry
from apps.agent_dev.http import DEV_ROUTER_PREFIX
from apps.api import create_app
from apps.api.capabilities import CAPABILITY_IDS
from core.contracts.publish_mode import PublishMode
from core.contracts.repo_binding import RepoBinding
from core.execution.service import ExecutionService
from tests.api.test_admin_api import World, _no_sleep

ROUTE_TEMPLATE = f"{DEV_ROUTER_PREFIX}/bindings/{{binding_id}}/publish-modes"
CAP_ID = "dev.publish_modes"
NEVER_LEAKED_REMOTE = "https://github.com/example/never-leaked.git"
NEVER_LEAKED_CREDREF = "credref_never_leaked"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _binding(tmp_path: Path, *, tenant_id: UUID, label: str = "secret-label") -> RepoBinding:
    root = tmp_path / label
    root.mkdir(parents=True, exist_ok=True)
    return RepoBinding(
        tenant_id=tenant_id,
        remote_url=NEVER_LEAKED_REMOTE,
        branch="main",
        local_root=str(root),
        credential_ref=NEVER_LEAKED_CREDREF,
        label=label,
    )


def _app(world: World, *, dev_bindings: RepoBindingRegistry | None) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    extra: dict[str, Any] = {}
    if dev_bindings is not None:
        extra["dev_bindings"] = dev_bindings
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=world.surface(),
        **extra,
    )


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def _served_paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def _cap_state(app: FastAPI, cap_id: str) -> str:
    response = run(_get(app, "/v1/admin/capabilities"))
    assert response.status_code == 200, response.text
    states = {row["id"]: row["state"] for row in response.json()["capabilities"]}
    return states[cap_id]


def _publish_modes(app: FastAPI, binding_id: str) -> httpx.Response:
    return run(_get(app, f"{DEV_ROUTER_PREFIX}/bindings/{binding_id}/publish-modes"))


def test_dev_publish_modes_is_a_closed_capability_id() -> None:
    assert CAP_ID in CAPABILITY_IDS


class TestSeamComposed:
    def test_publish_modes_resolves_with_four_modes(self, tmp_path: Path) -> None:
        world = World()
        registry = RepoBindingRegistry()
        binding = registry.register(_binding(tmp_path, tenant_id=world.principal.tenant_id))
        app = _app(world, dev_bindings=registry)

        response = _publish_modes(app, str(binding.id))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["binding_id"] == str(binding.id)
        assert body["default"] == "pull_request"
        modes = {row["id"]: row for row in body["modes"]}
        assert sorted(modes) == sorted(mode.value for mode in PublishMode)
        assert modes["pull_request"]["selectable"] is True
        assert modes["direct_push"]["selectable"] is False
        assert isinstance(modes["direct_push"]["reason"], str) and modes["direct_push"]["reason"]
        # The binding's credential_ref and remote never cross the wire.
        assert "credref" not in response.text
        assert "never-leaked" not in response.text

    def test_route_table_contains_the_dev_path(self, tmp_path: Path) -> None:
        world = World()
        app = _app(world, dev_bindings=RepoBindingRegistry())
        assert ROUTE_TEMPLATE in _served_paths(app)
        assert ROUTE_TEMPLATE in {getattr(r, "path", None) for r in app.routes}

    def test_capability_is_available_when_composed(self) -> None:
        world = World()
        app = _app(world, dev_bindings=RepoBindingRegistry())
        assert _cap_state(app, CAP_ID) == "available"

    def test_unknown_binding_is_one_typed_404(self) -> None:
        world = World()
        app = _app(world, dev_bindings=RepoBindingRegistry())
        missing = uuid4()

        response = _publish_modes(app, str(missing))

        assert response.status_code == 404, response.text
        body = response.json()
        assert set(body) == {"error"}
        error = body["error"]
        assert error["code"] == "validation_error"
        assert error["retryable"] is False
        assert error["details"] == {"binding_id": str(missing)}

    def test_malformed_binding_id_is_the_same_404(self) -> None:
        world = World()
        app = _app(world, dev_bindings=RepoBindingRegistry())

        response = _publish_modes(app, "not-a-uuid")

        assert response.status_code == 404, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"] == {"binding_id": "not-a-uuid"}

    def test_foreign_tenant_binding_is_indistinguishable_from_unknown(self, tmp_path: Path) -> None:
        world = World()
        registry = RepoBindingRegistry()
        foreign = registry.register(_binding(tmp_path, tenant_id=uuid4(), label="foreign-label"))
        app = _app(world, dev_bindings=registry)
        missing = uuid4()

        foreign_response = _publish_modes(app, str(foreign.id))
        unknown_response = _publish_modes(app, str(missing))

        assert foreign_response.status_code == 404
        assert unknown_response.status_code == 404

        def _normalised(response: httpx.Response, binding_id: UUID) -> dict[str, Any]:
            error = dict(response.json()["error"])
            assert error["details"] == {"binding_id": str(binding_id)}
            error.pop("details")
            error.pop("trace_id", None)
            return error

        assert _normalised(foreign_response, foreign.id) == _normalised(unknown_response, missing)
        for leak in ("foreign-label", "never-leaked", "credref", "main"):
            assert leak not in foreign_response.text

    def test_own_binding_still_resolves_beside_foreign_one(self, tmp_path: Path) -> None:
        world = World()
        registry = RepoBindingRegistry()
        registry.register(_binding(tmp_path, tenant_id=uuid4(), label="foreign-label"))
        own = registry.register(
            _binding(tmp_path, tenant_id=world.principal.tenant_id, label="own-label")
        )
        app = _app(world, dev_bindings=registry)

        response = _publish_modes(app, str(own.id))

        assert response.status_code == 200, response.text
        assert response.json()["binding_id"] == str(own.id)


class TestSeamAbsent:
    def test_route_absent_when_not_composed(self) -> None:
        world = World()
        app = _app(world, dev_bindings=None)
        assert ROUTE_TEMPLATE not in _served_paths(app)

        response = _publish_modes(app, str(uuid4()))

        assert response.status_code == 404
        assert "binding_id" not in response.text

    def test_capability_is_inert_when_not_composed(self) -> None:
        world = World()
        app = _app(world, dev_bindings=None)
        assert _cap_state(app, CAP_ID) == "inert"

    def test_default_runtime_profile_does_not_compose_the_dev_seam(self) -> None:
        # Owner decision (R172 C7): production composition does not build a
        # RepoBindingRegistry, so the seam stays inert there. Pinned so a later
        # round flipping it must do so deliberately (and update CAPABILITY_MAP).
        source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
        assert "dev_bindings=" not in source
