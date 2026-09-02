"""Gap 1c — POST /v1/admin/providers/onboard + composition derivations.

Hermetic pins over the new admin route and the ADR-0011 composition
helpers (manifest/adapter re-derivation, gateway hydration):

- deny-by-default admission: anonymous and non-admin callers refused;
- happy path returns the walker's report verbatim (201), provider is
  registered DISABLED, executability maps populated, enable stays a
  PREPARED draft (never enabled here);
- walker refusals surface verbatim as 409; unknown operations/capability
  keys refuse as 422 BEFORE any provider I/O;
- OPEN-2: v1-excluded operations cannot be declared (422);
- persist_registration receives EXACTLY the request definition (refs
  only — no secret value anywhere in the row);
- manifest_from_definition is deterministic (one derivation, two
  consumers) and hydrate_gateway_providers rebuilds registries + maps
  from persisted rows; without gateway settings the DATA hydrates but
  adapters stay honestly absent.

Async driven by asyncio.run (ADR-0001; no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.app import Principal
from apps.api.provider_onboarding import (
    GatewayOnboardRequest,
    ProviderOnboardingSurface,
    create_provider_onboarding_router,
    definition_from_request,
)
from apps.composition.provider_onboarding import manifest_from_definition
from core.contracts.domain import ProviderStatus
from core.providers import (
    BindingRegistry,
    ModelRegistry,
    ProviderOnboardingService,
    ProviderRegistry,
)
from core.providers.ports import ProviderAdapterPort
from tests.providers.test_onboarding_service import FakeAdapter, _manifest


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


ADMIN = Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=True)
USER = Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=False)


def _body(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "provider_key": "gw_alpha",
        "display_name": "Gateway Alpha",
        "operations": ["generate_text"],
        "capabilities": {"chat": True},
        "static_models": [],
        "credential_ref": "credref_alpha",
        "route_token_ref": "credref_route_alpha",
        "credential_mode": "platform",
    }
    data.update(overrides)
    return data


class RouteWorld:
    """Router mounted over a REAL walker with a FakeAdapter builder."""

    def __init__(
        self,
        *,
        principal: Principal | None = ADMIN,
        adapter: FakeAdapter | None = None,
        adapter_error: str | None = None,
        describe: dict[str, object] | None | str = "absent",
    ) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapters: dict[UUID, ProviderAdapterPort] = {}
        self.credential_refs: dict[UUID, str] = {}
        self.persisted: list[tuple[UUID, dict[str, object]]] = []
        self.adapter = (
            adapter
            if adapter is not None
            else FakeAdapter(manifest=_manifest(id="gw_alpha", name="Gateway Alpha"))
        )
        service = ProviderOnboardingService(
            providers=self.providers,
            models=self.models,
            bindings=self.bindings,
            adapters=self.adapters,
            credential_refs=self.credential_refs,
        )

        def _build_adapter(manifest: object, body: GatewayOnboardRequest) -> ProviderAdapterPort:
            if adapter_error is not None:
                raise ValueError(adapter_error)
            return self.adapter

        self.describe_calls: list[GatewayOnboardRequest] = []

        async def _describe(body: GatewayOnboardRequest) -> dict[str, object] | None:
            self.describe_calls.append(body)
            return None if describe is None else describe  # type: ignore[return-value]

        surface = ProviderOnboardingSurface(
            onboarding=service,
            build_manifest=manifest_from_definition,
            build_adapter=_build_adapter,
            persist_registration=lambda pid, d: self.persisted.append((pid, d)),
            describe_remote=None if describe == "absent" else _describe,
        )

        def _resolve(request: Request) -> Principal | JSONResponse:
            if principal is None:
                return JSONResponse(status_code=401, content={"error": "no session"})
            return principal

        self.app = FastAPI()
        self.app.include_router(create_provider_onboarding_router(surface, resolve=_resolve))

    def post(self, body: dict[str, object]) -> httpx.Response:
        async def _go() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/v1/admin/providers/onboard", json=body)

        return run(_go())


class TestAdmission:
    def test_anonymous_is_refused(self) -> None:
        world = RouteWorld(principal=None)
        assert world.post(_body()).status_code == 401

    def test_non_admin_is_refused(self) -> None:
        world = RouteWorld(principal=USER)
        response = world.post(_body())
        # ErrorCode.UNAUTHORIZED maps to 403 (HTTP_STATUS_BY_CODE) — the
        # same admitted-but-not-admin answer every admin route gives.
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "unauthorized"

    def test_refused_caller_causes_no_registration(self) -> None:
        world = RouteWorld(principal=USER)
        world.post(_body())
        assert world.persisted == []
        assert world.adapters == {}


class TestHappyPath:
    def test_201_with_walker_report_and_scope_caveat(self) -> None:
        world = RouteWorld()
        response = world.post(_body())
        assert response.status_code == 201, response.text
        report = response.json()
        assert report["provider_key"] == "gw_alpha"
        assert "step-11-register-provider" in report["steps_passed"]
        assert "step-13-provider-kept-disabled" in report["steps_passed"]
        assert report["enable_draft_payload"] == {"provider_key": "gw_alpha"}
        assert "canonical-gateway providers only" in report["scope"]

    def test_provider_registered_disabled_and_executable_maps_filled(self) -> None:
        world = RouteWorld()
        response = world.post(_body())
        provider_id = UUID(response.json()["provider_id"])
        entry = world.providers.get("gw_alpha")
        assert entry.provider.status is ProviderStatus.DISABLED
        assert world.adapters[provider_id] is world.adapter
        assert world.credential_refs[provider_id] == "credref_alpha"

    def test_registration_definition_persisted_refs_only(self) -> None:
        world = RouteWorld()
        response = world.post(_body())
        provider_id = UUID(response.json()["provider_id"])
        assert len(world.persisted) == 1
        pid, definition = world.persisted[0]
        assert pid == provider_id
        # EXACTLY the request body dump (one derivation, two consumers).
        assert definition == definition_from_request(GatewayOnboardRequest.model_validate(_body()))
        assert definition["credential_ref"] == "credref_alpha"
        assert definition["route_token_ref"] == "credref_route_alpha"


class TestRefusals:
    def test_unknown_operation_is_422_before_provider_io(self) -> None:
        world = RouteWorld()
        response = world.post(_body(operations=["conjure_magic"]))
        assert response.status_code == 422
        assert world.persisted == []

    def test_open2_excluded_operation_is_422(self) -> None:
        world = RouteWorld()
        response = world.post(_body(operations=["run_provider_agent"]))
        assert response.status_code == 422
        assert "excluded from gateway v1" in response.json()["error"]["message"]

    def test_unknown_capability_key_is_422(self) -> None:
        world = RouteWorld()
        response = world.post(_body(capabilities={"telepathy": True}))
        assert response.status_code == 422

    def test_gateway_not_configured_is_409(self) -> None:
        world = RouteWorld(adapter_error="gateway binding is not configured")
        response = world.post(_body())
        assert response.status_code == 409
        assert world.persisted == []

    def test_walker_refusal_surfaces_verbatim_as_409(self) -> None:
        world = RouteWorld(
            adapter=FakeAdapter(
                manifest=_manifest(id="gw_alpha", name="Gateway Alpha"),
                healthy=False,
            )
        )
        response = world.post(_body())
        assert response.status_code == 409
        message = response.json()["error"]["message"]
        assert "step-6-health-check" in message
        assert world.persisted == []

    def test_extra_body_field_is_rejected_closed_shape(self) -> None:
        world = RouteWorld()
        response = world.post(_body(api_key="sk-NEVER"))
        assert response.status_code == 422


class TestManifestDerivation:
    def test_deterministic_and_disabled(self) -> None:
        definition = GatewayOnboardRequest.model_validate(_body())
        first = manifest_from_definition(definition)
        second = manifest_from_definition(definition)
        assert first == second
        assert first.status == "disabled"
        assert first.id == "gw_alpha"
        assert first.is_template is False


DESCRIBED: dict[str, object] = {
    "display_name": "Gateway Alpha",
    "credential_mode": "platform",
    "capabilities": {"chat": True, "code": True},
    "operations": ["generate_text", "generate_image", "upload_asset"],
    "models": [{"name": "alpha-large", "context_window": 128000}, {"name": "alpha-mini"}],
    "definition_version": "2.3.0",
    "health_supported": True,
}


class TestDiscovery:
    """R160: opt-in auto-discovery via the gateway's /v1/describe — refs only."""

    def test_discover_fills_only_empty_fields_and_reports_what_it_learned(self) -> None:
        world = RouteWorld(describe=DESCRIBED)
        response = world.post(
            _body(discover=True, operations=[], capabilities={}, static_models=[])
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["discovery"]["filled"] == ["operations", "capabilities", "static_models"]
        # OPEN-2: the excluded op is dropped AND named, never registered.
        assert body["discovery"]["excluded_operations"] == ["upload_asset"]
        assert body["discovery"]["definition_version"] == "2.3.0"
        assert len(world.describe_calls) == 1
        # The persisted definition is the FILLED one (deterministic hydration).
        ((_, persisted),) = world.persisted
        assert persisted["operations"] == ["generate_text", "generate_image"]
        assert persisted["capabilities"] == {"chat": True, "code": True}
        assert persisted["static_models"] == ["alpha-large", "alpha-mini"]
        assert persisted["discover"] is True
        # Refs only — no secret value anywhere.
        assert persisted["credential_ref"] == "credref_alpha"
        # Hydration re-derives the SAME manifest from the filled row.
        manifest = manifest_from_definition(GatewayOnboardRequest.model_validate(persisted))
        assert [op.value for op in manifest.operations] == ["generate_text", "generate_image"]

    def test_explicit_declaration_wins_over_discovery(self) -> None:
        world = RouteWorld(describe=DESCRIBED)
        response = world.post(
            _body(discover=True, operations=["generate_text"], capabilities={"chat": True})
        )
        assert response.status_code == 201, response.text
        assert response.json()["discovery"]["filled"] == ["static_models"]
        ((_, persisted),) = world.persisted
        assert persisted["operations"] == ["generate_text"]
        assert persisted["capabilities"] == {"chat": True}

    def test_discovery_unreachable_is_a_loud_refusal_never_a_guess(self) -> None:
        world = RouteWorld(describe=None)
        response = world.post(_body(discover=True, operations=[]))
        assert response.status_code == 409
        assert "did not describe" in response.json()["error"]["message"]
        assert world.persisted == [] and world.providers.all_keys() == []

    def test_discovery_without_gateway_binding_is_409(self) -> None:
        world = RouteWorld()  # describe seam absent
        response = world.post(_body(discover=True, operations=[]))
        assert response.status_code == 409
        assert "not configured" in response.json()["error"]["message"]

    def test_discovery_with_only_excluded_operations_is_422(self) -> None:
        world = RouteWorld(describe={**DESCRIBED, "operations": ["upload_asset"]})
        response = world.post(_body(discover=True, operations=[]))
        assert response.status_code == 422
        assert response.json()["error"]["details"]["discovery"]["excluded_operations"] == [
            "upload_asset"
        ]

    def test_empty_operations_without_discover_is_422(self) -> None:
        world = RouteWorld(describe=DESCRIBED)
        assert world.post(_body(operations=[])).status_code == 422
        assert world.describe_calls == []

    def test_no_discover_never_calls_describe(self) -> None:
        world = RouteWorld(describe=DESCRIBED)
        assert world.post(_body()).status_code == 201
        assert world.describe_calls == []
        assert "discovery" not in world.post(_body(provider_key="gw_beta")).json()
