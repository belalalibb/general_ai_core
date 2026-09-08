"""R177-FIX-04 — wire PreferenceLearningGate (13 §6) + 13 §8 memory visibility.

Before: ``core/memory/preferences.PreferenceLearningGate`` had zero runtime
callers and no route let a user see or delete learned memory. After: an
OPTIONAL ``preferences`` seam observes succeeded ``/v1/execute`` requests,
asks the EXISTING gate, and writes admitted preferences as
``MemoryItem(scope=tenant, user_id=<caller>, source="preference")`` through
the EXISTING MemoryStorePort (secret guard applies). Two user routes expose
them. Absent seam ⇒ no learning, no routes (honest INERT).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api import Principal, create_app
from apps.api.preferences import PREFERENCE_SOURCE, PreferenceLearner
from core.contracts.memory import MemoryScope
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryMemoryStore
from core.memory.preferences import PreferenceLearningGate
from tests.api.test_admin_api import World, _no_sleep

PREFS = "/v1/memory/preferences"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _app(
    world: World,
    *,
    memory: InMemoryMemoryStore | None,
    learner: PreferenceLearner | None,
    principal: Principal | None = None,
) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    caller = principal or world.principal
    world.usage.configure_tenant(caller.tenant_id, plan="pro", task_units_limit=1000.0)
    return create_app(
        router=world.router,
        execution_service=service,
        principal=caller,
        admin=world.surface(),
        memory=memory,
        preferences=learner,
    )


async def _post(app: FastAPI, path: str, body: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


async def _delete(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.delete(path)


def _execute(app: FastAPI, *, language: str | None = None, fmt: str | None = None) -> None:
    body: dict[str, object] = {"ask": "hello"}
    if language is not None:
        body["context"] = {"language": language}
    if fmt is not None:
        body["output"] = {"format": fmt}
    response = run(_post(app, "/v1/execute", body))
    assert response.status_code == 200, response.text


def _learner(memory: InMemoryMemoryStore, *, policy_allows: bool = True) -> PreferenceLearner:
    return PreferenceLearner(
        memory=memory, gate=PreferenceLearningGate(), policy_allows_memory=policy_allows
    )


class TestLearningThroughTheGate:
    def test_single_observation_learns_nothing(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        app = _app(world, memory=memory, learner=_learner(memory))
        _execute(app, language="ar")
        assert run(_get(app, PREFS)).json() == {"preferences": []}
        assert memory.query(world.principal.tenant_id, user_id=world.principal.user_id) == ()

    def test_repeated_evidence_learns_a_user_scoped_preference(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        app = _app(world, memory=memory, learner=_learner(memory))
        _execute(app, language="ar")
        _execute(app, language="ar")
        rows = run(_get(app, PREFS)).json()["preferences"]
        assert len(rows) == 1
        row = rows[0]
        assert row["key"] == "preferred_language"
        assert row["value"] == "ar"
        assert row["source"] == PREFERENCE_SOURCE == "preference"
        assert row["scope"] == "tenant"
        assert row["user_id"] == str(world.principal.user_id)
        assert 0.0 < row["confidence"] <= 1.0
        # The item is a REAL MemoryItem in the composed store (one writer path).
        items = memory.query(world.principal.tenant_id, user_id=world.principal.user_id)
        assert [i.source for i in items] == [PREFERENCE_SOURCE]
        assert items[0].scope is MemoryScope.TENANT

    def test_contradiction_dominating_refuses(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = _learner(memory)
        app = _app(world, memory=memory, learner=learner)
        _execute(app, language="ar")
        _execute(app, language="en")
        _execute(app, language="en")  # en 2 vs ar 1: strict majority -> learned
        rows = run(_get(app, PREFS)).json()["preferences"]
        assert [r["value"] for r in rows] == ["en"]
        _execute(app, language="ar")  # ar 2 vs en 2: a tie never fabricates certainty
        decision = learner.last_decision(world.principal.tenant_id, world.principal.user_id)
        assert decision is not None and decision.learnable is False
        assert decision.reason == "contradiction_dominates:2vs2"
        rows = run(_get(app, PREFS)).json()["preferences"]
        assert [r["value"] for r in rows] == ["en"]  # ar was NOT written

    def test_policy_denies_by_default(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = PreferenceLearner(memory=memory, gate=PreferenceLearningGate())
        app = _app(world, memory=memory, learner=learner)
        _execute(app, language="ar")
        _execute(app, language="ar")
        assert run(_get(app, PREFS)).json()["preferences"] == []
        assert learner.last_decision(world.principal.tenant_id, world.principal.user_id) is not None
        decision = learner.last_decision(world.principal.tenant_id, world.principal.user_id)
        assert decision is not None and decision.reason == "memory_policy_denies"

    def test_failed_execution_is_not_evidence(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = _learner(memory)
        # Observe directly with a failed status: nothing recorded.
        learner.observe(
            tenant_id=world.principal.tenant_id,
            user_id=world.principal.user_id,
            language="ar",
            output_format=None,
            succeeded=False,
        )
        learner.observe(
            tenant_id=world.principal.tenant_id,
            user_id=world.principal.user_id,
            language="ar",
            output_format=None,
            succeeded=False,
        )
        assert memory.query(world.principal.tenant_id, user_id=world.principal.user_id) == ()

    def test_secret_shaped_value_is_refused_by_the_store_guard(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = _learner(memory)
        token = "ghp_" + "A" * 36
        for _ in range(2):
            learner.observe(
                tenant_id=world.principal.tenant_id,
                user_id=world.principal.user_id,
                language=None,
                output_format=token,
                succeeded=True,
            )
        assert memory.query(world.principal.tenant_id, user_id=world.principal.user_id) == ()
        decision = learner.last_decision(world.principal.tenant_id, world.principal.user_id)
        assert decision is not None and decision.learnable is False
        assert decision.reason is not None and decision.reason.startswith("store_refused:")

    def test_observation_window_is_bounded(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = PreferenceLearner(
            memory=memory,
            gate=PreferenceLearningGate(),
            policy_allows_memory=True,
            window=3,
        )
        for lang in ("en", "en", "ar", "ar", "ar"):
            learner.observe(
                tenant_id=world.principal.tenant_id,
                user_id=world.principal.user_id,
                language=lang,
                output_format=None,
                succeeded=True,
            )
        items = memory.query(world.principal.tenant_id, user_id=world.principal.user_id)
        assert [i.value for i in items] == ["ar"]


class TestVisibilityRoutes:
    def test_other_users_and_tenants_never_see_each_other(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = _learner(memory)
        app_a = _app(world, memory=memory, learner=learner)
        _execute(app_a, language="ar")
        _execute(app_a, language="ar")
        row = run(_get(app_a, PREFS)).json()["preferences"][0]
        # same tenant, other user
        other_user = Principal(tenant_id=world.principal.tenant_id, user_id=uuid4())
        app_b = _app(world, memory=memory, learner=learner, principal=other_user)
        assert run(_get(app_b, PREFS)).json()["preferences"] == []
        assert run(_delete(app_b, f"{PREFS}/{row['id']}")).status_code == 404
        # other tenant
        foreign = Principal(tenant_id=uuid4(), user_id=uuid4())
        app_c = _app(world, memory=memory, learner=learner, principal=foreign)
        assert run(_get(app_c, PREFS)).json()["preferences"] == []
        assert run(_delete(app_c, f"{PREFS}/{row['id']}")).status_code == 404
        # owner still has it
        assert len(run(_get(app_a, PREFS)).json()["preferences"]) == 1

    def test_delete_is_respected_and_non_preference_memory_is_invisible(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        learner = _learner(memory)
        app = _app(world, memory=memory, learner=learner)
        _execute(app, fmt="json")
        _execute(app, fmt="json")
        rows = run(_get(app, PREFS)).json()["preferences"]
        assert [r["key"] for r in rows] == ["preferred_output_format"]
        # a GOLD-looking tenant-shared item is NOT a preference row
        from core.contracts.base import utc_now
        from core.contracts.memory import MemoryItem

        memory.upsert(
            MemoryItem(
                id=uuid4(),
                tenant_id=world.principal.tenant_id,
                user_id=None,
                scope=MemoryScope.TENANT,
                key="ops.k",
                value={"a": 1},
                source="learning.gold",
                confidence=0.9,
                evidence_count=1,
                last_seen=utc_now(),
            )
        )
        assert len(run(_get(app, PREFS)).json()["preferences"]) == 1
        deleted = run(_delete(app, f"{PREFS}/{rows[0]['id']}"))
        assert deleted.status_code == 204
        assert run(_get(app, PREFS)).json()["preferences"] == []
        assert run(_delete(app, f"{PREFS}/{rows[0]['id']}")).status_code == 404
        assert run(_delete(app, f"{PREFS}/not-a-uuid")).status_code == 404

    def test_deleting_a_gold_item_through_the_preference_route_is_refused(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        app = _app(world, memory=memory, learner=_learner(memory))
        from core.contracts.base import utc_now
        from core.contracts.memory import MemoryItem

        gold = memory.upsert(
            MemoryItem(
                id=uuid4(),
                tenant_id=world.principal.tenant_id,
                user_id=None,
                scope=MemoryScope.TENANT,
                key="ops.k",
                value={"a": 1},
                source="learning.gold",
                confidence=0.9,
                evidence_count=1,
                last_seen=utc_now(),
            )
        )
        assert run(_delete(app, f"{PREFS}/{gold.id}")).status_code == 404
        assert memory.get(world.principal.tenant_id, gold.id).id == gold.id


class TestSeamAbsent:
    def test_no_learner_means_no_routes_and_no_learning(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        app = _app(world, memory=memory, learner=None)
        _execute(app, language="ar")
        _execute(app, language="ar")
        assert run(_get(app, PREFS)).status_code == 404
        assert memory.query(world.principal.tenant_id, user_id=world.principal.user_id) == ()

    def test_learner_requires_the_memory_seam(self) -> None:
        world = World()
        memory = InMemoryMemoryStore()
        import pytest

        with pytest.raises(ValueError, match="memory"):
            _app(world, memory=None, learner=_learner(memory))


def test_runtime_profile_composes_the_learner_over_the_same_memory_store() -> None:
    from pathlib import Path

    source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "PreferenceLearner(" in source
    assert "memory=memory_store" in source
    assert "preferences=preference_learner," in source


def test_memory_type_convention_recognises_the_preference_source() -> None:
    from tests.memory.test_memory_type_convention_r177 import (
        MEMORY_SOURCE_VOCABULARY,
        runtime_memory_item_sources,
    )

    assert PREFERENCE_SOURCE in MEMORY_SOURCE_VOCABULARY
    found = runtime_memory_item_sources()
    assert found.get("apps/api/preferences.py") == [PREFERENCE_SOURCE]
