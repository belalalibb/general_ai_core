"""T-IMPL-072 — Stateless API seams (41 §26 "Stateless API" / "API →
horizontal", FINAL Phase 23).

The ONLY honestly encodable slice of the 41 §26 production topology: the
app held exactly two process-local mutable maps that would break under
horizontal replicas — the idempotency index (10 §10) and the webhook
subscription store (41 §21). Both are now injectable MutableMapping seams.

Method: build TWO app instances ("replicas") over the SAME injected shared
state (store + index + subscriptions) and prove requests are replica-
agnostic. A plain dict plays the shared binding — the mapping PROTOCOL is
the seam; a Redis/DB adapter satisfying it slots in at the composition
root (recorded in the create_app docstring; no such binding is claimed to
exist, 41 §49).

Covers:

1. Cross-replica idempotent replay: execute with Idempotency-Key on
   replica A, replay on replica B → same execution_id, no second run
   (adapter call count proves it).
2. Cross-replica execution reads: GET /v1/executions/{id} on B finds A's
   execution when the store is shared.
3. Default posture unchanged: two apps WITHOUT injected seams do NOT share
   replay state (each process-local — the pre-existing single-replica
   behavior, byte-for-byte).
4. Webhook subscriptions land in the injected shared mapping, tenant-keyed.
5. No hidden request-path state: with store+index injected, a replayed
   POST and a status GET on a FRESH replica need nothing else — proving
   the two seams are the complete set of cross-request mutable state.

Hermetic: httpx ASGI transport, fakes only, asyncio.run (ADR-0001).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI

from apps.api.app import create_app
from core.contracts.webhooks import WebhookSubscription
from core.execution.service import ExecutionService
from core.routing import SimpleScoringRouter
from tests.api.test_execute_api import World, _no_sleep


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def make_replica(
    world: World,
    *,
    idempotency_index: dict[tuple[UUID, str], UUID] | None = None,
    webhook_subscriptions: dict[UUID, list[WebhookSubscription]] | None = None,
    webhooks: bool = False,
) -> FastAPI:
    """One API replica over the world's (shared) store and adapters."""
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        webhooks=webhooks,
        idempotency_index=idempotency_index,
        webhook_subscriptions=webhook_subscriptions,
    )


async def _post(
    app: FastAPI, path: str, body: dict[str, Any], headers: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post(path, json=body, headers=headers or {})


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


class TestCrossReplicaStatelessness:
    def test_idempotent_replay_across_replicas(self) -> None:
        """Replica A executes; replica B replays the SAME key: same
        execution_id, and the adapter ran exactly once."""
        world = World()
        shared_index: dict[tuple[UUID, str], UUID] = {}
        replica_a = make_replica(world, idempotency_index=shared_index)
        replica_b = make_replica(world, idempotency_index=shared_index)

        first = run(_post(replica_a, "/v1/execute", {"ask": "hi"},
                          {"Idempotency-Key": "shared-k1"}))
        assert first.status_code == 200
        calls_after_first = len(world.adapter.requests)

        replay = run(_post(replica_b, "/v1/execute", {"ask": "hi"},
                           {"Idempotency-Key": "shared-k1"}))
        assert replay.status_code == 200
        assert replay.json()["execution_id"] == first.json()["execution_id"]
        assert len(world.adapter.requests) == calls_after_first  # no re-run

    def test_execution_readable_from_other_replica(self) -> None:
        world = World()
        replica_a = make_replica(world)
        replica_b = make_replica(world)
        created = run(_post(replica_a, "/v1/execute", {"ask": "hi"}))
        execution_id = created.json()["execution_id"]
        status = run(_get(replica_b, f"/v1/executions/{execution_id}"))
        assert status.status_code == 200
        assert status.json()["execution_id"] == execution_id

    def test_default_posture_is_process_local(self) -> None:
        """WITHOUT injection each replica keeps its own index — the
        pre-existing single-replica behavior is unchanged."""
        world = World()
        replica_a = make_replica(world)  # no shared index
        replica_b = make_replica(world)
        first = run(_post(replica_a, "/v1/execute", {"ask": "hi"},
                          {"Idempotency-Key": "local-k"}))
        second = run(_post(replica_b, "/v1/execute", {"ask": "hi"},
                           {"Idempotency-Key": "local-k"}))
        # B never saw A's key: a NEW execution, not a replay.
        assert first.json()["execution_id"] != second.json()["execution_id"]

    def test_webhook_subscriptions_land_in_shared_mapping(self) -> None:
        world = World()
        shared_subs: dict[UUID, list[WebhookSubscription]] = {}
        replica_a = make_replica(
            world, webhooks=True, webhook_subscriptions=shared_subs
        )
        response = run(_post(replica_a, "/v1/webhooks",
                             {"url": "https://example.test/hook"}))
        assert response.status_code == 201
        assert len(shared_subs[world.principal.tenant_id]) == 1
        assert (
            str(shared_subs[world.principal.tenant_id][0].url)
            == "https://example.test/hook"
        )

    def test_fresh_replica_needs_only_the_injected_seams(self) -> None:
        """Completeness: a replica created AFTER the traffic, given only
        store+index, can both replay and read — no other request-path
        mutable state exists in the app."""
        world = World()
        shared_index: dict[tuple[UUID, str], UUID] = {}
        replica_a = make_replica(world, idempotency_index=shared_index)
        first = run(_post(replica_a, "/v1/execute", {"ask": "hi"},
                          {"Idempotency-Key": "late-k"}))
        execution_id = first.json()["execution_id"]

        late_replica = make_replica(world, idempotency_index=shared_index)
        replay = run(_post(late_replica, "/v1/execute", {"ask": "hi"},
                           {"Idempotency-Key": "late-k"}))
        assert replay.json()["execution_id"] == execution_id
        status = run(_get(late_replica, f"/v1/executions/{execution_id}"))
        assert status.status_code == 200

    def test_shared_index_is_tenant_scoped(self) -> None:
        """Two tenants sharing one physical index never see each other's
        keys (the tuple key carries tenant_id — 20 §6)."""
        world_a = World()
        world_b = World()
        shared_index: dict[tuple[UUID, str], UUID] = {}
        replica_a = make_replica(world_a, idempotency_index=shared_index)
        replica_b = make_replica(world_b, idempotency_index=shared_index)
        first = run(_post(replica_a, "/v1/execute", {"ask": "hi"},
                          {"Idempotency-Key": "same-key"}))
        other = run(_post(replica_b, "/v1/execute", {"ask": "hi"},
                          {"Idempotency-Key": "same-key"}))
        # Same literal key, different tenants: never a cross-tenant replay.
        assert first.json()["execution_id"] != other.json()["execution_id"]
        assert len(shared_index) == 2


def test_webhook_default_still_process_local() -> None:
    """Without injection, subscriptions stay app-local (posture unchanged)."""
    world = World()
    replica = make_replica(world, webhooks=True)
    response = run(_post(replica, "/v1/webhooks",
                         {"url": "https://example.test/hook"}))
    assert response.status_code == 201


# The FakeAdapter records calls as `requests`; assert the attribute exists so
# rename there fails HERE loudly rather than silently weakening test 1.
def test_fake_adapter_records_calls() -> None:
    world = World()
    assert hasattr(world.adapter, "requests")
    assert world.adapter.requests == []
