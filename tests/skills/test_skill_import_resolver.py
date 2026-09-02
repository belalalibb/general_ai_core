"""T-IMPL-062 tests: skill import lifecycle + resolver (FINAL Phase 13, 41 §16).

Exit-list mapping (14 §10, skill-domain items; tool items are Phase 14):

- "skill manifest validation" -> test_validate_checks_manifest_agreement,
  test_validate_requires_provenance_fields (+ pre-existing registry
  manifest-mismatch tests, verified by name, not redone).
- "skill import checksum" -> test_import_records_content_checksum,
  test_checksum_mismatch_refused.
- "malicious skill blocked" -> test_scan_findings_block_skill,
  test_blocked_skill_cannot_progress.
- 14 §9 "Imported skill becomes active without review" ->
  test_no_step_can_be_skipped (parametrized over every skipped step),
  test_activation_requires_recorded_reviewer, plus the pre-existing
  test_imported_active_skill_not_selectable_in_phase_6 (registry gate —
  now the structural enforcement of §9, verified by name, not redone).

41 §16 items:

- import sources as allowlist DATA -> test_unknown_source_refused,
  test_source_allowlist_is_the_verbatim_41s16_list.
- lifecycle imported→…→active -> test_full_pipeline_reaches_active.
- "every external Skill becomes a Local Version" ->
  test_activation_makes_the_skill_a_local_version (source flips to local,
  provenance keeps the import record, registry now SELECTS it).
- Resolver chain -> the resolver test group (candidates from registry
  admission, compatibility gates with named exclusions, preferred-first
  deterministic ranking, limit truncation, context accepted as seam).

Hermetic: no network, no I/O — content arrives as literal strings.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.contracts.context import ComposedContext
from core.contracts.role_profile import RoleProfile
from core.contracts.roles import Role
from core.contracts.routing import TaskAnalysis
from core.contracts.skills import Skill, SkillManifest, SkillSource, SkillStatus
from core.roles import SkillNotSelectable, SkillRegistry
from core.skills import (
    IMPORT_SOURCES,
    ChecksumMismatch,
    InvalidLifecycleStep,
    MissingProvenance,
    NotAnImportedSkill,
    ScanFindingsBlock,
    SkillImportService,
    SkillResolver,
    UnknownImportSource,
    content_checksum,
)

SOURCE = "https://github.com/mattpocock/skills"
CONTENT = "# skill: review the diff before approving\n"
NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


def manifest(
    *,
    manifest_id: str = "code_review",
    name: str = "Code Review",
    source: str = "local",
    status: str = "active",
    capabilities: list[str] | None = None,
    compatible_roles: list[str] | None = None,
) -> SkillManifest:
    return SkillManifest.model_validate(
        {
            "id": manifest_id,
            "name": name,
            "version": "1.0.0",
            "type": "instruction",
            "source": source,
            "status": status,
            "capabilities": capabilities if capabilities is not None else [],
            "runtime": {
                "invocation": "user_or_model",
                "compatible_roles": (compatible_roles if compatible_roles is not None else []),
            },
        }
    )


def imported(service: SkillImportService, **overrides: object) -> Skill:
    kwargs: dict[str, object] = {
        "skill_id": uuid4(),
        "manifest": manifest(),
        "content": CONTENT,
        "source_url": SOURCE,
        "source_version": "abc123",
        "imported_at": NOW,
    }
    kwargs.update(overrides)
    return service.import_skill(**kwargs)  # type: ignore[arg-type]


def pipeline_to(service: SkillImportService, target: SkillStatus) -> Skill:
    """Advance a fresh import to the given lifecycle state."""
    skill = imported(service)
    if target is SkillStatus.IMPORTED:
        return skill
    skill = service.scan(skill)
    if target is SkillStatus.SCANNED:
        return skill
    skill = service.validate(skill)
    if target is SkillStatus.VALIDATED:
        return skill
    skill = service.review(skill, reviewed_by="admin@example.test")
    if target is SkillStatus.REVIEWED:
        return skill
    skill = service.approve(skill)
    if target is SkillStatus.APPROVED:
        return skill
    return service.activate(skill)


# --- import entry -------------------------------------------------------------------


def test_source_allowlist_is_the_verbatim_41s16_list() -> None:
    assert IMPORT_SOURCES == (
        "https://github.com/mattpocock/skills",
        "https://www.aihero.dev/skills-wayfinder",
        "https://github.com/amElnagdy/review-skills",
    )


def test_unknown_source_refused() -> None:
    service = SkillImportService()
    with pytest.raises(UnknownImportSource) as exc:
        imported(service, source_url="https://evil.example.test/skills")
    assert "evil.example.test" in str(exc.value)


def test_allowlisted_subpath_admitted() -> None:
    service = SkillImportService()
    skill = imported(service, source_url=SOURCE + "/tree/main/review")
    assert skill.provenance.source_url == SOURCE + "/tree/main/review"


def test_import_records_content_checksum() -> None:
    service = SkillImportService()
    skill = imported(service)
    expected = hashlib.sha256(CONTENT.encode("utf-8")).hexdigest()
    assert skill.provenance.checksum == expected
    assert content_checksum(CONTENT) == expected


def test_checksum_mismatch_refused() -> None:
    service = SkillImportService()
    with pytest.raises(ChecksumMismatch):
        imported(service, expected_checksum=content_checksum("tampered content"))


def test_import_strips_self_declared_source_and_status() -> None:
    """An external manifest cannot pre-claim pipeline progress."""
    service = SkillImportService()
    skill = imported(service, manifest=manifest(source="local", status="active"))
    assert skill.source is SkillSource.IMPORTED
    assert skill.status is SkillStatus.IMPORTED
    assert skill.manifest.source is SkillSource.IMPORTED
    assert skill.manifest.status is SkillStatus.IMPORTED


def test_import_records_full_provenance() -> None:
    service = SkillImportService()
    skill = imported(service)
    prov = skill.provenance
    assert prov.source_url == SOURCE
    assert prov.source_version == "abc123"
    assert prov.imported_at == NOW
    assert prov.local_version == "abc123"  # defaults to source_version
    assert prov.reviewed_by is None  # review has not happened yet


# --- lifecycle order ------------------------------------------------------------------


def test_full_pipeline_reaches_active() -> None:
    service = SkillImportService()
    skill = pipeline_to(service, SkillStatus.ACTIVE)
    assert skill.status is SkillStatus.ACTIVE


@pytest.mark.parametrize(
    ("start", "step"),
    [
        (SkillStatus.IMPORTED, "validate"),  # skips scan
        (SkillStatus.IMPORTED, "review"),
        (SkillStatus.IMPORTED, "approve"),
        (SkillStatus.IMPORTED, "activate"),
        (SkillStatus.SCANNED, "review"),  # skips validate
        (SkillStatus.SCANNED, "activate"),
        (SkillStatus.VALIDATED, "approve"),  # skips review — 14 §9 directly
        (SkillStatus.VALIDATED, "activate"),
        (SkillStatus.REVIEWED, "activate"),  # skips approve
    ],
)
def test_no_step_can_be_skipped(start: SkillStatus, step: str) -> None:
    """14 §3 order + 14 §9: no path to active skips a stage."""
    service = SkillImportService()
    skill = pipeline_to(service, start)
    actions = {
        "validate": lambda s: service.validate(s),
        "review": lambda s: service.review(s, reviewed_by="admin@example.test"),
        "approve": lambda s: service.approve(s),
        "activate": lambda s: service.activate(s),
    }
    with pytest.raises(InvalidLifecycleStep) as exc:
        actions[step](skill)
    assert exc.value.current == start.value


def test_steps_reject_local_skills() -> None:
    """The import lifecycle governs source=imported only (14 §3)."""
    service = SkillImportService()
    local = Skill.model_validate(
        {
            "id": uuid4(),
            "name": "Code Review",
            "version": "1.0.0",
            "type": "instruction",
            "source": "local",
            "manifest": manifest(),
            "status": "active",
        }
    )
    with pytest.raises(NotAnImportedSkill):
        service.scan(local)


def test_scan_findings_block_skill() -> None:
    """14 §10 'malicious skill blocked': any finding refuses scanned."""
    service = SkillImportService()
    skill = imported(service)
    with pytest.raises(ScanFindingsBlock) as exc:
        service.scan(skill, findings=("embedded shell command", "obfuscated payload"))
    assert exc.value.findings == ("embedded shell command", "obfuscated payload")


def test_blocked_skill_cannot_progress() -> None:
    """A blocked scan leaves the record at imported — nothing advanced."""
    service = SkillImportService()
    skill = imported(service)
    with pytest.raises(ScanFindingsBlock):
        service.scan(skill, findings=("malware",))
    assert skill.status is SkillStatus.IMPORTED  # frozen input untouched
    with pytest.raises(InvalidLifecycleStep):
        service.validate(skill)  # still not scanned


def test_validate_checks_manifest_agreement() -> None:
    """14 §10 'skill manifest validation': divergent pairs refused."""
    service = SkillImportService()
    skill = imported(service)
    scanned = service.scan(skill)
    divergent = scanned.model_copy(
        update={"manifest": scanned.manifest.model_copy(update={"version": "9.9.9"})}
    )
    with pytest.raises(InvalidLifecycleStep) as exc:
        service.validate(divergent)
    assert "version" in str(exc.value)


def test_validate_requires_provenance_fields() -> None:
    """14 §3 provenance presence enforced for imported skills."""
    service = SkillImportService()
    scanned = service.scan(imported(service))
    stripped = scanned.model_copy(
        update={"provenance": scanned.provenance.model_copy(update={"checksum": None})}
    )
    with pytest.raises(MissingProvenance) as exc:
        service.validate(stripped)
    assert exc.value.field == "checksum"


def test_review_records_reviewer() -> None:
    service = SkillImportService()
    validated = pipeline_to(service, SkillStatus.VALIDATED)
    reviewed = service.review(validated, reviewed_by="admin@example.test")
    assert reviewed.provenance.reviewed_by == "admin@example.test"
    assert reviewed.status is SkillStatus.REVIEWED


def test_activation_requires_recorded_reviewer() -> None:
    """approve refuses a reviewed record whose reviewer was stripped."""
    service = SkillImportService()
    reviewed = pipeline_to(service, SkillStatus.REVIEWED)
    stripped = reviewed.model_copy(
        update={"provenance": reviewed.provenance.model_copy(update={"reviewed_by": None})}
    )
    with pytest.raises(MissingProvenance) as exc:
        service.approve(stripped)
    assert exc.value.field == "reviewed_by"


# --- Local Version (41 §16) ---------------------------------------------------------


def test_activation_makes_the_skill_a_local_version() -> None:
    """41 §16: source flips to local; provenance keeps the import record;
    the registry (untouched Phase-6 gate) now SELECTS it."""
    service = SkillImportService()
    active = pipeline_to(service, SkillStatus.ACTIVE)
    assert active.source is SkillSource.LOCAL
    assert active.manifest.source is SkillSource.LOCAL
    assert active.provenance.source_url == SOURCE  # import record retained
    assert active.provenance.reviewed_by == "admin@example.test"

    registry = SkillRegistry()
    registry.register(active)
    assert registry.select(active.id).id == active.id


def test_unfinished_pipeline_skill_stays_unselectable() -> None:
    """Every pre-active state remains loadable-but-not-selectable."""
    service = SkillImportService()
    approved = pipeline_to(service, SkillStatus.APPROVED)
    registry = SkillRegistry()
    registry.register(approved)
    with pytest.raises(SkillNotSelectable) as exc:
        registry.select(approved.id)
    assert exc.value.reason == "status=approved"


# --- Resolver (41 §16 chain) ---------------------------------------------------------


def make_role_profile(
    *, name: str = "software_engineer", preferred: list[str] | None = None
) -> RoleProfile:
    role = Role.model_validate(
        {
            "id": uuid4(),
            "scope": "system",
            "name": name,
            "version": "1.0.0",
            "objective": "Deliver correct, reviewed code changes.",
            "status": "active",
        }
    )
    return RoleProfile(role=role, preferred_skills=preferred if preferred is not None else [])


def make_task(*, capabilities: list[str] | None = None) -> TaskAnalysis:
    return TaskAnalysis.model_validate(
        {
            "task_type": "code_review",
            "complexity": "medium",
            "capabilities_required": (capabilities if capabilities is not None else []),
            "risk_level": "low",
        }
    )


def local_skill(
    *,
    name: str,
    capabilities: list[str] | None = None,
    compatible_roles: list[str] | None = None,
    status: str = "active",
    source: str = "local",
) -> Skill:
    return Skill.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "type": "instruction",
            "source": source,
            "manifest": manifest(
                manifest_id=name.lower().replace(" ", "_"),
                name=name,
                source=source,
                status=status,
                capabilities=capabilities,
                compatible_roles=compatible_roles,
            ),
            "status": status,
        }
    )


def test_resolver_candidates_come_from_registry_admission() -> None:
    """Pipeline-state / imported skills are never candidates — the
    registry admission rule is the single authority, unwidened."""
    registry = SkillRegistry()
    registry.register(local_skill(name="Active Local"))
    registry.register(local_skill(name="Draft", status="reviewed"))
    registry.register(local_skill(name="Imported", source="imported", status="active"))
    resolver = SkillResolver(registry)
    result = resolver.resolve(task=make_task(), role=make_role_profile())
    assert [s.name for s in result.selected] == ["Active Local"]
    assert result.excluded == ()  # non-candidates are not "excluded" — never candidates


def test_role_incompatibility_excluded_with_named_reason() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="Reviewer Only", compatible_roles=["reviewer"]))
    resolver = SkillResolver(registry)
    result = resolver.resolve(task=make_task(), role=make_role_profile())
    assert result.selected == ()
    assert result.excluded[0].skill_name == "Reviewer Only"
    assert result.excluded[0].reason == "role_incompatible:software_engineer"


def test_empty_compatible_roles_means_unrestricted() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="Anyone", compatible_roles=[]))
    resolver = SkillResolver(registry)
    result = resolver.resolve(task=make_task(), role=make_role_profile(name="poet"))
    assert [s.name for s in result.selected] == ["Anyone"]


def test_capability_gap_excluded_with_missing_named() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="Partial", capabilities=["review"]))
    resolver = SkillResolver(registry)
    result = resolver.resolve(
        task=make_task(capabilities=["review", "summarize"]),
        role=make_role_profile(),
    )
    assert result.selected == ()
    assert result.excluded[0].reason == "capabilities_missing:summarize"


def test_ranking_preferred_first_then_coverage_then_name() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="Broad", capabilities=["review", "summarize"]))
    registry.register(local_skill(name="Narrow", capabilities=["review"]))
    registry.register(local_skill(name="Favored", capabilities=["review"]))
    resolver = SkillResolver(registry)
    result = resolver.resolve(
        task=make_task(capabilities=["review"]),
        role=make_role_profile(preferred=["Favored"]),
    )
    # Favored (preferred) > Broad (coverage 1 but capabilities superset ties
    # at 1 relevant) — coverage counts TASK-relevant capabilities only, so
    # Broad and Narrow tie at 1 and order alphabetically after Favored.
    assert [s.name for s in result.selected] == ["Favored", "Broad", "Narrow"]


def test_ranking_coverage_counts_task_relevant_capabilities() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="Covers Both", capabilities=["review", "summarize"]))
    registry.register(local_skill(name="Covers One Plus Noise", capabilities=["review", "poetry"]))
    resolver = SkillResolver(registry)
    result = resolver.resolve(task=make_task(capabilities=["review"]), role=make_role_profile())
    # Both cover the single required capability — tie broken by name.
    assert [s.name for s in result.selected] == ["Covers Both", "Covers One Plus Noise"]


def test_limit_truncates_selection() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="A"))
    registry.register(local_skill(name="B"))
    resolver = SkillResolver(registry)
    result = resolver.resolve(task=make_task(), role=make_role_profile(), limit=1)
    assert [s.name for s in result.selected] == ["A"]


def test_limit_below_one_rejected() -> None:
    resolver = SkillResolver(SkillRegistry())
    with pytest.raises(ValueError):
        resolver.resolve(task=make_task(), role=make_role_profile(), limit=0)


def test_context_accepted_as_seam_without_effect() -> None:
    """§16 names Context as a chain input; no doc defines a context→skill
    rule yet, so it is accepted and (recorded) participates in nothing."""
    registry = SkillRegistry()
    registry.register(local_skill(name="Steady"))
    resolver = SkillResolver(registry)
    with_ctx = resolver.resolve(
        task=make_task(), role=make_role_profile(), context=ComposedContext()
    )
    without_ctx = resolver.resolve(task=make_task(), role=make_role_profile())
    assert [s.name for s in with_ctx.selected] == [s.name for s in without_ctx.selected]


def test_resolution_is_deterministic() -> None:
    registry = SkillRegistry()
    registry.register(local_skill(name="B"))
    registry.register(local_skill(name="A"))
    resolver = SkillResolver(registry)
    first = resolver.resolve(task=make_task(), role=make_role_profile())
    second = resolver.resolve(task=make_task(), role=make_role_profile())
    assert [s.name for s in first.selected] == [s.name for s in second.selected]


# --- hermeticity guard ---------------------------------------------------------------


def test_skill_modules_perform_no_io() -> None:
    """14 §3: 'External sources are references, not runtime dependencies.'
    No network/IO client appears in any core.skills module source."""
    import inspect

    import core.skills.errors as errors_mod
    import core.skills.importing as importing_mod
    import core.skills.resolver as resolver_mod

    for mod in (errors_mod, importing_mod, resolver_mod):
        source = inspect.getsource(mod)
        for banned in ("httpx", "requests", "urllib", "socket", "aiohttp"):
            assert banned not in source, f"{mod.__name__} references {banned}"
