"""Role + skill registries and governance (MVP Phase 6, 41 §45; FINAL Phase 12, 41 §15).

Loadable-not-selectable posture: registries hold any consistent record;
selection admits only status=active (and source=local for skills).
03 §8 binds: requested capabilities/tools are data, never grants.
Governance (41 §15): SYSTEM scope is admin-controlled; TENANT/USER/PROJECT
are the custom side; a custom role never grants permissions.
"""

from core.roles.errors import (
    DuplicateRegistration,
    ManifestMismatch,
    RegistryError,
    RoleNotRegistered,
    RoleNotSelectable,
    SkillNotRegistered,
    SkillNotSelectable,
)
from core.roles.governance import (
    CUSTOM_SCOPES,
    SYSTEM_SCOPES,
    RoleAdmissionDecision,
    RoleGovernance,
)
from core.roles.registry import RoleRegistry, SkillRegistry

__all__ = [
    "CUSTOM_SCOPES",
    "SYSTEM_SCOPES",
    "DuplicateRegistration",
    "ManifestMismatch",
    "RegistryError",
    "RoleAdmissionDecision",
    "RoleGovernance",
    "RoleNotRegistered",
    "RoleNotSelectable",
    "RoleRegistry",
    "SkillNotRegistered",
    "SkillNotSelectable",
    "SkillRegistry",
]
