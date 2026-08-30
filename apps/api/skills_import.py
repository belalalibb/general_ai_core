"""SKL-1 — HTTP surface over the EXISTING skill import pipeline (AA-3).

Doc B §5 SKL-1: "admin routes surfacing the pipeline steps verbatim (each
step already refuses out-of-order transitions in core)." This module adds
NO lifecycle mechanics — every step delegates to
:class:`core.skills.importing.SkillImportService` and every core refusal
(out-of-order step, scan findings, missing provenance, unknown source,
checksum mismatch) surfaces VERBATIM as an HTTP error body.

The pipeline is pure (Skill in → Skill out), so this surface holds the
skills-under-review between steps — an app-level, tenant-scoped holding
area (same in-memory posture as the execution store; persistence is the
repositories primitive, doc C §7 #1). ``activate`` registers the finished
LOCAL skill into the EXISTING SkillRegistry — the registry's own
local+active gate stays the only selectability authority.

Reviewer identity comes from the authenticated Principal — a review can
never claim an identity the session does not carry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from apps.api.errors import error_response
from core.contracts.errors import ErrorCode
from core.contracts.skills import Skill, SkillManifest
from core.roles.errors import DuplicateRegistration
from core.roles.registry import SkillRegistry
from core.skills.errors import (
    ChecksumMismatch,
    InvalidLifecycleStep,
    MissingProvenance,
    NotAnImportedSkill,
    ScanFindingsBlock,
    UnknownImportSource,
)
from core.skills.importing import IMPORT_SOURCES, SkillImportService

if TYPE_CHECKING:
    from apps.api.app import Principal


@dataclass
class SkillReviewSurface:
    """Pipeline + registry + the tenant-scoped holding area between steps."""

    importing: SkillImportService
    registry: SkillRegistry
    #: The allowlist DISPLAYED to admins — must match what ``importing``
    #: enforces (composition-root agreement duty, same rule as AdminSurface).
    allowed_sources: tuple[str, ...] = IMPORT_SOURCES
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _pending: dict[tuple[UUID, UUID], Skill] = field(default_factory=dict)

    def get(self, tenant_id: UUID, skill_id: UUID) -> Skill | None:
        return self._pending.get((tenant_id, skill_id))

    def put(self, tenant_id: UUID, skill: Skill) -> None:
        self._pending[(tenant_id, skill.id)] = skill

    def remove(self, tenant_id: UUID, skill_id: UUID) -> None:
        self._pending.pop((tenant_id, skill_id), None)

    def list(self, tenant_id: UUID) -> list[Skill]:
        return [s for (t, _), s in self._pending.items() if t == tenant_id]


class SkillImportRequest(BaseModel):
    """POST /v1/admin/skills/import body — closed shape."""

    model_config = ConfigDict(extra="forbid")

    manifest: dict[str, object]
    content: str
    source_url: str
    source_version: str
    expected_checksum: str | None = None


class ScanRequest(BaseModel):
    """Scanner findings arrive as caller data (scanner policy is external)."""

    model_config = ConfigDict(extra="forbid")

    findings: list[str] = []


def _skill_json(skill: Skill) -> dict[str, object]:
    row: dict[str, object] = {
        "skill_id": str(skill.id),
        "name": skill.name,
        "version": skill.version,
        "type": skill.type.value,
        "source": skill.source.value,
        "status": skill.status.value,
    }
    if skill.provenance is not None:
        row["provenance"] = {
            "source_url": skill.provenance.source_url,
            "checksum": skill.provenance.checksum,
            "reviewed_by": skill.provenance.reviewed_by,
            "local_version": skill.provenance.local_version,
        }
    return row


def create_skills_import_router(
    surface: SkillReviewSurface,
    *,
    resolve: Callable[[Request], Principal | JSONResponse],
) -> APIRouter:
    """The 14 §3 pipeline steps as admin routes — core refusals verbatim."""
    router = APIRouter(prefix="/v1/admin/skills")

    def _admit(request: Request) -> Principal | JSONResponse:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        if not caller.is_admin:
            return error_response(ErrorCode.UNAUTHORIZED, "Admin access required.")
        return caller

    def _unknown_skill() -> JSONResponse:
        # Anti-enumeration: absent and foreign-tenant are the same answer.
        return error_response(
            ErrorCode.VALIDATION_ERROR, "Unknown skill import id.", http_status=404
        )

    def _refused(exc: Exception) -> JSONResponse:
        # Core refusal surfaced VERBATIM — a state conflict (409, the same
        # recorded mapping the config lifecycle routes use).
        return error_response(ErrorCode.VALIDATION_ERROR, str(exc), http_status=409)

    @router.get("/imports")
    async def list_imports(request: Request) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return JSONResponse(
            status_code=200,
            content={
                "imports": [_skill_json(s) for s in surface.list(admitted.tenant_id)],
                "allowed_sources": list(surface.allowed_sources),
            },
        )

    @router.post("/import")
    async def import_skill(request: Request, body: SkillImportRequest) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        try:
            manifest = SkillManifest.model_validate(body.manifest)
        except ValidationError as exc:
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                f"manifest does not validate: {exc.errors()[0]['msg']}",
                details={"field": "manifest"},
            )
        try:
            skill = surface.importing.import_skill(
                skill_id=uuid4(),
                manifest=manifest,
                content=body.content,
                source_url=body.source_url,
                source_version=body.source_version,
                imported_at=surface.clock(),
                expected_checksum=body.expected_checksum,
            )
        except (UnknownImportSource, ChecksumMismatch) as exc:
            return error_response(ErrorCode.VALIDATION_ERROR, str(exc), http_status=422)
        surface.put(admitted.tenant_id, skill)
        return JSONResponse(status_code=201, content=_skill_json(skill))

    def _step(
        admitted: Principal,
        skill_id: str,
        advance: Callable[[Skill], Skill],
    ) -> Response:
        try:
            parsed = UUID(skill_id)
        except ValueError:
            return _unknown_skill()
        skill = surface.get(admitted.tenant_id, parsed)
        if skill is None:
            return _unknown_skill()
        try:
            advanced = advance(skill)
        except (
            InvalidLifecycleStep,
            ScanFindingsBlock,
            MissingProvenance,
            NotAnImportedSkill,
        ) as exc:
            return _refused(exc)
        surface.put(admitted.tenant_id, advanced)
        return JSONResponse(status_code=200, content=_skill_json(advanced))

    @router.post("/imports/{skill_id}/scan")
    async def scan(request: Request, skill_id: str, body: ScanRequest) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _step(
            admitted,
            skill_id,
            lambda s: surface.importing.scan(s, findings=tuple(body.findings)),
        )

    @router.post("/imports/{skill_id}/validate")
    async def validate(request: Request, skill_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _step(admitted, skill_id, surface.importing.validate)

    @router.post("/imports/{skill_id}/review")
    async def review(request: Request, skill_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        # Reviewer = the authenticated principal, never a claimed name.
        reviewer = str(admitted.user_id)
        return _step(
            admitted,
            skill_id,
            lambda s: surface.importing.review(s, reviewed_by=reviewer),
        )

    @router.post("/imports/{skill_id}/approve")
    async def approve(request: Request, skill_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        return _step(admitted, skill_id, surface.importing.approve)

    @router.post("/imports/{skill_id}/activate")
    async def activate(request: Request, skill_id: str) -> Response:
        admitted = _admit(request)
        if isinstance(admitted, JSONResponse):
            return admitted
        try:
            parsed = UUID(skill_id)
        except ValueError:
            return _unknown_skill()
        skill = surface.get(admitted.tenant_id, parsed)
        if skill is None:
            return _unknown_skill()
        try:
            active = surface.importing.activate(skill)
        except (InvalidLifecycleStep, MissingProvenance, NotAnImportedSkill) as exc:
            return _refused(exc)
        try:
            surface.registry.register(active)
        except DuplicateRegistration as exc:
            return _refused(exc)
        surface.remove(admitted.tenant_id, parsed)
        return JSONResponse(status_code=200, content=_skill_json(active))

    return router
