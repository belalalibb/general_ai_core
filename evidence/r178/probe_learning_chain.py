"""R178 hermetic invariant probes; no live provider, DB, training or production data.

Run: .venv/bin/python -m evidence.r178.probe_learning_chain
Exit 1 = observed invariant failure (NOT a passing regression test).
Uses real ASGI routes/services with existing test provider fixtures.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import httpx

from apps.api.promotion_evidence import PromotionEvidenceResolver
from apps.api.store import InMemoryExecutionStore
from core.contracts.provider import ProviderGenerateRequest, ProviderGenerateResponse
from tests.api.test_admin_api import FakeAdapter, World
from tests.api.test_promotion_evidence_r177 import _app


class FailedQualityAdapter(FakeAdapter):
    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output={"content": "probe", "error": "deliberate quality failure"},
            usage={"units": 1},
        )


async def main() -> int:
    rows: list[dict[str, object]] = []

    def observe(probe: str, expected: object, actual: object) -> None:
        rows.append(
            dict(
                probe=probe,
                expected=expected,
                actual=actual,
                status="VERIFIED" if actual == expected else "FAILED",
                evidence_type="TEST",
            )
        )

    world = World()
    tenant = world.principal.tenant_id
    world.usage.configure_tenant(tenant, plan="pro", task_units_limit=100.0)
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    resolver = PromotionEvidenceResolver(evaluations=world.evaluations, executions=store)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://hermetic"
    ) as client:
        created = await client.post(
            "/v1/admin/learning/samples",
            json={"knowledge_key": "r178.sample", "knowledge_value": {"answer": "probe"}},
        )
        assert created.status_code == 201, created.status_code
        sample = created.json()
        evaluated = await client.post(
            f"/v1/admin/learning/samples/{sample['id']}/evaluate",
            json={"output": {"answer": "probe"}},
        )
        assert evaluated.status_code == 200, evaluated.status_code
        assert evaluated.json()["evaluated"] is True
        listing = await client.get(
            f"/v1/admin/executions/{sample['source_execution_id']}/evaluations"
        )
        assert listing.status_code == 200, listing.status_code
        observe(
            "P01 evaluated sample has discoverable admin evidence",
            1,
            len(listing.json()["evaluations"]),
        )
        observe(
            "C01 evaluation alone does not grant training eligibility",
            "pending",
            evaluated.json()["sample"]["eligibility"],
        )
        for label in (None, {"scenario_id": str(uuid4())}):
            execution = await client.post(
                "/v1/execute",
                json={"ask": "probe", "context": {"metadata": {"test_scenario": label}}},
            )
            assert execution.status_code == 200, execution.status_code
            execution_id = UUID(execution.json()["execution_id"])
            observe(
                "C02 caller metadata alone must not establish regression pass",
                False,
                resolver.regression(tenant, execution_id).held,
            )
            observe(
                "C03 foreign tenant cannot resolve execution evidence",
                False,
                resolver.regression(uuid4(), execution_id).held,
            )

    failed_world = World()
    failed_world.adapter = FailedQualityAdapter()
    failed_tenant = failed_world.principal.tenant_id
    failed_world.usage.configure_tenant(failed_tenant, plan="pro", task_units_limit=100.0)
    failed_store = InMemoryExecutionStore()
    failed_app = _app(failed_world, strict=True, store=failed_store)
    scenarios = failed_app.state.scenario_service
    scenario = scenarios.save(
        failed_tenant, name="r178.quality-failure", ask="probe", checks=("error_free_output",)
    )
    replay = await scenarios.replay(failed_tenant, failed_world.principal.user_id, scenario.id)
    assert replay["replayed"] is True
    assert replay["passed"] is False, replay
    failed_resolver = PromotionEvidenceResolver(
        evaluations=failed_world.evaluations, executions=failed_store
    )
    verdict = failed_resolver.regression(failed_tenant, UUID(replay["execution_id"]))
    observe(
        "P03 required scenario check failure must refuse regression_pass",
        {"scenario_passed": False, "resolver_held": False},
        {"scenario_passed": replay["passed"], "resolver_held": verdict.held},
    )
    print(json.dumps({"environment": "hermetic ASGI; fake provider", "probes": rows}, indent=2))
    return int(any(row["status"] == "FAILED" for row in rows))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
