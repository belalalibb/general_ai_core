"""Admin + evaluation API surface semantics (T-IMPL-032; 41 §46; 21 §3-§7; 22 §7).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers:

- ADMIN GATE (R049 boundary (e)): every /v1/admin/* route denies 403
  ``unauthorized`` without ``Principal.is_admin`` — including BEFORE
  parameter parsing (no resource-id probing); an absent AdminSurface
  means NO admin route exists at all (strongest deny-by-default).
- CONFIG LIFECYCLE over HTTP: draft→validate→preview→publish→rollback in
  21 §3 order; out-of-order = 409; unknown change id = 404; unknown
  action string = 422; a published change visibly mutates the LIVE
  routing registries (no parallel admin state).
- READ VIEWS (21 §5): models INCLUDING disabled; providers INCLUDING
  marked templates; tenant plan via the usage seam (unconfigured = 404,
  never invented); current routing weights reflect published changes.
- EVALUATION READS (22 §7): records with score/confidence/evidence are
  admin-readable; foreign-tenant records unaddressable (404 / empty —
  20 §6 anti-enumeration); /v1/execute success bodies carry NO
  evaluation fields (22 §7 user-visibility split).
- LEARNING DASHBOARD PLACEHOLDER (21 §7; R049 boundary (a)): honest
  zeros/empties with ``placeholder: true`` — no fabricated metrics.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import Principal, create_app
from apps.api.admin import AdminSurface
from core.admin.service import AdminConfigService
from core.audit.memory import InMemoryAuditLog
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.evaluation.memory import InMemoryEvaluationStore
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- fixtures (registry shapes reused from tests/api + tests/admin) -------------------


def _manifest(provider_key: str, **overrides: object) -> ProviderManifest:
    payload: dict[str, object] = {
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
    payload.update(overrides)
    return ProviderManifest.model_validate(payload)


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(key: str, status: ModelStatus = ModelStatus.ACTIVE) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=status,
    )


class FakeAdapter:
    """Always-succeeding ProviderAdapterPort fake (execute-path test only)."""

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
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output={"content": "ok"},
            usage={"units": 1},
            latency_ms=5,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="fake",
        )


async def _no_sleep(seconds: float) -> None:
    return None


class World:
    """Live registries + admin service + evaluation store + composed app."""

    def __init__(self, *, is_admin: bool = True) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.usage = InMemoryUsageAccounting()
        self.audit = InMemoryAuditLog()
        self.evaluations = InMemoryEvaluationStore()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=is_admin)
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
        )

        self.provider = _provider("prov_a")
        self.providers.register(self.provider, _manifest("prov_a"))
        self.model = _model("model-a")
        self.models.register(self.model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=self.provider.id,
                model_id=self.model.id,
                provider_model_name="vendor/model-a",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        self.adapter = FakeAdapter()

    def surface(self) -> AdminSurface:
        # Same instances the AdminConfigService publishes into — the
        # composition-root agreement the AdminSurface docstring demands.
        return AdminSurface(
            service=self.admin,
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            evaluations=self.evaluations,
        )

    def app(self, *, with_admin: bool = True) -> FastAPI:
        service = ExecutionService(
            adapters={self.provider.id: self.adapter},
            credential_refs={self.provider.id: f"secret-ref://{self.provider.id}"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            usage=self.usage,
            sleeper=_no_sleep,
        )
        return create_app(
            router=self.router,
            execution_service=service,
            principal=self.principal,
            admin=self.surface() if with_admin else None,
        )


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


async def _post(app: FastAPI, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(path, json=body if body is not None else {})


def _assert_unified_error(body: dict[str, Any], code: str) -> None:
    """Every non-success body is the unified envelope (10 §9)."""
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["retryable"], bool)


def _record(tenant_id: UUID, execution_id: UUID | None = None) -> EvaluationRecord:
    return EvaluationRecord(
        tenant_id=tenant_id,
        execution_id=execution_id or uuid4(),
        level=VerificationLevel.EVALUATED,
        score=0.9,
        confidence=0.8,
        evidence_ref="evidence://grader-log/1",
        graders=(GraderResult(type=GraderType.DETERMINISTIC, name="json_valid", passed=True),),
    )


# --- admin gate: deny-by-default (R049 boundary (e); 20 §4) ---------------------------


class TestAdminGate:
    def test_non_admin_denied_on_every_admin_route(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        gets = [
            "/v1/admin/changes",
            f"/v1/admin/changes/{uuid4()}",
            "/v1/admin/models",
            "/v1/admin/providers",
            f"/v1/admin/plans/{uuid4()}",
            "/v1/admin/routing/weights",
            f"/v1/admin/evaluations/{uuid4()}",
            f"/v1/admin/executions/{uuid4()}/evaluations",
            "/v1/admin/learning/dashboard",
        ]
        for path in gets:
            response = run(_get(app, path))
            assert response.status_code == 403, path
            _assert_unified_error(response.json(), "unauthorized")
        posts = [
            ("/v1/admin/changes", {"action": "disable_model", "payload": {}}),
            (f"/v1/admin/changes/{uuid4()}/validate", None),
            (f"/v1/admin/changes/{uuid4()}/preview", None),
            (f"/v1/admin/changes/{uuid4()}/publish", None),
            (f"/v1/admin/changes/{uuid4()}/rollback", None),
        ]
        for path, body in posts:
            response = run(_post(app, path, body))
            assert response.status_code == 403, path
            _assert_unified_error(response.json(), "unauthorized")

    def test_gate_runs_before_parameter_parsing(self) -> None:
        # A non-admin probing with a NON-UUID id still gets 403, not 422:
        # the gate must not leak parameter-validity information (20 §6).
        world = World(is_admin=False)
        app = world.app()
        response = run(_get(app, "/v1/admin/changes/not-a-uuid"))
        assert response.status_code == 403
        _assert_unified_error(response.json(), "unauthorized")

    def test_absent_surface_means_no_admin_route_at_all(self) -> None:
        # Strongest deny-by-default: without an injected AdminSurface the
        # route does not exist — even for an admin principal.
        world = World(is_admin=True)
        app = world.app(with_admin=False)
        response = run(_get(app, "/v1/admin/models"))
        assert response.status_code == 404


# --- config lifecycle over HTTP (21 §3) ------------------------------------------------


def _draft(app: FastAPI, action: str, payload: dict[str, Any]) -> str:
    response = run(_post(app, "/v1/admin/changes", {"action": action, "payload": payload}))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "draft"
    return str(body["id"])


def _step(app: FastAPI, change_id: str, step: str) -> httpx.Response:
    return run(_post(app, f"/v1/admin/changes/{change_id}/{step}"))


class TestConfigLifecycle:
    def test_full_lifecycle_disables_model_in_live_registry(self) -> None:
        world = World()
        app = world.app()
        change_id = _draft(app, "disable_model", {"model_key": "model-a"})

        validated = _step(app, change_id, "validate")
        assert validated.status_code == 200
        assert validated.json()["state"] == "validated"

        previewed = _step(app, change_id, "preview")
        assert previewed.status_code == 200
        assert previewed.json()["impact_preview"]

        published = _step(app, change_id, "publish")
        assert published.status_code == 200
        body = published.json()
        assert body["state"] == "published"
        assert body["published_version"]
        # No parallel state: the LIVE routing registry changed.
        assert world.models.active_models() == []

        rolled = _step(app, change_id, "rollback")
        assert rolled.status_code == 200
        assert rolled.json()["state"] == "rolled_back"
        assert [m.model_key for m in world.models.active_models()] == ["model-a"]

    def test_out_of_order_transition_is_409(self) -> None:
        world = World()
        app = world.app()
        change_id = _draft(app, "disable_model", {"model_key": "model-a"})
        # publish straight from draft: 21 §3 order violation -> 409.
        response = _step(app, change_id, "publish")
        assert response.status_code == 409
        _assert_unified_error(response.json(), "validation_error")

    def test_unknown_change_id_is_404(self) -> None:
        world = World()
        app = world.app()
        response = run(_get(app, f"/v1/admin/changes/{uuid4()}"))
        assert response.status_code == 404
        _assert_unified_error(response.json(), "validation_error")

    def test_malformed_change_id_is_422_for_admins(self) -> None:
        world = World()
        app = world.app()
        response = run(_get(app, "/v1/admin/changes/not-a-uuid"))
        assert response.status_code == 422
        _assert_unified_error(response.json(), "validation_error")

    def test_unknown_action_is_422(self) -> None:
        world = World()
        app = world.app()
        response = run(
            _post(app, "/v1/admin/changes", {"action": "drop_all_tenants", "payload": {}})
        )
        assert response.status_code == 422
        _assert_unified_error(response.json(), "validation_error")

    def test_list_changes_shows_lifecycle_records(self) -> None:
        world = World()
        app = world.app()
        change_id = _draft(app, "disable_model", {"model_key": "model-a"})
        response = run(_get(app, "/v1/admin/changes"))
        assert response.status_code == 200
        changes = response.json()["changes"]
        assert [c["id"] for c in changes] == [change_id]

    def test_validation_failure_surfaces_as_rejected_record(self) -> None:
        world = World()
        app = world.app()
        change_id = _draft(app, "disable_model", {"model_key": "no-such-model"})
        response = _step(app, change_id, "validate")
        # Validation ran and REJECTED the draft — a successful lifecycle
        # step returning the terminal record, not an HTTP error.
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "rejected"
        assert body["validation_result"].startswith("rejected")


# --- read views (21 §5) ------------------------------------------------------------------


class TestReadViews:
    def test_models_view_includes_disabled(self) -> None:
        world = World()
        world.models.register(_model("model-off", status=ModelStatus.DISABLED))
        app = world.app()
        response = run(_get(app, "/v1/admin/models"))
        assert response.status_code == 200
        by_key = {m["model_key"]: m for m in response.json()["models"]}
        assert set(by_key) == {"model-a", "model-off"}
        assert by_key["model-off"]["status"] == "disabled"
        # Routing pool unchanged: the DISABLED model is admin-visible only.
        assert [m.model_key for m in world.models.active_models()] == ["model-a"]

    def test_providers_view_marks_templates(self) -> None:
        world = World()
        template = _provider("tmpl", status=ProviderStatus.DISABLED)
        world.providers.register(
            template,
            _manifest(
                "tmpl",
                status="template_disabled",
                is_template=True,
                is_functional=False,
                real_provider_required=True,
                auth={"types": [], "supports_refresh": False},
            ),
        )
        app = world.app()
        response = run(_get(app, "/v1/admin/providers"))
        assert response.status_code == 200
        by_key = {p["provider_key"]: p for p in response.json()["providers"]}
        assert by_key["tmpl"]["is_template"] is True
        assert by_key["tmpl"]["is_routable"] is False
        assert by_key["prov_a"]["is_template"] is False
        assert by_key["prov_a"]["is_routable"] is True

    def test_plan_view_reads_the_usage_seam(self) -> None:
        world = World()
        target = uuid4()
        world.usage.configure_tenant(target, plan="pro", task_units_limit=100.0)
        app = world.app()
        response = run(_get(app, f"/v1/admin/plans/{target}"))
        assert response.status_code == 200
        body = response.json()
        assert body["plan"] == "pro"
        assert body["task_units"]["limit"] == 100.0

    def test_unconfigured_plan_is_404_not_invented(self) -> None:
        world = World()
        app = world.app()
        response = run(_get(app, f"/v1/admin/plans/{uuid4()}"))
        assert response.status_code == 404
        _assert_unified_error(response.json(), "validation_error")

    def test_routing_weights_view_reflects_published_change(self) -> None:
        world = World()
        app = world.app()
        before = run(_get(app, "/v1/admin/routing/weights"))
        assert before.status_code == 200
        assert before.json()["quality"] == 0.35  # 11 §6 initial value
        weights = {
            "version": "test-v2",
            "quality": 0.7,
            "reliability": 0.1,
            "cost": 0.1,
            "latency": 0.05,
            "context_fit": 0.03,
            "policy_preference": 0.02,
        }
        change_id = _draft(app, "set_routing_weights", {"weights": weights})
        assert _step(app, change_id, "validate").json()["state"] == "validated"
        assert _step(app, change_id, "preview").status_code == 200
        assert _step(app, change_id, "publish").json()["state"] == "published"
        after = run(_get(app, "/v1/admin/routing/weights"))
        assert after.json()["quality"] == 0.7
        assert after.json()["version"] == "test-v2"


# --- evaluation reads (22 §7 admin visibility; 20 §6 anti-enumeration) ------------------


class TestEvaluationReads:
    def test_admin_reads_scores_confidence_evidence(self) -> None:
        world = World()
        record = _record(world.principal.tenant_id)
        world.evaluations.record(record)
        app = world.app()
        response = run(_get(app, f"/v1/admin/evaluations/{record.id}"))
        assert response.status_code == 200
        body = response.json()
        # 22 §7: ADMIN sees score/confidence/evidence — verbatim record.
        assert body["score"] == 0.9
        assert body["confidence"] == 0.8
        assert body["evidence_ref"] == "evidence://grader-log/1"
        assert body["graders"][0]["name"] == "json_valid"
        assert body["level"] == "EVALUATED"

    def test_execution_evaluations_listed_in_order(self) -> None:
        world = World()
        execution_id = uuid4()
        first = _record(world.principal.tenant_id, execution_id)
        second = _record(world.principal.tenant_id, execution_id)
        world.evaluations.record(first)
        world.evaluations.record(second)
        app = world.app()
        response = run(_get(app, f"/v1/admin/executions/{execution_id}/evaluations"))
        assert response.status_code == 200
        ids = [e["id"] for e in response.json()["evaluations"]]
        assert ids == [str(first.id), str(second.id)]

    def test_foreign_tenant_record_unaddressable(self) -> None:
        world = World()
        foreign = _record(uuid4())  # another tenant's record
        world.evaluations.record(foreign)
        app = world.app()
        response = run(_get(app, f"/v1/admin/evaluations/{foreign.id}"))
        assert response.status_code == 404  # identical to absent (20 §6)
        _assert_unified_error(response.json(), "validation_error")

    def test_unknown_execution_lists_empty_not_error(self) -> None:
        world = World()
        app = world.app()
        response = run(_get(app, f"/v1/admin/executions/{uuid4()}/evaluations"))
        assert response.status_code == 200
        assert response.json() == {"evaluations": []}

    def test_execute_response_carries_no_evaluation_fields(self) -> None:
        # 22 §7 user-visibility split: the user surface NEVER carries
        # scores/confidence/evidence — even with records in the store.
        world = World()
        world.evaluations.record(_record(world.principal.tenant_id))
        world.usage.configure_tenant(world.principal.tenant_id, plan="pro", task_units_limit=100.0)
        app = world.app()
        response = run(_post(app, "/v1/execute", {"ask": "hi"}))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "succeeded"
        for banned in ("evaluation", "score", "confidence", "evidence_ref", "graders"):
            assert banned not in body, banned


# --- learning dashboard placeholder (21 §7; R049 boundary (a)) ---------------------------


class TestLearningDashboardPlaceholder:
    def test_values_are_honest_zeros_with_placeholder_marker(self) -> None:
        world = World()
        app = world.app()
        response = run(_get(app, "/v1/admin/learning/dashboard"))
        assert response.status_code == 200
        body = response.json()
        assert body["placeholder"] is True
        assert body["verified_samples"] == 0
        assert body["gold_samples"] == 0
        assert body["dataset_coverage"] == {}
        assert body["task_coverage"] == {}
        assert body["specialist_models"] == []
        assert body["accuracy_trends"] == []
        assert body["promotion_history"] == []
        assert body["rollback_actions"] == []
        # Unknown metrics are ABSENT (exclude_none), never fabricated.
        for absent in ("cost_reduction", "teacher_agreement", "canary_status"):
            assert absent not in body

    def test_dashboard_gate_denies_non_admin(self) -> None:
        world = World(is_admin=False)
        app = world.app()
        response = run(_get(app, "/v1/admin/learning/dashboard"))
        assert response.status_code == 403
        _assert_unified_error(response.json(), "unauthorized")
