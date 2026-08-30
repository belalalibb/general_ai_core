"""AA-2 shipped tool set — 7 × R0 reads + 1 × R1 test execution.

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
from apps.api.store import InMemoryExecutionStore
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
    execution_store: InMemoryExecutionStore
    admin: AdminSurface
    usage: InMemoryUsageAccounting
    audit: AuditLogPort


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

    def _lifecycle_tool_step(
        caller: Principal, args: JsonObject, step: str
    ) -> JsonObject:
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

    return ToolRegistry(
        registrable=AA3_REGISTRABLE_CLASSES,
        specs=[
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
                    "(publish is a human UI act, never a tool)."
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
