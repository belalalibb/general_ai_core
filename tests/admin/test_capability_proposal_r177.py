"""R177-FIX-03 — composition-level capability-proposal record (A05 §6.1).

Before: enforcement of capability proposals was complete (firewall, approval
gates) but RECORDING was missing — later sessions could not know what the
operator approved or rejected, or why. After: the EXISTING 21 §3 admin
lifecycle carries one more closed-set change kind, ``capability_proposal``,
whose payload IS the §7 decision sheet; publishing it appends an
``APPROVAL_DECISION`` audit row with ``{proposal_id, decision, reason}`` and
mutates NO registry. Reads ride the existing ``GET /v1/admin/audit`` and
``GET /v1/admin/changes/{id}`` — no new route, no new store.

Area: TOOLS (21 §4 row "Tools: enable, permissions, approval rules" — a
capability proposal is an approval-rule record; "capability firewall" is the
row's cannot-break column). The runtime must therefore compose the FINAL
active-area set (T-IMPL-068 recorded: "the FINAL composition passes
FINAL_ACTIVE_ADMIN_AREAS") or the kind would be inert in the shipped profile.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from apps.api import Principal, create_app
from apps.api.admin import AdminSurface
from core.admin import AdminConfigService, RollbackUnavailable
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    ACTION_AREA,
    FINAL_ACTIVE_ADMIN_AREAS,
    MVP_ACTIVE_ADMIN_AREAS,
    AdminAction,
    AdminArea,
    CapabilityProposalDecision,
    CapabilityProposalPayload,
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
from core.evaluation.memory import InMemoryEvaluationStore
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.usage import InMemoryUsageAccounting

TENANT = uuid4()
ACTOR = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _sheet(**overrides: Any) -> dict[str, Any]:
    sheet: dict[str, Any] = {
        "proposal_id": "R177-FIX-03",
        "capability": "capability_proposal record",
        "target": "apps/api admin lifecycle",
        "what": "persist operator rulings on agent-proposed capabilities",
        "does": "new draft kind; publish emits APPROVAL_DECISION",
        "why": "A05 §6.1 — recording missing",
        "required": False,
        "dependencies": "admin lifecycle, audit store",
        "impact": "contracts: admin change-kind set +1",
        "risk": "low-medium",
        "alternative": "documentary only (60_DECISION_LOG)",
        "enforcement_point": "admin lifecycle + AuditEvent",
        "decision": "approved",
        "reason": "operator message: APPROVED: R177-FIX-03",
    }
    sheet.update(overrides)
    return sheet


# --- world: live registries + admin service + audit + composed app ----------------


def _manifest(provider_key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
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
    )


class World:
    def __init__(
        self,
        *,
        is_admin: bool = True,
        active_areas: frozenset[AdminArea] = FINAL_ACTIVE_ADMIN_AREAS,
    ) -> None:
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
            active_areas=active_areas,
        )
        self.principal = Principal(tenant_id=TENANT, user_id=ACTOR, is_admin=is_admin)
        provider = Provider(
            id=uuid4(),
            provider_key="prov_a",
            display_name="A",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(provider, _manifest("prov_a"))
        self.model = Model(
            id=uuid4(),
            model_key="model-a",
            display_name="A",
            tier=ModelTier.MEDIUM,
            modalities=["text"],
            capabilities=["reasoning"],
            quality_score=0.5,
            reliability_score=0.5,
            cost_score=0.5,
            speed_score=0.5,
            status=ModelStatus.ACTIVE,
        )
        self.models.register(self.model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=self.model.id,
                provider_model_name="vendor/model-a",
                availability=BindingAvailability.AVAILABLE,
            )
        )

    def app(self) -> FastAPI:
        service = ExecutionService(
            adapters={},
            credential_refs={},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            usage=self.usage,
        )
        return create_app(
            router=self.router,
            execution_service=service,
            principal=self.principal,
            admin=AdminSurface(
                service=self.admin,
                providers=self.providers,
                models=self.models,
                usage=self.usage,
                routing=self.router,
                evaluations=InMemoryEvaluationStore(),
                audit=self.audit,
            ),
        )


async def _post(app: FastAPI, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path, json=body if body is not None else {})


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


# --- closed sets ------------------------------------------------------------------------


class TestClosedSets:
    def test_kind_exists_and_maps_to_tools_area(self) -> None:
        assert AdminAction.CAPABILITY_PROPOSAL.value == "capability_proposal"
        assert ACTION_AREA[AdminAction.CAPABILITY_PROPOSAL] is AdminArea.TOOLS
        # No area activated: FINAL stays MVP + {SKILLS, TOOLS} (T-IMPL-068 pin).
        assert FINAL_ACTIVE_ADMIN_AREAS == MVP_ACTIVE_ADMIN_AREAS | {
            AdminArea.SKILLS,
            AdminArea.TOOLS,
        }

    def test_unknown_kind_still_refused(self) -> None:
        with pytest.raises(ValueError):
            AdminAction("capability_proposals")
        response = run(
            _post(World().app(), "/v1/admin/changes", {"action": "capability_proposals"})
        )
        assert response.status_code == 422

    def test_decision_is_the_sheet_closed_set(self) -> None:
        assert {d.value for d in CapabilityProposalDecision} == {"approved", "rejected"}

    def test_sheet_payload_is_strict(self) -> None:
        CapabilityProposalPayload.model_validate(_sheet())
        for broken in (
            {k: v for k, v in _sheet().items() if k != "reason"},  # reason required
            _sheet(decision="deferred"),  # not a ruling
            _sheet(decision="approve"),  # closed-set spelling
            _sheet(extra="x"),  # extra="forbid"
            _sheet(reason=""),  # bounded, non-empty
        ):
            with pytest.raises(ValidationError):
                CapabilityProposalPayload.model_validate(broken)


# --- lifecycle --------------------------------------------------------------------------


class TestLifecycle:
    def _through_preview(self, world: World, payload: dict[str, Any]) -> Any:
        change = world.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.CAPABILITY_PROPOSAL,
            payload=payload,
        )
        assert change.area is AdminArea.TOOLS
        validated = world.admin.validate(TENANT, change.id)
        if validated.state is not ConfigLifecycleState.VALIDATED:
            return validated, validated
        return validated, world.admin.preview(TENANT, change.id)

    def test_publish_records_approval_decision_and_mutates_nothing(self) -> None:
        world = World()
        validated, previewed = self._through_preview(world, _sheet())
        assert validated.state is ConfigLifecycleState.VALIDATED
        assert previewed.impact_preview is not None
        assert "approved" in previewed.impact_preview
        assert "R177-FIX-03" in previewed.impact_preview

        published = world.admin.publish(TENANT, previewed.id)
        assert published.state is ConfigLifecycleState.PUBLISHED

        decisions = world.audit.read(TENANT, event_type=AuditEventType.APPROVAL_DECISION)
        assert len(decisions) == 1
        row = decisions[0]
        assert row.actor_id == ACTOR
        assert row.details["surface"] == "capability_proposal"
        assert row.details["proposal_id"] == "R177-FIX-03"
        assert row.details["decision"] == "approved"
        assert row.details["reason"] == "operator message: APPROVED: R177-FIX-03"
        assert row.details["change_id"] == str(published.id)
        # 21 §8 record for the publish itself is still emitted.
        published_rows = world.audit.read(TENANT, event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED)
        assert len(published_rows) == 1
        assert published_rows[0].admin_change is not None
        assert "R177-FIX-03" in published_rows[0].admin_change.what
        # No registry mutated.
        assert world.models.get("model-a").status is ModelStatus.ACTIVE

    def test_rejected_ruling_is_recorded_verbatim(self) -> None:
        world = World()
        _, previewed = self._through_preview(
            world, _sheet(decision="rejected", reason="duplicates existing primitive")
        )
        world.admin.publish(TENANT, previewed.id)
        (row,) = world.audit.read(TENANT, event_type=AuditEventType.APPROVAL_DECISION)
        assert row.details["decision"] == "rejected"
        assert row.details["reason"] == "duplicates existing primitive"

    def test_malformed_sheet_is_rejected_at_validate_with_a_named_reason(self) -> None:
        world = World()
        validated, _ = self._through_preview(world, _sheet(decision="maybe"))
        assert validated.state is ConfigLifecycleState.REJECTED
        assert validated.validation_result is not None
        assert validated.validation_result.startswith("rejected: capability proposal")
        assert "decision" in validated.validation_result
        assert world.audit.read(TENANT, event_type=AuditEventType.APPROVAL_DECISION) == ()

    def test_rollback_is_refused_decisions_are_evidence(self) -> None:
        world = World()
        _, previewed = self._through_preview(world, _sheet())
        world.admin.publish(TENANT, previewed.id)
        with pytest.raises(RollbackUnavailable):
            world.admin.rollback(TENANT, previewed.id)
        assert world.admin.get(TENANT, previewed.id).state is ConfigLifecycleState.PUBLISHED
        assert len(world.audit.read(TENANT, event_type=AuditEventType.APPROVAL_DECISION)) == 1

    def test_mvp_only_composition_keeps_the_kind_inactive(self) -> None:
        from core.admin import InactiveAdminArea

        world = World(active_areas=MVP_ACTIVE_ADMIN_AREAS)
        with pytest.raises(InactiveAdminArea):
            world.admin.draft(
                tenant_id=TENANT,
                actor_id=ACTOR,
                action=AdminAction.CAPABILITY_PROPOSAL,
                payload=_sheet(),
            )


# --- API: existing routes only --------------------------------------------------------


class TestExistingRoutesCarryTheRecord:
    def test_draft_to_publish_then_read_via_audit_and_changes(self) -> None:
        world = World()
        app = world.app()
        drafted = run(
            _post(
                app,
                "/v1/admin/changes",
                {"action": "capability_proposal", "payload": _sheet()},
            )
        )
        assert drafted.status_code == 201, drafted.text
        change_id = drafted.json()["id"]
        for step in ("validate", "preview", "publish"):
            stepped = run(_post(app, f"/v1/admin/changes/{change_id}/{step}"))
            assert stepped.status_code == 200, (step, stepped.text)
        assert stepped.json()["state"] == "published"

        audit = run(_get(app, "/v1/admin/audit?event_type=approval_decision"))
        assert audit.status_code == 200
        events = audit.json()["events"]
        assert len(events) == 1
        assert events[0]["details"]["proposal_id"] == "R177-FIX-03"
        assert events[0]["details"]["decision"] == "approved"

        change = run(_get(app, f"/v1/admin/changes/{change_id}"))
        assert change.status_code == 200
        assert change.json()["payload"]["decision"] == "approved"
        assert change.json()["action"] == "capability_proposal"

        # RollbackUnavailable -> validation_error body, HTTP 409 (the recorded
        # state-conflict mapping in apps/api/admin.py — unchanged here).
        rollback = run(_post(app, f"/v1/admin/changes/{change_id}/rollback"))
        assert rollback.status_code == 409
        assert rollback.json()["error"]["code"] == "validation_error"
        assert "never un-recorded" in rollback.json()["error"]["message"]

    def test_non_admin_cannot_record(self) -> None:
        app = World(is_admin=False).app()
        response = run(
            _post(app, "/v1/admin/changes", {"action": "capability_proposal", "payload": _sheet()})
        )
        assert response.status_code in (401, 403)


# --- composition -----------------------------------------------------------------------


def test_runtime_composes_the_final_active_area_set() -> None:
    """T-IMPL-068: the FINAL composition passes FINAL_ACTIVE_ADMIN_AREAS.

    Without it the TOOLS-area kind is refused at the door (422) in the shipped
    profile and FIX-03 would be inert — a recorded gap, closed here.
    """
    source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "active_areas=FINAL_ACTIVE_ADMIN_AREAS" in source
