"""Contract tests: Role + Skill entities and the skill manifest.

Authority: 03 §6 (entities, field-for-field), 03 §8 (request-not-grant),
14 §2 (manifest shape), 14 §3 (import lifecycle + provenance).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.roles import Role, RoleScope, RoleStatus
from core.contracts.skills import (
    IMPORT_LIFECYCLE_ORDER,
    Skill,
    SkillInvocation,
    SkillManifest,
    SkillProvenance,
    SkillRuntime,
    SkillSource,
    SkillStatus,
    SkillToolRequirements,
    SkillType,
)

# --- Closed sets (verbatim from spec) ---------------------------------------------


def test_role_scope_closed_set_verbatim() -> None:
    assert {s.value for s in RoleScope} == {"system", "tenant", "user", "project"}


def test_role_status_closed_set_verbatim() -> None:
    assert {s.value for s in RoleStatus} == {"draft", "active", "disabled"}


def test_skill_type_closed_set_verbatim() -> None:
    assert {t.value for t in SkillType} == {"instruction", "workflow", "tool_enabled"}


def test_skill_source_closed_set_verbatim() -> None:
    assert {s.value for s in SkillSource} == {"local", "imported"}


def test_skill_status_closed_set_verbatim() -> None:
    assert {s.value for s in SkillStatus} == {
        "imported",
        "scanned",
        "validated",
        "reviewed",
        "approved",
        "active",
        "disabled",
    }


def test_import_lifecycle_order_is_14_s3_pipeline_verbatim() -> None:
    """14 §3: imported → scanned → validated → reviewed → approved → active."""
    assert [s.value for s in IMPORT_LIFECYCLE_ORDER] == [
        "imported",
        "scanned",
        "validated",
        "reviewed",
        "approved",
        "active",
    ]
    # disabled is an administrative state OUTSIDE the pipeline.
    assert SkillStatus.DISABLED not in IMPORT_LIFECYCLE_ORDER


# --- Role entity -------------------------------------------------------------------


def _role(**overrides: object) -> Role:
    base: dict[str, object] = {
        "id": uuid4(),
        "scope": "system",
        "name": "software_engineer",
        "version": "1.0.0",
        "objective": "Deliver correct, reviewed code changes.",
        "status": "active",
    }
    base.update(overrides)
    return Role.model_validate(base)


def test_role_entity_03_s6_fields() -> None:
    role = _role(
        behavior_policies={"tone": "precise"},
        output_contract={"format": "markdown"},
        capabilities_requested=["coding"],
    )
    assert role.scope is RoleScope.SYSTEM
    assert role.status is RoleStatus.ACTIVE
    assert role.behavior_policies == {"tone": "precise"}
    assert role.capabilities_requested == ["coding"]


def test_role_capabilities_are_requests_default_empty() -> None:
    """03 §8: capabilities are REQUESTED (data); default is nothing requested."""
    assert _role().capabilities_requested == []


def test_role_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        _role(granted_permissions=["admin"])  # grants do not exist on this contract


def test_role_unknown_scope_rejected() -> None:
    with pytest.raises(ValidationError):
        _role(scope="galaxy")


def test_role_empty_objective_rejected() -> None:
    with pytest.raises(ValidationError):
        _role(objective="")


def test_role_is_frozen() -> None:
    role = _role()
    with pytest.raises(ValidationError):
        role.status = RoleStatus.DISABLED  # type: ignore[misc]


# --- Skill manifest (14 §2) --------------------------------------------------------


def _manifest(**overrides: object) -> SkillManifest:
    base: dict[str, object] = {
        "id": "code_review",
        "name": "Code Review",
        "version": "1.0.0",
        "type": "instruction",
        "source": "local",
        "status": "active",
        "capabilities": ["coding", "reasoning"],
        "inputs_schema": None,
        "outputs_format": "markdown",
        "requires_tools": {"optional": ["github.read"], "required": []},
        "permissions_requested": [],
        "runtime": {
            "invocation": "user_or_model",
            "compatible_roles": ["software_engineer", "reviewer"],
        },
    }
    base.update(overrides)
    return SkillManifest.model_validate(base)


def test_manifest_14_s2_example_validates() -> None:
    """The 14 §2 code_review example validates field-for-field."""
    manifest = _manifest()
    assert manifest.type is SkillType.INSTRUCTION
    assert manifest.source is SkillSource.LOCAL
    assert manifest.inputs_schema is None
    assert manifest.requires_tools.optional == ["github.read"]
    assert manifest.requires_tools.required == []
    assert manifest.runtime.invocation is SkillInvocation.USER_OR_MODEL
    assert "reviewer" in manifest.runtime.compatible_roles


def test_manifest_tools_are_requirements_not_grants() -> None:
    """03 §8: requires_tools lists names as data; no grant field exists."""
    with pytest.raises(ValidationError):
        _manifest(granted_tools=["github.write"])


def test_manifest_unknown_invocation_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(runtime={"invocation": "autonomous"})


def test_manifest_defaults_are_safe() -> None:
    """Omitting optional blocks yields empty requests, never implicit ones."""
    manifest = SkillManifest.model_validate(
        {
            "id": "summarize",
            "name": "Summarize",
            "version": "0.1.0",
            "type": "instruction",
            "source": "local",
            "status": "active",
        }
    )
    assert manifest.capabilities == []
    assert manifest.permissions_requested == []
    assert manifest.requires_tools == SkillToolRequirements()
    assert manifest.runtime == SkillRuntime()


# --- Skill entity + provenance (03 §6 + 14 §3) --------------------------------------


def _skill(**overrides: object) -> Skill:
    manifest = overrides.pop("manifest", _manifest())
    base: dict[str, object] = {
        "id": uuid4(),
        "name": "Code Review",
        "version": "1.0.0",
        "type": "instruction",
        "source": "local",
        "manifest": manifest,
        "status": "active",
    }
    base.update(overrides)
    return Skill.model_validate(base)


def test_skill_entity_03_s6_fields() -> None:
    skill = _skill()
    assert skill.type is SkillType.INSTRUCTION
    assert skill.source is SkillSource.LOCAL
    assert skill.status is SkillStatus.ACTIVE
    assert skill.manifest.id == "code_review"


def test_skill_local_provenance_defaults_empty() -> None:
    """Local skills carry no import origin (14 §3 fields all optional)."""
    assert _skill().provenance == SkillProvenance()


def test_skill_imported_provenance_14_s3_fields() -> None:
    skill = _skill(
        source="imported",
        status="imported",
        manifest=_manifest(source="imported", status="imported"),
        provenance={
            "source_url": "https://example.org/skills/code-review",
            "source_version": "2.3.1",
            "checksum": "sha256:abc123",
            "imported_at": "2026-08-26T00:00:00Z",
            "reviewed_by": "admin@example.org",
            "local_version": "1.0.0",
        },
    )
    assert skill.provenance.checksum == "sha256:abc123"
    assert skill.provenance.local_version == "1.0.0"


def test_skill_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        _skill(executable=True)


def test_skill_is_frozen() -> None:
    skill = _skill()
    with pytest.raises(ValidationError):
        skill.status = SkillStatus.DISABLED  # type: ignore[misc]
