"""Registry tests: loadable-not-selectable admission for roles + skills.

Authority: 41 §45 (system roles, local skills), 03 §8 (request-not-grant),
14 §3 (pipeline states not selectable), 31 §10 posture mirror, R044
boundaries (a)/(b) (local-only selection; tools inert).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.contracts.roles import Role
from core.contracts.skills import Skill, SkillManifest
from core.roles import (
    DuplicateRegistration,
    ManifestMismatch,
    RoleNotRegistered,
    RoleNotSelectable,
    RoleRegistry,
    SkillNotRegistered,
    SkillNotSelectable,
    SkillRegistry,
)

# --- Builders ----------------------------------------------------------------------


def _role(*, name: str = "software_engineer", status: str = "active") -> Role:
    return Role.model_validate(
        {
            "id": uuid4(),
            "scope": "system",
            "name": name,
            "version": "1.0.0",
            "objective": "Deliver correct, reviewed code changes.",
            "status": status,
        }
    )


def _manifest(
    *, name: str = "Code Review", source: str = "local", status: str = "active"
) -> SkillManifest:
    return SkillManifest.model_validate(
        {
            "id": "code_review",
            "name": name,
            "version": "1.0.0",
            "type": "instruction",
            "source": source,
            "status": status,
            "requires_tools": {"optional": ["github.read"], "required": []},
        }
    )


def _skill(
    *,
    name: str = "Code Review",
    source: str = "local",
    status: str = "active",
    manifest: SkillManifest | None = None,
) -> Skill:
    return Skill.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "type": "instruction",
            "source": source,
            "manifest": manifest
            if manifest is not None
            else _manifest(name=name, source=source, status=status),
            "status": status,
        }
    )


# --- RoleRegistry ------------------------------------------------------------------


def test_register_and_get_role() -> None:
    registry = RoleRegistry()
    role = _role()
    registry.register(role)
    assert registry.get(role.id) == role


def test_duplicate_role_registration_rejected() -> None:
    registry = RoleRegistry()
    role = _role()
    registry.register(role)
    with pytest.raises(DuplicateRegistration):
        registry.register(role)


def test_unknown_role_raises_not_registered() -> None:
    with pytest.raises(RoleNotRegistered):
        RoleRegistry().get(uuid4())
    with pytest.raises(RoleNotRegistered):
        RoleRegistry().select(uuid4())


def test_select_active_role() -> None:
    registry = RoleRegistry()
    role = _role(status="active")
    registry.register(role)
    assert registry.select(role.id) == role


@pytest.mark.parametrize("status", ["draft", "disabled"])
def test_non_active_role_loadable_but_not_selectable(status: str) -> None:
    """31 §10 mirror: get succeeds (inspection), select denies with reason."""
    registry = RoleRegistry()
    role = _role(status=status)
    registry.register(role)
    assert registry.get(role.id) == role  # loadable
    with pytest.raises(RoleNotSelectable) as exc:
        registry.select(role.id)
    assert exc.value.status == status  # named, explainable denial


def test_list_selectable_roles_excludes_non_active() -> None:
    registry = RoleRegistry()
    active = _role(name="a_reviewer", status="active")
    registry.register(active)
    registry.register(_role(name="b_draft", status="draft"))
    registry.register(_role(name="c_disabled", status="disabled"))
    assert registry.list_selectable() == [active]
    assert len(registry.list_all()) == 3


def test_role_selection_grants_nothing() -> None:
    """03 §8: a selected role still only REQUESTS capabilities (data)."""
    registry = RoleRegistry()
    role = Role.model_validate(
        {
            "id": uuid4(),
            "scope": "system",
            "name": "software_engineer",
            "version": "1.0.0",
            "objective": "Deliver code.",
            "status": "active",
            "capabilities_requested": ["coding", "shell"],
        }
    )
    registry.register(role)
    selected = registry.select(role.id)
    # The registry returns the request list untouched — no grant surface exists.
    assert selected.capabilities_requested == ["coding", "shell"]
    assert not hasattr(selected, "capabilities_granted")


# --- SkillRegistry -----------------------------------------------------------------


def test_register_and_get_skill() -> None:
    registry = SkillRegistry()
    skill = _skill()
    registry.register(skill)
    assert registry.get(skill.id) == skill


def test_duplicate_skill_registration_rejected() -> None:
    registry = SkillRegistry()
    skill = _skill()
    registry.register(skill)
    with pytest.raises(DuplicateRegistration):
        registry.register(skill)


def test_unknown_skill_raises_not_registered() -> None:
    with pytest.raises(SkillNotRegistered):
        SkillRegistry().get(uuid4())
    with pytest.raises(SkillNotRegistered):
        SkillRegistry().select(uuid4())


def test_select_active_local_skill() -> None:
    registry = SkillRegistry()
    skill = _skill(source="local", status="active")
    registry.register(skill)
    assert registry.select(skill.id) == skill


@pytest.mark.parametrize(
    "status",
    ["imported", "scanned", "validated", "reviewed", "approved", "disabled"],
)
def test_pipeline_and_disabled_states_loadable_but_not_selectable(
    status: str,
) -> None:
    """14 §3 pipeline states + disabled: representable, never selectable."""
    registry = SkillRegistry()
    skill = _skill(status=status)
    registry.register(skill)
    assert registry.get(skill.id) == skill  # loadable
    with pytest.raises(SkillNotSelectable) as exc:
        registry.select(skill.id)
    assert exc.value.reason == f"status={status}"


def test_imported_active_skill_not_selectable_in_phase_6() -> None:
    """R044 boundary (b): source=imported denies even at status=active."""
    registry = SkillRegistry()
    skill = _skill(source="imported", status="active")
    registry.register(skill)
    with pytest.raises(SkillNotSelectable) as exc:
        registry.select(skill.id)
    assert exc.value.reason == "source=imported"


def test_manifest_mismatch_rejected_at_registration() -> None:
    """Divergent entity/manifest pairs are rejected, naming the field."""
    registry = SkillRegistry()
    skill = _skill(name="Code Review", manifest=_manifest(name="Other Name"))
    with pytest.raises(ManifestMismatch) as exc:
        registry.register(skill)
    assert exc.value.field == "name"
    # Nothing was stored: a rejected registration leaves no record.
    with pytest.raises(SkillNotRegistered):
        registry.get(skill.id)


def test_manifest_mismatch_checks_status_too() -> None:
    registry = SkillRegistry()
    skill = _skill(status="active", manifest=_manifest(status="disabled"))
    with pytest.raises(ManifestMismatch) as exc:
        registry.register(skill)
    assert exc.value.field == "status"


def test_list_selectable_skills_active_local_only() -> None:
    registry = SkillRegistry()
    selectable = _skill(name="a_local_active")
    registry.register(selectable)
    registry.register(_skill(name="b_local_draftish", status="approved"))
    registry.register(_skill(name="c_imported_active", source="imported"))
    assert registry.list_selectable() == [selectable]
    assert len(registry.list_all()) == 3


def test_selected_skill_tools_remain_inert_data() -> None:
    """R044 boundary (a) + 03 §8: requires_tools is data; no execution surface."""
    registry = SkillRegistry()
    skill = _skill()
    registry.register(skill)
    selected = registry.select(skill.id)
    assert selected.manifest.requires_tools.optional == ["github.read"]
    # No callable/execution attribute exists on the returned contract.
    assert not hasattr(selected, "execute")
    assert not hasattr(selected.manifest, "execute")
