"""Admin agent tool set — R0 reads + R1 test execution + R2 lifecycle drafts.

AA-2 shipped 7 × R0 + 1 × R1; AA-3 added 3 × R2 lifecycle tools; Vision V7
chunk 1 added the optional R0 ``list_capabilities`` (registered only when
the composition root hands the surface a derived catalog).

Every tool is a thin surface over EXISTING platform machinery (registries,
stores, ports) — the agent adds no parallel state (doc A §3.2 rule 3).
Every result passes :func:`~apps.admin_agent.secrecy.scrub_object` before
it can reach a transcript.

R1 labeling (acceptance criterion 2): ``run_test_execution`` builds its
payload with ``{"context": {"metadata": {"admin_agent": {...}}}}``. The
execution service stores the payload VERBATIM in the node's ``input_ref``
(verified: core/execution/service.py) — so the label is machine-checkable
from the recorded ExecutionNode with NO new persistence mechanism.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from apps.admin_agent.contracts import AA3_REGISTRABLE_CLASSES, ToolClass
from apps.admin_agent.dispatcher import ToolRegistry, ToolSpec
from apps.admin_agent.secrecy import scrub_object
from apps.api.admin import AdminSurface
from apps.api.app import Principal
from apps.api.capabilities import Capability, catalog_json
from apps.api.context_lab import (
    ContextLabRequest,
    ContextLabService,
    ConversationNotAdmitted,
)
from apps.api.exercise import ExerciseSurface
from apps.api.learning_observability import LearningObservabilityService
from apps.api.scenarios import (
    SCENARIO_CHECKS,
    ScenarioNotFound,
    ScenarioService,
    UnknownCheckName,
    scenario_json,
)
from apps.api.self_review import SelfReviewService
from apps.api.store import ExecutionStorePort
from core.admin.errors import (
    ChangeNotFound,
    InactiveAdminArea,
    InvalidLifecycleTransition,
)
from core.audit.ports import AuditLogPort
from core.contracts.admin import AdminAction, ConfigChange
from core.contracts.base import JsonObject
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.execution.service import ExecutionReport, ExecutionService
from core.providers.registry import ModelRegistry, ProviderRegistry
from core.routing.errors import FallbackNotConfigured, NoEligibleCandidates
from core.routing.router import SimpleScoringRouter, UnsupportedPolicyType
from core.tools.source_reader import SourceReader, SourceReadRefused
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured
from core.usage.memory import InMemoryUsageAccounting

#: The metadata key that labels agent-initiated executions (criterion 2).
AGENT_LABEL_KEY = "admin_agent"


@dataclass(frozen=True)
class AgentToolSurface:
    """Everything the agent's tools compose over — injected, existing."""

    providers: ProviderRegistry
    models: ModelRegistry
    router: SimpleScoringRouter
    execution_service: ExecutionService
    # Widened to the structural port (P2 posture recorded in apps/api/store.py:
    # "widen the annotation, never rewrite call sites") so the composition root
    # can hand the SAME store instance in BOTH profiles — InMemoryExecutionStore
    # and DurableExecutionStore each satisfy this surface verbatim.
    execution_store: ExecutionStorePort
    admin: AdminSurface
    usage: InMemoryUsageAccounting
    audit: AuditLogPort
    #: V7 chunk 1 — the SAME derived catalog create_app hands the admin
    #: route (one derivation, two consumers; read it from
    #: ``app.state.capability_catalog``). Optional (P2): absent seam =
    #: absent tool, and every pre-V7 construction stays valid verbatim.
    capabilities: tuple[Capability, ...] | None = None
    #: V7 chunk 2 — the SAME probe registry the admin exercise route
    #: dispatches (read it from ``app.state.exercise_surface``). Optional
    #: (P2): absent seam = absent tools — one registry, two consumers.
    exercise: ExerciseSurface | None = None
    #: V7 chunk 3 — the SAME scenario service the /v1/admin/scenarios
    #: routes dispatch (read it from ``app.state.scenario_service``).
    #: Optional (P2): absent seam = absent tools — one store, two consumers.
    scenarios: ScenarioService | None = None
    #: V7 chunk 4 — the SAME lab service the /v1/admin/context-lab routes
    #: dispatch (read it from ``app.state.context_lab_service``). Optional
    #: (P2): absent composer = absent lab = absent tools.
    context_lab: ContextLabService | None = None
    #: V7 chunk 5 — the SAME observability service the /v1/admin/learning/*
    #: review routes dispatch (read it from
    #: ``app.state.learning_observability_service``). Optional (P2).
    learning_observability: LearningObservabilityService | None = None
    #: V7 chunk 6 — the SAME service the /v1/admin/self-review and
    #: /v1/admin/changes/propose routes dispatch (read it from
    #: ``app.state.self_review_service``). Optional (P2).
    self_review: SelfReviewService | None = None
    #: Mandate §9 — bounded read-only source inspection over the shared
    #: :class:`core.tools.source_reader.SourceReader` primitive. Optional
    #: (P2): absent reader = absent tools — no composition is forced to
    #: expose its filesystem. The reader's own jail/denylist/caps hold;
    #: every result additionally passes scrub_object like all other tools.
    repo_reader: SourceReader | None = None


def _report_row(report: ExecutionReport) -> JsonObject:
    """One executions-list row — 10 §5 shape, ledger null-honest."""
    execution = report.execution
    ledger: JsonObject | None = None
    if report.usage is not None:
        ledger = {
            "status": report.usage.status.value,
            "units_reserved": report.usage.units_reserved,
            "units_settled": report.usage.units_settled,
        }
    return {
        "execution_id": str(execution.id),
        "status": execution.status.value,
        "created_at": execution.created_at.isoformat(),
        "strategy": execution.strategy.value,
        "ledger": ledger,
    }


def build_registry(surface: AgentToolSurface) -> ToolRegistry:
    """The AA-2 tool registry as configuration data — R0/R1 ONLY."""

    async def list_models(caller: Principal, args: JsonObject) -> JsonObject:
        rows = [
            {
                "model_key": m.model_key,
                "display_name": m.display_name,
                "tier": m.tier.value,
                "status": m.status.value,
                "capabilities": list(m.capabilities),
            }
            for m in surface.models.all_models()
        ]
        return scrub_object({"models": rows})

    async def list_providers(caller: Principal, args: JsonObject) -> JsonObject:
        rows = []
        for key in surface.providers.all_keys():
            entry = surface.providers.get(key)
            rows.append(
                {
                    "provider_key": entry.provider.provider_key,
                    "display_name": entry.provider.display_name,
                    "status": entry.provider.status.value,
                    "is_template": entry.is_template,
                    "is_routable": entry.is_routable,
                }
            )
        return scrub_object({"providers": rows})

    async def read_execution(caller: Principal, args: JsonObject) -> JsonObject:
        raw = args.get("execution_id")
        try:
            execution_id = UUID(str(raw))
            report = surface.execution_store.get(caller.tenant_id, execution_id)
        except (ValueError, KeyError):
            # Anti-enumeration: absent and foreign are the same answer.
            return {"error": "unknown execution id"}
        return scrub_object(_report_row(report))

    async def list_executions(caller: Principal, args: JsonObject) -> JsonObject:
        reports = surface.execution_store.list(caller.tenant_id, limit=50)
        return scrub_object({"executions": [_report_row(r) for r in reports]})

    async def usage_summary(caller: Principal, args: JsonObject) -> JsonObject:
        try:
            summary = surface.usage.summary(caller.tenant_id)
        except EntitlementNotConfigured:
            return {"error": "no entitlement configured for this tenant"}
        return scrub_object(
            {
                "plan": summary.plan,
                "task_units": {
                    "limit": summary.task_units.limit,
                    "used": summary.task_units.used,
                    "remaining": summary.task_units.remaining,
                },
            }
        )

    async def read_audit(caller: Principal, args: JsonObject) -> JsonObject:
        events = surface.audit.read(caller.tenant_id, limit=50)
        rows = [
            {
                "audit_event_id": str(e.id),
                "event_type": e.event_type.value,
                "occurred_at": e.occurred_at.isoformat(),
                "details": e.details,
            }
            for e in events
        ]
        return scrub_object({"events": rows})

    def _change_row(change: ConfigChange) -> JsonObject:
        row: JsonObject = {
            "change_id": str(change.id),
            "area": change.area.value,
            "action": change.action.value,
            "state": change.state.value,
            "created_at": change.created_at.isoformat(),
        }
        if change.validation_result is not None:
            row["validation_result"] = change.validation_result
        if change.impact_preview is not None:
            row["impact_preview"] = change.impact_preview
        return row

    async def list_changes(caller: Principal, args: JsonObject) -> JsonObject:
        changes = surface.admin.service.list_changes(caller.tenant_id)
        return scrub_object({"changes": [_change_row(c) for c in changes]})

    async def run_test_execution(caller: Principal, args: JsonObject) -> JsonObject:
        """R1: a REAL, budget-bounded, labeled execution over the real path."""
        ask = str(args.get("ask", "admin agent R1 test"))
        label: JsonObject = {"kind": "r1_test"}
        purpose = args.get("purpose")
        if purpose is not None:
            label["purpose"] = str(purpose)[:512]
        payload: JsonObject = {
            "ask": ask,
            "context": {"metadata": {AGENT_LABEL_KEY: label}},
        }
        try:
            decision = surface.router.route(
                RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
            )
        except (NoEligibleCandidates, FallbackNotConfigured, UnsupportedPolicyType) as exc:
            return {"error": f"routing failed: {type(exc).__name__}"}
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            report = await surface.execution_service.execute_single(
                tenant_id=caller.tenant_id,
                user_id=caller.user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=request_hash,
            )
        except BudgetExceeded as exc:
            return {
                "error": "budget exceeded",
                "requested": exc.requested,
                "remaining": exc.remaining,
            }
        except EntitlementNotConfigured:
            return {"error": "no entitlement configured for this tenant"}
        surface.execution_store.put(report)
        return scrub_object(_report_row(report))

    # --- R2 tools (AA-3, doc C §5): the EXISTING lifecycle, used verbatim ------
    #
    # These handlers call the SAME AdminConfigService the /v1/admin HTTP
    # routes call — an Agent-drafted change is structurally the same record
    # as a form-drafted one (criterion 1). Publish and rollback have NO
    # handler and NO ToolSpec here: they are explicit human UI acts
    # (criterion 2, proven structurally — the tool does not exist).

    async def draft_change(caller: Principal, args: JsonObject) -> JsonObject:
        raw_action = str(args.get("action", ""))
        try:
            action = AdminAction(raw_action)
        except ValueError:
            return {"error": f"unknown admin action: {raw_action[:100]}"}
        payload = args.get("payload") or {}
        if not isinstance(payload, dict):
            return {"error": "payload must be a JSON object"}
        try:
            change = surface.admin.service.draft(
                tenant_id=caller.tenant_id,
                actor_id=caller.user_id,
                action=action,
                payload=payload,
            )
        except InactiveAdminArea as exc:
            return {"error": str(exc)}
        return scrub_object(_change_row(change))

    def _lifecycle_tool_step(caller: Principal, args: JsonObject, step: str) -> JsonObject:
        raw = args.get("change_id")
        try:
            change_id = UUID(str(raw))
        except ValueError:
            return {"error": "unknown change id"}
        try:
            if step == "validate":
                change = surface.admin.service.validate(caller.tenant_id, change_id)
            else:
                change = surface.admin.service.preview(caller.tenant_id, change_id)
        except ChangeNotFound:
            # Anti-enumeration: absent and foreign-tenant are the same answer.
            return {"error": "unknown change id"}
        except InvalidLifecycleTransition as exc:
            return {"error": str(exc)}
        return scrub_object(_change_row(change))

    async def validate_change(caller: Principal, args: JsonObject) -> JsonObject:
        return _lifecycle_tool_step(caller, args, "validate")

    async def preview_change(caller: Principal, args: JsonObject) -> JsonObject:
        return _lifecycle_tool_step(caller, args, "preview")

    # --- V7 chunk 1: R0 capability catalog (registered ONLY when composed) ----
    #
    # ``catalog_json`` is validated once here (completeness + duplicates fail
    # at registry construction, never mid-dispatch) and the frozen payload is
    # what every call renders — the agent reads composition truth, it cannot
    # invent capability claims (P6: narration follows stored truth).
    capability_specs: list[ToolSpec] = []
    if surface.capabilities is not None:
        capability_payload = catalog_json(surface.capabilities)

        async def list_capabilities(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object(capability_payload)

        capability_specs.append(
            ToolSpec(
                name="list_capabilities",
                tool_class=ToolClass.R0_READ,
                handler=list_capabilities,
                description=(
                    "Honest closed-set capability catalog for THIS process "
                    "(available/inert/unavailable, with evidence)."
                ),
            )
        )

    # --- mandate §9: source inspection tools (registered ONLY when composed) --
    #
    # R0 read-only. The SourceReader enforces the jail, denylist, and byte/
    # entry caps; refusals surface as typed DATA (never a crash) so the
    # model can adapt to them within the round budget.
    if surface.repo_reader is not None:
        source_reader = surface.repo_reader

        async def read_source_file(caller: Principal, args: JsonObject) -> JsonObject:
            try:
                result = source_reader.read_file(str(args.get("path", "")))
            except SourceReadRefused as refusal:
                return scrub_object({"error": "read refused", "reason": refusal.reason})
            return scrub_object(dict(result))

        async def list_source_files(caller: Principal, args: JsonObject) -> JsonObject:
            try:
                result = source_reader.list_files(
                    str(args.get("path", "")), glob=str(args.get("glob", "**/*"))
                )
            except SourceReadRefused as refusal:
                return scrub_object({"error": "list refused", "reason": refusal.reason})
            return scrub_object(dict(result))

        async def search_source(caller: Principal, args: JsonObject) -> JsonObject:
            try:
                result = source_reader.search(
                    str(args.get("text", "")),
                    str(args.get("path", "")),
                    glob=str(args.get("glob", "**/*.py")),
                )
            except SourceReadRefused as refusal:
                return scrub_object({"error": "search refused", "reason": refusal.reason})
            return scrub_object(dict(result))

        capability_specs.extend(
            [
                ToolSpec(
                    name="read_source_file",
                    tool_class=ToolClass.R0_READ,
                    handler=read_source_file,
                    allowed_args=frozenset({"path"}),
                    description=(
                        "Read ONE repository file (root-jailed, byte-capped, "
                        "credential paths denied). READ ONLY."
                    ),
                ),
                ToolSpec(
                    name="list_source_files",
                    tool_class=ToolClass.R0_READ,
                    handler=list_source_files,
                    allowed_args=frozenset({"path", "glob"}),
                    description=(
                        "List repository files under a relative path "
                        "(entry-capped, credential paths hidden)."
                    ),
                ),
                ToolSpec(
                    name="search_source",
                    tool_class=ToolClass.R0_READ,
                    handler=search_source,
                    allowed_args=frozenset({"text", "path", "glob"}),
                    description=(
                        "Literal substring search across repository files "
                        "with line numbers (match-capped, no regex)."
                    ),
                ),
            ]
        )

    # --- V7 chunk 2: exercise tools (registered ONLY when composed) -----------
    #
    # The SAME ExerciseSurface the POST /v1/admin/capabilities/{id}/exercise
    # route dispatches — one probe registry, two consumers. list_exercisable
    # is R0 (pure registry read); exercise_capability is R1 (a probe may run
    # a REAL budget-bounded execution — same risk class as run_test_execution).
    if surface.exercise is not None:
        exercise_registry = surface.exercise

        async def list_exercisable(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object({"exercisable": exercise_registry.exercisable()})

        async def exercise_capability(caller: Principal, args: JsonObject) -> JsonObject:
            capability_id = str(args.get("capability_id", ""))
            handler = exercise_registry.get(capability_id)
            if handler is None:
                # Anti-enumeration: unknown and unregistered are the same
                # answer (mirrors the route's 404 mapping).
                return {"error": "unknown exercisable capability id"}
            result = await handler(caller)
            return scrub_object({"capability_id": capability_id, "result": result})

        capability_specs.append(
            ToolSpec(
                name="list_exercisable",
                tool_class=ToolClass.R0_READ,
                handler=list_exercisable,
                description="Capability ids that have a REAL exercise probe.",
            )
        )
        capability_specs.append(
            ToolSpec(
                name="exercise_capability",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=exercise_capability,
                allowed_args=frozenset({"capability_id"}),
                description=(
                    "Prove a capability by exercising it — a REAL probe over "
                    "the real path returning record evidence."
                ),
            )
        )

    # --- V7 chunk 6: self-review + impact-simulator tools (registered ONLY
    # when composed) — the SAME service the admin routes dispatch.
    # self_review is R0 (pure read assembly). propose_change is R2: it
    # creates config-lifecycle state (draft→validate→preview composed —
    # exactly the tier of the existing draft/validate/preview tools) and
    # NEVER publishes (publish stays a human act, structurally).
    if surface.self_review is not None:
        review_service = surface.self_review

        async def self_review_tool(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object(review_service.self_review(caller.tenant_id))

        async def propose_change_tool(caller: Principal, args: JsonObject) -> JsonObject:
            raw_action = str(args.get("action", ""))
            try:
                action = AdminAction(raw_action)
            except ValueError:
                return {"error": f"unknown admin action: {raw_action[:100]}"}
            payload = args.get("payload") or {}
            if not isinstance(payload, dict):
                return {"error": "payload must be a JSON object"}
            try:
                result = review_service.propose_change(
                    caller.tenant_id, caller.user_id, action, payload
                )
            except InactiveAdminArea as exc:
                return {"error": str(exc)}
            return scrub_object(result)

        capability_specs.append(
            ToolSpec(
                name="self_review",
                tool_class=ToolClass.R0_READ,
                handler=self_review_tool,
                description=(
                    "The platform's evidence-backed self-portrait: "
                    "capabilities, lifecycle, scenarios, review state."
                ),
            )
        )
        capability_specs.append(
            ToolSpec(
                name="propose_change",
                tool_class=ToolClass.R2_CONFIG_CHANGE,
                handler=propose_change_tool,
                allowed_args=frozenset({"action", "payload"}),
                description=(
                    "Simulate a change through the REAL lifecycle "
                    "(draft→validate→preview) — evidence-backed proposal, "
                    "NEVER auto-applied (publish stays a human act)."
                ),
            )
        )

    # --- V7 chunk 5: learning-observability tools (registered ONLY when
    # composed) — the SAME service the /v1/admin/learning/* review routes
    # dispatch. Reading the report is R0 (pure read over stores); MARKING a
    # review is a state change — R1 (recorded: bounded, reversible ops act;
    # R2 stays the config lifecycle's tier).
    if surface.learning_observability is not None:
        observability = surface.learning_observability

        async def changes_since_review(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object(observability.changes_since_review(caller.tenant_id))

        async def mark_reviewed(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object(observability.mark_reviewed(caller.tenant_id, caller.user_id))

        capability_specs.append(
            ToolSpec(
                name="changes_since_review",
                tool_class=ToolClass.R0_READ,
                handler=changes_since_review,
                description=(
                    "What changed since the last review — audit/config "
                    "windows WITH evidence rows; never fabricates metrics."
                ),
            )
        )
        capability_specs.append(
            ToolSpec(
                name="mark_reviewed",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=mark_reviewed,
                description=(
                    "Record the explicit review act; returns the new and "
                    "previous markers (self-evidencing)."
                ),
            )
        )

    # --- V7 chunk 4: context-lab tools (registered ONLY when composed) --------
    #
    # The SAME ContextLabService the /v1/admin/context-lab routes dispatch —
    # one composer, two consumers. BOTH tools are R0: the lab composes for
    # real but executes nothing, bills nothing, writes nothing — a dry-run
    # read over stores the caller already owns (unlike scenario replay,
    # which runs a real billed execution and is therefore R1).
    if surface.context_lab is not None:
        lab_service = surface.context_lab

        async def list_lab_checks(caller: Principal, args: JsonObject) -> JsonObject:
            return scrub_object({"checks": lab_service.checks()})

        async def validate_context(caller: Principal, args: JsonObject) -> JsonObject:
            raw_ask = str(args.get("ask", "")).strip()
            if not raw_ask:
                return {"error": "ask is required"}
            request_fields: dict[str, object] = {"ask": raw_ask}
            if args.get("role_id") is not None:
                request_fields["role_id"] = str(args["role_id"])
            if args.get("conversation_id") is not None:
                request_fields["conversation_id"] = str(args["conversation_id"])
            if args.get("context_budget") is not None:
                request_fields["context_budget"] = args["context_budget"]
            try:
                request = ContextLabRequest.model_validate(request_fields)
            except ValueError as exc:
                # Pydantic's named refusal crosses as honest content.
                return {"error": f"invalid lab request: {exc}"}
            try:
                result = lab_service.validate(caller.tenant_id, caller.user_id, request)
            except ConversationNotAdmitted:
                # Anti-enumeration: absent and foreign are the same answer.
                return {"error": "unknown conversation id"}
            return scrub_object(result)

        capability_specs.append(
            ToolSpec(
                name="list_lab_checks",
                tool_class=ToolClass.R0_READ,
                handler=list_lab_checks,
                description="The closed context-lab check name set.",
            )
        )
        capability_specs.append(
            ToolSpec(
                name="validate_context",
                tool_class=ToolClass.R0_READ,
                handler=validate_context,
                allowed_args=frozenset({"ask", "role_id", "conversation_id", "context_budget"}),
                description=(
                    "Dry-run the REAL context composer: blocks, named "
                    "exclusions, closed lab verdicts — executes nothing."
                ),
            )
        )

    # --- V7 chunk 3: scenario tools (registered ONLY when composed) -----------
    #
    # The SAME ScenarioService the /v1/admin/scenarios routes dispatch — one
    # scenario store, two consumers. Recorded design decision: a scenario is
    # TEST DATA, not platform config — saving one is R1 (same risk class as
    # run_test_execution), NOT R2 (no config lifecycle to route through).
    # Replay and the regression pack run REAL budget-bounded executions — R1.
    if surface.scenarios is not None:
        scenario_service = surface.scenarios

        async def list_scenarios(caller: Principal, args: JsonObject) -> JsonObject:
            rows = scenario_service.list(caller.tenant_id)
            return scrub_object({"scenarios": [scenario_json(s) for s in rows]})

        async def save_scenario(caller: Principal, args: JsonObject) -> JsonObject:
            name = str(args.get("name", "")).strip()
            ask = str(args.get("ask", "")).strip()
            if not name or not ask:
                return {"error": "name and ask are both required"}
            raw_checks = args.get("checks")
            if raw_checks is None:
                checks: tuple[str, ...] = tuple(sorted(SCENARIO_CHECKS))
            elif isinstance(raw_checks, list) and raw_checks:
                checks = tuple(str(c) for c in raw_checks)
            else:
                return {"error": "checks must be a non-empty list of check names"}
            try:
                scenario = scenario_service.save(
                    caller.tenant_id, name=name, ask=ask, checks=checks
                )
            except UnknownCheckName as exc:
                # The closed-set refusal, verbatim — honest, never silent.
                return {"error": str(exc)}
            return scrub_object(scenario_json(scenario))

        async def replay_scenario(caller: Principal, args: JsonObject) -> JsonObject:
            raw = args.get("scenario_id")
            try:
                scenario_id = UUID(str(raw))
            except ValueError:
                return {"error": "unknown scenario id"}
            try:
                result = await scenario_service.replay(
                    caller.tenant_id, caller.user_id, scenario_id
                )
            except ScenarioNotFound:
                # Anti-enumeration: absent and foreign-tenant are the same.
                return {"error": "unknown scenario id"}
            return scrub_object(result)

        async def run_regression_pack(caller: Principal, args: JsonObject) -> JsonObject:
            result = await scenario_service.regression_pack(caller.tenant_id, caller.user_id)
            return scrub_object(result)

        capability_specs.append(
            ToolSpec(
                name="list_scenarios",
                tool_class=ToolClass.R0_READ,
                handler=list_scenarios,
                description="The caller's tenant's saved test scenarios.",
            )
        )
        capability_specs.append(
            ToolSpec(
                name="save_scenario",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=save_scenario,
                allowed_args=frozenset({"name", "ask", "checks"}),
                description=(
                    "Save a named, replayable test scenario (closed "
                    "deterministic check set). 'checks' is optional — "
                    "omit it to use every check."
                ),
            )
        )
        capability_specs.append(
            ToolSpec(
                name="replay_scenario",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=replay_scenario,
                allowed_args=frozenset({"scenario_id"}),
                description=(
                    "Replay a saved scenario — a REAL labeled execution "
                    "graded by its stored checks."
                ),
            )
        )
        capability_specs.append(
            ToolSpec(
                name="run_regression_pack",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=run_regression_pack,
                allowed_args=frozenset(),
                description=(
                    "Replay every saved scenario — the Regression Center "
                    "pack with one honest regression_pass verdict."
                ),
            )
        )

    return ToolRegistry(
        registrable=AA3_REGISTRABLE_CLASSES,
        specs=[
            *capability_specs,
            ToolSpec(
                name="list_models",
                tool_class=ToolClass.R0_READ,
                handler=list_models,
                description="All registered models including disabled ones.",
            ),
            ToolSpec(
                name="list_providers",
                tool_class=ToolClass.R0_READ,
                handler=list_providers,
                description="All registered providers with template/routable flags.",
            ),
            ToolSpec(
                name="read_execution",
                tool_class=ToolClass.R0_READ,
                handler=read_execution,
                allowed_args=frozenset({"execution_id"}),
                description="One recorded execution by id (tenant-scoped).",
            ),
            ToolSpec(
                name="list_executions",
                tool_class=ToolClass.R0_READ,
                handler=list_executions,
                description="Newest recorded executions (tenant-scoped, limit 50).",
            ),
            ToolSpec(
                name="usage_summary",
                tool_class=ToolClass.R0_READ,
                handler=usage_summary,
                description="Tenant plan + task-unit budget summary.",
            ),
            ToolSpec(
                name="read_audit",
                tool_class=ToolClass.R0_READ,
                handler=read_audit,
                description="Newest audit events (tenant-scoped, limit 50).",
            ),
            ToolSpec(
                name="list_changes",
                tool_class=ToolClass.R0_READ,
                handler=list_changes,
                description="Config-change lifecycle records (tenant-scoped).",
            ),
            ToolSpec(
                name="run_test_execution",
                tool_class=ToolClass.R1_EXECUTE_TEST,
                handler=run_test_execution,
                allowed_args=frozenset({"ask", "purpose"}),
                description="One REAL budget-bounded labeled test execution.",
            ),
            ToolSpec(
                name="draft_change",
                tool_class=ToolClass.R2_CONFIG_CHANGE,
                handler=draft_change,
                allowed_args=frozenset({"action", "payload"}),
                description=(
                    "Draft a config change through the existing lifecycle "
                    "(publish is a human UI act, never a tool). "
                    "'action' must be one of: "
                    + ", ".join(sorted(a.value for a in AdminAction))
                    + "."
                ),
            ),
            ToolSpec(
                name="validate_change",
                tool_class=ToolClass.R2_CONFIG_CHANGE,
                handler=validate_change,
                allowed_args=frozenset({"change_id"}),
                description="Run lifecycle validation on a drafted change.",
            ),
            ToolSpec(
                name="preview_change",
                tool_class=ToolClass.R2_CONFIG_CHANGE,
                handler=preview_change,
                allowed_args=frozenset({"change_id"}),
                description="Attach the impact preview to a validated change.",
            ),
        ],
    )
