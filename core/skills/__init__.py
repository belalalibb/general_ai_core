"""Skill import pipeline + resolver (FINAL Phase 13, 41 §16; T-IMPL-062).

Hermetic by design: 14 §3 "External sources are references, not runtime
dependencies" — nothing here fetches; the 41 §16 source URLs are an
allowlist (configuration data). Completing the pipeline is what makes an
external skill a Local Version (41 §16) and thereby registry-selectable;
14 §9 "Imported skill becomes active without review" is structurally
impossible. The resolver implements the §16 chain over the existing
SkillRegistry with named exclusions (11 §14).
"""

from core.skills.errors import (
    ChecksumMismatch,
    InvalidLifecycleStep,
    MissingProvenance,
    NotAnImportedSkill,
    ScanFindingsBlock,
    SkillImportError,
    UnknownImportSource,
)
from core.skills.importing import (
    IMPORT_SOURCES,
    SkillImportService,
    content_checksum,
)
from core.skills.resolver import SkillExclusion, SkillResolution, SkillResolver

__all__ = [
    "IMPORT_SOURCES",
    "ChecksumMismatch",
    "InvalidLifecycleStep",
    "MissingProvenance",
    "NotAnImportedSkill",
    "ScanFindingsBlock",
    "SkillExclusion",
    "SkillImportError",
    "SkillImportService",
    "SkillResolution",
    "SkillResolver",
    "UnknownImportSource",
    "content_checksum",
]
