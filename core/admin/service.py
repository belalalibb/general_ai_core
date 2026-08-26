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
    ConfigChange,
    ConfigLifecycleState,
)
from core.contracts.audit import AdminChangeRecord, AuditEvent, AuditEventType
from core.contracts.base import JsonObject
from core.contracts.domain import ModelStatus, ProviderStatus
from core.contracts.routing import ScoringWeights
from core.contracts.usage import UsageSummary
from core.providers.errors import ModelNotRegistered, ProviderNotRegistered
from core.providers.registry import ModelRegistry, ProviderRegistry
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
    ) -> None:
        self._providers = providers
        self._models = models
        self._usage = usage
        self._routing = routing
        self._audit = audit_log
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
        if area not in MVP_ACTIVE_ADMIN_AREAS:  # pragma: no cover — MVP map
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
        for key in ("model_key", "provider_key", "target_tenant_id"):
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
            status = (
                ProviderStatus.ACTIVE
                if action is AdminAction.ENABLE_PROVIDER
                else ProviderStatus.DISABLED
            )
            self._set_provider_status(str(change.payload["provider_key"]), status)
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
