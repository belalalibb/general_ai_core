"""R168 §6.6 — the exercise probe is tenant-isolated (proof, not rewire).

Conflict ledger C-04: the mandate asked for an "isolated test tenant via
``configure_tenant`` + ExerciseSurface rewire"; the frozen derivation in
``apps/api/exercise.py`` says probes are CALLER-SCOPED ("no service account,
no invented identity") and INV-2 forbids non-additive production changes
outside D-01/D-08. Stricter reading applied: production stays caller-scoped;
this module PROVES the isolation property the rewire was meant to buy —

* the probe tenant is a fresh, dedicated tenant granted through the SAME
  ``configure_tenant`` admin seam (no shared demo tenant);
* a bystander tenant granted on the same accounting instance sees zero
  consumption and zero stored executions after the probe;
* the probe's units land on the caller only, and its record is visible
  only through the caller's store view (foreign lookup → ExecutionNotFound).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.app import Principal
from apps.api.exercise import EXERCISE_LABEL_KEY
from apps.api.store import ExecutionNotFound, InMemoryExecutionStore
from core.execution.service import ExecutionService
from tests.api.test_admin_api import World, _no_sleep

PROBE_PLAN = "r168_exercise_probe"
PROBE_LIMIT = 5.0


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _post(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path)


class _Isolated:
    """A World whose caller is a dedicated probe tenant plus one bystander tenant."""

    def __init__(self) -> None:
        self.world = World()
        # Dedicated probe tenant: fresh ids, granted via the admin seam.
        self.world.principal = Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=True)
        self.world.usage.configure_tenant(
            self.world.principal.tenant_id, plan=PROBE_PLAN, task_units_limit=PROBE_LIMIT
        )
        # Bystander on the SAME accounting instance — must stay untouched.
        self.bystander = uuid4()
        self.world.usage.configure_tenant(self.bystander, plan="bystander", task_units_limit=1.0)
        self.store = InMemoryExecutionStore()
        service = ExecutionService(
            adapters={self.world.provider.id: self.world.adapter},
            credential_refs={self.world.provider.id: f"secret-ref://{self.world.provider.id}"},
            bindings=self.world.bindings,
            max_retries_per_candidate=0,
            usage=self.world.usage,
            sleeper=_no_sleep,
        )
        self.app = create_app(
            router=self.world.router,
            execution_service=service,
            store=self.store,
            principal=self.world.principal,
            admin=self.world.surface(),
        )

    def probe(self) -> dict[str, Any]:
        response = run(_post(self.app, "/v1/admin/capabilities/execute.sync/exercise"))
        assert response.status_code == 200
        result: dict[str, Any] = response.json()["result"]
        return result


def test_probe_tenant_is_dedicated_and_granted_via_configure_tenant() -> None:
    iso = _Isolated()
    summary = iso.world.usage.summary(iso.world.principal.tenant_id)
    assert summary.plan == PROBE_PLAN
    assert summary.task_units.limit == PROBE_LIMIT
    assert summary.task_units.used == 0.0
    assert iso.world.principal.tenant_id != iso.bystander


def test_probe_bills_caller_only() -> None:
    iso = _Isolated()
    before_caller = iso.world.usage.summary(iso.world.principal.tenant_id).task_units.used
    before_bystander = iso.world.usage.summary(iso.bystander).task_units.used

    result = iso.probe()
    assert result["exercised"] is True

    after_caller = iso.world.usage.summary(iso.world.principal.tenant_id).task_units.used
    after_bystander = iso.world.usage.summary(iso.bystander).task_units.used
    assert after_caller > before_caller, "probe must consume the caller's units"
    assert after_bystander == before_bystander == 0.0, "bystander tenant must be untouched"


def test_probe_record_visible_only_to_caller() -> None:
    iso = _Isolated()
    result = iso.probe()
    execution_id = UUID(result["evidence"]["execution_id"])

    own = iso.store.get(iso.world.principal.tenant_id, execution_id)
    metadata = own.nodes[0].node.input_ref["context"]["metadata"]  # type: ignore[index]
    assert EXERCISE_LABEL_KEY in metadata

    assert iso.store.list(iso.bystander) == ()
    with pytest.raises(ExecutionNotFound):
        iso.store.get(iso.bystander, execution_id)


def test_probe_budget_exhaustion_stays_on_probe_tenant() -> None:
    iso = _Isolated()
    exhausted = False
    for _ in range(int(PROBE_LIMIT) + 2):
        result = iso.probe()
        if result["exercised"] is False:
            assert result["error"] == "budget exceeded"
            exhausted = True
            break
    assert exhausted, "dedicated probe budget must be finite and enforced"
    assert iso.world.usage.summary(iso.bystander).task_units.used == 0.0
