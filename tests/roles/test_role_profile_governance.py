"""T-IMPL-061 — Role profile + governance (41 §15; FINAL Phase 12).

41 §15 coverage map (honest, 41 §49):

- role profile seven items → RoleProfile (five entity-backed + the two
  profile-only: preferred_skills, runtime_override)
- "System Roles: admin-controlled" → governance SYSTEM-scope tests
- "Custom Roles: user/project created" → governance custom-scope tests
- "a Custom Role never grants permissions" → escalation-surface tests
  (override cannot carry capability fields; requests recorded, never
  granted) + pre-existing test_role_selection_grants_nothing

All hermetic: contracts + registries only; zero I/O, zero AI.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.role_profile import RoleProfile, RoleRuntimeOverride
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.roles import (
    CUSTOM_SCOPES,
    SYSTEM_SCOPES,
    DuplicateRegistration,
    RoleGovernance,
    RoleRegistry,
)


def make_role(
    *,
    scope: RoleScope = RoleScope.SYSTEM,
    status: RoleStatus = RoleStatus.ACTIVE,
    capabilities: list[str] | None = None,
    behavior: dict[str, object] | None = None,
    output: dict[str, object] | None = None,
) -> Role:
    return Role.model_validate(
        {
            "id": uuid4(),
            "scope": scope,
            "name": "software_engineer",
            "version": "1.0.0",
            "objective": "Write correct, reviewed code.",
            "behavior_policies": behavior or {},
            "output_contract": output or {},
            "status": status,
            "capabilities_requested": capabilities or [],
        }
    )


# --- governance: the 41 §15 control split ---------------------------------------


def test_scope_partition_covers_every_scope_exactly_once() -> None:
    """The system/custom partition is total and disjoint over RoleScope."""
    assert SYSTEM_SCOPES | CUSTOM_SCOPES == frozenset(RoleScope)
    assert SYSTEM_SCOPES & CUSTOM_SCOPES == frozenset()


def test_admin_registers_system_role() -> None:
    registry = RoleRegistry()
    role = make_role(scope=RoleScope.SYSTEM)
    decision = RoleGovernance(registry).register(role, is_admin=True)
    assert decision.admitted and decision.reason is None
    assert registry.get(role.id) == role


def test_non_admin_cannot_register_system_role() -> None:
    """41 §15: System Roles are admin-controlled."""
    registry = RoleRegistry()
    role = make_role(scope=RoleScope.SYSTEM)
    decision = RoleGovernance(registry).register(role, is_admin=False)
    assert not decision.admitted
    assert decision.reason == "system_role_requires_admin"
    assert registry.list_all() == []  # refusal writes nothing


@pytest.mark.parametrize("scope", [RoleScope.TENANT, RoleScope.USER, RoleScope.PROJECT])
def test_non_admin_creates_custom_roles(scope: RoleScope) -> None:
    """41 §15: Custom Roles are user/project created."""
    registry = RoleRegistry()
    role = make_role(scope=scope)
    decision = RoleGovernance(registry).register(role, is_admin=False)
    assert decision.admitted
    assert registry.get(role.id) == role


def test_admin_may_also_create_custom_roles() -> None:
    registry = RoleRegistry()
    decision = RoleGovernance(registry).register(make_role(scope=RoleScope.PROJECT), is_admin=True)
    assert decision.admitted


def test_evaluate_is_pure_and_writes_nothing() -> None:
    registry = RoleRegistry()
    decision = RoleGovernance(registry).evaluate(make_role(scope=RoleScope.USER), is_admin=False)
    assert decision.admitted
    assert registry.list_all() == []


def test_governed_registration_still_rejects_duplicates() -> None:
    """Governance layers OVER the registry; registry rules keep holding."""
    registry = RoleRegistry()
    governance = RoleGovernance(registry)
    role = make_role(scope=RoleScope.USER)
    assert governance.register(role, is_admin=False).admitted
    with pytest.raises(DuplicateRegistration):
        governance.register(role, is_admin=False)


# --- "a Custom Role never grants permissions" ------------------------------------


def test_custom_role_capability_requests_recorded_never_granted() -> None:
    """Requesting is legal (03 §8); the decision RECORDS, grants nothing."""
    registry = RoleRegistry()
    role = make_role(scope=RoleScope.USER, capabilities=["coding", "web_search"])
    decision = RoleGovernance(registry).register(role, is_admin=False)
    assert decision.admitted
    assert decision.capabilities_requested == ("coding", "web_search")
    # The stored role still only REQUESTS — no grant field exists at all.
    assert not hasattr(registry.get(role.id), "capabilities_granted")


def test_runtime_override_cannot_carry_capability_fields() -> None:
    """The runtime-escalation channel is structurally closed."""
    with pytest.raises(ValidationError):
        RoleRuntimeOverride.model_validate({"capabilities_requested": ["admin_access"]})
    with pytest.raises(ValidationError):
        RoleRuntimeOverride.model_validate({"scope": "system"})
    with pytest.raises(ValidationError):
        RoleRuntimeOverride.model_validate({"status": "active"})


# --- role profile: the seven 41 §15 items -----------------------------------------


def test_profile_exposes_the_five_entity_backed_items() -> None:
    role = make_role(
        capabilities=["coding"],
        behavior={"tone": "concise"},
        output={"format": "markdown"},
    )
    profile = RoleProfile.model_validate({"role": role})
    assert profile.identity == "system:software_engineer@1.0.0"
    assert profile.objective == "Write correct, reviewed code."
    assert profile.required_capabilities == ["coding"]
    assert profile.effective_behavior_policies() == {"tone": "concise"}
    assert profile.effective_output_contract() == {"format": "markdown"}


def test_profile_defaults_carry_no_preferences_and_no_override() -> None:
    profile = RoleProfile.model_validate({"role": make_role()})
    assert profile.preferred_skills == []
    assert profile.runtime_override is None


def test_preferred_skills_are_name_references() -> None:
    """Advisory input for the Phase 13 resolver — mirrors 14 §2 naming."""
    profile = RoleProfile.model_validate(
        {"role": make_role(), "preferred_skills": ["code_review", "test_gen"]}
    )
    assert profile.preferred_skills == ["code_review", "test_gen"]


def test_override_overlays_key_level_and_base_survives() -> None:
    role = make_role(
        behavior={"tone": "concise", "language": "en"},
        output={"format": "markdown"},
    )
    profile = RoleProfile.model_validate(
        {
            "role": role,
            "runtime_override": {"behavior_policies": {"tone": "formal"}},
        }
    )
    assert profile.effective_behavior_policies() == {
        "tone": "formal",  # override wins its key
        "language": "en",  # base survives untouched keys
    }
    assert profile.effective_output_contract() == {"format": "markdown"}


def test_override_never_mutates_the_persisted_entity() -> None:
    """Runtime override is invocation-scoped: the entity stays verbatim."""
    role = make_role(behavior={"tone": "concise"})
    profile = RoleProfile.model_validate(
        {
            "role": role,
            "runtime_override": {"behavior_policies": {"tone": "formal"}},
        }
    )
    assert profile.effective_behavior_policies()["tone"] == "formal"
    assert role.behavior_policies == {"tone": "concise"}
    assert profile.role.behavior_policies == {"tone": "concise"}


def test_profile_rejects_unknown_fields() -> None:
    """No smuggled surfaces: the profile is exactly the documented items."""
    with pytest.raises(ValidationError):
        RoleProfile.model_validate({"role": make_role(), "permissions": ["admin"]})
