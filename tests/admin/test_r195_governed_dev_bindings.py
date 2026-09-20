"""R195 (AD-1, operator APPROVED D1/D2): governed dev-binding registration and
remote-trust grant/revoke through the EXISTING admin change lifecycle.

Proves (60_DECISION_LOG R195-DEC-01):
- `AdminAction` +3 (`REGISTER_REPO_BINDING`, `GRANT_REMOTE_TRUST`,
  `REVOKE_REMOTE_TRUST`), all owned by `AdminArea.TOOLS`, auto-discovered by
  the capabilities read model (no hand-maintained list).
- draft → validate → preview → publish registers a `RepoBinding` visible to
  its OWN tenant only; foreign tenant lookups stay `BINDING_TENANT_MISMATCH`.
- absent seams fail validation LOUDLY with a named reason; nothing publishes.
- rollback removes the binding (durable store re-saved — no resurrection).
- trust grant/revoke flip `is_trusted` with the change actor recorded; revoke
  without an effective grant is refused at validate; rollback restores the
  prior trust state or raises `RollbackUnavailable` instead of inventing one.
- credential material still never rides a payload (R176 FIX-04 unchanged).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from apps.agent_dev.git_tools import BindingLookupRefused, RepoBindingRegistry
from apps.api.capabilities import admin_actions_json
from core.admin import AdminConfigService
from core.admin.service import RollbackUnavailable
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    ACTION_AREA,
    FINAL_ACTIVE_ADMIN_AREAS,
    AdminAction,
    AdminArea,
    AdminDraftRequest,
    ConfigLifecycleState,
)
from core.contracts.audit import AuditEventType
from core.contracts.base import JsonObject
from core.contracts.remote_trust import RemoteTrustGrant
from core.contracts.repo_binding import GitRefusalCode, RepoBinding
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import SimpleScoringRouter
from core.tools.binding_store import JsonBindingStore
from core.tools.remote_trust import JsonRemoteTrustStore, RemoteTrustRegistry
from core.usage import InMemoryUsageAccounting

PLATFORM = UUID("00000000-0000-0000-0000-00000000ada1")
ACTOR = UUID("00000000-0000-0000-0000-0000000000ac")
TENANT_A = UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = UUID("00000000-0000-0000-0000-00000000000b")
REMOTE = "https://github.com/acme/shop"

NEW_ACTIONS = (
    AdminAction.REGISTER_REPO_BINDING,
    AdminAction.GRANT_REMOTE_TRUST,
    AdminAction.REVOKE_REMOTE_TRUST,
)


def _binding(root: Path, tenant: UUID, *, ref: str = "vault:dev-a") -> RepoBinding:
    (root / "wt").mkdir(parents=True, exist_ok=True)
    return RepoBinding(
        tenant_id=tenant,
        remote_url=REMOTE,
        branch="main",
        local_root=str(root / "wt"),
        credential_ref=ref,
        label="shop",
    )


def _binding_payload(binding: RepoBinding) -> JsonObject:
    return {"binding": binding.model_dump(mode="json")}


def _trust_payload(tenant: UUID, *, note: str | None = None) -> JsonObject:
    payload: JsonObject = {"target_tenant_id": str(tenant), "remote_url": REMOTE}
    if note is not None:
        payload["note"] = note
    return payload


class World:
    def __init__(self, tmp_path: Path, *, with_seams: bool = True) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.usage = InMemoryUsageAccounting()
        self.router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        self.audit = InMemoryAuditLog()
        self.state = tmp_path / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.repo_bindings = RepoBindingRegistry(JsonBindingStore(self.state / "bindings.json"))
        self.trust = RemoteTrustRegistry(JsonRemoteTrustStore(self.state / "trust.json"))
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
            active_areas=FINAL_ACTIVE_ADMIN_AREAS,
            repo_bindings=self.repo_bindings if with_seams else None,
            remote_trust=self.trust if with_seams else None,
        )

    def draft(self, action: AdminAction, payload: JsonObject):
        return self.admin.draft(tenant_id=PLATFORM, actor_id=ACTOR, action=action, payload=payload)

    def validate(self, action: AdminAction, payload: JsonObject):
        change = self.draft(action, payload)
        return self.admin.validate(PLATFORM, change.id)

    def publish(self, action: AdminAction, payload: JsonObject):
        change = self.draft(action, payload)
        validated = self.admin.validate(PLATFORM, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED, validated.validation_result
        previewed = self.admin.preview(PLATFORM, change.id)
        assert previewed.impact_preview
        return self.admin.publish(PLATFORM, change.id)


# --- closed set + discovery --------------------------------------------------


class TestClosedSet:
    def test_three_new_actions_owned_by_tools(self) -> None:
        assert len(AdminAction) == 17
        for action in NEW_ACTIONS:
            assert ACTION_AREA[action] is AdminArea.TOOLS
        assert set(ACTION_AREA) == set(AdminAction)
        assert AdminArea.TOOLS in FINAL_ACTIVE_ADMIN_AREAS

    def test_actions_are_discovered_by_the_capabilities_read_model(self) -> None:
        payload = admin_actions_json()
        owners = {row["action"]: row["area"] for row in payload["actions"]}
        for action in NEW_ACTIONS:
            assert owners[action.value] == "tools"
        fields = {row["action"]: row["fields"] for row in payload["actions"]}
        assert [f["name"] for f in fields["register_repo_binding"]] == ["binding"]
        assert {f["name"] for f in fields["grant_remote_trust"]} == {
            "target_tenant_id",
            "remote_url",
            "note",
        }

    def test_credential_material_still_refused_in_payloads(self, tmp_path: Path) -> None:
        raw = _binding(tmp_path, TENANT_A).model_dump(mode="json")
        raw["token"] = "ghp_not_a_real_token"  # noqa: S105 — shape probe
        with pytest.raises(ValidationError, match="credential material"):
            AdminDraftRequest(action=AdminAction.REGISTER_REPO_BINDING, payload={"binding": raw})
        # the opaque handle IS admitted
        AdminDraftRequest(
            action=AdminAction.REGISTER_REPO_BINDING,
            payload=_binding_payload(_binding(tmp_path, TENANT_A)),
        )


# --- binding registration ----------------------------------------------------


class TestRegisterRepoBinding:
    def test_publish_registers_for_owner_only(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        binding = _binding(tmp_path, TENANT_A)
        published = w.publish(AdminAction.REGISTER_REPO_BINDING, _binding_payload(binding))
        assert published.state is ConfigLifecycleState.PUBLISHED
        assert w.repo_bindings.get(binding.id, tenant_id=TENANT_A) == binding
        with pytest.raises(BindingLookupRefused) as exc:
            w.repo_bindings.get(binding.id, tenant_id=TENANT_B)
        assert exc.value.code is GitRefusalCode.BINDING_TENANT_MISMATCH
        # durable: a fresh registry over the same store sees it
        reloaded = RepoBindingRegistry(JsonBindingStore(w.state / "bindings.json"))
        assert reloaded.get(binding.id, tenant_id=TENANT_A) == binding
        kinds = [e.event_type for e in w.audit.read(PLATFORM)]
        assert AuditEventType.ADMIN_CONFIG_PUBLISHED in kinds

    def test_invalid_contract_and_duplicate_refused_at_validate(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        bad = w.validate(
            AdminAction.REGISTER_REPO_BINDING,
            {"binding": {"tenant_id": str(TENANT_A), "remote_url": "http://insecure"}},
        )
        assert bad.state is ConfigLifecycleState.REJECTED
        assert "RepoBinding" in (bad.validation_result or "")
        binding = _binding(tmp_path, TENANT_A)
        w.publish(AdminAction.REGISTER_REPO_BINDING, _binding_payload(binding))
        dup = w.validate(AdminAction.REGISTER_REPO_BINDING, _binding_payload(binding))
        assert dup.state is ConfigLifecycleState.REJECTED
        assert "already registered" in (dup.validation_result or "")

    def test_absent_seam_fails_validation_loudly(self, tmp_path: Path) -> None:
        w = World(tmp_path, with_seams=False)
        r = w.validate(
            AdminAction.REGISTER_REPO_BINDING, _binding_payload(_binding(tmp_path, TENANT_A))
        )
        assert r.state is ConfigLifecycleState.REJECTED
        assert "repo bindings registry seam is not bound" in (r.validation_result or "")
        t = w.validate(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        assert t.state is ConfigLifecycleState.REJECTED
        assert "remote trust registry seam is not bound" in (t.validation_result or "")

    def test_rollback_removes_binding_without_resurrection(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        binding = _binding(tmp_path, TENANT_A)
        published = w.publish(AdminAction.REGISTER_REPO_BINDING, _binding_payload(binding))
        rolled = w.admin.rollback(PLATFORM, published.id)
        assert rolled.state is ConfigLifecycleState.ROLLED_BACK
        with pytest.raises(BindingLookupRefused) as exc:
            w.repo_bindings.get(binding.id, tenant_id=TENANT_A)
        assert exc.value.code is GitRefusalCode.BINDING_UNKNOWN
        reloaded = RepoBindingRegistry(JsonBindingStore(w.state / "bindings.json"))
        assert reloaded.list_for_tenant(TENANT_A) == []

    def test_registry_remove_is_tenant_scoped(self, tmp_path: Path) -> None:
        registry = RepoBindingRegistry()
        binding = registry.register(_binding(tmp_path, TENANT_A))
        with pytest.raises(BindingLookupRefused) as exc:
            registry.remove(binding.id, tenant_id=TENANT_B)
        assert exc.value.code is GitRefusalCode.BINDING_TENANT_MISMATCH
        assert registry.remove(binding.id, tenant_id=TENANT_A) == binding
        with pytest.raises(BindingLookupRefused) as unknown:
            registry.remove(binding.id, tenant_id=TENANT_A)
        assert unknown.value.code is GitRefusalCode.BINDING_UNKNOWN


# --- remote trust ------------------------------------------------------------


class TestRemoteTrust:
    def test_grant_then_revoke_records_actor(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        assert w.trust.is_trusted(TENANT_A, REMOTE) is False
        w.publish(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A, note="pilot"))
        grant = w.trust.get(TENANT_A, REMOTE)
        assert grant is not None and grant.trusted and grant.granted_by == str(ACTOR)
        assert grant.note == "pilot"
        assert w.trust.is_trusted(TENANT_A, REMOTE) is True
        assert w.trust.is_trusted(TENANT_B, REMOTE) is False  # keyed by tenant
        w.publish(AdminAction.REVOKE_REMOTE_TRUST, _trust_payload(TENANT_A))
        revoked = w.trust.get(TENANT_A, REMOTE)
        assert revoked is not None and revoked.revoked_by == str(ACTOR)
        assert w.trust.is_trusted(TENANT_A, REMOTE) is False
        # durable
        reloaded = RemoteTrustRegistry(JsonRemoteTrustStore(w.state / "trust.json"))
        assert reloaded.is_trusted(TENANT_A, REMOTE) is False
        assert reloaded.get(TENANT_A, REMOTE) is not None

    def test_grant_validation_rules(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        insecure = w.validate(
            AdminAction.GRANT_REMOTE_TRUST,
            {"target_tenant_id": str(TENANT_A), "remote_url": "http://github.com/x/y"},
        )
        assert insecure.state is ConfigLifecycleState.REJECTED
        assert "remote_url" in (insecure.validation_result or "")
        w.publish(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        again = w.validate(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        assert again.state is ConfigLifecycleState.REJECTED
        assert "already trusted" in (again.validation_result or "")

    def test_revoke_without_effective_grant_refused(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        r = w.validate(AdminAction.REVOKE_REMOTE_TRUST, _trust_payload(TENANT_A))
        assert r.state is ConfigLifecycleState.REJECTED
        assert "nothing to revoke" in (r.validation_result or "")
        assert w.trust.get(TENANT_A, REMOTE) is None  # no phantom row

    def test_rollback_of_grant_without_prior_revokes_auditably(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        published = w.publish(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        rolled = w.admin.rollback(PLATFORM, published.id)
        assert rolled.state is ConfigLifecycleState.ROLLED_BACK
        assert w.trust.is_trusted(TENANT_A, REMOTE) is False
        row = w.trust.get(TENANT_A, REMOTE)
        assert row is not None and row.revoked_by == str(ACTOR)  # never silent deletion

    def test_rollback_of_revoke_restores_prior_grant(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        prior = RemoteTrustGrant(
            tenant_id=TENANT_A,
            remote_url=REMOTE,
            trusted=True,
            granted_by="operator-0",
            granted_at=datetime.now(UTC),
            note="seed",
        )
        w.trust.grant(prior)
        published = w.publish(AdminAction.REVOKE_REMOTE_TRUST, _trust_payload(TENANT_A))
        assert w.trust.is_trusted(TENANT_A, REMOTE) is False
        w.admin.rollback(PLATFORM, published.id)
        restored = w.trust.get(TENANT_A, REMOTE)
        assert restored is not None and restored.effective
        assert restored.note == "seed" and restored.granted_by == str(ACTOR)

    def test_rollback_of_revoke_is_unavailable_when_nothing_effective_was_replaced(
        self, tmp_path: Path
    ) -> None:
        # A revoke can only publish over an effective grant; if the snapshot
        # somehow carries no prior grant, restore refuses rather than invent.
        w = World(tmp_path)
        w.publish(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        published = w.publish(AdminAction.REVOKE_REMOTE_TRUST, _trust_payload(TENANT_A))
        w.admin._snapshots[published.id] = {"trust_grant": None}  # internal probe
        with pytest.raises(RollbackUnavailable):
            w.admin.rollback(PLATFORM, published.id)

    def test_previews_are_plain_language(self, tmp_path: Path) -> None:
        w = World(tmp_path)
        c1 = w.draft(
            AdminAction.REGISTER_REPO_BINDING, _binding_payload(_binding(tmp_path, TENANT_A))
        )
        w.admin.validate(PLATFORM, c1.id)
        assert "binding" in (w.admin.preview(PLATFORM, c1.id).impact_preview or "")
        c2 = w.draft(AdminAction.GRANT_REMOTE_TRUST, _trust_payload(TENANT_A))
        w.admin.validate(PLATFORM, c2.id)
        assert "trust" in (w.admin.preview(PLATFORM, c2.id).impact_preview or "")
