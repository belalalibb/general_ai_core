"""R161 Phase 3 — Real Learning Improvement, part 2: GOLD reaches PRODUCTION.

Before R161 the platform could prove a GOLD answer existed ONLY through
the isolated ``ask_learned`` path. Whether promoted knowledge reached a
real ``/v1/execute`` answer was an inference: the composer retrieved
tenant memory, the payload carried it, and the local echo adapter
dropped it on the floor — no response field ever said "learned
knowledge was in the model input".

Now it is MEASURED through the SAME local runtime profile the operator
runs (P1: no test-only wiring):

- ``result.artifacts`` carries ONE ``context_provenance`` artifact derived
  from the STORED node ``input_ref`` (execution truth, not a re-compose):
  per memory block the memory id + its memory ``source`` label — never
  the content;
- BEFORE promotion: ``gold_blocks == 0``; AFTER: ``== 1`` and the memory
  id resolves to ``learning.gold`` — a before/after delta over the
  production route, the Phase 3 acceptance test;
- GET /v1/executions/{id} shows the SAME artifact (one derivation, two
  readers);
- the hermetic echo adapter mirrors the composed blocks it RECEIVED
  (``context_blocks``) so the local profile shows the knowledge in the
  model input honestly;
- tenant isolation: another tenant's GOLD item never appears;
- the artifact never echoes memory content (only ids + labels).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx

from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.contracts.base import utc_now
from core.contracts.evaluation import VerificationLevel
from core.contracts.memory import MemoryItem, MemoryScope
from core.learning import EligibilitySignals, PromotionSignals

ALL_ELIGIBLE = EligibilitySignals(
    privacy_policy_allows=True,
    tenant_user_policy_allows=True,
    sensitive_data_handled=True,
    not_poisoned=True,
)
ALL_PROMOTE = PromotionSignals(
    offline_eval_pass=True,
    regression_pass=True,
    security_eval_pass=True,
    shadow_performance_acceptable=True,
    canary_performance_acceptable=True,
    rollback_plan_exists=True,
    approval_required=True,
    admin_approved=True,
)
SECRET_MARKER = "learned-value-never-echoed-in-artifact"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _profile() -> RuntimeProfile:
    return build_runtime_profile(environ={})


async def _execute(profile: RuntimeProfile, ask: str) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=profile.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.post("/v1/execute", json={"ask": ask})
        assert response.status_code == 200, response.text
        return dict(response.json())


async def _fetch(profile: RuntimeProfile, execution_id: str) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=profile.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get(f"/v1/executions/{execution_id}")
        assert response.status_code == 200, response.text
        return dict(response.json())


def _promote(profile: RuntimeProfile, tenant_id: UUID, key: str, value: dict[str, Any]) -> UUID:
    service = profile.app.state.learning_lifecycle_service
    sample = service.capture_external(tenant_id, knowledge_key=key, knowledge_value=value)
    service.mark_sanitized(tenant_id, sample.id, passed=True)
    service.set_verification_level(tenant_id, sample.id, VerificationLevel.VERIFIED)
    service.admit_to_training(tenant_id, sample.id, ALL_ELIGIBLE)
    item = service.promote_to_gold(tenant_id, sample.id, ALL_PROMOTE)
    return UUID(str(item.id))


def _provenance(body: dict[str, Any]) -> dict[str, Any]:
    artifacts = body["result"]["artifacts"]
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["type"] == "context_provenance"
    return dict(artifact)


class TestGoldReachesProductionMeasurably:
    def test_before_after_delta_over_the_real_execute_route(self) -> None:
        profile = _profile()
        tenant = profile.demo_principal.tenant_id

        before = run(_execute(profile, "what is the rollback procedure"))
        prov_before = _provenance(before)
        assert prov_before["gold_blocks"] == 0
        assert prov_before["memory_blocks"] == []
        assert prov_before["blocks_total"] == 1  # the ask itself

        memory_id = _promote(
            profile, tenant, "ops.rollback", {"answer": f"drain then flip {SECRET_MARKER}"}
        )

        after = run(_execute(profile, "what is the rollback procedure"))
        prov_after = _provenance(after)
        assert prov_after["gold_blocks"] == 1
        assert prov_after["blocks_total"] == 2
        assert prov_after["memory_blocks"] == [
            {"memory_id": str(memory_id), "source": "learning.gold", "type": "preference"}
        ]
        # the artifact carries ids + labels only — never the learned content
        assert SECRET_MARKER not in json.dumps(after["result"]["artifacts"])

        # the hermetic echo adapter shows the knowledge WAS in the model input
        content = json.loads(after["result"]["content"])
        assert content["provider"] == "local-echo"
        sources = {block["source"] for block in content["context_blocks"]}
        assert f"memory:{memory_id}" in sources and "request" in sources
        assert any(SECRET_MARKER in block["content"] for block in content["context_blocks"])

    def test_execution_fetch_reports_the_same_artifact(self) -> None:
        profile = _profile()
        tenant = profile.demo_principal.tenant_id
        _promote(profile, tenant, "k", {"v": "x"})
        sync = run(_execute(profile, "ask"))
        fetched = run(_fetch(profile, sync["execution_id"]))
        assert fetched["result"]["artifacts"] == sync["result"]["artifacts"]
        assert fetched["result"]["artifacts"][0]["gold_blocks"] == 1

    def test_other_tenants_gold_is_invisible(self) -> None:
        profile = _profile()
        foreign = uuid4()
        _promote(profile, foreign, "k", {"v": "foreign"})
        body = run(_execute(profile, "ask"))
        assert _provenance(body)["gold_blocks"] == 0
        assert _provenance(body)["memory_blocks"] == []

    def test_non_gold_memory_is_labeled_by_its_own_source(self) -> None:
        """Memory that did NOT go through the learning gates is not GOLD."""
        profile = _profile()
        tenant = profile.demo_principal.tenant_id
        service = profile.app.state.learning_lifecycle_service
        item = service._knowledge.upsert(  # the same store the composer reads
            MemoryItem(
                id=uuid4(),
                tenant_id=tenant,
                user_id=None,
                scope=MemoryScope.TENANT,
                key="pref.tone",
                value="terse",
                source="user.stated",
                confidence=0.8,
                evidence_count=1,
                last_seen=utc_now(),
            )
        )
        body = run(_execute(profile, "ask"))
        prov = _provenance(body)
        assert prov["gold_blocks"] == 0
        assert prov["memory_blocks"] == [
            {"memory_id": str(item.id), "source": "user.stated", "type": "preference"}
        ]
