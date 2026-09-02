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

Phase AA-1 — API SEAMS (doc C §3; doc B §5) — recorded decisions:

- IDN-1: ``create_app`` accepts EXACTLY ONE of ``principal`` (the fixed
  dev-composition mode every existing caller uses — unchanged behavior)
  or ``auth`` (an :class:`~apps.api.auth.AuthSurface`): passing both or
  neither raises ``ValueError`` loudly at composition time. In auth mode
  the /v1/auth/* router mounts and every tenant-scoped handler resolves
  its Principal PER REQUEST from the Bearer session token; any failure is
  the ONE constant-message ``unauthenticated`` 401 (20 §6). Identity runs
  FIRST — before rate limiting, replay, and persistence — an anonymous
  caller consumes no work and leaves zero state. ``is_admin`` projects
  from the AuthSurface email allowlist (composition data — the seam a
  real 20 §3 RBAC binding fills later; R049 boundary (e) unchanged).
- EXE-1: GET /v1/executions — the tenant-scoped, filterable list over
  the store's new ``list`` method. Rows are the 10 §5 status shape plus
  ``initiated_by``/``created_at``; NO result bodies ride the list (the
  by-id route serves those) — a list must not become a bulk-exfil
  surface. Filter parse failures are named 422s.
- WBH-1: GET /v1/webhooks + DELETE /v1/webhooks/{subscription_id} under
  the SAME ``webhooks`` seam flag. Delete searches ONLY the caller
  tenant's rows: unknown and foreign-tenant ids are byte-identical 404s
  (20 §6; the recorded unknown-resource mapping — validation_error body,
  HTTP 404). No update route exists (no doc defines one — absent, not
  fabricated).
- SYS-1: GET /healthz — opt-in (``healthz=True``), UNAUTHENTICATED BY
  DESIGN (liveness probes cannot carry sessions), body exactly
  ``{status, scope, time}`` with ``scope: "process"`` — process-local
  truth only, never fleet claims (41 §49). GET /v1/admin/system rides
  the admin router via the ``system_info`` callable (admin.py decisions).
- Catalog reads (GET /v1/skills, GET /v1/models) stay PRINCIPAL-FREE —
  they serve tenant-independent catalog data and carried no principal
  before this phase; recorded decision, not an oversight.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from apps.api.admin import AdminSurface, create_admin_router
from apps.api.agent import AGENT_STRATEGY, AgentSurface, AgentToolSelection, AgentToolsRejected
from apps.api.auth import AuthSurface, bearer_token, create_auth_router, unauthenticated
from apps.api.capabilities import Capability, CapabilityState
from apps.api.context_lab import ContextLabService
from apps.api.engineering_admin import EngineeringAdminSurface
from apps.admin_agent.secrecy import scrub_object
from apps.api.errors import (
    HTTP_STATUS_BY_CODE,
    error_response,
    execution_failure_detail,
)
from apps.api.exercise import EXERCISE_LABEL_KEY, ExerciseHandler, ExerciseSurface
from apps.api.learning_observability import LearningObservabilityService
from apps.api.provenance import context_provenance as _context_provenance
from apps.api.scenarios import ScenarioService
from apps.api.self_review import SelfReviewService
from apps.api.store import (
    ExecutionNotFound,
    ExecutionStorePort,
    InMemoryExecutionStore,
)
from apps.api.streaming import Sleeper, event_stream
from apps.api.workspaces import (
    InMemoryProjectStore,
    InMemoryWorkspaceStore,
    ProjectStorePort,
    WorkspaceStorePort,
    create_workspace_router,
)
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
from core.contracts.evaluation import VerificationLevel
from core.contracts.execute import (
    ExecuteAsyncAccepted,
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
from core.contracts.execution import Execution, ExecutionNodeStatus, ExecutionStrategy
from core.contracts.model_listing import ModelListEntry, ModelsListResponse
from core.contracts.model_policy import (
    AgentNodeMappingPolicy,
    ExplicitModelsPolicy,
    NodeModelPolicy,
)
from core.contracts.provider import ProviderError, ProviderOperation
from core.contracts.role_profile import RoleProfile
from core.contracts.roles import Role
from core.contracts.routing import RoutingDecision, RoutingRequest, TaskAnalysis
from core.contracts.skills import Skill, SkillListEntry, SkillsListResponse
from core.contracts.usage import UsageLedger
from core.contracts.webhooks import (
    WebhookSubscription,
    WebhookSubscriptionRequest,
    WebhookSubscriptionResponse,
)
from core.evaluation import InMemoryEvaluationStore
from core.evaluation.policy import EvaluationPolicyService
from core.events import (
    WebhookUrlRefused,
    stage_execution_event,
    validate_webhook_url,
)
from core.execution.multi_model import (
    CompareRefused,
    InvalidJudgePolicy,
    MultiModelExecutor,
    UnsupportedStrategy,
    resolve_node_policy,
)
from core.execution.service import (
    ExecutionReport,
    ExecutionService,
    PipelineStage,
)
from core.identity.errors import SessionInvalid
from core.learning import LearningLifecycleService, TrainingEligibilityGate
from core.memory.errors import ConversationNotFound
from core.memory.ports import ConversationStorePort, MemoryStorePort
from core.providers.registry import BindingRegistry, ModelRegistry
from core.roles.errors import RoleNotRegistered, RoleNotSelectable
from core.roles.registry import RoleRegistry, SkillRegistry
from core.routing.errors import (
    FallbackNotConfigured,
    NoEligibleCandidates,
)
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.runtime.outbox import OutboxPort
from core.runtime.ports import RateLimitPort
from core.skills import SkillResolver
from core.sourcechange.sandbox import (
    SOURCE_VERIFICATION_CHECKS as _SOURCE_CHECKS,
)
from core.sourcechange.sandbox import HermeticSandbox, VerificationSuite
from core.sourcechange.store import (
    InMemoryProposalStore,
    InMemorySnapshotStore,
    ProposalStorePort,
    SnapshotStorePort,
)
from core.sourcechange.workflow import SourceChangeWorkflow
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


def _result_from_output(
    output: JsonObject,
    format_hint: str | None,
    artifacts: list[JsonObject] | None = None,
) -> ExecutionResult:
    """Shape the final node output as the 10 §3 ``result`` object.

    Adapters return normalized JSON objects; when the output carries a string
    ``content`` field it is surfaced verbatim, otherwise the whole object is
    serialized — the API never invents content. ``artifacts`` are evidence
    objects derived from stored execution truth (R161 context provenance).
    """
    content = output.get("content")
    if not isinstance(content, str):
        content = json.dumps(output, sort_keys=True)
    return ExecutionResult(
        type="message",
        content=content,
        format=format_hint,
        artifacts=list(artifacts or []),
    )


def _async_accepted(execution_id: UUID) -> Response:
    """The 10 §4 async ack: 202 + queued + poll URL (contract shape,
    defined since the API contract landed — zero contract changes)."""
    accepted = ExecuteAsyncAccepted(
        execution_id=str(execution_id),
        status=ExecutionStatus.QUEUED,
        poll_url=f"/v1/executions/{execution_id}",
    )
    return JSONResponse(
        status_code=202,
        content=accepted.model_dump(mode="json", exclude_none=True),
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


def _agent_failure(report: ExecutionReport) -> JsonObject | None:
    """R165: WHY a ``strategy=agent`` run failed, from what the loop recorded.

    ``stop_reason`` rides the loop summary (``cost_snapshot``); the cause is
    the LAST failed node's recorded error (invalid-proposal detail, refused
    capability, deadline…). Scrubbed (R4) before it crosses the boundary.
    ``None`` for non-agent records — the historical shape stays untouched.
    """
    if report.execution.strategy is not ExecutionStrategy.AGENT:
        return None
    failure: JsonObject = {}
    stop_reason = report.execution.cost_snapshot.get("stop_reason")
    if isinstance(stop_reason, str):
        failure["stop_reason"] = stop_reason
    for node_report in reversed(report.nodes):
        node = node_report.node
        if node.status is ExecutionNodeStatus.FAILED and node.error:
            failure["node"] = node.node_key
            failure["error"] = scrub_object(dict(node.error))
            break
    return failure or None


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
    store: ExecutionStorePort | None = None,
    principal: Principal | None = None,
    auth: AuthSurface | None = None,
    skills: SkillRegistry | None = None,
    roles: RoleRegistry | None = None,
    conversations: ConversationStorePort | None = None,
    memory: MemoryStorePort | None = None,
    composer: ContextComposer | None = None,
    context_budget: int = 16_000,
    admin: AdminSurface | None = None,
    models: ModelRegistry | None = None,
    bindings: BindingRegistry | None = None,
    usage: UsageAccountingPort | None = None,
    webhooks: bool = False,
    rate_limits: RateLimitPort | None = None,
    execute_rate_limit: int = 0,
    execute_rate_window_seconds: float = 1.0,
    outbox: OutboxPort | None = None,
    execute_stream: str = "executions.requests",
    idempotency_index: MutableMapping[tuple[UUID, str], UUID] | None = None,
    webhook_subscriptions: MutableMapping[UUID, list[WebhookSubscription]] | None = None,
    system_info: Callable[[], JsonObject] | None = None,
    healthz: bool = False,
    sse: bool = False,
    sse_poll_interval_seconds: float = 0.5,
    sse_timeout_seconds: float = 60.0,
    sse_sleeper: Sleeper | None = None,
    source_proposals: ProposalStorePort | None = None,
    workspaces: WorkspaceStorePort | None = None,
    projects: ProjectStorePort | None = None,
    source_snapshots: SnapshotStorePort | None = None,
    agent: AgentSurface | None = None,
    engineering_admin: EngineeringAdminSurface | None = None,
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

    FINAL Phase 21 seam (T-IMPL-070; 41 §24 "API: rate limits") — recorded
    decisions:

    - ``rate_limits`` + ``execute_rate_limit > 0`` gate POST /v1/execute
      through the EXISTING RateLimitPort (40 §4.5 admission machinery —
      core/runtime; nothing new invented). The scope is per-tenant
      (``execute:{tenant_id}``) because 20 §3 names the unbounded-spend /
      account-abuse threats at tenant granularity and the Principal is the
      only identity at this seam. Refusal = the unified ``rate_limited``
      429 (10 §9 closed set) with ``retryable=true`` — the code already
      existed for provider-side limits; the SAME code serves the API-side
      gate (one vocabulary, both directions).
    - The gate runs FIRST, before idempotent replay and all persistence —
      a limited caller must not consume composition/storage work, and a
      429 must leave ZERO state behind (same zero-residue posture the
      admin deny gate holds).
    - No doc defines default numeric limits ⇒ limits are composition-root
      DATA (same posture as plan/task-unit values, 41 §19). The default
      ``execute_rate_limit=0`` means NOT CONFIGURED ⇒ gate absent —
      composition roots must OPT IN with a real number; a zero/absent
      configuration never silently rate-limits (and never silently
      unlimits a configured one). ``rate_limits`` absent ⇒ gate absent
      (same absent-seam posture as every other optional seam here).

    FINAL Phase 23 seams (T-IMPL-072; 41 §26 "Stateless API") — recorded
    decisions:

    - 41 §26 names "Stateless API" + "API → horizontal" scaling. The app
      held exactly TWO process-local mutable maps that would break under
      horizontal replicas: the idempotency index (10 §10) and the webhook
      subscription store (41 §21). Both become INJECTABLE MutableMapping
      seams here — a shared binding (Redis-hash/DB-table adapter offering
      the mapping protocol) restores cross-replica statelessness at the
      composition root without touching handler code.
    - Defaults stay process-local dicts: single-process behavior, every
      existing caller and test, and the recorded single-replica posture
      are all UNCHANGED. This seam is honesty-complete: no distributed
      binding is claimed to exist (41 §49) — the seam makes one POSSIBLE.
    - The injected execution ``store`` was ALREADY a seam (same posture);
      registries/services are read-only at request time; no other
      request-path mutable process state remains — asserted by the
      T-IMPL-072 statelessness suite.
    """
    # AA-1 (IDN-1): an identity mode is REQUIRED — loud composition error,
    # never a silent default (20 §4). Three modes:
    #   principal only  → fixed principal (hermetic tests);
    #   auth only       → every call authenticates (durable profile);
    #   principal + auth → HYBRID (R160; in-memory runtime profile): a Bearer
    #                      token resolves a REAL session (admin via
    #                      ADMIN_EMAILS), NO token falls back to the fixed
    #                      principal. Invalid token ⇒ 401, never the fallback
    #                      (a bad credential is a refusal, not anonymity).
    if principal is None and auth is None:
        raise ValueError("exactly one of principal / auth must be provided (or both: hybrid)")

    app = FastAPI(title="AI Orchestration Platform", version="0.1.0", docs_url=None)
    execution_store = store if store is not None else InMemoryExecutionStore()
    # 10 §13.4 explicit_models seam — composed over the SAME router and
    # execution service (Router still decides every branch; 02 inv. 5).
    multi_model_executor = MultiModelExecutor(router=router, execution=execution_service)
    skill_registry = skills if skills is not None else SkillRegistry()
    role_registry = roles if roles is not None else RoleRegistry()
    # Idempotency index (10 §10): (tenant_id, key) -> execution_id.
    # Injectable for horizontal replicas (T-IMPL-072); default process-local.
    if idempotency_index is None:
        idempotency_index = {}

    # --- AA-1 (IDN-1): per-request principal resolution -----------------------
    if auth is None:
        assert principal is not None  # checked above
        fixed_principal = principal

        def _principal(_request: Request) -> Principal | JSONResponse:
            return fixed_principal

    else:
        auth_surface = auth
        fallback_principal = principal  # None ⇒ strict; set ⇒ hybrid

        def _principal(_request: Request) -> Principal | JSONResponse:
            token = bearer_token(_request)
            if token is None:
                if fallback_principal is not None:
                    return fallback_principal
                return unauthenticated()
            try:
                user = auth_surface.identity.get_user_for_session(token)
            except SessionInvalid:
                return unauthenticated()
            return Principal(
                tenant_id=user.tenant_id,
                user_id=user.id,
                is_admin=user.email in auth_surface.admin_emails,
            )

        app.include_router(create_auth_router(auth_surface, fallback=fallback_principal))

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request body failed contract validation.",
            details={"errors": [str(err.get("msg", "")) for err in exc.errors()]},
        )

    @app.exception_handler(Exception)
    async def _internal_handler(_request: Request, _exc: Exception) -> JSONResponse:
        # 20 §4: internals never leak to clients.
        return error_response(ErrorCode.INTERNAL_ERROR, "Internal error.", retryable=False)

    # --- /v1/workspaces + /v1/projects (closure GAP 1) -------------------------
    # The EXISTING 03 §2 entities over HTTP — the ExecutionStorePort seam
    # posture: in-memory defaults keep the surface present in both
    # profiles; the composition root binds the EXISTING Postgres
    # repositories (bridged) in the durable profile. Same per-request
    # principal resolver, same anti-enumeration mapping as every other
    # tenant-scoped route (apps/api/workspaces.py records the decisions).
    app.include_router(
        create_workspace_router(
            workspaces=(workspaces if workspaces is not None else InMemoryWorkspaceStore()),
            projects=projects if projects is not None else InMemoryProjectStore(),
            resolve=_principal,
        )
    )

    @app.post("/v1/execute")
    async def execute(
        request: Request,
        body: ExecuteRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> Response:
        # --- identity FIRST (AA-1): an anonymous caller consumes no rate-
        # limit, replay, persistence, or composition work (zero residue).
        caller = _principal(request)
        if isinstance(caller, JSONResponse):
            return caller
        # --- API rate limit (41 §24; T-IMPL-070) — a limited caller
        # consumes no replay/persistence/composition work and leaves no state.
        if rate_limits is not None and execute_rate_limit > 0:
            within = await rate_limits.hit(
                f"execute:{caller.tenant_id}",
                execute_rate_limit,
                execute_rate_window_seconds,
            )
            if not within:
                return error_response(
                    ErrorCode.RATE_LIMITED,
                    "Rate limit exceeded for this tenant.",
                    retryable=True,
                    details={"scope": "execute"},
                )

        # --- loud scope rejections (module docstring posture) ------------------
        policy = body.execution_policy
        if policy is not None and policy.async_ is True and outbox is None:
            # Vision V2: async needs the outbox seam. Absent seam ⇒ the
            # SAME loud rejection this slice always gave (never a silent
            # fallback to sync — 20 §4).
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
        # --- agent strategy (R160): the SHARED core.agent runtime ------------
        # Absent seam ⇒ loud rejection (never a silent single-shot). Present
        # ⇒ the caller's ``tools`` allow-list is resolved against the
        # composition catalog (unknown ⇒ validation error); admission per
        # call is the Capability Firewall's, inside the runtime.
        agent_strategy = policy is not None and policy.strategy == AGENT_STRATEGY
        agent_tools: AgentToolSelection | None = None
        if agent_strategy:
            if agent is None:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Agent strategy is not available on this deployment slice.",
                    details={"field": "execution_policy.strategy"},
                )
            if policy is not None and policy.async_ is True:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Agent strategy runs synchronously in this slice.",
                    details={"field": "execution_policy.async"},
                )
            # R165: the caller may ask for LESS budget than the runtime cap,
            # never more — the cap is the operator's (S4); above it is loud.
            if policy is not None and policy.max_steps is not None:
                cap = agent.runtime.max_steps
                if policy.max_steps > cap:
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        f"execution_policy.max_steps exceeds this runtime's cap ({cap}).",
                        details={"field": "execution_policy.max_steps", "max": cap},
                    )
            # Allow-list names are validated HERE (before any admission work);
            # the full selection (skill-required tools) is made once skills
            # are admitted below — same catalog, one rule.
            try:
                agent.resolve(body.tools)
            except AgentToolsRejected as exc:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    str(exc),
                    details={"field": "tools.allowed", "unknown": exc.unknown},
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

        # --- skill admission (10 §7 selectable set; 41 §16 Selected Skills) -----
        # Explicit selection by MANIFEST id — validated against the SAME
        # registry the /v1/skills listing reads (one admission rule, P2).
        # Unknown or non-selectable ids refuse loudly (deny-by-default);
        # admitted skills ride the execution payload as DATA (their tools
        # remain inert — 03 §8, enforced by the tool gate, not here).
        admitted_skills: list[JsonObject] = []
        admitted_skill_objects: list[Skill] = []
        if body.skills:
            selectable = {skill.manifest.id: skill for skill in skill_registry.list_selectable()}
            seen_skill_ids: set[str] = set()
            for requested in body.skills:
                if requested in seen_skill_ids:
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        f"skill requested twice: {requested}",
                        details={"field": "skills"},
                    )
                seen_skill_ids.add(requested)
                skill = selectable.get(requested)
                if skill is None:
                    # Unknown and non-selectable are indistinguishable
                    # (20 §6 anti-enumeration — same denial for both).
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        f"skill is not selectable: {requested}",
                        details={"field": "skills"},
                    )
                admitted_skills.append(
                    {
                        "id": skill.manifest.id,
                        "name": skill.name,
                        "version": skill.version,
                    }
                )
                admitted_skill_objects.append(skill)
        elif role is not None:
            # --- AUTO skill resolution (41 §16) when the caller selected
            # nothing. EXPLICIT WINS: this branch never runs when body.skills
            # is supplied. The EXISTING SkillResolver chain (Task + Role +
            # Context → selectable candidates → compatibility → ranking)
            # decides — same registry admission rule as the explicit path
            # (ACTIVE/selectable only), same DATA-ONLY posture (a selected
            # skill's tools stay inert; the tool gate is untouched). The
            # role is REQUIRED input to the chain (compatibility gates on
            # role identity) — no admitted role ⇒ no auto selection, which
            # keeps the prior behavior for role-less asks. TaskAnalysis is
            # derived from THIS request honestly: generate_text task, no
            # invented capability requirements (an empty requirement set
            # gates nothing; ranking still orders by the role's preferred
            # skills). Auto-selected skills ride the payload in the SAME
            # id/name/version shape the explicit path uses.
            resolution = SkillResolver(skill_registry).resolve(
                task=TaskAnalysis(
                    task_type="generate_text",
                    complexity="unknown",
                    risk_level="unknown",
                ),
                role=RoleProfile(role=role),
                limit=1,
            )
            admitted_skills.extend(
                {
                    "id": skill.manifest.id,
                    "name": skill.name,
                    "version": skill.version,
                }
                for skill in resolution.selected
            )
            admitted_skill_objects.extend(resolution.selected)

        # --- R160 skill → tool intelligence (agent strategy only) --------------
        # Admitted skills disclose the tools their manifests REQUIRE when the
        # deployment offers them (03 §8: never a grant — the firewall still
        # decides per call). Missing ones are a named gap the model sees.
        if agent_strategy:
            assert agent is not None
            agent_tools = agent.select(body.tools, admitted_skill_objects)

        # --- idempotent replay (10 §10) ----------------------------------------
        # BEFORE persistence/composition: a replay must not duplicate turns.
        if idempotency_key is not None:
            replay_id = idempotency_index.get((caller.tenant_id, idempotency_key))
            if replay_id is not None:
                replayed = execution_store.get(caller.tenant_id, replay_id)
                if replayed.execution.status in (
                    ExecutionStatus.QUEUED,
                    ExecutionStatus.RUNNING,
                ):
                    # Async execution still in flight: the honest replay is
                    # the SAME 202 ack (10 §10 replay over the 10 §4 shape)
                    # — never a duplicate enqueue, never a fake result.
                    return _async_accepted(replayed.execution.id)
                return _sync_response(replayed, body)

        # --- conversation admission (13 §7; module-docstring decisions) ---------
        conversation: Conversation | None = None
        if conversations is not None and conversation_id is not None:
            try:
                conversation = conversations.get_conversation(caller.tenant_id, conversation_id)
            except ConversationNotFound:
                # Auto-create under the caller (recorded decision): absent
                # and foreign-tenant are indistinguishable (20 §6), so both
                # start a fresh conversation owned by the caller.
                conversation = conversations.create_conversation(
                    Conversation(
                        id=conversation_id,
                        tenant_id=caller.tenant_id,
                        user_id=caller.user_id,
                        title=body.ask[:80],
                        status=ConversationStatus.ACTIVE,
                    )
                )
            if conversation.user_id != caller.user_id:
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
                        tenant_id=caller.tenant_id,
                        user_id=caller.user_id,
                        ask=body.ask,
                        role_id=role.id if role is not None else None,
                        conversation_id=(conversation.id if conversation is not None else None),
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
                caller.tenant_id,
                Message(
                    id=uuid4(),
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content=body.ask,
                    created_at=utc_now(),
                ),
            )

        # --- resolve 10 §13.5 agent_node_mapping --------------------------------
        # Resolution order verbatim (node > agent default > request policy >
        # auto). A mapping WITH declared node policies is a REAL straight
        # node sequence: declaration order IS the execution order, every
        # node routes independently through the SAME Router below, and the
        # sequence executes via the EXISTING pipeline orchestration (each
        # node a distinct ExecutionNode record; previous output threads
        # forward). Richer graph semantics (branch/join/loop) are OUT of
        # this slice — nothing here accepts them. A mapping WITHOUT node
        # policies keeps the prior single-node behavior (key "single").
        effective_policy = body.model_policy
        node_sequence: list[tuple[str, NodeModelPolicy | None]] = []
        if isinstance(effective_policy, AgentNodeMappingPolicy):
            mapping_policy = effective_policy
            if mapping_policy.node_model_policies:
                node_sequence = [
                    (node_key, resolve_node_policy(mapping_policy, node_key))
                    for node_key in mapping_policy.node_model_policies
                ]
                effective_policy = None  # routed PER NODE below
            else:
                effective_policy = resolve_node_policy(mapping_policy, "single")

        # --- 10 §13.4 explicit_models: per-branch routing happens INSIDE the
        # MultiModelExecutor (Router still decides every branch); the single
        # up-front route below is skipped for this policy type.
        multi_model_policy = (
            effective_policy if isinstance(effective_policy, ExplicitModelsPolicy) else None
        )

        # --- route (11; Router decides) ----------------------------------------
        # Node-mapping path: ONE routing decision PER declared node — the
        # Router stays the single routing authority; per-node model policies
        # (rule 1) already resolved above, agent default (rule 2) filled the
        # gaps, None routes auto (rule 4). A node whose policy the Router
        # refuses (e.g. explicit_models inside a node) refuses the WHOLE
        # request loudly, named by node — never a silent downgrade.
        decision = None
        node_decisions: list[tuple[str, RoutingDecision]] = []
        if node_sequence:
            for node_key, node_policy in node_sequence:
                try:
                    node_decisions.append(
                        (
                            node_key,
                            router.route(
                                RoutingRequest(
                                    operation=ProviderOperation.GENERATE_TEXT,
                                    model_policy=node_policy,
                                )
                            ),
                        )
                    )
                except UnsupportedPolicyType as exc:
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        str(exc),
                        details={"field": "model_policy", "node": node_key},
                    )
                except NoEligibleCandidates as exc:
                    return error_response(
                        ErrorCode.MODEL_UNAVAILABLE,
                        f"No eligible model candidates for node '{node_key}'.",
                        details={
                            "node": node_key,
                            "excluded": [
                                record.model_dump(mode="json", exclude_none=True)
                                for record in exc.excluded
                            ],
                        },
                    )
                except FallbackNotConfigured as exc:
                    return error_response(ErrorCode.MODEL_UNAVAILABLE, str(exc))
        elif multi_model_policy is None:
            routing_request = RoutingRequest(
                operation=ProviderOperation.GENERATE_TEXT,
                model_policy=effective_policy,
            )
            try:
                decision = router.route(routing_request)
            except UnsupportedPolicyType as exc:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    str(exc),
                    details={"field": "model_policy"},
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
        if admitted_skills:
            # Admitted selections ride verbatim (id/name/version only — the
            # manifest content is registry data the executor can look up;
            # the payload never becomes a skill-content channel).
            payload["skills"] = admitted_skills
        if agent_tools is not None and (agent_tools.by_skill or agent_tools.unavailable):
            payload["skill_tools"] = agent_tools.describe()

        # --- ASYNC path (Vision V2; 10 §4): enqueue via the outbox, ack 202 -----
        if policy is not None and policy.async_ is True:
            if node_decisions:
                # The async worker re-routes a SINGLE decision at execution
                # time; multi-node sequencing on the async path is a separate
                # slice — refused loudly, never silently degraded (same
                # posture as explicit_models below).
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "agent_node_mapping with node policies is not supported "
                    "on the async path in this slice; run it synchronously.",
                    details={"field": "model_policy"},
                )
            if multi_model_policy is not None:
                # The async worker re-routes a SINGLE decision at execution
                # time; multi-model branch orchestration on the async path is
                # a separate slice — refused loudly, never silently degraded.
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "explicit_models is not supported on the async path "
                    "in this slice; run it synchronously.",
                    details={"field": "model_policy"},
                )
            assert outbox is not None  # guarded by the loud rejection above
            execution_id = uuid4()
            # Durable message FIRST (40 §4.2): everything the worker needs
            # to re-run the admitted request rides the flat payload — the
            # request body verbatim (contract JSON), the admitted identity,
            # and the pre-assigned execution id (the ack and the eventual
            # record MUST agree). The worker re-routes at execution time:
            # a RoutingDecision is a point-in-time selection; replaying a
            # stale one after minutes in the queue would defeat 11 §16's
            # point — the POLICY snapshot rides verbatim instead (inside
            # the request body), which is what routing honors.
            message_payload = {
                "execution_id": str(execution_id),
                "tenant_id": str(caller.tenant_id),
                "user_id": str(caller.user_id),
                "request": body.model_dump_json(by_alias=True, exclude_none=True),
                # The COMPOSED execution payload (ask + output + context/
                # role) — composition ran HERE, under this request's
                # admission; the worker consumes it verbatim and never
                # re-implements composition (P1/P2).
                "payload": json.dumps(payload, sort_keys=True),
                "request_hash": _request_hash(body),
            }
            if idempotency_key is not None:
                message_payload["idempotency_key"] = idempotency_key
            if conversation_id is not None:
                message_payload["conversation_id"] = str(conversation_id)
            await outbox.append(execute_stream, message_payload, f"execute:{execution_id}")
            # V6 chunk 3: stage execution.queued (10 §12) for the caller
            # tenant's matching subscriptions — SAME outbox, SAME durability
            # posture as the execute message itself (40 §4.2). No matching
            # subscription ⇒ nothing staged (silence is correct, not a
            # failure). Rows were URL-admitted at registration; staging
            # re-judges them (stage_execution_event validates again, P7).
            if webhook_subscriptions is not None:
                tenant_subscriptions = webhook_subscriptions.get(caller.tenant_id, [])
                if tenant_subscriptions:
                    await stage_execution_event(
                        outbox,
                        tenant_subscriptions,
                        event=WebhookEventType.EXECUTION_QUEUED,
                        execution_id=str(execution_id),
                        tenant_id=str(caller.tenant_id),
                        timestamp=utc_now(),
                    )
            # QUEUED placeholder so GET /v1/executions/{id} answers from
            # the ack onward (10 §5); the worker overwrites it with the
            # terminal report. Same store, same tenant scoping.
            placeholder = ExecutionReport(
                execution=Execution(
                    id=execution_id,
                    tenant_id=caller.tenant_id,
                    user_id=caller.user_id,
                    conversation_id=conversation_id,
                    request_hash=_request_hash(body),
                    idempotency_key=idempotency_key,
                    status=ExecutionStatus.QUEUED,
                    strategy=ExecutionStrategy.SINGLE,
                    cost_snapshot={},
                    created_at=utc_now(),
                ),
                nodes=(),
                status_history=(ExecutionStatus.QUEUED,),
            )
            execution_store.put(placeholder)
            if idempotency_key is not None:
                idempotency_index[(caller.tenant_id, idempotency_key)] = execution_id
            return _async_accepted(execution_id)

        try:
            if agent_strategy:
                assert agent is not None and agent_tools is not None
                outcome = await agent.runtime.run(
                    tenant_id=caller.tenant_id,
                    user_id=caller.user_id,
                    task=payload,
                    tools=list(agent_tools.tools),
                    model_policy=(
                        effective_policy
                        if multi_model_policy is None and not node_decisions
                        else None
                    ),
                    max_steps=policy.max_steps if policy is not None else None,
                    deadline_ms=policy.deadline_ms if policy is not None else None,
                    conversation_id=conversation_id,
                    idempotency_key=idempotency_key,
                    label={"surface": "v1.execute"},
                )
                report = outcome.execution_report
            elif node_decisions:
                # REAL node sequence: the EXISTING pipeline orchestration —
                # one PipelineStage per mapped node, each carrying ITS OWN
                # RoutingDecision (per-node model selection preserved);
                # distinct ExecutionNode records, deterministic declaration
                # order, previous output threaded forward, partial failure
                # recorded (failed node fails the run, the rest are skipped
                # — never hidden). No new engine; strategy=pipeline is the
                # honest record of what ran.
                report = await execution_service.execute_pipeline(
                    tenant_id=caller.tenant_id,
                    user_id=caller.user_id,
                    stages=[
                        PipelineStage(
                            node_key=node_key,
                            decision=node_decision,
                            operation=ProviderOperation.GENERATE_TEXT,
                            payload=payload,
                        )
                        for node_key, node_decision in node_decisions
                    ],
                    request_hash=_request_hash(body),
                    idempotency_key=idempotency_key,
                    conversation_id=conversation_id,
                )
            elif multi_model_policy is not None:
                # 10 §13.4: branches route+execute inside the executor; the
                # API responds with the strategy's final report (winner or
                # judge).
                try:
                    multi_report = await multi_model_executor.execute(
                        tenant_id=caller.tenant_id,
                        user_id=caller.user_id,
                        policy=multi_model_policy,
                        operation=ProviderOperation.GENERATE_TEXT,
                        payload=payload,
                        request_hash=_request_hash(body),
                        idempotency_key=idempotency_key,
                        conversation_id=conversation_id,
                    )
                except (UnsupportedStrategy, InvalidJudgePolicy) as exc:
                    return error_response(
                        ErrorCode.VALIDATION_ERROR,
                        str(exc),
                        details={"field": "model_policy"},
                    )
                except CompareRefused as exc:
                    return error_response(ErrorCode.MODEL_UNAVAILABLE, str(exc))
                report = multi_report.final_report
            else:
                assert decision is not None  # routed above
                report = await execution_service.execute_single(
                    tenant_id=caller.tenant_id,
                    user_id=caller.user_id,
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
            idempotency_index[(caller.tenant_id, idempotency_key)] = report.execution.id
        # --- persist the assistant turn (succeeded only; same content) ----------
        if (
            conversations is not None
            and conversation is not None
            and report.execution.status is ExecutionStatus.SUCCEEDED
            and report.final_output is not None
        ):
            format_hint = body.output.format if body.output is not None else None
            conversations.append_message(
                caller.tenant_id,
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
            provenance = _context_provenance(report, report.execution.tenant_id, memory)
            sync = ExecuteSyncResponse(
                execution_id=str(report.execution.id),
                status=report.execution.status,
                result=_result_from_output(
                    output, format_hint, [provenance] if provenance else None
                ),
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
            str(report.execution.id),
            _last_provider_error(report),
            agent_failure=_agent_failure(report),
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
            skills=[SkillListEntry.from_skill(skill) for skill in skill_registry.list_selectable()]
        )
        return JSONResponse(
            status_code=200,
            content=response.model_dump(mode="json", exclude_none=True),
        )

    # --- GET /v1/agent-tools (R160): the offered agent tool catalog ------------
    # The external-consumption seam: what a caller MAY name in
    # ``tools.allowed`` for ``execution_policy.strategy="agent"``. Composition
    # DATA only (name/description/arguments/permission/risk) — per-call
    # admission remains the Capability Firewall's. Absent agent seam ⇒ absent
    # route (nothing to probe, 20 §4). Tenant-authenticated like every list.
    if agent is not None:
        agent_surface = agent

        @app.get("/v1/agent-tools")
        async def list_agent_tools(request: Request) -> Response:
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            return JSONResponse(
                status_code=200,
                content={
                    "strategy": AGENT_STRATEGY,
                    "max_steps": agent_surface.runtime.max_steps,
                    "tools": agent_surface.offered(),
                },
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
                    ModelListEntry.from_model(model, binding_registry.bindings_for_model(model.id))
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
        async def usage_summary(request: Request) -> Response:
            """GET /v1/usage (10 §8): the caller tenant's plan + budgets.

            Tenant-scoped by the principal (never a client-supplied tenant
            id — 20 §6 anti-enumeration); an unconfigured tenant denies
            with the same entitlement_exceeded mapping as /v1/execute.
            """
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            try:
                summary = usage_accounting.summary(caller.tenant_id)
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
        # Tenant-scoped subscription store — injectable for horizontal
        # replicas (T-IMPL-072); default process-local (docstring posture).
        if webhook_subscriptions is None:
            webhook_subscriptions = {}

        @app.post("/v1/webhooks", status_code=201)
        async def register_webhook(request: Request, body: WebhookSubscriptionRequest) -> Response:
            """POST /v1/webhooks: register a subscription for the caller tenant.

            ``events`` absent ⇒ all six documented 10 §12 types (the closed
            set is the universe — recorded in core/contracts/webhooks.py);
            an empty explicit list is a contradiction and refuses loudly.
            Delivery itself rides the V6 outbox chain when composed.

            V6 chunk 3: the URL passes SSRF admission (validate_webhook_url,
            core/events) AT REGISTRATION — an inadmissible target is refused
            with a NAMED 422 before any row exists (P7; the validator runs
            AGAIN at staging and at delivery — this gate is the first of
            three, not the only one).
            """
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            try:
                validate_webhook_url(body.url)
            except WebhookUrlRefused as exc:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    f"webhook url refused: {exc.reason}",
                    details={"field": "url"},
                )
            if body.events is not None and len(body.events) == 0:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "events must be omitted (all types) or non-empty.",
                    details={"field": "events"},
                )
            events = list(body.events) if body.events is not None else list(WebhookEventType)
            subscription = WebhookSubscription(
                id=uuid4(),
                tenant_id=caller.tenant_id,
                url=body.url,
                events=events,
            )
            webhook_subscriptions.setdefault(caller.tenant_id, []).append(subscription)
            response = WebhookSubscriptionResponse.from_subscription(subscription)
            return JSONResponse(
                status_code=201,
                content=response.model_dump(mode="json", exclude_none=True),
            )

        # --- AA-1 seam WBH-1: list/delete over the SAME subscription map --------

        @app.get("/v1/webhooks")
        async def list_webhooks(request: Request) -> Response:
            """GET /v1/webhooks: the caller tenant's OWN subscriptions only."""
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            rows = webhook_subscriptions.get(caller.tenant_id, [])
            return JSONResponse(
                status_code=200,
                content={
                    "webhooks": [
                        WebhookSubscriptionResponse.from_subscription(s).model_dump(
                            mode="json", exclude_none=True
                        )
                        for s in rows
                    ]
                },
            )

        @app.delete("/v1/webhooks/{subscription_id}")
        async def delete_webhook(request: Request, subscription_id: str) -> Response:
            """DELETE /v1/webhooks/{id}: caller-tenant rows ONLY (20 §6).

            Unknown and foreign-tenant ids are byte-identical 404s — the
            search never leaves the caller's own subscription list.
            """
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            try:
                parsed = UUID(subscription_id)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "subscription id must be a UUID.",
                    details={"field": "subscription_id"},
                )
            rows = webhook_subscriptions.get(caller.tenant_id, [])
            for index, subscription in enumerate(rows):
                if subscription.id == parsed:
                    del rows[index]
                    return Response(status_code=204)
            # Recorded unknown-resource mapping: validation_error body,
            # HTTP 404 — identical for absent and foreign (20 §6).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown webhook subscription id.",
                details={"subscription_id": subscription_id},
                http_status=404,
            )

    @app.get("/v1/executions")
    async def executions_list(
        request: Request,
        status: str | None = None,
        initiated_by: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        limit: int | None = None,
    ) -> Response:
        """GET /v1/executions (AA-1 seam EXE-1): tenant-scoped list.

        Rows are the 10 §5 status shape + initiated_by/created_at; NO
        result bodies (the by-id route serves those — a list is not a
        bulk-exfil surface). All filter parse failures are named 422s.
        """
        caller = _principal(request)
        if isinstance(caller, JSONResponse):
            return caller
        parsed_status: ExecutionStatus | None = None
        if status is not None:
            try:
                parsed_status = ExecutionStatus(status)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Unknown execution status.",
                    details={"field": "status"},
                )
        parsed_initiated_by: UUID | None = None
        if initiated_by is not None:
            try:
                parsed_initiated_by = UUID(initiated_by)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "initiated_by must be a UUID.",
                    details={"field": "initiated_by"},
                )

        def _parse_time(value: str, field: str) -> datetime | JSONResponse:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    f"{field} must be an ISO-8601 timestamp.",
                    details={"field": field},
                )

        parsed_after: datetime | None = None
        if created_after is not None:
            after = _parse_time(created_after, "created_after")
            if isinstance(after, JSONResponse):
                return after
            parsed_after = after
        parsed_before: datetime | None = None
        if created_before is not None:
            before = _parse_time(created_before, "created_before")
            if isinstance(before, JSONResponse):
                return before
            parsed_before = before
        if limit is not None and limit < 1:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "limit must be >= 1.",
                details={"field": "limit"},
            )
        reports = execution_store.list(
            caller.tenant_id,
            status=parsed_status,
            initiated_by=parsed_initiated_by,
            created_after=parsed_after,
            created_before=parsed_before,
            limit=limit,
        )
        rows = [
            {
                "execution_id": str(r.execution.id),
                "status": r.execution.status.value,
                "initiated_by": str(r.execution.user_id),
                "created_at": r.execution.created_at.isoformat(),
                "progress": _progress(r).model_dump(mode="json", exclude_none=True),
            }
            for r in reports
        ]
        return JSONResponse(status_code=200, content={"executions": rows})

    @app.get("/v1/executions/{execution_id}")
    async def execution_status(request: Request, execution_id: str) -> Response:
        caller = _principal(request)
        if isinstance(caller, JSONResponse):
            return caller
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
            report = execution_store.get(caller.tenant_id, parsed)
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
            provenance = _context_provenance(report, caller.tenant_id, memory)
            result = _result_from_output(
                report.final_output, None, [provenance] if provenance else None
            )
        elif status is ExecutionStatus.FAILED:
            error_detail = execution_failure_detail(
                execution_id,
                _last_provider_error(report),
                agent_failure=_agent_failure(report),
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

    # --- GET /v1/executions/{id}/events (Vision V6): SSE progress -------------
    # Opt-in seam (``sse=True``) — absent, the route does not exist at all
    # (20 §4). Emits the EXISTING 10 §11 StreamEvent shapes DERIVED from
    # the stored report (apps/api/streaming.py decisions); tenant scoping
    # and the 404 mapping are byte-identical to the status route above.
    if sse:

        @app.get("/v1/executions/{execution_id}/events")
        async def execution_events(request: Request, execution_id: str) -> Response:
            caller = _principal(request)
            if isinstance(caller, JSONResponse):
                return caller
            try:
                parsed = UUID(execution_id)
            except ValueError:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "execution id must be a UUID.",
                    details={"field": "execution_id"},
                )
            tenant_id = caller.tenant_id
            try:
                # Existence + tenant scoping decided BEFORE any stream
                # starts — the 404 is a plain JSON error, never a stream.
                execution_store.get(tenant_id, parsed)
            except ExecutionNotFound:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "Unknown execution id.",
                    details={"execution_id": execution_id},
                    http_status=404,
                )

            def _load() -> ExecutionReport:
                return execution_store.get(tenant_id, parsed)

            return StreamingResponse(
                event_stream(
                    _load,
                    poll_interval_seconds=sse_poll_interval_seconds,
                    timeout_seconds=sse_timeout_seconds,
                    sleeper=sse_sleeper,
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )

    # --- GET /healthz (AA-1 seam SYS-1): opt-in process liveness --------------
    if healthz:

        @app.get("/healthz")
        async def health() -> Response:
            """Process liveness ONLY — labeled, never fleet claims (41 §49).

            Unauthenticated BY DESIGN: liveness probes cannot carry
            sessions; the body contains no tenant data.
            """
            return JSONResponse(
                status_code=200,
                content={
                    "status": "alive",
                    "scope": "process",
                    "time": utc_now().isoformat(),
                },
            )

    # --- Capability Catalog derivation (Vision V7 chunk 1) --------------------
    # Derived HERE because create_app is the only place that knows which
    # seams were actually composed (module header of apps/api/capabilities).
    # Each row's state comes from the SAME variable that mounted (or did
    # not mount) the corresponding surface above — honesty by construction.
    def _cap(cap_id: str, available: bool, evidence: str) -> Capability:
        return Capability(
            id=cap_id,
            state=CapabilityState.AVAILABLE if available else CapabilityState.INERT,
            evidence=evidence,
        )

    capability_catalog: tuple[Capability, ...] = (
        _cap("execute.sync", True, "POST /v1/execute (always mounted)"),
        _cap(
            "execute.async",
            outbox is not None,
            "outbox seam -> 202 path (V2); core/runtime/outbox.py",
        ),
        # Recorded UNAVAILABLE (V6-2): inline token streaming needs
        # streaming provider adapters, which do not exist in the repo.
        Capability(
            id="execute.token_streaming",
            state=CapabilityState.UNAVAILABLE,
            evidence="no streaming provider adapters exist (R115/V6-2 record)",
        ),
        _cap(
            "executions.progress_sse",
            sse,
            "sse seam -> GET /v1/executions/{id}/events (V6-2)",
        ),
        _cap(
            "conversations.persistence",
            conversations is not None,
            "conversations seam; core/memory/ports.py",
        ),
        _cap(
            "context.composition",
            composer is not None,
            "composer seam; core/context (13 §5)",
        ),
        _cap(
            "models.listing",
            models is not None and bindings is not None,
            "models+bindings seams -> GET /v1/models (10 §6)",
        ),
        _cap("skills.listing", True, "GET /v1/skills over the skill registry"),
        _cap(
            "usage.reporting",
            usage is not None,
            "usage seam -> GET /v1/usage (10 §8)",
        ),
        _cap(
            "webhooks.registration",
            webhooks,
            "webhooks seam -> POST /v1/webhooks (41 §21)",
        ),
        _cap(
            "webhooks.delivery_staging",
            webhooks and outbox is not None,
            "webhooks+outbox seams -> execution.queued staging (V6-3)",
        ),
        _cap(
            "admin.control_plane",
            admin is not None,
            "admin seam -> /v1/admin/* (T-IMPL-032)",
        ),
        _cap(
            "learning.lifecycle",
            admin is not None and memory is not None,
            "learning lifecycle seam -> /v1/admin/learning/* (R158; core/learning/lifecycle.py)",
        ),
        _cap(
            "rate_limits.execute",
            rate_limits is not None and execute_rate_limit > 0,
            "rate_limits seam + configured limit (T-IMPL-070)",
        ),
        _cap(
            "auth.sessions",
            auth is not None,
            "auth seam -> /v1/auth/* (AA-1 IDN-1)",
        ),
        _cap("health.liveness", healthz, "healthz seam -> GET /healthz (SYS-1)"),
    )
    # One derivation, two consumers (module header): the admin route below
    # AND the composition root (which hands the SAME tuple to the agent's
    # AgentToolSurface) read this attribute — zero parallel derivations.
    app.state.capability_catalog = capability_catalog

    # --- Capability Exercise Surface (Vision V7 chunk 2) ----------------------
    # REAL probes over the SAME composed machinery the catalog rows point
    # at (apps/api/exercise.py header) — registered ONLY for AVAILABLE
    # capabilities whose exercise is a safe, budget-bounded read/execute.
    # A capability without a registered probe is honestly not exercisable
    # (the surface lists exactly what has a real probe, 41 §49).
    async def _exercise_execute_sync(caller: Principal) -> JsonObject:
        # Identical posture to the agent's R1 run_test_execution: a REAL
        # execution over the real path, billed to the caller's tenant,
        # labeled machine-checkably in the stored node's input_ref.
        probe_payload: JsonObject = {
            "ask": "capability exercise probe",
            "context": {"metadata": {EXERCISE_LABEL_KEY: {"kind": "probe"}}},
        }
        try:
            probe_decision = router.route(RoutingRequest(operation=ProviderOperation.GENERATE_TEXT))
        except (
            NoEligibleCandidates,
            FallbackNotConfigured,
            UnsupportedPolicyType,
        ) as exc:
            return {"exercised": False, "error": f"routing failed: {type(exc).__name__}"}
        probe_hash = hashlib.sha256(
            json.dumps(probe_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            probe_report = await execution_service.execute_single(
                tenant_id=caller.tenant_id,
                user_id=caller.user_id,
                decision=probe_decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=probe_payload,
                request_hash=probe_hash,
            )
        except BudgetExceeded as exc:
            return {
                "exercised": False,
                "error": "budget exceeded",
                "requested": exc.requested,
                "remaining": exc.remaining,
            }
        except EntitlementNotConfigured:
            return {
                "exercised": False,
                "error": "no entitlement configured for this tenant",
            }
        execution_store.put(probe_report)
        return {
            # Honest verdict: exercised means the machinery RAN and stored
            # a record — the stored status is the evidence, success or not.
            "exercised": True,
            "evidence": {
                "kind": "execution",
                "execution_id": str(probe_report.execution.id),
                "status": probe_report.execution.status.value,
            },
        }

    async def _exercise_skills_listing(caller: Principal) -> JsonObject:
        rows = skill_registry.list_selectable()
        return {
            "exercised": True,
            "evidence": {
                "kind": "system",
                "selectable_count": len(rows),
                "source": "SkillRegistry.list_selectable",
            },
        }

    exercise_handlers: dict[str, ExerciseHandler] = {
        "execute.sync": _exercise_execute_sync,
        "skills.listing": _exercise_skills_listing,
    }
    if usage is not None:
        usage_port = usage

        async def _exercise_usage_reporting(caller: Principal) -> JsonObject:
            try:
                summary = usage_port.summary(caller.tenant_id)
            except EntitlementNotConfigured:
                return {
                    "exercised": False,
                    "error": "no entitlement configured for this tenant",
                }
            return {
                "exercised": True,
                "evidence": {
                    "kind": "usage_summary",
                    "plan": summary.plan,
                    "task_units_limit": summary.task_units.limit,
                },
            }

        exercise_handlers["usage.reporting"] = _exercise_usage_reporting
    if models is not None and bindings is not None:
        model_registry_probe = models

        async def _exercise_models_listing(caller: Principal) -> JsonObject:
            active = model_registry_probe.active_models()
            return {
                "exercised": True,
                "evidence": {
                    "kind": "system",
                    "active_model_count": len(active),
                    "source": "ModelRegistry.active_models",
                },
            }

        exercise_handlers["models.listing"] = _exercise_models_listing
    exercise_surface = ExerciseSurface(exercise_handlers)
    app.state.exercise_surface = exercise_surface

    # --- V7 chunk 3: Test Scenarios → Regression Center -----------------------
    # Composed with the SAME router/execution service/store user traffic
    # rides (P1): a scenario replay is a real, labeled, billed execution.
    # One service, two consumers (admin routes + agent tools, P3).
    scenario_service = ScenarioService(
        router=router,
        execution_service=execution_service,
        execution_store=execution_store,
    )
    app.state.scenario_service = scenario_service

    # --- V7 chunk 4: Context Validation Lab ------------------------------------
    # Exists ONLY when a composer is composed (nothing to validate without
    # one — 20 §4 absent seam). Dry-runs the SAME composer instance the
    # execute path composes with; conversation ownership is admitted through
    # the SAME conversations store (13 §7). One lab, two consumers (P3).
    context_lab_service: ContextLabService | None = None
    if composer is not None:
        context_lab_service = ContextLabService(
            composer=composer,
            conversations=conversations,
        )
    app.state.context_lab_service = context_lab_service

    # --- V7 chunk 5: Learning observability -------------------------------------
    # Composed over the SAME audit log and admin service the admin surface
    # carries (P1 — one store, two consumers); exists ONLY when an admin
    # surface exists (it is an admin review instrument, 20 §4).
    learning_observability_service: LearningObservabilityService | None = None
    if admin is not None:
        learning_observability_service = LearningObservabilityService(
            audit=admin.audit,
            admin_service=admin.service,
        )
    app.state.learning_observability_service = learning_observability_service

    # --- R158: Learning lifecycle (22 §8 operator over EXISTING components) ----
    # Composed ONLY with an admin surface (its management surface, 20 §4)
    # AND a memory seam (the knowledge substrate). Knowledge rides the SAME
    # memory store the context composer reads (P1: one retrieval substrate,
    # two consumers); promotion audits into the SAME audit log the admin
    # surface carries; evaluation delegates to a policy service over the
    # EXISTING evaluation store.
    learning_lifecycle_service: LearningLifecycleService | None = None
    if admin is not None and memory is not None:
        learning_lifecycle_service = LearningLifecycleService(
            evaluation=EvaluationPolicyService(store=InMemoryEvaluationStore()),
            knowledge=memory,
            audit=admin.audit,
            eligibility_gate=TrainingEligibilityGate(minimum_level=VerificationLevel.RAW),
        )
    app.state.learning_lifecycle_service = learning_lifecycle_service

    # --- V8: R3 Source-Change Workflow (ADR-0009) --------------------------------
    # Composed ONLY when an admin surface exists (a human-only admin
    # instrument, 20 §4). Hermetic end to end: in-memory stores, in-process
    # sandbox, and — THE §14 GATE — authoritative_applier=None. That None
    # is deliberate and operator-gated: no AuthoritativeApplierPort
    # implementation exists anywhere in this repository, so applied
    # proposals live in the snapshot store's space only and can never
    # touch authoritative source. Activation later = implement + compose
    # the port (a composition act, criterion 12) — after the operator
    # clears the 5 open credential items.
    # P-B seam (ADR-0010 "persisting is not applying"): the STORES are
    # injectable so the composition root can bind the durable P-A.3
    # implementations; absent, the in-memory defaults keep this slice
    # byte-identical. The applier gate below is NOT a parameter and
    # remains None regardless of what stores are bound.
    source_change_workflow: SourceChangeWorkflow | None = None
    if admin is not None:
        source_change_workflow = SourceChangeWorkflow(
            proposals=(
                source_proposals if source_proposals is not None else InMemoryProposalStore()
            ),
            snapshots=(
                source_snapshots if source_snapshots is not None else InMemorySnapshotStore()
            ),
            sandbox=HermeticSandbox(),
            suite=VerificationSuite(name="default", checks=_SOURCE_CHECKS),
            audit=admin.audit,
            authoritative_applier=None,  # §14 OPERATOR GATE — never wired in V8
        )
    app.state.source_change_workflow = source_change_workflow

    # --- V7 chunk 6: Self-Review + Change Impact Simulator ----------------------
    # Assembly over the SAME derivations this root already made (catalog
    # tuple, scenario service, observability service) plus the admin
    # lifecycle — exists ONLY when an admin surface exists (it reviews and
    # proposes through admin machinery, 20 §4). NEVER calls publish.
    # Built AFTER the R3 workflow (R161) so the evolution section can quote
    # the workflow's own §14 authoritative-apply status.
    self_review_service: SelfReviewService | None = None
    if admin is not None:
        self_review_service = SelfReviewService(
            admin_service=admin.service,
            catalog=capability_catalog,
            scenarios=scenario_service,
            observability=learning_observability_service,
            # R161: the two self-evolution lanes, reported with their gates.
            learning=learning_lifecycle_service,
            source_changes=source_change_workflow,
        )
    app.state.self_review_service = self_review_service

    # --- /v1/admin/* (T-IMPL-032): mounted ONLY when a surface is injected ----
    if admin is not None:
        app.include_router(
            create_admin_router(
                admin,
                resolve=_principal,
                system_info=system_info,
                capabilities=capability_catalog,
                exercise=exercise_surface,
                scenarios=scenario_service,
                context_lab=context_lab_service,
                learning_observability=learning_observability_service,
                learning_lifecycle=learning_lifecycle_service,
                execution_store=execution_store,
                self_review=self_review_service,
                source_changes=source_change_workflow,
                memory=memory,
                engineering=engineering_admin,
            )
        )

    return app
