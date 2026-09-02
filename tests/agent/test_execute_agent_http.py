"""POST /v1/execute with ``execution_policy.strategy = "agent"`` (R160).

The API is a thin consumer of the SHARED ``core.agent.AgentRuntime``: it
resolves the ``tools`` allow-list against the composition catalog and hands
off. Pins: absent seam ⇒ loud rejection; unknown tools ⇒ validation error;
empty allow-list ⇒ pure-answer run (no tools, never "all tools"); a cited
final returns 200 with the answer and a stored strategy=agent record readable
via GET /v1/executions/{id} (with reasoning execution ids); ungranted tool ⇒
refused observation (handler never ran); other tenant cannot read the record.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import InMemoryExecutionStore, Principal, create_app
from apps.api.agent import AgentSurface
from tests.agent.world import (
    TENANT,
    USER,
    AgentWorld,
    final,
    model_says,
    run,
    tool_call,
)


def _app(
    world: AgentWorld,
    *,
    with_agent: bool = True,
    tenant: UUID = TENANT,
    store: InMemoryExecutionStore | None = None,
) -> FastAPI:
    store = store if store is not None else InMemoryExecutionStore()
    world.runtime._store_report = store.put  # the API's store IS the runtime's store
    catalog = {"fs": world.read_spec()}
    write = world.write_spec()
    catalog[write.name] = write
    return create_app(
        router=world.router,
        execution_service=world.execution_service,
        store=store,
        principal=Principal(tenant_id=tenant, user_id=USER),
        agent=AgentSurface(runtime=world.runtime, catalog=catalog) if with_agent else None,
    )


async def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.post("/v1/execute", json=body)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


AGENT = {"strategy": "agent"}


def test_absent_agent_seam_is_rejected_loudly() -> None:
    world = AgentWorld([model_says(final("x"))])
    app = _app(world, with_agent=False)
    response = run(_post(app, {"ask": "hi", "execution_policy": AGENT}))
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"]["field"] == "execution_policy.strategy"
    assert world.adapter.requests == []  # nothing ran


def test_unknown_tool_names_are_rejected_before_any_run() -> None:
    world = AgentWorld([model_says(final("x"))])
    app = _app(world)
    response = run(
        _post(
            app,
            {"ask": "hi", "execution_policy": AGENT, "tools": {"allowed": ["fs", "shell"]}},
        )
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "tools.allowed", "unknown": ["shell"]}
    assert world.adapter.requests == []


def test_async_agent_is_rejected() -> None:
    world = AgentWorld([model_says(final("x"))])
    app = _app(world)
    response = run(
        _post(app, {"ask": "hi", "execution_policy": {"strategy": "agent", "async": True}})
    )
    assert response.status_code == 422


def test_tool_run_returns_answer_and_stores_agent_record() -> None:
    world = AgentWorld(
        [model_says(tool_call("fs", path="README.md")), model_says(final("hello", 1))]
    )
    store = InMemoryExecutionStore()
    app = _app(world, store=store)
    response = run(
        _post(
            app,
            {
                "ask": "what does README say?",
                "execution_policy": AGENT,
                "tools": {"allowed": ["fs"]},
            },
        )
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert '"answer": "hello"' in body["result"]["content"]
    assert world.fs.reads == ["README.md"]
    # The model saw ONLY the allowed tool (progressive disclosure).
    first_ask = world.adapter.requests[0].payload["ask"]
    assert '"name": "fs"' in first_ask and '"name": "fs_write"' not in first_ask
    # GET /v1/executions/{id} answers for the agent record (10 §5 shape).
    detail = run(_get(app, f"/v1/executions/{body['execution_id']}"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "succeeded"
    assert detail.json()["progress"]["current_stage"] == "final"
    # The stored record is strategy=agent with the reasoning trail, and every
    # reasoning execution is itself stored + readable (P6).
    record = store.get(TENANT, UUID(body["execution_id"]))
    assert record.execution.strategy.value == "agent"
    snap = record.execution.cost_snapshot
    assert snap["stop_reason"] == "final" and len(snap["reasoning_execution_ids"]) == 2
    for rid in snap["reasoning_execution_ids"]:
        assert run(_get(app, f"/v1/executions/{rid}")).status_code == 200


def test_empty_allow_list_means_no_tools() -> None:
    world = AgentWorld([model_says(tool_call("fs", path="README.md")), model_says(final("guess"))])
    app = _app(world)
    response = run(_post(app, {"ask": "read it", "execution_policy": AGENT}))
    assert response.status_code == 200
    assert world.fs.reads == []  # the tool call was REFUSED (no tools admitted)
    assert "Available tools:\n[]" in world.adapter.requests[0].payload["ask"]


def test_ungranted_permission_is_refused_by_the_one_firewall() -> None:
    world = AgentWorld(
        [model_says(tool_call("fs_write", path="x", content="y")), model_says(final("done"))]
    )
    app = _app(world)
    response = run(
        _post(app, {"ask": "write", "execution_policy": AGENT, "tools": {"allowed": ["fs_write"]}})
    )
    assert response.status_code == 200
    assert world.fs.writes == []
    assert "refused" in world.adapter.requests[1].payload["ask"]


def test_failed_run_is_unified_error_with_execution_id() -> None:
    world = AgentWorld([{"content": "not json at all"}], max_steps=1)
    app = _app(world)
    response = run(_post(app, {"ask": "hi", "execution_policy": AGENT}))
    assert response.status_code >= 400
    error = response.json()["error"]
    assert error["code"] == "execution_failed"
    assert "execution_id" in error["details"]


def test_other_tenant_cannot_read_agent_record() -> None:
    world = AgentWorld([model_says(final("x"))])
    store = InMemoryExecutionStore()
    app = _app(world, store=store)
    created = run(_post(app, {"ask": "hi", "execution_policy": AGENT})).json()
    other_app = _app(world, tenant=uuid4(), store=store)
    assert run(_get(other_app, f"/v1/executions/{created['execution_id']}")).status_code == 404
