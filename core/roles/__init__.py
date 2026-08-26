"""Role + skill registries (MVP Phase 6, 41 §45).

Loadable-not-selectable posture: registries hold any consistent record;
selection admits only status=active (and source=local for skills).
03 §8 binds: requested capabilities/tools are data, never grants.
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
from core.roles.registry import RoleRegistry, SkillRegistry

__all__ = [
    "DuplicateRegistration",
    "ManifestMismatch",
    "RegistryError",
    "RoleNotRegistered",
    "RoleNotSelectable",
    "RoleRegistry",
    "SkillNotRegistered",
    "SkillNotSelectable",
    "SkillRegistry",
]
