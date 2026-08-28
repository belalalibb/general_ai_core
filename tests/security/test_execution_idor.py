"""Cross-tenant execution IDOR regression (T-IMPL-033; 20 §6).

CONFIRMED DEFECT (found while starting T-IMPL-033, fixed in the same
slice): ``InMemoryExecutionStore`` keyed reports by execution id ONLY and
``GET /v1/executions/{id}`` never checked the caller's tenant — any
principal holding (or enumerating) a foreign execution id could read the
full report, including result content, cross-tenant.

FIX UNDER TEST: the store read is tenant-scoped from the stored
``Execution.tenant_id`` fact; a foreign tenant's execution raises the SAME
``ExecutionNotFound`` as a truly absent id, and the API surfaces both as
the SAME 404 body (20 §6 anti-enumeration — existence must not leak;
NEVER 403 for foreign resources). The idempotency replay path is likewise
tenant-scoped end-to-end.

Hermetic — httpx ASGI transport, fake adapters (reused from the execute-api
suite), no network. The two tenants SHARE one process store and one
registries set: that shared store is exactly the attack surface.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import Principal, create_app
from apps.api.store import ExecutionNotFound
from core.execution.service import ExecutionService
from core.routing.router import SimpleScoringRouter
from tests.api.test_execute_api import World, _no_sleep, run


class _SharedWorld(World):
    """One provider/model/store world serving TWO tenant principals."""

    def __init__(self) -> None:
        super().__init__()
        self.principal_b = Principal(tenant_id=uuid4(), user_id=uuid4())

    def app_for(self, principal: Principal) -> FastAPI:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        service = ExecutionService(
            adapters={self.provider.id: self.adapter},
            credential_refs={self.provider.id: f"secret-ref://{self.provider.id}"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            usage=self.usage,
            sleeper=_no_sleep,
        )
        return create_app(
            router=router,
            execution_service=service,
            store=self.store,  # SHARED across tenants — the attack surface
            principal=principal,
        )


async def _post(
    app: FastAPI, body: dict[str, object], headers: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/v1/execute", json=body, headers=headers or {})


async def _get_execution(app: FastAPI, execution_id: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(f"/v1/executions/{execution_id}")


# --- store level -----------------------------------------------------------------


def test_store_read_is_tenant_scoped() -> None:
    world = _SharedWorld()
    created = run(_post(world.app_for(world.principal), {"ask": "classified"}))
    assert created.status_code == 200
    execution_id = UUID(created.json()["execution_id"])

    # Owner reads fine.
    report = world.store.get(world.principal.tenant_id, execution_id)
    assert report.execution.tenant_id == world.principal.tenant_id

    # Foreign tenant: SAME error as absent (anti-enumeration, 20 §6).
    with pytest.raises(ExecutionNotFound):
        world.store.get(world.principal_b.tenant_id, execution_id)
    with pytest.raises(ExecutionNotFound):
        world.store.get(world.principal_b.tenant_id, uuid4())


# --- API level -------------------------------------------------------------------


def test_foreign_tenant_execution_read_is_404_not_403() -> None:
    world = _SharedWorld()
    created = run(_post(world.app_for(world.principal), {"ask": "classified"}))
    assert created.status_code == 200
    execution_id = created.json()["execution_id"]

    # Owner still reads it.
    owner = run(_get_execution(world.app_for(world.principal), execution_id))
    assert owner.status_code == 200

    # Attacker (tenant B) holding the leaked id: 404, NEVER 403, and no
    # execution result content in the body.
    attacker = run(_get_execution(world.app_for(world.principal_b), execution_id))
    assert attacker.status_code == 404
    assert owner.json().get("result") is not None
    assert "result" not in attacker.json()


def test_foreign_and_absent_are_indistinguishable() -> None:
    """20 §6: the attacker cannot tell 'exists elsewhere' from 'never existed'."""
    world = _SharedWorld()
    created = run(_post(world.app_for(world.principal), {"ask": "hi"}))
    foreign_id = created.json()["execution_id"]
    absent_id = str(uuid4())

    app_b = world.app_for(world.principal_b)
    foreign = run(_get_execution(app_b, foreign_id))
    absent = run(_get_execution(app_b, absent_id))

    assert foreign.status_code == absent.status_code == 404
    foreign_error = foreign.json()["error"]
    absent_error = absent.json()["error"]
    # Identical code and message; only the echoed id differs.
    assert foreign_error["code"] == absent_error["code"]
    assert foreign_error["message"] == absent_error["message"]


def test_idempotency_replay_does_not_cross_tenants() -> None:
    """The SAME Idempotency-Key used by two tenants must not share records."""
    world = _SharedWorld()
    headers = {"Idempotency-Key": "shared-key-123"}

    first = run(_post(world.app_for(world.principal), {"ask": "a"}, headers))
    second = run(_post(world.app_for(world.principal_b), {"ask": "a"}, headers))
    assert first.status_code == 200
    assert second.status_code == 200
    # Different tenants => different executions, even with the same key.
    assert first.json()["execution_id"] != second.json()["execution_id"]
