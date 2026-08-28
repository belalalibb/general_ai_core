"""FastAPI composition root — POST /v1/execute + GET /v1/executions/{id}.

MVP Phase 5 slice 3 (T-IMPL-023; 41 §44 API surface; 10 §2-§5 contracts).
ADR-0001: FastAPI lives ONLY here in apps/ — core/ and providers/ stay
framework-free (import-linter contract in pyproject.toml, landed with the
dependency pin in the same commit).

The app is a pure composition of already-verified core services:

    ExecuteRequest (10 §2)  ->  SimpleScoringRouter (T-IMPL-021)
                            ->  ExecutionService    (T-IMPL-022)
                            ->  ExecuteSyncResponse / unified error (10 §3/§9)

Scope decisions for this slice (loud rejections, never silent degradation):

- Sync execution only. ``execution_policy.async=true`` and ``stream=true``
  are REJECTED with ``validation_error`` — the durable async runtime and
  streaming belong to later phases (12 §9; 10 §11) and are not faked.
- Text surface: requests route as ``generate_text`` (30 §5); mode stays a
  free-form hint (10 §2) and does not change the operation in this slice.
- Authentication is a later MVP phase; the composition injects a fixed
  dev tenant/user principal. The seam (``principal`` parameter) is where
  the auth dependency will plug in without touching handlers.
- Idempotency (10 §10): same tenant + same ``Idempotency-Key`` header
  returns the SAME execution instead of creating a duplicate.
- Persistence is the process-local InMemoryExecutionStore (slice decision
  recorded in PROJECT_EXECUTION_STATE.md); repository-backed storage swaps
  in at the composition root without handler changes.
- Usage accounting (T-IMPL-024; 10 §3 ``usage`` block): when the injected
  ExecutionService carries a UsageAccountingPort, entitlement denials
  (missing budget / budget exceeded) map to the unified
  ``entitlement_exceeded`` code (10 §9, HTTP 403) BEFORE any provider work,
  and successful responses surface the settled ledger as the ``usage``
  block. A service without accounting keeps ``usage`` absent — never faked.

Phase 6 slice 4 (T-IMPL-028; 41 §45; 10 §2/§7) — recorded decisions:

- GET /v1/skills lists ONLY selectable skills (SkillRegistry.list_selectable:
  status=active AND source=local — the loadable-not-selectable posture
  surfaced to the API). Rows are the 10 §7 shape via SkillListEntry
  (manifest id, not the registry UUID; flat deduplicated tool-name list —
  DATA, never a grant, 03 §8).
- Role selection (10 §2 ``role``): ``role.id`` may be the registry UUID or
  the unique role NAME (the 10 §2 example uses a symbolic id like
  ``senior_software_architect``). Admission is RoleRegistry.select — only
  ACTIVE roles compose. The closed 10 §9 set has no ``not_found``/
  ``role_unavailable``: unknown, ambiguous, non-selectable, and
  scope-mismatched role references all map to ``validation_error`` 422
  with the named reason in ``details`` (same mapping posture as the
  unknown-execution-id decision in apps/api/errors.py).
- Conversation persistence (10 §2 ``conversation_id``): when a
  ConversationStorePort is injected, an unknown conversation id is
  AUTO-CREATED under the caller's tenant/user (there is no separate
  create-conversation endpoint in this slice — recorded, not accidental;
  anti-enumeration (20 §6) makes "absent" and "exists in a foreign tenant"
  indistinguishable, so both create fresh under the caller's own tenant).
  A conversation owned by ANOTHER user in the same tenant denies with
  ``unauthorized`` 403 (13 §7 cross-user rule). The user ask is appended
  BEFORE execution (history is an audit-grade record of what was asked —
  failures keep the ask); the assistant turn is appended only on
  ``succeeded`` with the same content the client receives. Idempotent
  replays short-circuit BEFORE persistence, so no duplicate turns.
  Without an injected store, ``conversation_id`` stays what it was in
  slice 3: execution-record metadata only.
- Context composition (T-IMPL-027 wiring): when a ContextComposer is
  injected, the composed 13 §5 object (blocks + NAMED exclusions —
  exclusions stay data) rides the execution payload under ``context``;
  composition runs BEFORE the current ask is appended, so history blocks
  are prior turns only. ``ContextBudgetExceeded`` maps to
  ``validation_error`` 422 with the required/budget facts. The composer
  MUST share the SAME registry/store instances injected here — that
  agreement is the composition root's duty. When a role is selected AND a
  composer is present, the role objective rides ONLY inside the composed
  context (role block); without a composer it rides as ``payload["role"]``
  — never both (no duplicated instruction blocks).

FINAL Phase 18 slice 1 (T-IMPL-067; 41 §21; 10 §6/§8) — recorded decisions:

- GET /v1/models and GET /v1/usage land as OPTIONAL seams (``models`` +
  ``bindings``, ``usage``) with the admin-router posture: absent seam ⇒
  the route does not exist at all (nothing to probe, 20 §4). Full seam
  decisions live on the ``create_app`` docstring.
- The remaining 41 §21 surface (POST /v1/webhooks, Async, Streaming,
  API Keys, Scopes) is NOT in this slice — async/streaming stay the
  recorded loud rejections (12 §9 durable runtime seam exists as
  WorkflowRuntimePort with no engine binding — a real engine is a NEW
  DEPENDENCY requiring an operator-ACCEPTED ADR); webhook DELIVERY is
  outbound I/O gated the same way. Contracts for all of them already
  exist in core/contracts/execute.py (10 §4/§11/§12). Never faked (41 §49).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.api.admin import AdminSurface, create_admin_router
from apps.api.errors import (
    HTTP_STATUS_BY_CODE,
    error_response,
    execution_failure_detail,
)
from apps.api.store import ExecutionNotFound, InMemoryExecutionStore
from core.context.composer import ContextComposer
from core.context.errors import ContextBudgetExceeded
from core.contracts.base import JsonObject, utc_now
from core.contracts.context import ComposedContext, ContextComposeRequest
from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.errors import ErrorCode
from core.contracts.execute import (
    ExecuteRequest,
    ExecuteSyncResponse,
    ExecutionProgress,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStatusResponse,
    RoleSelector,
    UsageReport,
    WebhookEventType,
)
from core.contracts.model_listing import ModelListEntry, ModelsListResponse
from core.contracts.provider import ProviderError, ProviderOperation
from core.contracts.roles import Role
from core.contracts.routing import RoutingRequest
from core.contracts.skills import SkillListEntry, SkillsListResponse
from core.contracts.usage import UsageLedger
from core.contracts.webhooks import (
    WebhookSubscription,
    WebhookSubscriptionRequest,
    WebhookSubscriptionResponse,
)
from core.execution.service import ExecutionReport, ExecutionService
from core.memory.errors import ConversationNotFound
from core.memory.ports import ConversationStorePort
from core.providers.registry import BindingRegistry, ModelRegistry
from core.roles.errors import RoleNotRegistered, RoleNotSelectable
from core.roles.registry import RoleRegistry, SkillRegistry
from core.routing.errors import (
    FallbackNotConfigured,
    NoEligibleCandidates,
)
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured
from core.usage.ports import UsageAccountingPort


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity — the seam the auth phase will fill.

    ``is_admin`` (T-IMPL-032; R049 boundary (e)): deny-by-default admin
    flag — NOT a rebuilt RBAC system, just the single seam a real 20 §3
    role binding will later populate. False unless composition explicitly
    grants it; every /v1/admin/* route denies without it.
    """

    tenant_id: UUID
    user_id: UUID
    is_admin: bool = False


def _request_hash(payload: ExecuteRequest) -> str:
    """Deterministic content hash of the request (03 §5 Execution.request_hash)."""
    canonical = json.dumps(
        payload.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result_from_output(output: JsonObject, format_hint: str | None) -> ExecutionResult:
    """Shape the final node output as the 10 §3 ``result`` object.

    Adapters return normalized JSON objects; when the output carries a string
    ``content`` field it is surfaced verbatim, otherwise the whole object is
    serialized — the API never invents content.
    """
    content = output.get("content")
    if not isinstance(content, str):
        content = json.dumps(output, sort_keys=True)
    return ExecutionResult(
        type="message",
        content=content,
        format=format_hint,
        artifacts=[],
    )


def _progress(report: ExecutionReport) -> ExecutionProgress:
    """Stage-completion progress for GET /v1/executions/{id} (10 §5).

    This slice runs executions synchronously, so stored reports are always
    terminal — every node is in a terminal state and percent is 100 for any
    non-empty report. The shape still honors 10 §5 so an async runtime can
    reuse it unchanged.
    """
    terminal = ("succeeded", "failed", "skipped")
    total = len(report.nodes)
    done = sum(1 for entry in report.nodes if entry.node.status.value in terminal)
    percent = int(round(100 * done / total)) if total else None
    current = report.nodes[-1].node.node_key if report.nodes else None
    return ExecutionProgress(current_stage=current, percent=percent)


def _usage_report(ledger: UsageLedger | None) -> UsageReport | None:
    """Shape the settled ledger as the 10 §3 ``usage`` block (absent if none).

    The ledger carries floats (estimates may be fractional in later plans);
    the 10 §3 block is whole task units — int conversion is exact for the
    MVP metric (1 unit per stage) and any fractional policy would change
    the contract first, not silently truncate here.
    """
    if ledger is None:
        return None
    return UsageReport(
        units_reserved=int(ledger.units_reserved),
        units_settled=int(ledger.units_settled),
        details={"status": ledger.status.value},
    )


def _last_provider_error(report: ExecutionReport) -> ProviderError | None:
    for node_report in reversed(report.nodes):
        for attempt in reversed(node_report.attempts):
            if attempt.error is not None:
                return attempt.error
    return None


def _resolve_role(selector: RoleSelector, registry: RoleRegistry) -> Role | JSONResponse:
    """Admit the requested role or return the unified-error denial (10 §9).

    ``role.id`` accepts the registry UUID or the unique role NAME (10 §2
    example: ``senior_software_architect``). All denials are the recorded
    ``validation_error`` mappings (module docstring) — named, never silent.
    """
    candidate_id: UUID | None
    try:
        candidate_id = UUID(selector.id)
    except ValueError:
        candidate_id = None
    if candidate_id is None:
        matches = [r for r in registry.list_all() if r.name == selector.id]
        if not matches:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown role.",
                details={"field": "role.id"},
            )
        if len(matches) > 1:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Ambiguous role name; use the role id.",
                details={"field": "role.id"},
            )
        candidate_id = matches[0].id
    try:
        role = registry.select(candidate_id)
    except RoleNotRegistered:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Unknown role.",
            details={"field": "role.id"},
        )
    except RoleNotSelectable as exc:
        # Loadable-but-not-selectable (draft/disabled): the named reason
        # crosses the boundary as data, never a silent skip (11 §14).
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Role is not selectable.",
            details={"field": "role.id", "role_status": exc.status},
        )
    if selector.type != role.scope.value:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "role.type does not match the selected role's scope.",
            details={"field": "role.type", "expected": role.scope.value},
        )
    return role


def create_app(
    *,
    router: SimpleScoringRouter,
    execution_service: ExecutionService,
    store: InMemoryExecutionStore | None = None,
    principal: Principal,
    skills: SkillRegistry | None = None,
    roles: RoleRegistry | None = None,
    conversations: ConversationStorePort | None = None,
    composer: ContextComposer | None = None,
    context_budget: int = 16_000,
    admin: AdminSurface | None = None,
    models: ModelRegistry | None = None,
    bindings: BindingRegistry | None = None,
    usage: UsageAccountingPort | None = None,
    webhooks: bool = False,
) -> FastAPI:
    """Build the API application from injected, already-verified services.

    Phase 6 seams (all optional — absent seams keep prior slices' behavior):
    ``skills``/``roles`` default to EMPTY registries (deny-by-default:
    nothing listed, no role admissible — 20 §4); ``conversations`` enables
    history persistence; ``composer`` enables 13 §5 context composition and
    MUST share the same registry/store instances injected here.

    Phase 7 seam: ``admin`` (T-IMPL-032) mounts /v1/admin/* over the
    injected AdminSurface; absent, NO admin route exists at all — the
    strongest deny-by-default (nothing to probe, 20 §4).

    FINAL Phase 18 seams (T-IMPL-067; 41 §21; 10 §6/§8) — recorded decisions:

    - ``models`` + ``bindings`` mount GET /v1/models (10 §6). BOTH must be
      the SAME instances the injected router routes over (composition-root
      duty, same posture as the composer/registry agreement above) — the
      listing must describe the pool that actually routes. Either absent ⇒
      the route does not exist (nothing to probe, 20 §4). The listing shows
      ACTIVE models only (``ModelRegistry.active_models`` — the routing
      pool; disabled models are an ADMIN read surface, 21 §5, already
      served by /v1/admin/models). Row availability is the best-across-
      bindings projection recorded in core/contracts/model_listing.py.
    - ``usage`` mounts GET /v1/usage (10 §8) over UsageAccountingPort
      .summary — the SAME accounting instance the execution service
      reserves/settles against (composition-root duty). Absent ⇒ no route.
      An unconfigured tenant maps to ``entitlement_exceeded`` 403 — the
      SAME deny-by-default mapping the execute path already applies to
      EntitlementNotConfigured (one behavior, both surfaces).
    - ``webhooks=True`` mounts POST /v1/webhooks (41 §21) — subscription
      REGISTRATION only, stored process-locally and tenant-scoped, same
      persistence posture as InMemoryExecutionStore (repository binding
      swaps in at the composition root). Event DELIVERY is outbound I/O:
      the documented 40 §4.2 outbox chain (core/runtime/outbox.py) is the
      recorded seam a delivery relay will consume — never claimed here
      (41 §49). Default False ⇒ route absent (nothing to probe, 20 §4).
    """
    app = FastAPI(title="AI Orchestration Platform", version="0.1.0", docs_url=None)
    execution_store = store if store is not None else InMemoryExecutionStore()
    skill_registry = skills if skills is not None else SkillRegistry()
    role_registry = roles if roles is not None else RoleRegistry()
    # Idempotency index (10 §10): (tenant_id, key) -> execution_id.
    idempotency_index: dict[tuple[UUID, str], UUID] = {}

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request body failed contract validation.",
            details={"errors": [str(err.get("msg", "")) for err in exc.errors()]},
        )

    @app.exception_handler(Exception)
    async def _internal_handler(_request: Request, _exc: Exception) -> JSONResponse:
        # 20 §4: internals never leak to clients.
        return error_response(
            ErrorCode.INTERNAL_ERROR, "Internal error.", retryable=False
        )

    @app.post("/v1/execute")
    async def execute(
        body: ExecuteRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Response:
        # --- loud scope rejections (module docstring posture) ------------------
        policy = body.execution_policy
        if policy is not None and policy.async_ is True:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Async execution is not available on this deployment slice.",
                details={"field": "execution_policy.async"},
            )
        if policy is not None and policy.stream is True:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Streaming is not available on this deployment slice.",
                details={"field": "execution_policy.stream"},
            )
        conversation_id: UUID | None = None
        if body.conversation_id is not None:
            try:
                conversation_id = UUID(body.conversation_id)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "conversation_id must be a UUID.",
                    details={"field": "conversation_id"},
                )

        # --- role admission (10 §2 role; T-IMPL-026 registry) -------------------
        role: Role | None = None
        if body.role is not None:
            resolved = _resolve_role(body.role, role_registry)
            if isinstance(resolved, JSONResponse):
                return resolved
            role = resolved

        # --- idempotent replay (10 §10) ----------------------------------------
        # BEFORE persistence/composition: a replay must not duplicate turns.
        if idempotency_key is not None:
            replay_id = idempotency_index.get((principal.tenant_id, idempotency_key))
            if replay_id is not None:
                return _sync_response(
                    execution_store.get(principal.tenant_id, replay_id), body
                )

        # --- conversation admission (13 §7; module-docstring decisions) ---------
        conversation: Conversation | None = None
        if conversations is not None and conversation_id is not None:
            try:
                conversation = conversations.get_conversation(
                    principal.tenant_id, conversation_id
                )
            except ConversationNotFound:
                # Auto-create under the caller (recorded decision): absent
                # and foreign-tenant are indistinguishable (20 §6), so both
                # start a fresh conversation owned by the caller.
                conversation = conversations.create_conversation(
                    Conversation(
                        id=conversation_id,
                        tenant_id=principal.tenant_id,
                        user_id=principal.user_id,
                        title=body.ask[:80],
                        status=ConversationStatus.ACTIVE,
                    )
                )
            if conversation.user_id != principal.user_id:
                # Same tenant, different user: 13 §7 — one user's history is
                # never used for another. Named denial, not silent skip.
                return error_response(
                    ErrorCode.UNAUTHORIZED,
                    "Conversation belongs to another user.",
                    details={"field": "conversation_id"},
                )

        # --- context composition (T-IMPL-027; BEFORE appending the ask) ---------
        composed: ComposedContext | None = None
        if composer is not None:
            try:
                composed = composer.compose(
                    ContextComposeRequest(
                        tenant_id=principal.tenant_id,
                        user_id=principal.user_id,
                        ask=body.ask,
                        role_id=role.id if role is not None else None,
                        conversation_id=(
                            conversation.id if conversation is not None else None
                        ),
                        context_budget=context_budget,
                    )
                )
            except ContextBudgetExceeded as exc:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Mandatory context exceeds the context budget.",
                    details={"required": exc.required, "budget": exc.budget},
                )

        # --- persist the ask (append-only history; failures keep the ask) -------
        if conversations is not None and conversation is not None:
            conversations.append_message(
                principal.tenant_id,
                Message(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content=body.ask,
                    created_at=utc_now(),
                ),
            )

        # --- route (11; Router decides) ----------------------------------------
        routing_request = RoutingRequest(
            operation=ProviderOperation.GENERATE_TEXT,
            model_policy=body.model_policy,
        )
        try:
            decision = router.route(routing_request)
        except UnsupportedPolicyType as exc:
            return error_response(
                ErrorCode.VALIDATION_ERROR, str(exc), details={"field": "model_policy"}
            )
        except NoEligibleCandidates as exc:
            return error_response(
                ErrorCode.MODEL_UNAVAILABLE,
                "No eligible model candidates for this request.",
                details={
                    "excluded": [
                        record.model_dump(mode="json", exclude_none=True)
                        for record in exc.excluded
                    ]
                },
            )
        except FallbackNotConfigured as exc:
            return error_response(ErrorCode.MODEL_UNAVAILABLE, str(exc))

        # --- execute (02 invariant 5: Execution executes) -----------------------
        payload: JsonObject = {"ask": body.ask}
        if body.output is not None:
            payload["output"] = body.output.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        if composed is not None:
            # The composed 13 §5 object rides the payload verbatim — blocks
            # AND named exclusions stay data all the way down.
            payload["context"] = composed.model_dump(mode="json", exclude_none=True)
        elif role is not None:
            # No composer: the admitted role's objective rides as payload
            # data (never both — recorded decision, no duplicated blocks).
            payload["role"] = {"id": str(role.id), "objective": role.objective}
        try:
            report = await execution_service.execute_single(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=_request_hash(body),
                idempotency_key=idempotency_key,
                conversation_id=conversation_id,
            )
        except BudgetExceeded as exc:
            # Denied BEFORE any provider work (03 §7; 10 §9). The accounting
            # facts explain the denial without leaking other tenants' data.
            return error_response(
                ErrorCode.ENTITLEMENT_EXCEEDED,
                "Task-unit budget exceeded for this request.",
                details={"requested": exc.requested, "remaining": exc.remaining},
            )
        except EntitlementNotConfigured:
            # Deny-by-default (20 §4): no budget configured means DENY, and
            # the client-facing message stays generic.
            return error_response(
                ErrorCode.ENTITLEMENT_EXCEEDED,
                "No task-unit entitlement is configured for this tenant.",
            )
        execution_store.put(report)
        if idempotency_key is not None:
            idempotency_index[(principal.tenant_id, idempotency_key)] = (
                report.execution.id
            )
        # --- persist the assistant turn (succeeded only; same content) ----------
        if (
            conversations is not None
            and conversation is not None
            and report.execution.status is ExecutionStatus.SUCCEEDED
            and report.final_output is not None
        ):
            format_hint = body.output.format if body.output is not None else None
            conversations.append_message(
                principal.tenant_id,
                Message(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=_result_from_output(report.final_output, format_hint).content,
                    created_at=utc_now(),
                ),
            )
        return _sync_response(report, body)

    def _sync_response(report: ExecutionReport, body: ExecuteRequest) -> Response:
        if report.execution.status is ExecutionStatus.SUCCEEDED:
            output = report.final_output
            assert output is not None  # succeeded => last node has output
            format_hint = body.output.format if body.output is not None else None
            sync = ExecuteSyncResponse(
                execution_id=str(report.execution.id),
                status=report.execution.status,
                result=_result_from_output(output, format_hint),
                usage=_usage_report(report.usage),
                evaluation=None,
            )
            return JSONResponse(
                status_code=200,
                content=sync.model_dump(mode="json", exclude_none=True),
            )
        # Failed execution: unified error (10 §9) carrying the execution id so
        # GET /v1/executions/{id} remains fully usable for diagnosis.
        detail = execution_failure_detail(
            str(report.execution.id), _last_provider_error(report)
        )
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CODE[detail.code],
            content={"error": detail.model_dump(mode="json", exclude_none=True)},
        )

    @app.get("/v1/skills")
    async def list_skills() -> Response:
        """GET /v1/skills (10 §7): selectable skills only, name-ordered.

        Non-selectable registrations (pipeline states, disabled, imported
        source) are LOADED but never listed — the registry's admission rule
        surfaced, not re-implemented here.
        """
        response = SkillsListResponse(
            skills=[
                SkillListEntry.from_skill(skill)
                for skill in skill_registry.list_selectable()
            ]
        )
        return JSONResponse(
            status_code=200,
            content=response.model_dump(mode="json", exclude_none=True),
        )

    # --- GET /v1/models (10 §6; T-IMPL-067): mounted ONLY with both seams ------
    if models is not None and bindings is not None:
        model_registry = models
        binding_registry = bindings

        @app.get("/v1/models")
        async def list_models() -> Response:
            """GET /v1/models (10 §6): ACTIVE models only, key-ordered.

            The routing pool surfaced, not re-derived: rows come from the
            same registries the router selects over; availability is the
            recorded best-across-bindings projection (empty ⇒ unavailable).
            """
            response = ModelsListResponse(
                models=[
                    ModelListEntry.from_model(
                        model, binding_registry.bindings_for_model(model.id)
                    )
                    for model in model_registry.active_models()
                ]
            )
            return JSONResponse(
                status_code=200,
                content=response.model_dump(mode="json", exclude_none=True),
            )

    # --- GET /v1/usage (10 §8; T-IMPL-067): mounted ONLY with the usage seam ---
    if usage is not None:
        usage_accounting = usage

        @app.get("/v1/usage")
        async def usage_summary() -> Response:
            """GET /v1/usage (10 §8): the caller tenant's plan + budgets.

            Tenant-scoped by the principal (never a client-supplied tenant
            id — 20 §6 anti-enumeration); an unconfigured tenant denies
            with the same entitlement_exceeded mapping as /v1/execute.
            """
            try:
                summary = usage_accounting.summary(principal.tenant_id)
            except EntitlementNotConfigured:
                return error_response(
                    ErrorCode.ENTITLEMENT_EXCEEDED,
                    "No task-unit entitlement is configured for this tenant.",
                )
            return JSONResponse(
                status_code=200,
                content=summary.model_dump(mode="json", exclude_none=True),
            )

    # --- POST /v1/webhooks (41 §21; T-IMPL-067 slice 2): registration only -----
    if webhooks:
        # Tenant-scoped subscription store (process-local, same posture as
        # InMemoryExecutionStore — recorded in the create_app docstring).
        webhook_subscriptions: dict[UUID, list[WebhookSubscription]] = {}

        @app.post("/v1/webhooks", status_code=201)
        async def register_webhook(body: WebhookSubscriptionRequest) -> Response:
            """POST /v1/webhooks: register a subscription for the caller tenant.

            ``events`` absent ⇒ all six documented 10 §12 types (the closed
            set is the universe — recorded in core/contracts/webhooks.py);
            an empty explicit list is a contradiction and refuses loudly.
            Delivery is NOT performed or promised by this route (41 §49).
            """
            if body.events is not None and len(body.events) == 0:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "events must be omitted (all types) or non-empty.",
                    details={"field": "events"},
                )
            events = (
                list(body.events)
                if body.events is not None
                else list(WebhookEventType)
            )
            subscription = WebhookSubscription(
                id=uuid4(),
                tenant_id=principal.tenant_id,
                url=body.url,
                events=events,
            )
            webhook_subscriptions.setdefault(principal.tenant_id, []).append(
                subscription
            )
            response = WebhookSubscriptionResponse.from_subscription(subscription)
            return JSONResponse(
                status_code=201,
                content=response.model_dump(mode="json", exclude_none=True),
            )

    @app.get("/v1/executions/{execution_id}")
    async def execution_status(execution_id: str) -> Response:
        try:
            parsed = UUID(execution_id)
        except ValueError:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "execution id must be a UUID.",
                details={"field": "execution_id"},
            )
        try:
            # Tenant-scoped read (T-IMPL-033 IDOR fix, 20 §6): a foreign
            # tenant's execution is indistinguishable from an absent one.
            report = execution_store.get(principal.tenant_id, parsed)
        except ExecutionNotFound:
            # Closed 10 §9 code set has no not_found; mapping decision in
            # apps/api/errors.py — validation_error body with HTTP 404.
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown execution id.",
                details={"execution_id": execution_id},
                http_status=404,
            )

        status = report.execution.status
        result = None
        error_detail = None
        if status is ExecutionStatus.SUCCEEDED and report.final_output is not None:
            result = _result_from_output(report.final_output, None)
        elif status is ExecutionStatus.FAILED:
            error_detail = execution_failure_detail(
                execution_id, _last_provider_error(report)
            )
        status_response = ExecutionStatusResponse(
            execution_id=execution_id,
            status=status,
            progress=_progress(report),
            result=result,
            error=error_detail,
        )
        return JSONResponse(
            status_code=200,
            content=status_response.model_dump(mode="json", exclude_none=True),
        )

    # --- /v1/admin/* (T-IMPL-032): mounted ONLY when a surface is injected ----
    if admin is not None:
        app.include_router(
            create_admin_router(
                admin,
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                is_admin=principal.is_admin,
            )
        )

    return app
