"""Gap 1c — admin HTTP surface over the EXISTING provider onboarding walker.

POST /v1/admin/providers/onboard runs :class:`core.providers.onboarding.
ProviderOnboardingService` (the 31 §19 checklist, steps 3-14 machine-run
subset) for ONE canonical-gateway provider and returns the walker's
report verbatim — including the PREPARED step-14 ``enable_draft_payload``.
Enabling stays the audited draft→publish path through the EXISTING
/v1/admin/changes lifecycle (AdminConfigService); this surface NEVER
enables anything.

DECISION 2 (recorded, binding): this route onboards CANONICAL-GATEWAY
providers only — the RemoteGatewayAdapter over the platform's remote
provider gateway. A foreign/native-API provider still REQUIRES its own
adapter/shim implementation (30 §7) and cannot be onboarded here; that
caveat is part of this surface's contract, not a temporary limitation.

Secret custody (20 §5): the request body carries OPAQUE references only
(``credential_ref``, ``route_token_ref``) — never a raw key, token, or
secret value. Nothing here logs, echoes, or stores a secret value.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from apps.api.errors import error_response
from core.contracts.errors import ErrorCode
from core.contracts.provider import ProviderManifest
from core.providers.onboarding import (
    OnboardingRefused,
    OnboardingReport,
    ProviderOnboardingService,
)
from core.providers.ports import ProviderAdapterPort

if TYPE_CHECKING:
    from apps.api.app import Principal


class GatewayOnboardRequest(BaseModel):
    """POST /v1/admin/providers/onboard body — closed shape, REFS ONLY.

    ``operations``/``capabilities``/``static_models`` are the OPERATOR's
    declared surface (build_gateway_manifest shapes them; OPEN-2 excluded
    operations refuse at build time). ``credential_ref``/``route_token_ref``
    are opaque secret-manager references (20 §5) — never values.
    """

    model_config = ConfigDict(extra="forbid")

    provider_key: str = Field(min_length=1, max_length=512)
    display_name: str = Field(min_length=1, max_length=512)
    #: Operator-declared operations. May be EMPTY only with ``discover=True``
    #: (then the gateway's ``/v1/describe`` projection fills it).
    operations: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    static_models: list[str] = Field(default_factory=list)
    credential_ref: str = Field(min_length=1, max_length=512)
    route_token_ref: str = Field(min_length=1, max_length=512)
    credential_mode: str = "platform"
    definition_version: str = "1.0.0"
    #: R160 auto-discovery (opt-in): read the gateway's ``/v1/describe`` and
    #: fill ONLY the fields the operator left empty (operations,
    #: capabilities, static_models). Explicit declarations always win; the
    #: persisted definition is the FILLED one (deterministic hydration).
    discover: bool = False

    @model_validator(mode="after")
    def _operations_or_discover(self) -> GatewayOnboardRequest:
        if not self.operations and not self.discover:
            raise ValueError("operations must be declared unless discover=true")
        return self


def definition_from_request(body: GatewayOnboardRequest) -> dict[str, object]:
    """The persisted registration definition (ADR-0011) — exactly the
    request body dump: operator data, refs only. One derivation, two
    consumers: the route persists it; startup hydration rebuilds the
    adapter from it."""
    return body.model_dump(mode="json")


@dataclass
class ProviderOnboardingSurface:
    """Onboarding walker + the composition-bound adapter builder.

    ``build_adapter`` is the composition root's doorway (Gap 1a): given
    the validated manifest and the request, it constructs the
    RemoteGatewayAdapter with resolvers bound to the SecretManagerPort.
    It raises ``ValueError`` when the gateway is not configured or the
    definition is unbuildable — surfaced as a loud refusal, never a
    silent degradation. ``persist_registration`` (Gap 1b/ADR-0011)
    stores the definition row AFTER a successful onboarding so startup
    hydration can rebuild the adapter; absent seam = no durability
    (in-memory profile, honest posture).
    """

    onboarding: ProviderOnboardingService
    build_adapter: Callable[[ProviderManifest, GatewayOnboardRequest], ProviderAdapterPort]
    build_manifest: Callable[[GatewayOnboardRequest], ProviderManifest]
    persist_registration: Callable[[UUID, dict[str, object]], None] | None = None
    #: R160: read the gateway's ``/v1/describe`` for ONE request (refs only;
    #: nothing registered). Absent seam ⇒ ``discover=true`` refuses loudly.
    describe_remote: (
        Callable[[GatewayOnboardRequest], Awaitable[dict[str, object] | None]] | None
    ) = None


#: Gateway v1 operations the platform never admits (ADR-0008 OPEN-2) — a
#: discovered declaration naming them is FILTERED and reported, never
#: registered (the manifest builder would refuse them anyway).
_EXCLUDED_DISCOVERED = frozenset({"run_provider_agent", "upload_asset", "download_asset"})


def fill_from_description(
    body: GatewayOnboardRequest, declared: dict[str, object]
) -> tuple[GatewayOnboardRequest, dict[str, object]]:
    """Fill the operator's EMPTY fields from the describe projection.

    Explicit wins: a non-empty operator field is never overwritten. Returns
    the filled request + a data record of what was taken from discovery
    (and which excluded operations were dropped) so the response can say
    exactly what the platform learned versus what the operator declared.
    """
    update: dict[str, object] = {}
    record: dict[str, object] = {"filled": [], "excluded_operations": []}
    filled: list[str] = []
    if not body.operations:
        raw_ops = declared.get("operations")
        ops = [op for op in raw_ops if isinstance(op, str)] if isinstance(raw_ops, list) else []
        excluded = sorted(op for op in ops if op in _EXCLUDED_DISCOVERED)
        update["operations"] = [op for op in ops if op not in _EXCLUDED_DISCOVERED]
        record["excluded_operations"] = excluded
        filled.append("operations")
    if not body.capabilities:
        raw_caps = declared.get("capabilities")
        if isinstance(raw_caps, dict):
            update["capabilities"] = {str(k): v for k, v in raw_caps.items() if isinstance(v, bool)}
            filled.append("capabilities")
    if not body.static_models:
        raw_models = declared.get("models")
        if isinstance(raw_models, list):
            names = [
                m["name"]
                for m in raw_models
                if isinstance(m, dict) and isinstance(m.get("name"), str) and m["name"]
            ]
            update["static_models"] = names
            filled.append("static_models")
    record["filled"] = filled
    record["definition_version"] = declared.get("definition_version")
    return body.model_copy(update=update), record


def _report_json(report: OnboardingReport) -> dict[str, object]:
    return {
        "provider_id": str(report.provider_id),
        "provider_key": report.provider_key,
        "steps_passed": list(report.steps_passed),
        "unverified": list(report.unverified),
        "discovered_models": list(report.discovered_models),
        "registered_model_keys": list(report.registered_model_keys),
        # Step 14 stays admin-lifecycle territory: publish this payload
        # through POST /v1/admin/changes (action=enable_provider) to enable.
        "enable_draft_payload": dict(report.enable_draft_payload),
        # DECISION 2 caveat — part of the response contract, always present.
        "scope": (
            "canonical-gateway providers only; foreign/native-API providers "
            "require their own adapter/shim and cannot be onboarded here"
        ),
    }


def create_provider_onboarding_router(
    surface: ProviderOnboardingSurface,
    *,
    resolve: Callable[[Request], Principal | JSONResponse],
) -> APIRouter:
    """The 31 §19 walker as ONE admin route — core refusals verbatim."""
    router = APIRouter(prefix="/v1/admin/providers")

    def _admit(request: Request) -> Principal | JSONResponse:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        if not caller.is_admin:
            return error_response(ErrorCode.UNAUTHORIZED, "Admin access required.")
        return caller

    @router.post("/onboard")
    async def onboard_provider(request: Request, body: GatewayOnboardRequest) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted

        # R160 opt-in discovery: fill the operator's EMPTY fields from the
        # gateway's /v1/describe. Unreachable / absent seam ⇒ loud 409 —
        # never a guessed surface. Explicit declarations always win.
        discovery: dict[str, object] | None = None
        if body.discover:
            if surface.describe_remote is None:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "discovery is not available: the gateway binding is not configured",
                    http_status=409,
                )
            declared = await surface.describe_remote(body)
            if declared is None:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "discovery failed: the gateway did not describe this provider",
                    http_status=409,
                )
            body, discovery = fill_from_description(body, declared)
            if not body.operations:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "discovery returned no admissible operations",
                    details={"discovery": discovery},
                    http_status=422,
                )

        # Shape the operator's declaration (OPEN-2 exclusions + closed
        # capability keys refuse HERE, before any provider I/O).
        try:
            manifest = surface.build_manifest(body)
        except (ValueError, ValidationError) as exc:
            return error_response(ErrorCode.VALIDATION_ERROR, str(exc), http_status=422)

        # Composition-bound adapter construction (gateway not configured
        # ⇒ loud refusal — never a fake adapter).
        try:
            adapter = surface.build_adapter(manifest, body)
        except ValueError as exc:
            return error_response(ErrorCode.VALIDATION_ERROR, str(exc), http_status=409)

        try:
            report = await surface.onboarding.onboard(
                adapter=adapter,
                provider_key=body.provider_key,
                display_name=body.display_name,
                auth_types=list(manifest.auth.types),
                credential_ref=body.credential_ref,
            )
        except OnboardingRefused as exc:
            # The walker's refusal, verbatim (409 — state conflict, the
            # same mapping the config lifecycle routes use).
            return error_response(ErrorCode.VALIDATION_ERROR, str(exc), http_status=409)

        # ADR-0011: persist the registration definition (refs only) so the
        # composition root rebuilds this adapter at the next startup.
        if surface.persist_registration is not None:
            surface.persist_registration(report.provider_id, definition_from_request(body))

        content = _report_json(report)
        if discovery is not None:
            content["discovery"] = discovery
        return JSONResponse(status_code=201, content=content)

    return router


__all__ = [
    "GatewayOnboardRequest",
    "ProviderOnboardingSurface",
    "create_provider_onboarding_router",
    "definition_from_request",
    "fill_from_description",
]
