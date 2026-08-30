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

Phase AA-1 (seams AUD-1, USG-2, SYS-1) — recorded decisions:

- PER-REQUEST PRINCIPAL: ``create_admin_router`` now takes a ``resolve``
  callable instead of a frozen (tenant_id, actor_id, is_admin) triple —
  the seam the T-IMPL-032 docstring promised ("exactly where a
  per-request identity dependency will later bind"). ``_admit`` resolves
  the caller THEN applies the is_admin gate, both BEFORE any parameter
  parsing — anonymous callers get the constant 401, authenticated
  non-admins the unchanged 403, and neither can probe id validity.
- AUD-1 (GET /v1/admin/audit): the ``AuditLogPort.read`` result surfaced
  VERBATIM — tenant-scoped by the admitted principal, optional closed-set
  ``event_type`` filter (unknown names refuse loudly, 422), optional
  ``limit`` (>=1). ``total_recorded`` rides via ``count`` so a truncated
  page is visibly a page. Seam optional: absent ``surface.audit`` ⇒ route
  absent entirely (nothing to probe, 20 §4).
- USG-2 (GET /v1/admin/usage): per-execution usage drill-down over the
  execution store's ledgers. ``ledger`` is ``null`` whenever accounting
  was not bound for that run — NEVER fabricated (41 §49). Seam optional:
  absent ``surface.executions`` ⇒ route absent.
- SYS-1 (GET /v1/admin/system): the injected ``system_info`` snapshot
  with ``scope`` FORCED to ``"process"`` — the route structurally cannot
  claim fleet/deployment truths it does not have (41 §49). ``system_info``
  absent ⇒ route absent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from apps.api.capabilities import Capability, catalog_json
from apps.api.context_lab import (
    ContextLabRequest,
    ContextLabService,
    ConversationNotAdmitted,
)
from apps.api.errors import error_response
from apps.api.exercise import ExerciseSurface
from apps.api.learning_observability import LearningObservabilityService
from apps.api.scenarios import (
    ScenarioNotFound,
    ScenarioSaveRequest,
    ScenarioService,
    UnknownCheckName,
    scenario_json,
)
from apps.api.store import InMemoryExecutionStore
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
from core.audit.ports import AuditLogPort
from core.contracts.admin import AdminDraftRequest, ConfigChange, LearningDashboard
from core.contracts.audit import AuditEventType
from core.contracts.base import JsonObject
from core.contracts.errors import ErrorCode
from core.evaluation.errors import EvaluationNotFound
from core.evaluation.ports import EvaluationStorePort
from core.providers.registry import ModelRegistry, ProviderRegistry
from core.usage.errors import EntitlementNotConfigured

if TYPE_CHECKING:
    from apps.api.app import Principal


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
    # AA-1 optional seams — absent ⇒ the corresponding route is absent
    # entirely (nothing to probe, 20 §4).
    audit: AuditLogPort | None = None
    executions: InMemoryExecutionStore | None = None


def _json(payload: object, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=payload)


def _change_json(change: ConfigChange) -> dict[str, object]:
    return change.model_dump(mode="json", exclude_none=True)


def create_admin_router(
    surface: AdminSurface,
    *,
    resolve: Callable[[Request], Principal | JSONResponse],
    system_info: Callable[[], JsonObject] | None = None,
    capabilities: tuple[Capability, ...] | None = None,
    exercise: ExerciseSurface | None = None,
    scenarios: ScenarioService | None = None,
    context_lab: ContextLabService | None = None,
    learning_observability: LearningObservabilityService | None = None,
) -> APIRouter:
    """Build the /v1/admin/* router over a per-request principal resolver.

    ``resolve`` returns the caller's Principal or a ready denial response
    (401) — the per-request identity binding the T-IMPL-032 docstring
    reserved this exact spot for (AA-1 seam IDN-1). ``_admit`` runs the
    resolver THEN the is_admin gate, both BEFORE any parameter parsing.
    """
    router = APIRouter(prefix="/v1/admin")

    def _admit(request: Request) -> Principal | JSONResponse:
        """Resolve the caller, then deny-by-default admin gate (20 §4)."""
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        if not caller.is_admin:
            return error_response(
                ErrorCode.UNAUTHORIZED,
                "Admin access required.",
            )
        return caller

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
    async def draft_change(request: Request, body: AdminDraftRequest) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        try:
            change = surface.service.draft(
                tenant_id=admitted.tenant_id,
                actor_id=admitted.user_id,
                action=body.action,
                payload=body.payload,
            )
        except InactiveAdminArea as exc:
            return error_response(
                ErrorCode.VALIDATION_ERROR, str(exc), details={"field": "action"}
            )
        return _json(_change_json(change), status=201)

    @router.get("/changes")
    async def list_changes(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _json(
            {
                "changes": [
                    _change_json(c)
                    for c in surface.service.list_changes(admitted.tenant_id)
                ]
            }
        )

    @router.get("/changes/{change_id}")
    async def get_change(request: Request, change_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        parsed = _parse_uuid(change_id, "change_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            change = surface.service.get(admitted.tenant_id, parsed)
        except ChangeNotFound:
            return _change_not_found(change_id)
        return _json(_change_json(change))

    def _lifecycle_step(tenant_id: UUID, change_id: str, step: str) -> Response:
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
    async def validate_change(request: Request, change_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _lifecycle_step(admitted.tenant_id, change_id, "validate")

    @router.post("/changes/{change_id}/preview")
    async def preview_change(request: Request, change_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _lifecycle_step(admitted.tenant_id, change_id, "preview")

    @router.post("/changes/{change_id}/publish")
    async def publish_change(request: Request, change_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _lifecycle_step(admitted.tenant_id, change_id, "publish")

    @router.post("/changes/{change_id}/rollback")
    async def rollback_change(request: Request, change_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _lifecycle_step(admitted.tenant_id, change_id, "rollback")

    # --- read views over the EXISTING registries (21 §5 posture) --------------------

    @router.get("/models")
    async def list_models(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
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
    async def list_providers(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
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
    async def get_plan(request: Request, plan_tenant_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
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
    async def get_routing_weights(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _json(
            surface.routing.default_weights.model_dump(mode="json", exclude_none=True)
        )

    # --- evaluation reads (22 §7: ADMIN sees scores/confidence/evidence) -------------

    @router.get("/evaluations/{evaluation_id}")
    async def get_evaluation(request: Request, evaluation_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        parsed = _parse_uuid(evaluation_id, "evaluation_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        try:
            record = surface.evaluations.get(admitted.tenant_id, parsed)
        except EvaluationNotFound:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown evaluation id.",
                details={"evaluation_id": evaluation_id},
                http_status=404,
            )
        return _json(record.model_dump(mode="json", exclude_none=True))

    @router.get("/executions/{execution_id}/evaluations")
    async def list_execution_evaluations(
        request: Request, execution_id: str
    ) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        parsed = _parse_uuid(execution_id, "execution_id")
        if isinstance(parsed, JSONResponse):
            return parsed
        records = surface.evaluations.list_for_execution(admitted.tenant_id, parsed)
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
    async def learning_dashboard(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        # Honest zeros/empties + the structural placeholder marker — the
        # learning lifecycle (22 §8-§11) is NOT built this phase and this
        # response cannot pretend otherwise (LearningDashboard.placeholder
        # is Literal[True]).
        return _json(LearningDashboard().model_dump(mode="json", exclude_none=True))

    # --- V7 chunk 5: Learning observability ("what changed since last
    # review" with evidence). Absent seam = absent routes (20 §4). Reading
    # the report is a pure read; marking a review is the one state change.

    if learning_observability is not None:
        observability = learning_observability

        @router.get("/learning/changes-since-review")
        async def changes_since_review(request: Request) -> Response:
            """GET .../changes-since-review: window facts WITH evidence rows."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            return _json(observability.changes_since_review(admitted.tenant_id))

        @router.post("/learning/mark-reviewed")
        async def mark_reviewed(request: Request) -> Response:
            """POST .../mark-reviewed: the explicit review ACT (self-evidencing)."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            return _json(
                observability.mark_reviewed(admitted.tenant_id, admitted.user_id)
            )

    # --- AA-1 seam AUD-1: audit read (20 §9 events, port surfaced verbatim) ---------

    if surface.audit is not None:
        audit_log = surface.audit

        @router.get("/audit")
        async def read_audit(
            request: Request,
            event_type: str | None = None,
            limit: int | None = None,
        ) -> Response:
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            parsed_type: AuditEventType | None = None
            if event_type is not None:
                try:
                    parsed_type = AuditEventType(event_type)
                except ValueError:
                    # Closed 20 §9 set — unknown names refuse loudly (11 §14).
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        "Unknown audit event type.",
                        details={"field": "event_type"},
                    )
            if limit is not None and limit < 1:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "limit must be >= 1.",
                    details={"field": "limit"},
                )
            events = audit_log.read(
                admitted.tenant_id, event_type=parsed_type, limit=limit
            )
            return _json(
                {
                    "events": [
                        e.model_dump(mode="json", exclude_none=True) for e in events
                    ],
                    "total_recorded": audit_log.count(admitted.tenant_id),
                }
            )

    # --- AA-1 seam USG-2: per-execution usage drill-down (ledger read-model) --------

    if surface.executions is not None:
        execution_store = surface.executions

        @router.get("/usage")
        async def usage_drilldown(request: Request) -> Response:
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            rows = []
            for report in execution_store.list(admitted.tenant_id):
                ledger = report.usage
                rows.append(
                    {
                        "execution_id": str(report.execution.id),
                        "status": report.execution.status.value,
                        "created_at": report.execution.created_at.isoformat(),
                        # NEVER fabricated: null means accounting was not
                        # bound for that run (41 §49).
                        "ledger": (
                            None
                            if ledger is None
                            else ledger.model_dump(mode="json", exclude_none=True)
                        ),
                    }
                )
            return _json({"usage": rows})

    # --- V7 chunk 1: Capability Catalog (honest closed-set, derived) ----------------

    if capabilities is not None:
        # Serialize ONCE at mount time: the derivation is composition-time
        # truth and cannot change per request; completeness/duplicate
        # violations fail HERE, loudly, at composition (never mid-request).
        catalog_payload = catalog_json(capabilities)

        @router.get("/capabilities")
        async def capability_catalog(request: Request) -> Response:
            """GET /v1/admin/capabilities: what THIS process can actually do.

            Admin-gated like every /v1/admin/* route (deny-by-default).
            States are derived from composition facts in create_app — the
            same variables that mounted (or didn't mount) each surface.
            """
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            return _json(catalog_payload)

    # --- V7 chunk 2: Capability Exercise Surface (real probes, real evidence) -------

    if exercise is not None:
        exercise_registry = exercise

        @router.get("/capabilities/exercisable")
        async def exercisable_capabilities(request: Request) -> Response:
            """The ids that have a REAL probe — exactly the registered set."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            return _json({"exercisable": exercise_registry.exercisable()})

        @router.post("/capabilities/{capability_id}/exercise")
        async def exercise_capability(
            request: Request, capability_id: str
        ) -> Response:
            """POST /v1/admin/capabilities/{id}/exercise: prove it by running it.

            The probe runs the SAME machinery a user request runs, as the
            admitted caller (billed/recorded against their tenant). The
            response is EVIDENCE (record ids, stored statuses) — an
            unexercisable id maps to the recorded unknown-resource 404
            (anti-enumeration: unknown and unregistered are identical).
            """
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            handler = exercise_registry.get(capability_id)
            if handler is None:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Unknown exercisable capability id.",
                    details={"capability_id": capability_id[:100]},
                    http_status=404,
                )
            result = await handler(admitted)
            return _json({"capability_id": capability_id, "result": result})

    # --- V7 chunk 3: Test Scenarios → Regression Center (absent seam = absent
    # routes, 20 §4). A scenario is TEST DATA, not platform config — saving one
    # is an R1-style act (recorded design decision), so no draft/approve cycle.

    if scenarios is not None:
        scenario_service = scenarios

        def _scenario_not_found(scenario_id: str) -> JSONResponse:
            """One answer for absent, foreign, and malformed ids (20 §6)."""
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown scenario id.",
                details={"scenario_id": scenario_id[:100]},
                http_status=404,
            )

        @router.get("/scenarios")
        async def list_scenarios(request: Request) -> Response:
            """GET /v1/admin/scenarios: the caller's tenant's saved scenarios."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            rows = scenario_service.list(admitted.tenant_id)
            return _json({"scenarios": [scenario_json(s) for s in rows]})

        @router.post("/scenarios")
        async def save_scenario(
            request: Request, body: ScenarioSaveRequest
        ) -> Response:
            """POST /v1/admin/scenarios: save a named, replayable scenario.

            The check set is CLOSED (the platform's own deterministic
            checks, P1) — an unknown name is a loud 422, never silent data.
            """
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            try:
                scenario = scenario_service.save(
                    admitted.tenant_id,
                    name=body.name,
                    ask=body.ask,
                    checks=tuple(body.checks),
                )
            except UnknownCheckName as exc:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    str(exc),
                    details={"field": "checks"},
                    http_status=422,
                )
            return _json(scenario_json(scenario), status=201)

        @router.post("/scenarios/{scenario_id}/replay")
        async def replay_scenario(request: Request, scenario_id: str) -> Response:
            """POST /v1/admin/scenarios/{id}/replay: a REAL labeled execution."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            parsed = _parse_uuid(scenario_id, "scenario_id")
            if isinstance(parsed, JSONResponse):
                return _scenario_not_found(scenario_id)
            try:
                result = await scenario_service.replay(
                    admitted.tenant_id, admitted.user_id, parsed
                )
            except ScenarioNotFound:
                return _scenario_not_found(scenario_id)
            return _json(result)

        @router.post("/scenarios/regression-pack")
        async def run_regression_pack(request: Request) -> Response:
            """POST /v1/admin/scenarios/regression-pack: replay them ALL."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            result = await scenario_service.regression_pack(
                admitted.tenant_id, admitted.user_id
            )
            return _json(result)

    # --- V7 chunk 4: Context Validation Lab (absent seam = absent routes,
    # 20 §4 — no composer means there is nothing to validate). A dry-run
    # READ surface: it composes for real but executes nothing, writes nothing.

    if context_lab is not None:
        lab_service = context_lab

        @router.get("/context-lab/checks")
        async def list_lab_checks(request: Request) -> Response:
            """GET /v1/admin/context-lab/checks: the closed lab-check set."""
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            return _json({"checks": lab_service.checks()})

        @router.post("/context-lab/validate")
        async def validate_context(
            request: Request, body: ContextLabRequest
        ) -> Response:
            """POST /v1/admin/context-lab/validate: dry-run the REAL composer.

            Returns the composed blocks + named exclusions + closed lab
            verdicts. Composition failures (impossible budget, refused
            role) are honest ``validated: False`` DATA; only an
            unadmitted conversation id is a transport 404 (absent and
            foreign answer identically, 20 §6).
            """
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            try:
                result = lab_service.validate(
                    admitted.tenant_id, admitted.user_id, body
                )
            except ConversationNotAdmitted:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Unknown conversation id.",
                    details={"field": "conversation_id"},
                    http_status=404,
                )
            return _json(result)

    # --- AA-1 seam SYS-1: system read-model (process-local truths, labeled) ---------

    if system_info is not None:
        system_snapshot = system_info

        @router.get("/system")
        async def system_read_model(request: Request) -> Response:
            admitted = _admit(request)
            if isinstance(admitted, JSONResponse):
                return admitted
            snapshot = dict(system_snapshot())
            # Forced label (41 §49): this surface reports THIS process
            # only — it cannot claim fleet/deployment truths.
            snapshot["scope"] = "process"
            return _json(snapshot)

    return router
