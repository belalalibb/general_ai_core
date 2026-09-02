"""PR12 final slice — REAL agent_node_mapping + AUTO skill resolution.

Slice A pins (10 §13.5 over the EXISTING pipeline orchestration):
- a mapping with declared node policies runs a REAL straight node
  sequence: one ExecutionNode record per node, declaration order,
  per-node model selection through the EXISTING Router;
- Planner→model-alpha / Executor→model-beta actually BOTH execute;
- agent default (rule 2) fills unmapped... nodes route their own policy
  (rule 1); the node trail is exposed honestly (stored report + GET);
- a failing node fails the run and skips the rest (recorded, not hidden);
- mapping WITHOUT node policies keeps prior single-node behavior;
- async path refuses the multi-node mapping loudly (no silent downgrade);
- per-node routing refusals name the node.

Slice B pins (41 §16 AUTO selection through the EXISTING SkillResolver):
- no explicit skills + admitted role ⇒ resolver selects an eligible
  ACTIVE skill automatically and it rides the payload as id/name/version
  DATA (same shape as the explicit path);
- explicit skills WIN — the resolver never overrides them;
- role-incompatible skills are not auto-selected;
- non-selectable (non-ACTIVE) skills are never candidates;
- auto-selection grants NO tool permission (skills stay data-only);
- no role ⇒ no auto selection (prior behavior preserved).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import InMemoryExecutionStore, Principal, create_app
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderManifest,
)
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillRuntime,
    SkillSource,
    SkillStatus,
    SkillToolRequirements,
    SkillType,
)
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.roles.registry import RoleRegistry, SkillRegistry
from core.routing.router import SimpleScoringRouter


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    del seconds


def _manifest(provider_key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": provider_key,
            "name": provider_key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )


def make_role(name: str = "senior_software_architect") -> Role:
    return Role(
        id=uuid4(),
        scope=RoleScope.SYSTEM,
        name=name,
        version="1.0.0",
        objective="Design and review software architecture.",
        status=RoleStatus.ACTIVE,
    )


def make_skill(
    *,
    manifest_id: str = "code_review",
    status: SkillStatus = SkillStatus.ACTIVE,
    compatible_roles: list[str] | None = None,
    required_tools: list[str] | None = None,
) -> Skill:
    manifest = SkillManifest(
        id=manifest_id,
        name=manifest_id,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        status=status,
        requires_tools=SkillToolRequirements(required=required_tools or []),
        runtime=SkillRuntime(compatible_roles=compatible_roles or []),
    )
    return Skill(
        id=uuid4(),
        name=manifest_id,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=SkillSource.LOCAL,
        manifest=manifest,
        status=status,
    )


class FakeAdapter:
    """Scripted adapter: ProviderError => fail, dict => succeed."""

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"content": "answer"}
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=step,
                latency_ms=7,
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=7,
        )


class World:
    """Hermetic API world with TWO models bound to one provider."""

    def __init__(self, *, script: list[object] | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4())
        self.store = InMemoryExecutionStore()
        self.skills = SkillRegistry()
        self.roles = RoleRegistry()
        self.provider = Provider(
            id=uuid4(),
            provider_key="prov_a",
            display_name="prov_a",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(self.provider, _manifest("prov_a"))
        self.model_alpha = _model("model-alpha")
        self.model_beta = _model("model-beta")
        for model in (self.model_alpha, self.model_beta):
            self.models.register(model)
            self.bindings.register(
                ProviderModelBinding(
                    provider_id=self.provider.id,
                    model_id=model.id,
                    provider_model_name=f"vendor/{model.model_key}",
                    availability=BindingAvailability.AVAILABLE,
                )
            )
        self.adapter = FakeAdapter(script)

    def app(self) -> FastAPI:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        service = ExecutionService(
            adapters={self.provider.id: self.adapter},
            credential_refs={self.provider.id: f"secret-ref://{self.provider.id}"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
        )
        return create_app(
            router=router,
            execution_service=service,
            store=self.store,
            principal=self.principal,
            skills=self.skills,
            roles=self.roles,
        )


async def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/v1/execute", json=body)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


def _mapping_body(ask: str = "plan then build") -> dict[str, Any]:
    return {
        "ask": ask,
        "model_policy": {
            "type": "agent_node_mapping",
            "node_model_policies": {
                "planner": {"type": "explicit_model", "model_id": "model-alpha"},
                "executor": {"type": "explicit_model", "model_id": "model-beta"},
            },
        },
    }


# --- Slice A: real node-mapping execution -------------------------------------------


class TestNodeMappingExecution:
    def test_two_nodes_execute_in_order_with_their_own_models(self) -> None:
        world = World(script=[{"content": "the plan"}, {"content": "the build"}])
        response = run(_post(world.app(), _mapping_body()))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "succeeded"
        # Both nodes ACTUALLY executed — two provider calls, each with the
        # node's OWN model (per-node selection preserved end to end).
        assert [r.provider_model_name for r in world.adapter.requests] == [
            "vendor/model-alpha",
            "vendor/model-beta",
        ]
        # The final output is the LAST node's output (pipeline semantics).
        assert body["result"]["content"] == "the build"

    def test_node_trail_is_exposed_honestly(self) -> None:
        world = World(script=[{"content": "a"}, {"content": "b"}])
        response = run(_post(world.app(), _mapping_body()))
        execution_id = response.json()["execution_id"]
        # Stored report: two DISTINCT ExecutionNode records, declaration
        # order, both terminal-succeeded, strategy recorded as pipeline.
        report = world.store.get(world.principal.tenant_id, UUID(execution_id))
        assert report.execution.strategy.value == "pipeline"
        assert [n.node.node_key for n in report.nodes] == ["planner", "executor"]
        assert len({n.node.id for n in report.nodes}) == 2
        assert all(n.node.status.value == "succeeded" for n in report.nodes)
        assert all(n.node.execution_id == UUID(execution_id) for n in report.nodes)
        # GET /v1/executions/{id}: the trail feeds progress honestly.
        status = run(_get(world.app(), f"/v1/executions/{execution_id}")).json()
        assert status["progress"]["percent"] == 100
        assert status["progress"]["current_stage"] == "executor"

    def test_previous_node_output_threads_forward(self) -> None:
        world = World(script=[{"content": "the plan"}, {"content": "done"}])
        run(_post(world.app(), _mapping_body()))
        second_payload = world.adapter.requests[1].payload
        assert second_payload["previous_output"] == {"content": "the plan"}

    def test_agent_default_fills_unmapped_resolution_gap(self) -> None:
        # Rule 2: a node whose policy is present routes it (rule 1); the
        # default policy exists but the declared node wins over it.
        world = World(script=[{"content": "x"}, {"content": "y"}])
        body = _mapping_body()
        body["model_policy"]["default_model_policy"] = {
            "type": "explicit_model",
            "model_id": "model-alpha",
        }
        response = run(_post(world.app(), body))
        assert response.status_code == 200
        assert [r.provider_model_name for r in world.adapter.requests] == [
            "vendor/model-alpha",  # planner's own policy (rule 1)
            "vendor/model-beta",  # executor's own policy (rule 1)
        ]

    def test_failed_node_fails_run_and_skips_rest(self) -> None:
        world = World(
            script=[
                ProviderError(
                    category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
                    retryable=False,
                    safe_message="fake non_retryable_error",
                )
            ]
        )
        response = run(_post(world.app(), _mapping_body()))
        assert response.status_code == 502
        execution_id = response.json()["error"]["details"]["execution_id"]
        report = world.store.get(world.principal.tenant_id, UUID(execution_id))
        assert [n.node.status.value for n in report.nodes] == ["failed", "skipped"]
        # Only the failed node reached a provider — nothing ran after it.
        assert len(world.adapter.requests) == 1

    def test_mapping_without_node_policies_keeps_single_node_behavior(self) -> None:
        world = World(script=[{"content": "solo"}])
        response = run(
            _post(
                world.app(),
                {
                    "ask": "hi",
                    "model_policy": {
                        "type": "agent_node_mapping",
                        "default_model_policy": {
                            "type": "explicit_model",
                            "model_id": "model-beta",
                        },
                    },
                },
            )
        )
        assert response.status_code == 200
        execution_id = response.json()["execution_id"]
        report = world.store.get(world.principal.tenant_id, UUID(execution_id))
        assert report.execution.strategy.value == "single"
        assert [n.node.node_key for n in report.nodes] == ["single"]
        assert world.adapter.requests[0].provider_model_name == "vendor/model-beta"

    def test_async_path_refuses_multi_node_mapping_loudly(self) -> None:
        world = World()
        body = _mapping_body()
        body["policy"] = {"async": True}
        response = run(_post(world.app(), body))
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert world.adapter.requests == []

    def test_per_node_routing_refusal_names_the_node(self) -> None:
        world = World()
        body = {
            "ask": "hi",
            "model_policy": {
                "type": "agent_node_mapping",
                "node_model_policies": {
                    "planner": {"type": "explicit_model", "model_id": "model-alpha"},
                    "executor": {"type": "explicit_model", "model_id": "ghost"},
                },
            },
        }
        response = run(_post(world.app(), body))
        assert response.status_code == 503
        payload = response.json()
        assert payload["error"]["code"] == "model_unavailable"
        assert payload["error"]["details"]["node"] == "executor"
        assert world.adapter.requests == []  # refused BEFORE any execution


# --- Slice B: AUTO skill resolution ---------------------------------------------------


class TestAutoSkillResolution:
    def test_auto_selects_eligible_skill_when_none_requested(self) -> None:
        world = World()
        world.roles.register(make_role())
        world.skills.register(make_skill(manifest_id="code_review"))
        response = run(
            _post(
                world.app(),
                {
                    "ask": "review this",
                    "role": {"type": "system", "id": "senior_software_architect"},
                },
            )
        )
        assert response.status_code == 200
        sent = world.adapter.requests[0].payload
        assert sent["skills"] == [{"id": "code_review", "name": "code_review", "version": "1.0.0"}]

    def test_explicit_selection_wins_over_auto(self) -> None:
        world = World()
        world.roles.register(make_role())
        world.skills.register(make_skill(manifest_id="code_review"))
        world.skills.register(make_skill(manifest_id="doc_writer"))
        response = run(
            _post(
                world.app(),
                {
                    "ask": "review this",
                    "role": {"type": "system", "id": "senior_software_architect"},
                    "skills": ["doc_writer"],
                },
            )
        )
        assert response.status_code == 200
        sent = world.adapter.requests[0].payload
        # EXACTLY the explicit selection — the resolver never overrode it.
        assert sent["skills"] == [{"id": "doc_writer", "name": "doc_writer", "version": "1.0.0"}]

    def test_role_incompatible_skill_is_not_auto_selected(self) -> None:
        world = World()
        world.roles.register(make_role())
        world.skills.register(make_skill(manifest_id="legal_only", compatible_roles=["lawyer"]))
        response = run(
            _post(
                world.app(),
                {
                    "ask": "hi",
                    "role": {"type": "system", "id": "senior_software_architect"},
                },
            )
        )
        assert response.status_code == 200
        assert "skills" not in world.adapter.requests[0].payload

    def test_non_selectable_skill_is_never_an_auto_candidate(self) -> None:
        world = World()
        world.roles.register(make_role())
        world.skills.register(make_skill(manifest_id="pending", status=SkillStatus.REVIEWED))
        response = run(
            _post(
                world.app(),
                {
                    "ask": "hi",
                    "role": {"type": "system", "id": "senior_software_architect"},
                },
            )
        )
        assert response.status_code == 200
        assert "skills" not in world.adapter.requests[0].payload

    def test_auto_selected_skill_grants_no_tool_permission(self) -> None:
        # 03 §8: a skill REQUESTING a tool changes nothing about grants —
        # the payload carries id/name/version DATA only; no tool names, no
        # permission objects ride to the provider.
        world = World()
        world.roles.register(make_role())
        world.skills.register(make_skill(manifest_id="tooly", required_tools=["web_search"]))
        response = run(
            _post(
                world.app(),
                {
                    "ask": "hi",
                    "role": {"type": "system", "id": "senior_software_architect"},
                },
            )
        )
        assert response.status_code == 200
        sent = world.adapter.requests[0].payload
        assert sent["skills"] == [{"id": "tooly", "name": "tooly", "version": "1.0.0"}]
        assert "web_search" not in str(sent["skills"])
        assert "tools" not in sent

    def test_no_role_means_no_auto_selection(self) -> None:
        world = World()
        world.skills.register(make_skill(manifest_id="code_review"))
        response = run(_post(world.app(), {"ask": "hi"}))
        assert response.status_code == 200
        assert "skills" not in world.adapter.requests[0].payload
