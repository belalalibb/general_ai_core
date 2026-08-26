"""Admin + evaluation API surface — /v1/admin/* (MVP Phase 7 slice 4).

T-IMPL-032 (41 §46; R049 slicing decision, binding). Recorded decisions:

- ADMIN GATE (R049 boundary (e)): admin AuthN/RBAC is NOT rebuilt. The
  ``is_admin`` flag on the EXISTING :class:`~apps.api.app.Principal` is the
  seam a real RBAC binding will fill; WITHOUT the flag every /v1/admin/*
  route denies with ``unauthorized`` 403 (deny-by-default, 20 §4). The gate
  runs BEFORE any parameter parsing so non-admins cannot even probe
  resource-id validity.
- LIFECYCLE ENDPOINTS surface the T-IMPL-031 AdminConfigService verbatim
  (21 §3 order enforced THERE, not re-implemented here): draft / validate /
  preview / publish / rollback / list / get. Error mappings (closed 10 §9
  set, same posture as apps/api/errors.py):
    * ChangeNotFound        -> validation_error body, HTTP 404 (the
      recorded unknown-resource mapping — no ``not_found`` code exists).
    * InvalidLifecycleTransition / RollbackUnavailable -> validation_error
      body, HTTP 409 (state conflict; the closed set has no ``conflict``
      code — recorded mapping decision, not a contract change).
    * InactiveAdminArea     -> validation_error 422 (the request named an
      area outside the deployed MVP surface).
- READ VIEWS (21 §5 posture): admin reads are surfaces over the EXISTING
  registries — models INCLUDING disabled ones (an admin must see what it
  can re-enable), providers INCLUDING templates (marked, never routable),
  the tenant plan summary via the usage seam, and the router's current
  default scoring weights. No parallel state, no re-derived eligibility.
- EVALUATION READS (22 §7): "Admin sees scores, confidence, evidence,
  traces." Evaluation records — WITH score/confidence/evidence_ref — are
  readable HERE and only here; the user-facing /v1/execute surface never
  carries them (the 10 §3 response contract has no evaluation fields).
- LEARNING DASHBOARD PLACEHOLDER (R049 boundary (a)): the 21 §7 read-model
  shape served with honest zero/empty values and ``placeholder: true`` —
  NO fabricated metrics; the learning lifecycle (22 §8–§11) does not exist
  in this phase and the response says so structurally.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from apps.api.errors import error_response
from core.admin.errors import (
    ChangeNotFound,
    InactiveAdminArea,
    InvalidLifecycleTransition,
    RollbackUnavailable,
)
from core.admin.service import (
    AdminConfigService,
    RoutingWeightsPort,
    UsageConfigurationPort,
)
from core.contracts.admin import AdminDraftRequest, ConfigChange, LearningDashboard
from core.contracts.errors import ErrorCode
from core.evaluation.errors import EvaluationNotFound
from core.evaluation.ports import EvaluationStorePort
from core.providers.registry import ModelRegistry, ProviderRegistry
from core.usage.errors import EntitlementNotConfigured


@dataclass(frozen=True)
class AdminSurface:
    """Everything the /v1/admin/* router composes over — injected, existing.

    The read seams (providers/models/usage/routing) MUST be the same
    instances the AdminConfigService publishes into — that agreement is the
    composition root's duty (same rule as the ContextComposer wiring).
    """

    service: AdminConfigService
    providers: ProviderRegistry
    models: ModelRegistry
    usage: UsageConfigurationPort
    routing: RoutingWeightsPort
    evaluations: EvaluationStorePort


def _json(payload: object, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=payload)


def _change_json(change: ConfigChange) -> dict[str, object]:
    return change.model_dump(mode="json", exclude_none=True)


def create_admin_router(
    surface: AdminSurface,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    is_admin: bool,
) -> APIRouter:
    """Build the /v1/admin/* router for one composed principal.

    Every handler re-checks the ``is_admin`` gate FIRST — with the current
    fixed-principal composition the value is static, but the check sits
    exactly where a per-request identity dependency will later bind.
    """
    router = APIRouter(prefix="/v1/admin")

    def _gate() -> JSONResponse | None:
        """Deny-by-default admin gate (R049 boundary (e); 20 §4)."""
        if not is_admin:
            return error_response(
                ErrorCode.UNAUTHORIZED,
                "Admin access required.",
            )
        return None

    def _parse_uuid(value: str, field: str) -> UUID | JSONResponse:
        try:
            return UUID(value)
        except ValueError:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                f"{field} must be a UUID.",
                details={"field": field},
            )

    def _change_not_found(change_id: str) -> JSONResponse:
        # Recorded unknown-resource mapping (apps/api/errors.py): the closed
        # 10 §9 set has no not_found — validation_error body, HTTP 404.
        # Anti-enumeration (20 §6): absent and foreign-tenant are identical.
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Unknown config change id.",
            details={"change_id": change_id},
            http_status=404,
        )

    # --- config lifecycle (21 §3, surfaced verbatim) --------------------------------

    @router.post("/changes")
    async def draft_change(body: AdminDraftRequest) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        try:
            change = surface.service.draft(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action=body.action,
                payload=body.payload,
            )
        except InactiveAdminArea as exc:
            return error_response(
                ErrorCode.VALIDATION_ERROR, str(exc), details={"field": "action"}
            )
        return _json(_change_json(change), status=201)

    @router.get("/changes")
    async def list_changes() -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _json(
            {
                "changes": [
                    _change_json(c) for c in surface.service.list_changes(tenant_id)
                ]
            }
        )

    @router.get("/changes/{change_id}")
    async def get_change(change_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        parsed = _parse_uuid(change_id, "change_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            change = surface.service.get(tenant_id, parsed)
        except ChangeNotFound:
            return _change_not_found(change_id)
        return _json(_change_json(change))

    def _lifecycle_step(change_id: str, step: str) -> Response:
        parsed = _parse_uuid(change_id, "change_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            if step == "validate":
                change = surface.service.validate(tenant_id, parsed)
            elif step == "preview":
                change = surface.service.preview(tenant_id, parsed)
            elif step == "publish":
                change = surface.service.publish(tenant_id, parsed)
            else:
                change = surface.service.rollback(tenant_id, parsed)
        except ChangeNotFound:
            return _change_not_found(change_id)
        except (InvalidLifecycleTransition, RollbackUnavailable) as exc:
            # 21 §3 order violation / no-prior-state rollback: a state
            # CONFLICT — validation_error body with HTTP 409 (recorded
            # mapping decision; the closed set has no conflict code).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                str(exc),
                details={"change_id": change_id},
                http_status=409,
            )
        return _json(_change_json(change))

    @router.post("/changes/{change_id}/validate")
    async def validate_change(change_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _lifecycle_step(change_id, "validate")

    @router.post("/changes/{change_id}/preview")
    async def preview_change(change_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _lifecycle_step(change_id, "preview")

    @router.post("/changes/{change_id}/publish")
    async def publish_change(change_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _lifecycle_step(change_id, "publish")

    @router.post("/changes/{change_id}/rollback")
    async def rollback_change(change_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _lifecycle_step(change_id, "rollback")

    # --- read views over the EXISTING registries (21 §5 posture) --------------------

    @router.get("/models")
    async def list_models() -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        # ALL models including disabled: an admin must see what it can
        # re-enable (21 §4 Models row). Routing keeps its own ACTIVE filter.
        return _json(
            {
                "models": [
                    m.model_dump(mode="json", exclude_none=True)
                    for m in surface.models.all_models()
                ]
            }
        )

    @router.get("/providers")
    async def list_providers() -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        rows = []
        for key in surface.providers.all_keys():
            entry = surface.providers.get(key)
            row = entry.provider.model_dump(mode="json", exclude_none=True)
            # Registry-derived facts as DATA (31 §10): templates are shown
            # and marked — an admin sees WHY a provider can never route.
            row["is_template"] = entry.is_template
            row["is_routable"] = entry.is_routable
            rows.append(row)
        return _json({"providers": rows})

    @router.get("/plans/{plan_tenant_id}")
    async def get_plan(plan_tenant_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        parsed = _parse_uuid(plan_tenant_id, "plan_tenant_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            summary = surface.usage.summary(parsed)
        except EntitlementNotConfigured:
            # No plan configured is an honest 404-mapped absence — the
            # surface never invents a default plan (20 §4).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "No plan is configured for this tenant.",
                details={"plan_tenant_id": plan_tenant_id},
                http_status=404,
            )
        return _json(summary.model_dump(mode="json", exclude_none=True))

    @router.get("/routing/weights")
    async def get_routing_weights() -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        return _json(
            surface.routing.default_weights.model_dump(mode="json", exclude_none=True)
        )

    # --- evaluation reads (22 §7: ADMIN sees scores/confidence/evidence) -------------

    @router.get("/evaluations/{evaluation_id}")
    async def get_evaluation(evaluation_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        parsed = _parse_uuid(evaluation_id, "evaluation_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            record = surface.evaluations.get(tenant_id, parsed)
        except EvaluationNotFound:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown evaluation id.",
                details={"evaluation_id": evaluation_id},
                http_status=404,
            )
        return _json(record.model_dump(mode="json", exclude_none=True))

    @router.get("/executions/{execution_id}/evaluations")
    async def list_execution_evaluations(execution_id: str) -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        parsed = _parse_uuid(execution_id, "execution_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        records = surface.evaluations.list_for_execution(tenant_id, parsed)
        # Empty is honest for unknown/foreign executions alike (20 §6
        # anti-enumeration — the port contract, surfaced unchanged).
        return _json(
            {
                "evaluations": [
                    r.model_dump(mode="json", exclude_none=True) for r in records
                ]
            }
        )

    # --- learning dashboard PLACEHOLDER (21 §7; R049 boundary (a)) -------------------

    @router.get("/learning/dashboard")
    async def learning_dashboard() -> Response:
        denied = _gate()
        if denied is not None:
            return denied
        # Honest zeros/empties + the structural placeholder marker — the
        # learning lifecycle (22 §8-§11) is NOT built this phase and this
        # response cannot pretend otherwise (LearningDashboard.placeholder
        # is Literal[True]).
        return _json(LearningDashboard().model_dump(mode="json", exclude_none=True))

    return router
