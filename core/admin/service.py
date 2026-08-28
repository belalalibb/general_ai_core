"""Admin config-lifecycle service over the EXISTING registries (T-IMPL-031).

MVP Phase 7 slice 3 (41 §46 "admin models/providers/plans/routing").

EXACT SLICE SCOPE (per the task ruling, from 21 §§1–6/§8 re-read):

- MODELS: enable/disable a registered model (21 §4 row "Models").
- PROVIDERS: enable/disable a registered provider (21 §4 row "Providers").
- PLANS: set a tenant's plan units/limits (21 §5) through the EXISTING
  ``InMemoryUsageAccounting.configure_tenant`` seam.
- ROUTING_POLICIES: set the router's default scoring weights (21 §6)
  through the router's default-weights admin seam.

NO PARALLEL STATE: every publish mutates the SAME registries the router
reads (ProviderRegistry / ModelRegistry / usage accounting / the router's
default weights) — a published change is immediately visible to routing;
this service holds only lifecycle records + rollback snapshots, never a
second copy of configuration.

Lifecycle enforced in 21 §3 order — Draft → Validate → Preview Impact →
Publish → (Observe) → Rollback — with EXACT-predecessor checks: publishing
an unvalidated or unpreviewed draft is denied; validation failure is
terminal (REJECTED). Every publish/rollback lands an ADMIN_CONFIG_* audit
event through the EXISTING audit seam whose 21 §8 AdminChangeRecord
carries who/what/versions/validation/preview/rollback-target — the
InMemoryAuditLog REJECTS admin events without that record, so auditing is
structurally unskippable.

21 §4 "Admin Cannot Break" column honored structurally: the closed
AdminAction set has no verb that touches tenant isolation, accounting
integrity, or deny-by-default security; plan changes go through
``configure_tenant`` which PRESERVES consumed history (accounting
integrity); enabling a scaffold template provider is rejected at
validation (31 §10 — templates stay non-routable no matter what the
domain status says; the admin surface refuses to publish a change the
registry's eligibility layer would silently ignore).

Rollback is HONEST: the pre-publish state is snapshotted at publish time
and restored verbatim; when no prior state exists (first plan config for
a tenant) rollback is DENIED (RollbackUnavailable) instead of inventing a
"previous version" that never existed.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from core.admin.errors import (
    ChangeNotFound,
    InactiveAdminArea,
    InvalidLifecycleTransition,
    RollbackUnavailable,
)
from core.audit.ports import AuditLogPort
from core.contracts.admin import (
    ACTION_AREA,
    MVP_ACTIVE_ADMIN_AREAS,
    AdminAction,
    AdminArea,
    ConfigChange,
    ConfigLifecycleState,
)
from core.contracts.audit import AdminChangeRecord, AuditEvent, AuditEventType
from core.contracts.base import JsonObject
from core.contracts.domain import ModelStatus, ProviderStatus
from core.contracts.routing import ScoringWeights
from core.contracts.skills import SkillStatus
from core.contracts.tools import ToolStatus
from core.contracts.usage import UsageSummary
from core.providers.errors import ModelNotRegistered, ProviderNotRegistered
from core.providers.registry import ModelRegistry, ProviderRegistry
from core.roles.errors import SkillNotRegistered
from core.roles.registry import SkillRegistry
from core.tools.errors import ToolNotRegistered
from core.tools.registry import ToolRegistry
from core.usage.errors import EntitlementNotConfigured


class UsageConfigurationPort(Protocol):
    """The 21 §5 plan seam this service publishes through.

    ``configure_tenant`` is the EXISTING admin seam on
    ``InMemoryUsageAccounting`` (preserves accounting history);
    ``summary`` provides the rollback snapshot.
    """

    def configure_tenant(
        self,
        tenant_id: UUID,
        *,
        plan: str,
        task_units_limit: float,
        modality_limits: JsonObject | None = None,
    ) -> None: ...

    def summary(self, tenant_id: UUID) -> UsageSummary: ...


class RoutingWeightsPort(Protocol):
    """The 21 §6 routing-policy seam (router default weights)."""

    @property
    def default_weights(self) -> ScoringWeights: ...

    def set_default_weights(self, weights: ScoringWeights) -> None: ...


class AdminConfigService:
    """Config lifecycle (21 §3) over existing registries — no new authority."""

    def __init__(
        self,
        *,
        providers: ProviderRegistry,
        models: ModelRegistry,
        usage: UsageConfigurationPort,
        routing: RoutingWeightsPort,
        audit_log: AuditLogPort,
        skills: SkillRegistry | None = None,
        tools: ToolRegistry | None = None,
        active_areas: frozenset[AdminArea] = MVP_ACTIVE_ADMIN_AREAS,
    ) -> None:
        """FINAL Phase 19 widening (T-IMPL-068) — recorded decisions:

        ``active_areas`` is injectable DATA (default MVP — the T-IMPL-064
        ``active_types`` pattern: existing compositions keep their exact
        behavior; the FINAL composition passes FINAL_ACTIVE_ADMIN_AREAS).
        ``skills``/``tools`` are the SAME registry instances selection/
        the tool gate read (no parallel state); a skill/tool action whose
        registry seam is absent FAILS VALIDATION loudly — an admin area
        without bindable machinery cannot pretend to publish (41 §49).
        """
        self._providers = providers
        self._models = models
        self._usage = usage
        self._routing = routing
        self._audit = audit_log
        self._skills = skills
        self._tools = tools
        self._active_areas = active_areas
        # Lifecycle records, physically keyed by (tenant, id) — foreign
        # changes are unaddressable by construction (20 §6).
        self._changes: dict[tuple[UUID, UUID], ConfigChange] = {}
        self._order: list[tuple[UUID, UUID]] = []
        # Per-area published-version counters ("versioned", 21 §1).
        self._versions: dict[str, int] = {}
        # Rollback snapshots captured AT PUBLISH TIME, keyed by change id.
        self._snapshots: dict[UUID, dict[str, object]] = {}

    # -- lifecycle: Draft -----------------------------------------------------------

    def draft(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        action: AdminAction,
        payload: JsonObject | None = None,
    ) -> ConfigChange:
        """Create a DRAFT change. Area is DERIVED from the action (never both).

        Inactive-area denial happens HERE (R049 pattern): a draft against a
        non-MVP area never even enters the lifecycle.
        """
        area = ACTION_AREA[action]
        if area not in self._active_areas:
            raise InactiveAdminArea(area)
        change = ConfigChange(
            tenant_id=tenant_id,
            actor_id=actor_id,
            area=area,
            action=action,
            payload=dict(payload or {}),
        )
        key = (tenant_id, change.id)
        self._changes[key] = change
        self._order.append(key)
        return change

    # -- lifecycle: Validate ----------------------------------------------------------

    def validate(self, tenant_id: UUID, change_id: UUID) -> ConfigChange:
        """DRAFT -> VALIDATED, or DRAFT -> REJECTED (terminal) with a reason."""
        change = self._require(tenant_id, change_id, ConfigLifecycleState.DRAFT)
        problem = self._validation_problem(change)
        if problem is not None:
            return self._replace(
                change,
                state=ConfigLifecycleState.REJECTED,
                validation_result=f"rejected: {problem}",
            )
        return self._replace(
            change,
            state=ConfigLifecycleState.VALIDATED,
            validation_result="passed",
        )

    # -- lifecycle: Preview Impact ------------------------------------------------------

    def preview(self, tenant_id: UUID, change_id: UUID) -> ConfigChange:
        """Attach the impact preview to a VALIDATED change (21 §3/§8)."""
        change = self._require(tenant_id, change_id, ConfigLifecycleState.VALIDATED)
        if change.impact_preview is not None:
            raise InvalidLifecycleTransition("impact already previewed")
        return self._replace(change, impact_preview=self._impact_preview(change))

    # -- lifecycle: Publish ---------------------------------------------------------------

    def publish(self, tenant_id: UUID, change_id: UUID) -> ConfigChange:
        """Apply a validated+previewed change to the live registries.

        Snapshot-then-apply: the pre-publish state is captured FIRST so a
        later rollback restores reality, not a guess. Publishing is what
        makes the change visible to routing (no parallel state).
        """
        change = self._require(tenant_id, change_id, ConfigLifecycleState.VALIDATED)
        if change.impact_preview is None:
            raise InvalidLifecycleTransition(
                "publish requires a previewed change (21 §3 order)"
            )
        self._snapshots[change.id] = self._capture_snapshot(change)
        self._apply(change)

        current = self._versions.get(change.area.value, 0)
        self._versions[change.area.value] = current + 1
        previous_version = f"{change.area.value}-v{current}"
        new_version = f"{change.area.value}-v{current + 1}"

        published = self._replace(
            change,
            state=ConfigLifecycleState.PUBLISHED,
            published_version=new_version,
        )
        self._audit.append(
            AuditEvent(
                tenant_id=tenant_id,
                event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED,
                actor_id=change.actor_id,
                details={"change_id": str(change.id), "action": change.action.value},
                admin_change=AdminChangeRecord(
                    what=f"{change.action.value}: {self._subject(change)}",
                    previous_version=previous_version,
                    new_version=new_version,
                    validation_result=change.validation_result or "passed",
                    impact_preview=change.impact_preview,
                    rollback_target=previous_version,
                ),
            )
        )
        return published

    # -- lifecycle: Rollback ---------------------------------------------------------------

    def rollback(self, tenant_id: UUID, change_id: UUID) -> ConfigChange:
        """Restore the snapshotted pre-publish state (PUBLISHED -> ROLLED_BACK)."""
        change = self._require(tenant_id, change_id, ConfigLifecycleState.PUBLISHED)
        snapshot = self._snapshots[change.id]
        self._restore(change, snapshot)

        rolled_back_version = change.published_version or "unversioned"
        rollback_target = f"{change.area.value}-pre-{rolled_back_version}"
        result = self._replace(change, state=ConfigLifecycleState.ROLLED_BACK)
        self._audit.append(
            AuditEvent(
                tenant_id=tenant_id,
                event_type=AuditEventType.ADMIN_CONFIG_ROLLED_BACK,
                actor_id=change.actor_id,
                details={"change_id": str(change.id), "action": change.action.value},
                admin_change=AdminChangeRecord(
                    what=f"rollback {change.action.value}: {self._subject(change)}",
                    previous_version=rolled_back_version,
                    new_version=rollback_target,
                    validation_result=change.validation_result or "passed",
                    impact_preview=change.impact_preview or "n/a",
                    rollback_target=rolled_back_version,
                ),
            )
        )
        return result

    # -- reads (tenant-scoped, 20 §6) ----------------------------------------------------

    def get(self, tenant_id: UUID, change_id: UUID) -> ConfigChange:
        change = self._changes.get((tenant_id, change_id))
        if change is None:
            raise ChangeNotFound(change_id)
        return change

    def list_changes(self, tenant_id: UUID) -> tuple[ConfigChange, ...]:
        return tuple(self._changes[key] for key in self._order if key[0] == tenant_id)

    # -- internals -------------------------------------------------------------------------

    def _require(
        self, tenant_id: UUID, change_id: UUID, state: ConfigLifecycleState
    ) -> ConfigChange:
        change = self.get(tenant_id, change_id)
        if change.state is not state:
            raise InvalidLifecycleTransition(
                f"expected {state.value}, found {change.state.value}"
            )
        return change

    def _replace(self, change: ConfigChange, **updates: object) -> ConfigChange:
        updated = change.model_copy(update=updates)
        self._changes[(change.tenant_id, change.id)] = updated
        return updated

    def _subject(self, change: ConfigChange) -> str:
        payload = change.payload
        for key in ("model_key", "provider_key", "target_tenant_id", "skill_id", "tool_id"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return "default"

    # -- per-action validation (21 §3 Validate; deny-by-default) --------------------------

    def _validation_problem(self, change: ConfigChange) -> str | None:
        action = change.action
        payload = change.payload
        if action in (AdminAction.ENABLE_MODEL, AdminAction.DISABLE_MODEL):
            model_key = payload.get("model_key")
            if not isinstance(model_key, str) or not model_key:
                return "payload requires a non-empty 'model_key'"
            try:
                self._models.get(model_key)
            except ModelNotRegistered:
                return f"model not registered: {model_key}"
            return None
        if action in (AdminAction.ENABLE_PROVIDER, AdminAction.DISABLE_PROVIDER):
            provider_key = payload.get("provider_key")
            if not isinstance(provider_key, str) or not provider_key:
                return "payload requires a non-empty 'provider_key'"
            try:
                entry = self._providers.get(provider_key)
            except ProviderNotRegistered:
                return f"provider not registered: {provider_key}"
            if action is AdminAction.ENABLE_PROVIDER and entry.is_template:
                # 31 §10 / 21 §4 "cannot break provider/core boundary":
                # a scaffold template can never be made routable; refusing
                # here keeps the admin surface honest instead of publishing
                # a change eligibility would silently ignore.
                return f"provider is a scaffold template (31 §10): {provider_key}"
            return None
        if action in (AdminAction.ENABLE_SKILL, AdminAction.DISABLE_SKILL):
            if self._skills is None:
                return "skills registry seam is not bound in this composition"
            problem = self._require_uuid_payload(payload, "skill_id")
            if problem is not None:
                return problem
            try:
                skill = self._skills.get(UUID(str(payload["skill_id"])))
            except SkillNotRegistered:
                return f"skill not registered: {payload['skill_id']}"
            if action is AdminAction.ENABLE_SKILL and skill.status not in (
                SkillStatus.APPROVED,
                SkillStatus.DISABLED,
                SkillStatus.ACTIVE,
            ):
                # 21 §4 'Admin Cannot Break: scan/review requirement' —
                # enable never skips the 14 §3 pipeline: only a skill that
                # ALREADY passed review/approval (or was active and then
                # disabled) may be (re-)enabled by admin action.
                return (
                    "skill has not completed the import pipeline "
                    f"(status={skill.status.value}); enable cannot skip "
                    "scan/review (21 §4, 14 §3)"
                )
            return None
        if action in (AdminAction.ENABLE_TOOL, AdminAction.DISABLE_TOOL):
            if self._tools is None:
                return "tools registry seam is not bound in this composition"
            problem = self._require_uuid_payload(payload, "tool_id")
            if problem is not None:
                return problem
            try:
                self._tools.get(UUID(str(payload["tool_id"])))
            except ToolNotRegistered:
                return f"tool not registered: {payload['tool_id']}"
            return None
        if action is AdminAction.SET_PLAN:
            target = payload.get("target_tenant_id")
            plan = payload.get("plan")
            limit = payload.get("task_units_limit")
            if not isinstance(target, str) or not target:
                return "payload requires 'target_tenant_id'"
            try:
                UUID(target)
            except ValueError:
                return "'target_tenant_id' is not a UUID"
            if not isinstance(plan, str) or not plan:
                return "payload requires a non-empty 'plan'"
            if isinstance(limit, bool) or not isinstance(limit, int | float):
                return "payload requires a numeric 'task_units_limit'"
            if limit < 0:
                return "'task_units_limit' must be >= 0"
            return None
        weights = payload.get("weights")
        if not isinstance(weights, dict):
            return "payload requires a 'weights' object"
        try:
            ScoringWeights.model_validate(weights)
        except ValueError:
            return "'weights' is not a valid ScoringWeights object"
        return None

    @staticmethod
    def _require_uuid_payload(payload: JsonObject, field: str) -> str | None:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            return f"payload requires a non-empty '{field}'"
        try:
            UUID(value)
        except ValueError:
            return f"'{field}' is not a UUID"
        return None

    def _impact_preview(self, change: ConfigChange) -> str:
        action = change.action
        if action is AdminAction.DISABLE_MODEL:
            return (
                f"model '{self._subject(change)}' leaves the routing pool "
                "(03 §4: only ACTIVE models are candidates)"
            )
        if action is AdminAction.ENABLE_MODEL:
            return f"model '{self._subject(change)}' re-enters the routing pool"
        if action is AdminAction.DISABLE_PROVIDER:
            return (
                f"provider '{self._subject(change)}' is excluded from routing "
                "candidates (03 §4 status filter)"
            )
        if action is AdminAction.ENABLE_PROVIDER:
            return f"provider '{self._subject(change)}' becomes a routing candidate"
        if action is AdminAction.SET_PLAN:
            return (
                f"tenant {self._subject(change)} plan/limits replaced; "
                "accounting history preserved (21 §4 accounting integrity)"
            )
        if action is AdminAction.DISABLE_SKILL:
            return (
                f"skill {self._subject(change)} leaves the selectable set "
                "(registry admission: active+local only)"
            )
        if action is AdminAction.ENABLE_SKILL:
            return f"skill {self._subject(change)} becomes selectable"
        if action is AdminAction.DISABLE_TOOL:
            return (
                f"tool {self._subject(change)} is refused by the tool call "
                "gate (14 §1: never trusted by default)"
            )
        if action is AdminAction.ENABLE_TOOL:
            return f"tool {self._subject(change)} becomes admissible to the call gate"
        return "router default scoring weights replaced (11 §6 versioned weights)"

    # -- snapshot / apply / restore (the registry-mutating core) ---------------------------

    def _capture_snapshot(self, change: ConfigChange) -> dict[str, object]:
        action = change.action
        if action in (AdminAction.ENABLE_MODEL, AdminAction.DISABLE_MODEL):
            model = self._models.get(str(change.payload["model_key"]))
            return {"model_status": model.status}
        if action in (AdminAction.ENABLE_PROVIDER, AdminAction.DISABLE_PROVIDER):
            entry = self._providers.get(str(change.payload["provider_key"]))
            return {"provider_status": entry.provider.status}
        if action is AdminAction.SET_PLAN:
            target = UUID(str(change.payload["target_tenant_id"]))
            try:
                summary: UsageSummary | None = self._usage.summary(target)
            except EntitlementNotConfigured:
                summary = None  # first-ever plan config: nothing to roll back TO
            return {"plan_summary": summary}
        if action in (AdminAction.ENABLE_SKILL, AdminAction.DISABLE_SKILL):
            assert self._skills is not None  # validated pre-publish
            skill = self._skills.get(UUID(str(change.payload["skill_id"])))
            return {"skill_status": skill.status}
        if action in (AdminAction.ENABLE_TOOL, AdminAction.DISABLE_TOOL):
            assert self._tools is not None  # validated pre-publish
            tool = self._tools.get(UUID(str(change.payload["tool_id"])))
            return {"tool_status": tool.status}
        return {"weights": self._routing.default_weights}

    def _apply(self, change: ConfigChange) -> None:
        action = change.action
        if action in (AdminAction.ENABLE_MODEL, AdminAction.DISABLE_MODEL):
            status = (
                ModelStatus.ACTIVE
                if action is AdminAction.ENABLE_MODEL
                else ModelStatus.DISABLED
            )
            self._set_model_status(str(change.payload["model_key"]), status)
            return
        if action in (AdminAction.ENABLE_PROVIDER, AdminAction.DISABLE_PROVIDER):
            provider_status = (
                ProviderStatus.ACTIVE
                if action is AdminAction.ENABLE_PROVIDER
                else ProviderStatus.DISABLED
            )
            self._set_provider_status(
                str(change.payload["provider_key"]), provider_status
            )
            return
        if action is AdminAction.SET_PLAN:
            payload = change.payload
            raw_limit = payload["task_units_limit"]
            assert isinstance(raw_limit, int | float)  # validated pre-publish
            modality_limits = payload.get("modality_limits")
            self._usage.configure_tenant(
                UUID(str(payload["target_tenant_id"])),
                plan=str(payload["plan"]),
                task_units_limit=float(raw_limit),
                modality_limits=(
                    dict(modality_limits) if isinstance(modality_limits, dict) else None
                ),
            )
            return
        if action in (AdminAction.ENABLE_SKILL, AdminAction.DISABLE_SKILL):
            skill_status = (
                SkillStatus.ACTIVE
                if action is AdminAction.ENABLE_SKILL
                else SkillStatus.DISABLED
            )
            self._set_skill_status(UUID(str(change.payload["skill_id"])), skill_status)
            return
        if action in (AdminAction.ENABLE_TOOL, AdminAction.DISABLE_TOOL):
            tool_status = (
                ToolStatus.ACTIVE
                if action is AdminAction.ENABLE_TOOL
                else ToolStatus.DISABLED
            )
            self._set_tool_status(UUID(str(change.payload["tool_id"])), tool_status)
            return
        weights_payload = change.payload["weights"]
        self._routing.set_default_weights(ScoringWeights.model_validate(weights_payload))

    def _restore(self, change: ConfigChange, snapshot: dict[str, object]) -> None:
        action = change.action
        if action in (AdminAction.ENABLE_MODEL, AdminAction.DISABLE_MODEL):
            status = snapshot["model_status"]
            assert isinstance(status, ModelStatus)  # snapshot shape is internal
            self._set_model_status(str(change.payload["model_key"]), status)
            return
        if action in (AdminAction.ENABLE_PROVIDER, AdminAction.DISABLE_PROVIDER):
            provider_status = snapshot["provider_status"]
            assert isinstance(provider_status, ProviderStatus)
            self._set_provider_status(
                str(change.payload["provider_key"]), provider_status
            )
            return
        if action is AdminAction.SET_PLAN:
            summary = snapshot["plan_summary"]
            if summary is None:
                raise RollbackUnavailable(
                    "no prior plan configuration exists for this tenant; "
                    "restoring would invent a version that never was (21 §8)"
                )
            assert isinstance(summary, UsageSummary)
            self._usage.configure_tenant(
                UUID(str(change.payload["target_tenant_id"])),
                plan=summary.plan,
                task_units_limit=summary.task_units.limit,
                modality_limits=dict(summary.modality_limits),
            )
            return
        if action in (AdminAction.ENABLE_SKILL, AdminAction.DISABLE_SKILL):
            skill_status = snapshot["skill_status"]
            assert isinstance(skill_status, SkillStatus)
            self._set_skill_status(UUID(str(change.payload["skill_id"])), skill_status)
            return
        if action in (AdminAction.ENABLE_TOOL, AdminAction.DISABLE_TOOL):
            tool_status = snapshot["tool_status"]
            assert isinstance(tool_status, ToolStatus)
            self._set_tool_status(UUID(str(change.payload["tool_id"])), tool_status)
            return
        weights = snapshot["weights"]
        assert isinstance(weights, ScoringWeights)
        self._routing.set_default_weights(weights)

    def _set_model_status(self, model_key: str, status: ModelStatus) -> None:
        model = self._models.get(model_key)
        self._models.replace(model.model_copy(update={"status": status}))

    def _set_provider_status(self, provider_key: str, status: ProviderStatus) -> None:
        entry = self._providers.get(provider_key)
        self._providers.replace(
            entry.provider.model_copy(update={"status": status}), entry.manifest
        )

    def _set_skill_status(self, skill_id: UUID, status: SkillStatus) -> None:
        # Entity and embedded manifest advance TOGETHER (the registry's
        # agreement rule holds at every state — same posture as the
        # Phase-13 import steps).
        assert self._skills is not None
        skill = self._skills.get(skill_id)
        self._skills.replace(
            skill.model_copy(
                update={
                    "status": status,
                    "manifest": skill.manifest.model_copy(update={"status": status}),
                }
            )
        )

    def _set_tool_status(self, tool_id: UUID, status: ToolStatus) -> None:
        assert self._tools is not None
        tool = self._tools.get(tool_id)
        self._tools.replace(tool.model_copy(update={"status": status}))
