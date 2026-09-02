"""SkillSourceCatalog + SET_SKILL_SOURCES — chunk-4 pins.

Catalog pins:

- default seeds the three 41 §16 URLs verbatim, in doc order;
- classification derives from the URL (github ⇒ git_repository, other
  https ⇒ web_catalog) — never guessed;
- order = priority: entries() and allowed_prefixes() preserve list order;
- disabled entries stay LISTED but leave allowed_prefixes();
- admission refuses http://, empty, duplicate, and disabled-not-listed;
- set_sources is a REPLACE returning the previous entries; restore()
  brings a captured snapshot back verbatim (the rollback path).

Import-service live seam:

- source_prefixes bound ⇒ the catalog IS the allowlist (an admin change
  takes effect on the NEXT import, no recomposition);
- catalog-disabled source refuses an import that the frozen default
  would have admitted;
- seam absent ⇒ frozen 41 §16 default holds (prior behavior unchanged).

Admin action (full 21 §3 lifecycle over FINAL_ACTIVE_ADMIN_AREAS):

- publish replaces the live catalog atomically (same instance the import
  service reads);
- validation refuses: unbound seam, empty urls, http url, disabled not
  in urls — all BEFORE any mutation (live catalog untouched);
- rollback restores the exact previous entries (enabled flags included);
- the publish lands in the audit trail as ADMIN_CONFIG_PUBLISHED.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.admin import AdminConfigService
from core.audit.memory import InMemoryAuditLog
from core.contracts.admin import (
    FINAL_ACTIVE_ADMIN_AREAS,
    AdminAction,
    ConfigLifecycleState,
)
from core.contracts.audit import AuditEventType
from core.contracts.base import JsonObject
from core.contracts.skills import SkillManifest
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing import SimpleScoringRouter
from core.skills.errors import UnknownImportSource
from core.skills.importing import IMPORT_SOURCES, SkillImportService
from core.skills.sources import (
    InvalidSourceUrl,
    SkillSourceCatalog,
    SkillSourceEntry,
    SkillSourceKind,
    classify_source,
)
from core.usage import InMemoryUsageAccounting

TENANT = uuid4()
ACTOR = uuid4()

NEW_GIT = "https://github.com/example/approved-skills"
NEW_WEB = "https://skills.example.com/catalog"


# --- catalog -------------------------------------------------------------------------


class TestCatalog:
    def test_default_seeds_41_16_urls_in_doc_order(self) -> None:
        catalog = SkillSourceCatalog()
        assert catalog.allowed_prefixes() == IMPORT_SOURCES

    def test_classification_derives_from_url(self) -> None:
        assert classify_source(NEW_GIT) is SkillSourceKind.GIT_REPOSITORY
        assert classify_source(NEW_WEB) is SkillSourceKind.WEB_CATALOG
        kinds = [e.kind for e in SkillSourceCatalog().entries()]
        assert kinds == [
            SkillSourceKind.GIT_REPOSITORY,  # mattpocock/skills
            SkillSourceKind.WEB_CATALOG,  # aihero.dev
            SkillSourceKind.GIT_REPOSITORY,  # amElnagdy/review-skills
        ]

    def test_order_is_priority(self) -> None:
        catalog = SkillSourceCatalog([NEW_WEB, NEW_GIT])
        assert catalog.allowed_prefixes() == (NEW_WEB, NEW_GIT)

    def test_disabled_entry_listed_but_not_allowed(self) -> None:
        catalog = SkillSourceCatalog()
        catalog.set_sources([NEW_GIT, NEW_WEB], disabled=[NEW_WEB])
        assert len(catalog.entries()) == 2
        assert catalog.entries()[1].enabled is False
        assert catalog.allowed_prefixes() == (NEW_GIT,)

    def test_http_url_refused(self) -> None:
        with pytest.raises(InvalidSourceUrl):
            SkillSourceCatalog(["http://insecure.example.com/skills"])

    def test_duplicate_url_refused(self) -> None:
        with pytest.raises(InvalidSourceUrl):
            SkillSourceCatalog([NEW_GIT, NEW_GIT])

    def test_disabled_not_in_list_refused(self) -> None:
        catalog = SkillSourceCatalog()
        with pytest.raises(InvalidSourceUrl):
            catalog.set_sources([NEW_GIT], disabled=[NEW_WEB])

    def test_set_sources_returns_previous_and_restore_reverts(self) -> None:
        catalog = SkillSourceCatalog()
        before = catalog.entries()
        previous = catalog.set_sources([NEW_GIT])
        assert previous == before
        assert catalog.allowed_prefixes() == (NEW_GIT,)
        catalog.restore(previous)
        assert catalog.allowed_prefixes() == IMPORT_SOURCES


# --- import-service live seam ----------------------------------------------------------


def _manifest(name: str = "skill-x") -> SkillManifest:
    return SkillManifest.model_validate(
        {
            "id": name,
            "name": name,
            "version": "1.0.0",
            "type": "instruction",
            "source": "imported",
            "status": "imported",
            "capabilities": ["review"],
            "runtime": {"invocation": "user_or_model", "compatible_roles": []},
        }
    )


class TestImportSeam:
    def test_catalog_addition_admits_next_import(self) -> None:
        catalog = SkillSourceCatalog()
        service = SkillImportService(source_prefixes=catalog)
        kwargs: dict[str, object] = {
            "skill_id": uuid4(),
            "manifest": _manifest(),
            "content": "content",
            "source_url": f"{NEW_GIT}/skill-x",
            "source_version": "1.0.0",
            "imported_at": datetime.now(UTC),
        }
        with pytest.raises(UnknownImportSource):
            service.import_skill(**kwargs)  # type: ignore[arg-type]
        catalog.set_sources([*IMPORT_SOURCES, NEW_GIT])
        skill = service.import_skill(**kwargs)  # type: ignore[arg-type]
        assert skill.provenance is not None

    def test_catalog_disable_refuses_previously_allowed_source(self) -> None:
        catalog = SkillSourceCatalog()
        service = SkillImportService(source_prefixes=catalog)
        catalog.set_sources(list(IMPORT_SOURCES), disabled=[IMPORT_SOURCES[0]])
        with pytest.raises(UnknownImportSource):
            service.import_skill(
                skill_id=uuid4(),
                manifest=_manifest(),
                content="content",
                source_url=f"{IMPORT_SOURCES[0]}/skill-x",
                source_version="1.0.0",
                imported_at=datetime.now(UTC),
            )

    def test_unbound_seam_keeps_frozen_default(self) -> None:
        service = SkillImportService()
        skill = service.import_skill(
            skill_id=uuid4(),
            manifest=_manifest(),
            content="content",
            source_url=f"{IMPORT_SOURCES[0]}/skill-x",
            source_version="1.0.0",
            imported_at=datetime.now(UTC),
        )
        assert skill.provenance is not None


# --- admin action ----------------------------------------------------------------------


class World:
    def __init__(self, *, with_catalog: bool = True) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.usage = InMemoryUsageAccounting()
        self.router = SimpleScoringRouter(self.providers, self.models, BindingRegistry())
        self.audit = InMemoryAuditLog()
        self.catalog = SkillSourceCatalog() if with_catalog else None
        self.admin = AdminConfigService(
            providers=self.providers,
            models=self.models,
            usage=self.usage,
            routing=self.router,
            audit_log=self.audit,
            skill_sources=self.catalog,
            active_areas=FINAL_ACTIVE_ADMIN_AREAS,
        )

    def draft(self, payload: JsonObject):
        return self.admin.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.SET_SKILL_SOURCES,
            payload=payload,
        )

    def publish(self, payload: JsonObject):
        change = self.draft(payload)
        validated = self.admin.validate(TENANT, change.id)
        assert validated.state is ConfigLifecycleState.VALIDATED, validated.validation_result
        self.admin.preview(TENANT, change.id)
        return self.admin.publish(TENANT, change.id)


class TestAdminAction:
    def test_publish_replaces_live_catalog(self) -> None:
        world = World()
        published = world.publish({"urls": [NEW_GIT, NEW_WEB], "disabled": [NEW_WEB]})
        assert published.state is ConfigLifecycleState.PUBLISHED
        assert world.catalog is not None
        assert world.catalog.allowed_prefixes() == (NEW_GIT,)
        assert len(world.catalog.entries()) == 2

    def test_unbound_catalog_seam_fails_validation(self) -> None:
        world = World(with_catalog=False)
        change = world.draft({"urls": [NEW_GIT]})
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED

    def test_empty_urls_rejected(self) -> None:
        world = World()
        change = world.draft({"urls": []})
        assert world.admin.validate(TENANT, change.id).state is ConfigLifecycleState.REJECTED

    def test_http_url_rejected_before_any_mutation(self) -> None:
        world = World()
        change = world.draft({"urls": ["http://bad.example.com"]})
        rejected = world.admin.validate(TENANT, change.id)
        assert rejected.state is ConfigLifecycleState.REJECTED
        assert world.catalog is not None
        assert world.catalog.allowed_prefixes() == IMPORT_SOURCES  # untouched

    def test_disabled_not_in_urls_rejected(self) -> None:
        world = World()
        change = world.draft({"urls": [NEW_GIT], "disabled": [NEW_WEB]})
        assert world.admin.validate(TENANT, change.id).state is ConfigLifecycleState.REJECTED

    def test_rollback_restores_previous_entries_verbatim(self) -> None:
        world = World()
        assert world.catalog is not None
        before = world.catalog.entries()
        published = world.publish({"urls": [NEW_GIT]})
        assert world.catalog.allowed_prefixes() == (NEW_GIT,)
        rolled = world.admin.rollback(TENANT, published.id)
        assert rolled.state is ConfigLifecycleState.ROLLED_BACK
        assert world.catalog.entries() == before

    def test_audit_trail_records_publish(self) -> None:
        world = World()
        published = world.publish({"urls": [NEW_GIT]})
        events = world.audit.read(TENANT)
        assert any(e.event_type is AuditEventType.ADMIN_CONFIG_PUBLISHED for e in events)
        assert published.action is AdminAction.SET_SKILL_SOURCES


class TestEntryModel:
    def test_entry_is_frozen(self) -> None:
        entry = SkillSourceEntry(url=NEW_GIT, kind=SkillSourceKind.GIT_REPOSITORY)
        with pytest.raises(AttributeError):
            entry.enabled = False  # type: ignore[misc]
