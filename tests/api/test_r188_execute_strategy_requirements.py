"""R188 API pins — provider/learning closure + agent execution customization.

A5  ``requirements`` (capability-first routing input) rides into routing:
    an unmet capability ⇒ MODEL_UNAVAILABLE naming the exclusion; met ⇒ 200.
A6  Runtime resource signals are composed: a RATE_LIMITED provider is
    excluded from the NEXT decision (same model, other provider continues),
    and when every candidate is cooling the 503 detail carries
    ``retry_after_ms`` (WAIT data, no provider internals).
C3  ``execution_strategy`` — a caller-defined structure executes through
    the ONE router + ONE service: per-stage model policy honoured, stages
    become distinct stored child executions, the parent report is stored
    as strategy=hybrid with one node per stage, review receives the
    subject. AUTO composes a policy-valid plan. Combos (async / agent /
    agent_node_mapping) and unknown templates are refused loudly.
C4  ``GET /v1/models`` rows name their ``providers`` when the provider
    registry seam is bound; the pre-R188 row shape is unchanged otherwise.

Hermetic: scripted adapters, in-memory registries, no network.
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
from core.contracts.execution_strategy import ExecutionStrategySpec
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
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.capacity import ResourceSignalBoard
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


def _model(key: str, *, capabilities: list[str] | None = None) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=capabilities or ["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )


class EchoAdapter:
    """Echoes provider/model/stage facts; optional scripted failure per call."""

    def __init__(self, name: str, *, script: list[object] | None = None) -> None:
        self.name = name
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

    def normalize_error(self, error: object) -> ProviderError:  # pragma: no cover
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code="raised",
            safe_message=str(error),
        )

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, ProviderError):
                return ProviderGenerateResponse(
                    request_id=request.request_id, succeeded=False, error=step, latency_ms=3
                )
        stage = request.payload.get("stage")
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output={
                "content": f"{self.name}:{request.provider_model_name}",
                "provider": self.name,
                "stage": stage,
                "subject": request.payload.get("subject"),
                "previous_output": request.payload.get("previous_output"),
            },
            usage={"units": 1},
            latency_ms=3,
        )


class World:
    """Two providers, both bound to model-x and model-y; one vision model on beta only."""

    def __init__(self, *, scripts: dict[str, list[object]] | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.board = ResourceSignalBoard()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4())
        self.store = InMemoryExecutionStore()
        self.adapters: dict[UUID, EchoAdapter] = {}
        self.by_key: dict[str, Provider] = {}
        scripts = scripts or {}
        for key in ("alpha", "beta"):
            provider = Provider(
                id=uuid4(),
                provider_key=key,
                display_name=key,
                status=ProviderStatus.ACTIVE,
                auth_types=["api_key"],
                supports_account_pool=False,
            )
            self.providers.register(provider, _manifest(key))
            self.by_key[key] = provider
            self.adapters[provider.id] = EchoAdapter(key, script=scripts.get(key))
        self.model_x = _model("model-x")
        self.model_y = _model("model-y")
        self.model_vision = _model("model-vision", capabilities=["vision"])
        for model in (self.model_x, self.model_y, self.model_vision):
            self.models.register(model)
        for provider in self.by_key.values():
            for model in (self.model_x, self.model_y):
                self._bind(provider, model)
        self._bind(self.by_key["beta"], self.model_vision)

    def _bind(self, provider: Provider, model: Model) -> None:
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name=f"{provider.provider_key}/{model.model_key}",
                availability=BindingAvailability.AVAILABLE,
            )
        )

    def adapter(self, key: str) -> EchoAdapter:
        return self.adapters[self.by_key[key].id]

    def app(
        self,
        *,
        with_providers: bool = True,
        templates: dict[str, ExecutionStrategySpec] | None = None,
    ) -> FastAPI:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings, signals=self.board)
        service = ExecutionService(
            adapters=self.adapters,
            credential_refs={pid: f"secret-ref://{pid}" for pid in self.adapters},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
            signals=self.board,
        )
        return create_app(
            router=router,
            execution_service=service,
            store=self.store,
            principal=self.principal,
            models=self.models,
            bindings=self.bindings,
            providers=self.providers if with_providers else None,
            strategy_templates=templates,
            system_info=lambda: {"resource_signals": self.board.snapshot()},
        )


async def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.post("/v1/execute", json=body)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path)


def _explicit(model: str) -> dict[str, Any]:
    return {"type": "explicit_model", "model_id": model}


# --- A5: requirements -------------------------------------------------------------


class TestRequirements:
    def test_unmet_capability_is_a_loud_model_unavailable(self) -> None:
        world = World()
        response = run(
            _post(
                world.app(),
                {"ask": "read this image", "requirements": {"capabilities": ["speech"]}},
            )
        )
        assert response.status_code == 503
        body = response.json()["error"]
        assert body["code"] == "model_unavailable"
        assert body["details"]["excluded"], "exclusions are named, never hidden"

    def test_met_capability_routes_to_the_capable_model_only(self) -> None:
        world = World()
        response = run(
            _post(
                world.app(),
                {"ask": "read this image", "requirements": {"capabilities": ["vision"]}},
            )
        )
        assert response.status_code == 200
        content = response.json()["result"]["content"]
        assert content == "beta:beta/model-vision"


# --- A6: runtime resource signals through the API ---------------------------------


class TestResourceSignals:
    def test_rate_limited_provider_fails_over_and_is_excluded_next_time(self) -> None:
        limited = ProviderError(
            category=ProviderErrorCategory.RATE_LIMITED,
            retryable=True,
            retry_after_ms=30_000,
            provider_code="429",
            safe_message="rate limited",
        )
        world = World()
        # ONE shared script: whichever provider is hit first is rate-limited
        # exactly once; the other serves the same model.
        shared: list[object] = [limited]
        world.adapter("alpha").script = shared
        world.adapter("beta").script = shared
        app = world.app()
        first = run(_post(app, {"ask": "hi", "model_policy": _explicit("model-x")}))
        assert first.status_code == 200, first.text
        # Whichever provider was hit first is now cooling; the same model was
        # served by the other provider (SAME MODEL → DIFFERENT PROVIDER).
        served = first.json()["result"]["content"].split(":")[0]
        cooling = {"alpha", "beta"} - {served}
        second = run(_post(app, {"ask": "again", "model_policy": _explicit("model-x")}))
        assert second.status_code == 200
        assert second.json()["result"]["content"].startswith(served)
        (cooling_key,) = cooling
        assert len(world.adapter(cooling_key).requests) == 1, "cooling provider not re-hit"
        snapshot = world.board.snapshot()
        states = {row["provider_id"]: row["state"] for row in snapshot}
        assert states[str(world.by_key[cooling_key].id)] == "cooldown"

    def test_all_cooling_returns_retry_after_ms_wait_data(self) -> None:
        world = World()
        for key in ("alpha", "beta"):
            world.board.record_error(
                provider_id=world.by_key[key].id,
                model_id=world.model_x.id,
                error=ProviderError(
                    category=ProviderErrorCategory.RATE_LIMITED,
                    retryable=True,
                    retry_after_ms=12_000,
                    provider_code="429",
                    safe_message="rate limited",
                ),
            )
        response = run(_post(world.app(), {"ask": "hi", "model_policy": _explicit("model-x")}))
        assert response.status_code == 503
        details = response.json()["error"]["details"]
        assert 0 < details["retry_after_ms"] <= 12_000, "WAIT data = time remaining"
        assert "429" not in response.text, "provider codes never cross the API boundary"

    def test_admin_system_info_carries_resource_signals(self) -> None:
        world = World()
        world.board.record_attempt(
            provider_id=world.by_key["alpha"].id, model_id=world.model_x.id, limits={"rpm": 5}
        )
        rows = world.board.snapshot()
        (row,) = rows
        assert set(row) == {
            "provider_id",
            "model_id",
            "state",
            "reason",
            "cooldown_until",
            "rpm_used",
            "rpm_limit",
            "last_category",
        }
        assert row["rpm_used"] == 1 and row["rpm_limit"] == 5


# --- C3: execution_strategy -------------------------------------------------------


DIAMOND: dict[str, Any] = {
    "mode": "custom",
    "max_parallel": 2,
    "stages": [
        {"key": "discover", "role": "analyst", "instruction": "list the facts"},
        {
            "key": "analysis_a",
            "model_policy": _explicit("model-x"),
            "depends_on": ["discover"],
        },
        {
            "key": "analysis_b",
            "model_policy": _explicit("model-y"),
            "depends_on": ["discover"],
        },
        {
            "key": "review",
            "kind": "review",
            "role": "reviewer",
            "depends_on": ["analysis_a", "analysis_b"],
        },
    ],
}


class TestExecutionStrategy:
    def test_custom_dag_executes_through_core_with_per_stage_models(self) -> None:
        world = World()
        app = world.app()
        response = run(_post(app, {"ask": "plan the migration", "execution_strategy": DIAMOND}))
        assert response.status_code == 200, response.text
        body = response.json()
        # Final output is the review stage; it saw both analyses as subject.
        assert body["result"]["content"]
        parent = run(_get(app, f"/v1/executions/{body['execution_id']}"))
        assert parent.status_code == 200
        stored = world.store.get(world.principal.tenant_id, UUID(body["execution_id"]))
        assert stored is not None
        assert stored.execution.strategy.value == "hybrid"
        assert [n.node.node_key for n in stored.nodes] == [
            "discover",
            "analysis_a",
            "analysis_b",
            "review",
        ]
        assert all(n.node.status.value == "succeeded" for n in stored.nodes)
        child_ids = stored.execution.cost_snapshot["child_execution_ids"]
        assert len(set(child_ids)) == 4
        for child_id in child_ids:
            child = world.store.get(world.principal.tenant_id, UUID(child_id))
            assert child is not None, "every stage is its own stored child execution"
        # Per-stage model policy honoured: analysis_a ran model-x, analysis_b model-y.
        by_stage = {
            req.payload["stage"]["key"]: req.provider_model_name.split("/")[1]
            for adapter in world.adapters.values()
            for req in adapter.requests
        }
        assert by_stage["analysis_a"] == "model-x"
        assert by_stage["analysis_b"] == "model-y"
        review_req = next(
            req
            for adapter in world.adapters.values()
            for req in adapter.requests
            if req.payload["stage"]["key"] == "review"
        )
        assert set(review_req.payload["subject"]) == {"analysis_a", "analysis_b"}
        assert review_req.payload["stage"]["role"] == "reviewer"

    def test_failed_stage_skips_dependents_and_fails_loudly(self) -> None:
        boom = ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code="500",
            safe_message="upstream failed",
        )
        world = World()
        # Single provider serving the failing stage: pin model-x to alpha by
        # cooling beta for model-x so the failure is deterministic.
        world.board.record_error(
            provider_id=world.by_key["beta"].id,
            model_id=world.model_x.id,
            error=ProviderError(
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                retry_after_ms=60_000,
                provider_code="429",
                safe_message="rate limited",
            ),
        )
        spec = {
            "mode": "custom",
            "stages": [
                {"key": "a", "model_policy": _explicit("model-x")},
                {"key": "b", "depends_on": ["a"]},
            ],
        }
        world.adapter("alpha").script = [boom]
        response = run(_post(world.app(), {"ask": "x", "execution_strategy": spec}))
        assert response.status_code != 200
        assert "500" not in response.text
        executions = [
            r
            for r in world.store.list(world.principal.tenant_id)
            if r.execution.strategy.value == "hybrid"
        ]
        (parent,) = executions
        statuses = {n.node.node_key: n.node.status.value for n in parent.nodes}
        assert statuses == {"a": "failed", "b": "skipped"}
        assert parent.execution.status.value == "failed"

    def test_auto_mode_composes_a_policy_valid_plan(self) -> None:
        world = World()
        response = run(
            _post(
                world.app(),
                {
                    "ask": "hi",
                    "model_policy": _explicit("model-y"),
                    "execution_strategy": {"mode": "auto"},
                },
            )
        )
        assert response.status_code == 200, response.text
        content = response.json()["result"]["content"]
        assert content.endswith("/model-y"), "request policy carried into AUTO plan"
        stored = world.store.get(world.principal.tenant_id, UUID(response.json()["execution_id"]))
        assert stored is not None
        assert [n.node.node_key for n in stored.nodes] == ["generate"]

    def test_template_resolves_or_refuses(self) -> None:
        world = World()
        template = ExecutionStrategySpec.model_validate(DIAMOND)
        app = world.app(templates={"diamond": template})
        ok = run(
            _post(
                app,
                {"ask": "x", "execution_strategy": {"mode": "template", "template_id": "diamond"}},
            )
        )
        assert ok.status_code == 200, ok.text
        missing = run(
            _post(
                app, {"ask": "x", "execution_strategy": {"mode": "template", "template_id": "nope"}}
            )
        )
        assert missing.status_code == 422
        error = missing.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"]["field"] == "execution_strategy.template_id"

    def test_async_and_agent_combos_are_refused_loudly(self) -> None:
        world = World()
        app = world.app()
        spec = {"mode": "custom", "stages": [{"key": "a"}]}
        async_response = run(
            _post(
                app,
                {"ask": "x", "execution_strategy": spec, "execution_policy": {"async": True}},
            )
        )
        assert async_response.status_code == 422
        assert async_response.json()["error"]["code"] == "validation_error"
        mapping = run(
            _post(
                app,
                {
                    "ask": "x",
                    "execution_strategy": spec,
                    "model_policy": {
                        "type": "agent_node_mapping",
                        "node_model_policies": {"planner": _explicit("model-x")},
                    },
                },
            )
        )
        assert mapping.status_code == 422
        assert mapping.json()["error"]["details"]["field"] == "execution_strategy"

    def test_malformed_spec_is_a_contract_refusal(self) -> None:
        world = World()
        bad = {"mode": "custom", "stages": [{"key": "a", "depends_on": ["a"]}]}
        response = run(_post(world.app(), {"ask": "x", "execution_strategy": bad}))
        assert response.status_code in (400, 422)
        assert response.status_code != 200


# --- C4: /v1/models providers ------------------------------------------------------


class TestModelsProviders:
    def test_rows_name_their_providers_when_seam_bound(self) -> None:
        world = World()
        response = run(_get(world.app(), "/v1/models"))
        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["models"]}
        assert rows["model-x"]["providers"] == ["alpha", "beta"]
        assert rows["model-vision"]["providers"] == ["beta"]

    def test_row_shape_unchanged_without_provider_seam(self) -> None:
        world = World()
        response = run(_get(world.app(with_providers=False), "/v1/models"))
        assert response.status_code == 200
        for row in response.json()["models"]:
            assert "providers" not in row
