"""Skill import pipeline — 41 §16 / 14 §3 lifecycle machinery (T-IMPL-062).

Spec anchors:

- 41 §16 (verbatim): import sources (three named URLs), import lifecycle
  ``imported → scanned → validated → reviewed → approved → active``, and
  "Local copy: every external Skill becomes a Local Version."
- 14 §3 (verbatim): the same lifecycle; "External sources are references,
  not runtime dependencies."; the six provenance fields every imported
  skill must carry (source_url / source_version / checksum / imported_at /
  reviewed_by / local_version).
- 14 §9 (forbidden, verbatim): "Imported skill becomes active without
  review." — the step preconditions make this structurally impossible.
- 14 §10 test list: "skill manifest validation", "skill import checksum",
  "malicious skill blocked".

Recorded derivations (nothing invented silently):

- HERMETIC BY DESIGN: 14 §3 verbatim — "External sources are references,
  not runtime dependencies." This module NEVER fetches. The caller obtains
  external content out-of-band (actual network import is Lane-C-adjacent
  and is NOT claimed, 41 §49); the pipeline receives content as DATA and
  the three 41 §16 source URLs are configuration data (an allowlist),
  never dereferenced.
- SOURCE ALLOWLIST: deny-by-default (41 §1 rule 9) — a source_url is
  admitted only if it starts with one of the configured sources
  (prefix match admits repo sub-paths); anything else refuses loudly.
- CHECKSUM = SHA-256 hex digest of the content. 14 §3 names "checksum"
  without an algorithm; SHA-256 (stdlib hashlib, no new dependency) is
  recorded as the chosen digest. A caller-declared expected checksum is
  verified (14 §10 "skill import checksum"); mismatch refuses.
- SELF-DECLARATION STRIPPED: the pipeline OWNS source/status. Whatever
  the external manifest claims, import produces source=imported /
  status=imported — an external artifact cannot pre-claim pipeline
  progress (deny-by-default).
- LOCAL VERSION = ACTIVATION (the key reading): 41 §16 "every external
  Skill becomes a Local Version" + the registry's Phase-6 rule (select
  admits source=local only, docstring: "until the import machinery ...
  exists to have vouched for it") compose into one coherent posture —
  completing the pipeline IS the vouching, and ``activate()`` flips
  ``source`` to LOCAL (provenance keeps the full import record). The
  registry's local+active gate is untouched and now STRUCTURALLY enforces
  14 §9: a skill registered directly as (imported, active) remains
  unselectable; the only path from external content to selectability is
  the full pipeline. The pre-existing Phase-6 test stays true.
- ONE STEP AT A TIME, IN ORDER: each step names its required predecessor
  status; any other status refuses with the step and current state named
  (11 §14 explainability). ``disabled`` stays a terminal administrative
  state OUTSIDE the pipeline (as recorded on SkillStatus) — no step
  produces or consumes it.
- SCAN FINDINGS BLOCK: a non-empty findings list refuses the scanned
  transition (14 §10 "malicious skill blocked") and the record does not
  progress; findings CONTENT is caller data — what scanning looks for is
  scanner policy, not defined by any doc, so the pipeline only enforces
  "findings ⇒ blocked".
- VALIDATED = manifest agreement + provenance completeness: 14 §10 names
  "skill manifest validation"; the validation step re-checks the entity/
  manifest agreement rule (same fields the registry enforces) and the
  14 §3 provenance presence promise recorded on SkillProvenance
  (reviewed_by is checked from review onward — it cannot exist earlier).
- ``local_version`` defaults to ``source_version`` (no doc defines a
  local-version scheme; the caller may override).
- The steps are PURE: each returns a NEW frozen Skill (entity and manifest
  advanced together so the registry's agreement rule keeps holding);
  registration/persistence stays with the registry and infrastructure.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol
from uuid import UUID

from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillProvenance,
    SkillSource,
    SkillStatus,
)
from core.skills.errors import (
    ChecksumMismatch,
    InvalidLifecycleStep,
    MissingProvenance,
    NotAnImportedSkill,
    ScanFindingsBlock,
    UnknownImportSource,
)

class SourcePrefixProvider(Protocol):
    """Live allowlist seam (the SkillSourceCatalog duck type)."""

    def allowed_prefixes(self) -> tuple[str, ...]:
        """ENABLED source URL prefixes, priority order."""
        ...


#: 41 §16 import sources, verbatim — configuration DATA, never dereferenced.
IMPORT_SOURCES: tuple[str, ...] = (
    "https://github.com/mattpocock/skills",
    "https://www.aihero.dev/skills-wayfinder",
    "https://github.com/amElnagdy/review-skills",
)

#: Provenance fields that must be present from the validated step onward
#: (14 §3 list minus reviewed_by, which the review step itself records).
_PRE_REVIEW_PROVENANCE_FIELDS = (
    "source_url",
    "source_version",
    "checksum",
    "imported_at",
    "local_version",
)

#: Entity/manifest fields that must agree (same rule the registry enforces).
_AGREEMENT_FIELDS = ("name", "version", "type", "source", "status")


def content_checksum(content: str) -> str:
    """SHA-256 hex digest of skill content (recorded checksum algorithm)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class SkillImportService:
    """The 14 §3 import lifecycle as explicit, ordered, pure steps."""

    def __init__(
        self,
        *,
        allowed_sources: tuple[str, ...] = IMPORT_SOURCES,
        source_prefixes: "SourcePrefixProvider | None" = None,
    ) -> None:
        """``source_prefixes`` (chunk 4): a LIVE provider of the allowlist —
        the SkillSourceCatalog seam. Bound, it supersedes the static
        ``allowed_sources`` tuple so admin SET_SKILL_SOURCES takes effect
        without recomposition (one source of truth, P2). Absent, the
        frozen 41 §16 default holds (existing behavior unchanged).
        """
        self._allowed_sources = allowed_sources
        self._source_prefixes = source_prefixes

    # --- entry: external content becomes an imported record ------------------

    def import_skill(
        self,
        *,
        skill_id: UUID,
        manifest: SkillManifest,
        content: str,
        source_url: str,
        source_version: str,
        imported_at: datetime,
        expected_checksum: str | None = None,
        local_version: str | None = None,
    ) -> Skill:
        """Create the imported record from externally-obtained content.

        The caller fetched ``content`` out-of-band (never this module);
        ``imported_at`` is caller-supplied so the pipeline stays
        deterministic (injectable time, same posture as the runtime fakes).
        """
        prefixes = (
            self._source_prefixes.allowed_prefixes()
            if self._source_prefixes is not None
            else self._allowed_sources
        )
        if not any(source_url.startswith(source) for source in prefixes):
            raise UnknownImportSource(source_url)
        checksum = content_checksum(content)
        if expected_checksum is not None and checksum != expected_checksum:
            raise ChecksumMismatch(expected=expected_checksum, actual=checksum)
        provenance = SkillProvenance(
            source_url=source_url,
            source_version=source_version,
            checksum=checksum,
            imported_at=imported_at,
            reviewed_by=None,
            local_version=local_version if local_version is not None else source_version,
        )
        # Self-declaration stripped: the pipeline owns source/status.
        normalized_manifest = manifest.model_copy(
            update={"source": SkillSource.IMPORTED, "status": SkillStatus.IMPORTED}
        )
        return Skill(
            id=skill_id,
            name=manifest.name,
            version=manifest.version,
            type=manifest.type,
            source=SkillSource.IMPORTED,
            provenance=provenance,
            manifest=normalized_manifest,
            status=SkillStatus.IMPORTED,
        )

    # --- lifecycle steps (14 §3 order, one at a time) -------------------------

    def scan(self, skill: Skill, *, findings: tuple[str, ...] = ()) -> Skill:
        """imported → scanned; any finding blocks (14 §10)."""
        self._require(skill, SkillStatus.IMPORTED, step="scan")
        if findings:
            raise ScanFindingsBlock(skill.id, findings)
        return _advance(skill, status=SkillStatus.SCANNED)

    def validate(self, skill: Skill) -> Skill:
        """scanned → validated; manifest agreement + provenance presence."""
        self._require(skill, SkillStatus.SCANNED, step="validate")
        for field in _AGREEMENT_FIELDS:
            if getattr(skill, field) != getattr(skill.manifest, field):
                raise InvalidLifecycleStep(
                    skill.id, skill.status.value, f"validate (manifest disagrees on {field})"
                )
        for field in _PRE_REVIEW_PROVENANCE_FIELDS:
            if getattr(skill.provenance, field) is None:
                raise MissingProvenance(skill.id, field)
        return _advance(skill, status=SkillStatus.VALIDATED)

    def review(self, skill: Skill, *, reviewed_by: str) -> Skill:
        """validated → reviewed; the reviewer is recorded in provenance."""
        self._require(skill, SkillStatus.VALIDATED, step="review")
        provenance = skill.provenance.model_copy(update={"reviewed_by": reviewed_by})
        return _advance(skill, status=SkillStatus.REVIEWED, provenance=provenance)

    def approve(self, skill: Skill) -> Skill:
        """reviewed → approved; unreachable without a recorded reviewer."""
        self._require(skill, SkillStatus.REVIEWED, step="approve")
        if skill.provenance.reviewed_by is None:
            raise MissingProvenance(skill.id, "reviewed_by")
        return _advance(skill, status=SkillStatus.APPROVED)

    def activate(self, skill: Skill) -> Skill:
        """approved → active — the skill BECOMES the Local Version.

        41 §16 "every external Skill becomes a Local Version": source flips
        to LOCAL here; provenance keeps the full import record. This is the
        ONLY sanctioned path from external content to registry
        selectability (the registry's local+active gate stays untouched).
        """
        self._require(skill, SkillStatus.APPROVED, step="activate")
        return _advance(skill, status=SkillStatus.ACTIVE, source=SkillSource.LOCAL)

    # --- internals -------------------------------------------------------------------

    def _require(self, skill: Skill, expected: SkillStatus, *, step: str) -> None:
        if skill.source is not SkillSource.IMPORTED:
            raise NotAnImportedSkill(skill.id, skill.source.value)
        if skill.status is not expected:
            raise InvalidLifecycleStep(skill.id, skill.status.value, step)


def _advance(
    skill: Skill,
    *,
    status: SkillStatus,
    source: SkillSource | None = None,
    provenance: SkillProvenance | None = None,
) -> Skill:
    """Produce the advanced record — entity and manifest move TOGETHER.

    The registry's agreement rule (name/version/type/source/status) must
    keep holding at every state, so both copies advance in one motion.
    """
    manifest_update: dict[str, object] = {"status": status}
    entity_update: dict[str, object] = {"status": status}
    if source is not None:
        manifest_update["source"] = source
        entity_update["source"] = source
    if provenance is not None:
        entity_update["provenance"] = provenance
    entity_update["manifest"] = skill.manifest.model_copy(update=manifest_update)
    return skill.model_copy(update=entity_update)
