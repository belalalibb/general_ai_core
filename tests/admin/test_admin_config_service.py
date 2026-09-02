"""AdminConfigService — config lifecycle over live registries (T-IMPL-031).

Hermetic — in-memory registries/usage/audit only; no network.

21 §9 required-test matrix, mapped to this slice:

    config draft validation                  -> TestValidation
    publish creates version                  -> test_publish_creates_version
    rollback restores previous version       -> TestRollback
    invalid policy rejected                  -> test_invalid_weights_rejected
    security invariant cannot be disabled    -> test_no_security_action_exists,
                                                test_template_provider_cannot_be_enabled
    plan change affects eligibility          -> test_plan_publish_changes_reserve_outcome
    routing policy version used in           -> test_weights_version_visible_in_decision
        execution snapshot
    admin action audited                     -> TestAudit

Plus lifecycle-order enforcement (21 §3), tenant isolation of change
records (20 §6), and the honest-rollback denial (RollbackUnavailable).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.admin import (
    AdminConfigService,
    ChangeNotFound,
    InvalidLifecycleTransition,
    RollbackUnavailable,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    ACTION_AREA,
    MVP_ACTIVE_ADMIN_AREAS,
    AdminAction,
    AdminArea,
    ConfigLifecycleState,
)
from core.contracts.audit import AuditEventType
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import ProviderManifest
from core.contracts.routing import RoutingRequest
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import NoEligibleCandidates, SimpleScoringRouter
from core.usage import BudgetExceeded, InMemoryUsageAccounting

TENANT = uuid4()
OTHER_TENANT = uuid4()
ACTOR = uuid4()

# --- fixtures (registry shapes reused from tests/routing) ---------------------------


def _manifest(provider_key: str, **overrides: object) -> ProviderManifest:
    payload: dict[str, object] = {
        "id": provider_key,
        "name": provider_key,
        "version": "1.0.0",
        "status": "active",
        "auth": {"types": ["api_key"], "supports_refresh": False},
        "account_pool": {"supported": False},
        "capabilities": {"chat": True},
        "operations": ["generate_text"],
        "models": {"discovery": "static", "static_models": []},
        "rate_limits": {"strategy": "provider_defined"},
        "health": {"checks": ["ping"]},
        "errors": {"mapping": "error_map.json"},
    }
    payload.update(overrides)
    return ProviderManifest.model_validate(payload)


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(key: str, status: ModelStatus = ModelStatus.ACTIVE) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=status,
    )


class _World:
    """Live registries + usage + router + audit, shared by admin AND routing."""

    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.usage = InMemoryUsageAccounting()
        self.audit = InMemoryAuditLog()
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
        )

    def seed(self) -> tuple[Provider, Model]:
        provider = _provider("prov_a")
        self.providers.register(provider, _manifest("prov_a"))
        model = _model("model-a")
        self.models.register(model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name=model.model_key,
                availability=BindingAvailability.AVAILABLE,
            )
        )
        return provider, model


def _through_preview(world: _World, action: AdminAction, payload: dict[str, object]) -> UUID:
    """Draft + validate + preview; returns the change id (ready to publish)."""
    change = world.admin.draft(tenant_id=TENANT, actor_id=ACTOR, action=action, payload=payload)
    world.admin.validate(TENANT, change.id)
    world.admin.preview(TENANT, change.id)
    return change.id


def _published(world: _World, action: AdminAction, payload: dict[str, object]) -> UUID:
    change_id = _through_preview(world, action, payload)
    world.admin.publish(TENANT, change_id)
    return change_id


# --- contracts ------------------------------------------------------------------------


class TestContracts:
    def test_admin_area_carries_21s2_verbatim(self) -> None:
        assert len(list(AdminArea)) == 21  # 21 §2 module list, nothing added/dropped

    def test_mvp_active_areas_are_the_41s46_four(self) -> None:
        assert MVP_ACTIVE_ADMIN_AREAS == {
            AdminArea.MODELS,
            AdminArea.PROVIDERS,
            AdminArea.PLANS,
            AdminArea.ROUTING_POLICIES,
        }

    def test_every_action_maps_to_an_active_area(self) -> None:
        # 21 §4: only "can control" verbs exist. FINAL Phase 19 (T-IMPL-068)
        # widened the action set beyond MVP areas: every action maps into
        # FINAL_ACTIVE_ADMIN_AREAS; the original six still map into MVP.
        from core.contracts.admin import FINAL_ACTIVE_ADMIN_AREAS

        assert set(ACTION_AREA) == set(AdminAction)
        assert set(ACTION_AREA.values()) <= FINAL_ACTIVE_ADMIN_AREAS
        mvp_actions = {
            AdminAction.ENABLE_MODEL,
            AdminAction.DISABLE_MODEL,
            AdminAction.ENABLE_PROVIDER,
            AdminAction.DISABLE_PROVIDER,
            AdminAction.SET_PLAN,
            AdminAction.SET_ROUTING_WEIGHTS,
        }
        assert {ACTION_AREA[a] for a in mvp_actions} <= MVP_ACTIVE_ADMIN_AREAS

    def test_no_security_action_exists(self) -> None:
        # 21 §4 "cannot break": no action can touch security/tenancy/accounting.
        forbidden = {"security", "tenant_isolation", "audit", "accounting"}
        for action in AdminAction:
            assert not any(word in action.value for word in forbidden)


# --- config draft validation (21 §9) -----------------------------------------------------


class TestValidation:
    def test_valid_draft_passes(self) -> None:
        world = _World()
        world.seed()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        assert change.state is ConfigLifecycleState.DRAFT
        assert change.area is AdminArea.MODELS  # derived from the action
        validated = world.admin.validate(TENANT, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED
        assert validated.validation_result == "passed"

    def test_unknown_model_rejected(self) -> None:
        world = _World()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "ghost"},
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "not registered" in (rejected.validation_result or "")

    def test_rejected_is_terminal(self) -> None:
        world = _World()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={},
        )
        world.admin.validate(TENANT, change.id)  # rejects: missing model_key
        with pytest.raises(InvalidLifecycleTransition):
            world.admin.preview(TENANT, change.id)
        with pytest.raises(InvalidLifecycleTransition):
            world.admin.publish(TENANT, change.id)

    def test_invalid_weights_rejected(self) -> None:
        # 21 §9 "invalid policy rejected": out-of-range weight never validates.
        world = _World()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.SET_ROUTING_WEIGHTS,
            payload={"weights": {"quality": 7.0}},
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED

    def test_plan_payload_validation(self) -> None:
        world = _World()
        bad_payloads: list[dict[str, object]] = [
            {},  # no target
            {"target_tenant_id": "not-a-uuid", "plan": "pro", "task_units_limit": 5},
            {"target_tenant_id": str(uuid4()), "plan": "", "task_units_limit": 5},
            {"target_tenant_id": str(uuid4()), "plan": "pro", "task_units_limit": -1},
            {"target_tenant_id": str(uuid4()), "plan": "pro", "task_units_limit": True},
        ]
        for payload in bad_payloads:
            change = world.admin.draft(
                tenant_id=TENANT,
                actor_id=ACTOR,
                action=AdminAction.SET_PLAN,
                payload=payload,
            )
            assert world.admin.validate(TENANT, change.id).state is ConfigLifecycleState.REJECTED

    def test_template_provider_cannot_be_enabled(self) -> None:
        # 21 §9 "security invariant cannot be disabled" (31 §10 boundary).
        world = _World()
        template = _provider("tmpl", status=ProviderStatus.DISABLED)
        world.providers.register(
            template,
            _manifest(
                "tmpl",
                status="template_disabled",
                is_template=True,
                is_functional=False,
                real_provider_required=True,
                auth={"types": [], "supports_refresh": False},
            ),
        )
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.ENABLE_PROVIDER,
            payload={"provider_key": "tmpl"},
        )
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert "template" in (rejected.validation_result or "")


# --- lifecycle order (21 §3) ---------------------------------------------------------------


class TestLifecycleOrder:
    def test_publish_requires_preview(self) -> None:
        world = _World()
        world.seed()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        world.admin.validate(TENANT, change.id)
        with pytest.raises(InvalidLifecycleTransition, match="preview"):
            world.admin.publish(TENANT, change.id)

    def test_preview_requires_validation(self) -> None:
        world = _World()
        world.seed()
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        with pytest.raises(InvalidLifecycleTransition):
            world.admin.preview(TENANT, change.id)

    def test_rollback_requires_published(self) -> None:
        world = _World()
        world.seed()
        change_id = _through_preview(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        with pytest.raises(InvalidLifecycleTransition):
            world.admin.rollback(TENANT, change_id)

    def test_double_publish_denied(self) -> None:
        world = _World()
        world.seed()
        change_id = _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        with pytest.raises(InvalidLifecycleTransition):
            world.admin.publish(TENANT, change_id)

    def test_preview_content_recorded(self) -> None:
        world = _World()
        world.seed()
        change_id = _through_preview(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        change = world.admin.get(TENANT, change_id)
        assert "routing pool" in (change.impact_preview or "")


# --- publish semantics (21 §9 "publish creates version" + live-registry effect) --------------


class TestPublish:
    def test_publish_creates_version(self) -> None:
        world = _World()
        world.seed()
        change_id = _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        change = world.admin.get(TENANT, change_id)
        assert change.state is ConfigLifecycleState.PUBLISHED
        assert change.published_version == "models-v1"

    def test_versions_are_per_area_monotonic(self) -> None:
        world = _World()
        world.seed()
        _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        second = _published(world, AdminAction.ENABLE_MODEL, {"model_key": "model-a"})
        weights = _published(
            world,
            AdminAction.SET_ROUTING_WEIGHTS,
            {"weights": {"version": "w2", "quality": 0.5}},
        )
        assert world.admin.get(TENANT, second).published_version == "models-v2"
        # Different area starts its own counter.
        assert world.admin.get(TENANT, weights).published_version == "routing_policies-v1"

    def test_disable_model_removes_from_routing_pool(self) -> None:
        # No parallel state: the router sees the published change immediately.
        world = _World()
        world.seed()
        request = RoutingRequest.model_validate({"operation": "generate_text"})
        model_id = world.models.get("model-a").id
        assert world.router.route(request).selected.model_id == model_id
        _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        assert world.models.get("model-a").status is ModelStatus.DISABLED
        with pytest.raises(NoEligibleCandidates):
            world.router.route(request)

    def test_disable_provider_removes_candidates(self) -> None:
        world = _World()
        world.seed()
        request = RoutingRequest.model_validate({"operation": "generate_text"})
        _published(world, AdminAction.DISABLE_PROVIDER, {"provider_key": "prov_a"})
        assert world.providers.get("prov_a").provider.status is ProviderStatus.DISABLED
        with pytest.raises(NoEligibleCandidates):
            world.router.route(request)

    def test_plan_publish_changes_reserve_outcome(self) -> None:
        # 21 §9 "plan change affects eligibility": budget enforcement flips.
        world = _World()
        subject = uuid4()
        _published(
            world,
            AdminAction.SET_PLAN,
            {"target_tenant_id": str(subject), "plan": "free", "task_units_limit": 1},
        )
        with pytest.raises(BudgetExceeded):
            world.usage.reserve(subject, uuid4(), 5.0)
        _published(
            world,
            AdminAction.SET_PLAN,
            {"target_tenant_id": str(subject), "plan": "pro", "task_units_limit": 100},
        )
        ledger = world.usage.reserve(subject, uuid4(), 5.0)
        assert ledger is not None
        assert world.usage.summary(subject).plan == "pro"

    def test_weights_version_visible_in_decision(self) -> None:
        # 21 §9 "routing policy version used in execution snapshot" (11 §6).
        world = _World()
        world.seed()
        _published(
            world,
            AdminAction.SET_ROUTING_WEIGHTS,
            {"weights": {"version": "admin-w9", "quality": 0.9, "cost": 0.1}},
        )
        assert world.router.default_weights.version == "admin-w9"
        decision = world.router.route(RoutingRequest.model_validate({"operation": "generate_text"}))
        assert decision.weights.version == "admin-w9"


# --- rollback (21 §9 "rollback restores previous version") -----------------------------------


class TestRollback:
    def test_rollback_restores_model_status(self) -> None:
        world = _World()
        world.seed()
        change_id = _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        result = world.admin.rollback(TENANT, change_id)
        assert result.state is ConfigLifecycleState.ROLLED_BACK
        assert world.models.get("model-a").status is ModelStatus.ACTIVE
        # Routing works again — restoration is live, not cosmetic.
        decision = world.router.route(RoutingRequest.model_validate({"operation": "generate_text"}))
        assert decision.selected.model_id == world.models.get("model-a").id

    def test_rollback_restores_provider_status(self) -> None:
        world = _World()
        world.seed()
        change_id = _published(world, AdminAction.DISABLE_PROVIDER, {"provider_key": "prov_a"})
        world.admin.rollback(TENANT, change_id)
        assert world.providers.get("prov_a").provider.status is ProviderStatus.ACTIVE

    def test_rollback_restores_previous_plan(self) -> None:
        world = _World()
        subject = uuid4()
        _published(
            world,
            AdminAction.SET_PLAN,
            {"target_tenant_id": str(subject), "plan": "free", "task_units_limit": 10},
        )
        upgrade = _published(
            world,
            AdminAction.SET_PLAN,
            {"target_tenant_id": str(subject), "plan": "pro", "task_units_limit": 100},
        )
        world.admin.rollback(TENANT, upgrade)
        summary = world.usage.summary(subject)
        assert summary.plan == "free"
        assert summary.task_units.limit == 10

    def test_rollback_restores_previous_weights(self) -> None:
        world = _World()
        default_version = world.router.default_weights.version
        change_id = _published(
            world,
            AdminAction.SET_ROUTING_WEIGHTS,
            {"weights": {"version": "admin-w9", "quality": 0.9}},
        )
        world.admin.rollback(TENANT, change_id)
        assert world.router.default_weights.version == default_version

    def test_first_plan_config_rollback_denied(self) -> None:
        # HONEST rollback: no prior state -> loud denial, never invention.
        world = _World()
        subject = uuid4()
        change_id = _published(
            world,
            AdminAction.SET_PLAN,
            {"target_tenant_id": str(subject), "plan": "free", "task_units_limit": 10},
        )
        with pytest.raises(RollbackUnavailable):
            world.admin.rollback(TENANT, change_id)
        # The plan itself stays published (denial did not corrupt state).
        assert world.usage.summary(subject).plan == "free"


# --- audit (21 §9 "admin action audited"; 21 §8 record fields) --------------------------------


class TestAudit:
    def test_publish_lands_admin_audit_event(self) -> None:
        world = _World()
        world.seed()
        _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        events = world.audit.read(TENANT)
        assert [e.event_type for e in events] == [AuditEventType.ADMIN_CONFIG_PUBLISHED]
        record = events[0].admin_change
        assert record is not None  # who/what/versions/validation/preview (21 §8)
        assert events[0].actor_id == ACTOR
        assert "model-a" in record.what
        assert record.previous_version == "models-v0"
        assert record.new_version == "models-v1"
        assert record.rollback_target == "models-v0"
        assert record.validation_result == "passed"

    def test_rollback_lands_second_audit_event(self) -> None:
        world = _World()
        world.seed()
        change_id = _published(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        world.admin.rollback(TENANT, change_id)
        events = world.audit.read(TENANT)
        assert [e.event_type for e in events] == [
            AuditEventType.ADMIN_CONFIG_PUBLISHED,
            AuditEventType.ADMIN_CONFIG_ROLLED_BACK,
        ]
        record = events[1].admin_change
        assert record is not None
        assert record.rollback_target == "models-v1"  # the version rolled back


# --- tenant isolation of change records (20 §6) ------------------------------------------------


class TestTenantIsolation:
    def test_foreign_change_unaddressable(self) -> None:
        world = _World()
        world.seed()
        change_id = _through_preview(world, AdminAction.DISABLE_MODEL, {"model_key": "model-a"})
        # Same error for absent and foreign (anti-enumeration).
        with pytest.raises(ChangeNotFound):
            world.admin.get(OTHER_TENANT, change_id)
        with pytest.raises(ChangeNotFound):
            world.admin.publish(OTHER_TENANT, change_id)
        with pytest.raises(ChangeNotFound):
            world.admin.get(TENANT, uuid4())

    def test_list_is_tenant_scoped(self) -> None:
        world = _World()
        world.seed()
        world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        world.admin.draft(
            tenant_id=OTHER_TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        assert len(world.admin.list_changes(TENANT)) == 1
        assert len(world.admin.list_changes(OTHER_TENANT)) == 1

    def test_lifecycle_replaces_record_not_mutates(self) -> None:
        world = _World()
        world.seed()
        draft = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        world.admin.validate(TENANT, draft.id)
        # The originally returned frozen instance is untouched.
        assert draft.state is ConfigLifecycleState.DRAFT
        assert world.admin.get(TENANT, draft.id).state is (ConfigLifecycleState.VALIDATED)
