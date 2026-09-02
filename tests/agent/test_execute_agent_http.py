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
from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillSource,
    SkillStatus,
    SkillToolRequirements,
    SkillType,
)
from core.roles.registry import SkillRegistry
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
    skills: SkillRegistry | None = None,
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
        skills=skills,
    )


def _skill(manifest_id: str, required: list[str]) -> Skill:
    manifest = SkillManifest(
        id=manifest_id,
        name=manifest_id,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        status=SkillStatus.ACTIVE,
        requires_tools=SkillToolRequirements(required=required),
    )
    return Skill(
        id=uuid4(),
        name=manifest_id,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        manifest=manifest,
        status=SkillStatus.ACTIVE,
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
    # R165: the client sees WHY — the loop's stop reason and the failed
    # node's recorded cause — on the sync error AND on the status route.
    agent = error["details"]["agent"]
    assert agent["stop_reason"] == "invalid_proposal"
    assert agent["node"] == "plan-1"
    assert agent["error"]["reason"] == "invalid_proposal"
    assert "invalid_proposal" in error["message"]
    detail = run(_get(app, f"/v1/executions/{error['details']['execution_id']}"))
    assert detail.json()["error"]["details"]["agent"] == agent


def test_failed_run_cause_is_scrubbed() -> None:
    leaked = "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
    world = AgentWorld([{"content": f"{leaked} is not json"}], max_steps=1)
    app = _app(world)
    response = run(_post(app, {"ask": "hi", "execution_policy": AGENT}))
    assert response.status_code >= 400
    assert leaked not in response.text
    assert "agent" in response.json()["error"]["details"]


def test_other_tenant_cannot_read_agent_record() -> None:
    world = AgentWorld([model_says(final("x"))])
    store = InMemoryExecutionStore()
    app = _app(world, store=store)
    created = run(_post(app, {"ask": "hi", "execution_policy": AGENT})).json()
    other_app = _app(world, tenant=uuid4(), store=store)
    assert run(_get(other_app, f"/v1/executions/{created['execution_id']}")).status_code == 404


def test_agent_tools_listing_is_the_offered_catalog() -> None:
    world = AgentWorld([model_says(final("x"))])
    app = _app(world)
    response = run(_get(app, "/v1/agent-tools"))
    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "agent" and body["max_steps"] == 8
    assert [t["name"] for t in body["tools"]] == ["fs", "fs_write"]
    assert body["tools"][0]["arguments"] == {"path": "string"}


def test_agent_tools_listing_absent_without_seam() -> None:
    world = AgentWorld([model_says(final("x"))])
    app = _app(world, with_agent=False)
    assert run(_get(app, "/v1/agent-tools")).status_code == 404


class TestSkillToolIntelligence:
    """R160: admitted skills disclose the tools their manifests REQUIRE."""

    def _registry(self) -> SkillRegistry:
        registry = SkillRegistry()
        registry.register(_skill("repo_reader", ["fs"]))
        registry.register(_skill("deployer", ["fs", "shell"]))
        return registry

    def test_skill_required_tool_is_disclosed_without_allow_list(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("fs", path="README.md")), model_says(final("ok", 1))]
        )
        app = _app(world, skills=self._registry())
        response = run(
            _post(app, {"ask": "read", "execution_policy": AGENT, "skills": ["repo_reader"]})
        )
        assert response.status_code == 200, response.text
        assert world.fs.reads == ["README.md"]  # fs was disclosed AND admitted
        first_ask = world.adapter.requests[0].payload["ask"]
        assert '"name": "fs"' in first_ask and '"name": "fs_write"' not in first_ask
        assert '"by_skill": {"fs": ["repo_reader"]}' in first_ask

    def test_unoffered_required_tool_is_a_named_gap_not_a_grant(self) -> None:
        world = AgentWorld([model_says(final("cannot deploy here"))])
        app = _app(world, skills=self._registry())
        response = run(
            _post(app, {"ask": "deploy", "execution_policy": AGENT, "skills": ["deployer"]})
        )
        assert response.status_code == 200, response.text
        first_ask = world.adapter.requests[0].payload["ask"]
        assert '"unavailable": {"deployer": ["shell"]}' in first_ask
        assert '"name": "fs"' in first_ask  # the offered half IS disclosed

    def test_denied_overrides_skill_disclosure(self) -> None:
        world = AgentWorld([model_says(final("x"))])
        app = _app(world, skills=self._registry())
        response = run(
            _post(
                app,
                {
                    "ask": "read",
                    "execution_policy": AGENT,
                    "skills": ["repo_reader"],
                    "tools": {"allowed": [], "denied": ["fs"]},
                },
            )
        )
        assert response.status_code == 200, response.text
        assert "Available tools:\n[]" in world.adapter.requests[0].payload["ask"]

    def test_skill_disclosure_never_bypasses_the_firewall(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("writer", ["fs_write"]))
        world = AgentWorld(
            [model_says(tool_call("fs_write", path="x", content="y")), model_says(final("done"))]
        )
        app = _app(world, skills=registry)
        response = run(
            _post(app, {"ask": "write", "execution_policy": AGENT, "skills": ["writer"]})
        )
        assert response.status_code == 200
        assert world.fs.writes == []  # disclosed by the skill, REFUSED by the firewall
        assert "refused" in world.adapter.requests[1].payload["ask"]


# --- R165: caller-requested agent budget (execution_policy.max_steps / deadline_ms) ---


def test_requested_max_steps_above_runtime_cap_is_loud_validation_error() -> None:
    world = AgentWorld([model_says(final("x"))], max_steps=4)
    app = _app(world)
    response = run(
        _post(
            app,
            {
                "ask": "hi",
                "execution_policy": {"strategy": "agent", "max_steps": 5},
                "tools": {"allowed": []},
            },
        )
    )
    assert response.status_code == 422, response.text
    err = response.json()["error"]
    assert err["details"]["field"] == "execution_policy.max_steps"
    assert err["details"]["max"] == 4
    # No reasoning call was made — rejected before any admission work.
    assert world.adapter.requests == []


def test_requested_budget_within_cap_is_honoured_and_recorded() -> None:
    world = AgentWorld([model_says(final("x"))], max_steps=8, deadline_ms=60_000)
    store = InMemoryExecutionStore()
    app = _app(world, store=store)
    response = run(
        _post(
            app,
            {
                "ask": "hi",
                "execution_policy": {"strategy": "agent", "max_steps": 2, "deadline_ms": 5_000},
                "tools": {"allowed": []},
            },
        )
    )
    assert response.status_code == 200, response.text
    # The model was told the SMALLER budget it must finalize within.
    first_ask = world.adapter.requests[0].payload["ask"]
    assert '"max_steps": 2' in first_ask
    record = store.get(TENANT, UUID(response.json()["execution_id"]))
    assert record.execution.cost_snapshot["deadline_ms"] == 5_000


def test_requested_deadline_above_runtime_deadline_is_clamped_not_rejected() -> None:
    # Wall-clock is clamped by the runtime (existing rule); steps are the loud one.
    world = AgentWorld([model_says(final("x"))], deadline_ms=1_000)
    store = InMemoryExecutionStore()
    app = _app(world, store=store)
    response = run(
        _post(
            app,
            {
                "ask": "hi",
                "execution_policy": {"strategy": "agent", "deadline_ms": 999_000},
                "tools": {"allowed": []},
            },
        )
    )
    assert response.status_code == 200, response.text
    record = store.get(TENANT, UUID(response.json()["execution_id"]))
    assert record.execution.cost_snapshot["deadline_ms"] == 1_000


def test_execution_policy_budget_fields_are_bounded() -> None:
    from pydantic import ValidationError

    from core.contracts.execute import ExecutionPolicy

    assert ExecutionPolicy.model_validate({"max_steps": 1, "deadline_ms": 1000}).max_steps == 1
    for bad in ({"max_steps": 0}, {"deadline_ms": 999}, {"max_steps": "many"}):
        try:
            ExecutionPolicy.model_validate(bad)
        except ValidationError:
            continue
        raise AssertionError(f"accepted {bad}")
