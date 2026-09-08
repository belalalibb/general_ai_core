"""R177-FIX-06 — persisted repository model via memory (``repo_map`` tool).

F-R177-05: discovery was transient per agent run; nothing persisted a
project model. The OPTIONAL ``repo_map`` tool uses the EXISTING jailed
SourceReader (bounds + denylist), ranks Python modules by import-degree
(stdlib ``ast``), and writes ONE compact ``MemoryItem(scope=project,
source="repo.map")`` per project through the EXISTING MemoryStorePort.
Permission = ``source.read`` only (no new permission, no write authority).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from apps.api.workspaces import InMemoryProjectStore
from apps.composition.agent import (
    AGENT_TOOLS_ENTITLEMENT,
    SOURCE_READ_PERMISSION,
    build_agent,
    grant_agent_tenant,
)
from apps.composition.repo_map import (
    REPO_MAP_KEY,
    REPO_MAP_SOURCE,
    REPO_MAP_TOOL,
    RepoMapper,
    bind_repo_map_tenant,
)
from core.contracts.identity import Project
from core.contracts.memory import MemoryScope
from core.memory.memory import InMemoryMemoryStore
from core.tools.denied_paths import DENIED_PATH_PATTERNS
from core.tools.source_reader import SourceReader
from tests.agent.world import TENANT, USER, AgentWorld, final, model_says, tool_call


def _tree(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text("def run():\n    return 1\n\nclass Engine:\n    pass\n")
    (root / "pkg" / "api.py").write_text("from pkg import core\nfrom pkg.util import helper\n")
    (root / "pkg" / "util.py").write_text("import pkg.core\n\ndef helper():\n    return 2\n")
    (root / "main.py").write_text("import pkg.api\nimport pkg.core\n")
    (root / "notes.txt").write_text("not python\n")
    (root / ".env").write_text("SECRET=1\n")
    (root / "credentials.json").write_text("{}\n")
    (root / "engineering").mkdir()
    (root / "engineering" / "verification").mkdir()
    (root / "engineering" / "verification" / "green_manifest.json").write_text("{}\n")


def _reader(root: Path) -> SourceReader:
    return SourceReader(root=root, denied_patterns=DENIED_PATH_PATTERNS)


def _project(tenant: UUID = TENANT) -> Project:
    return Project(id=uuid4(), tenant_id=tenant, name="p", metadata={})


def _mapper(root: Path, memory: InMemoryMemoryStore, projects: InMemoryProjectStore) -> RepoMapper:
    return RepoMapper(reader=_reader(root), memory=memory, projects=projects)


class TestMapperUnit:
    def test_denied_paths_never_appear_and_python_is_ranked_by_import_degree(
        self, tmp_path: Path
    ) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        mapper = _mapper(tmp_path, memory, projects)
        result = asyncio.run(mapper.build(tenant_id=TENANT, project_id=project.id))
        files = [m["path"] for m in result["modules"]]
        assert ".env" not in " ".join(files)
        assert not any("credentials" in f for f in files)
        assert not any("green_manifest" in f for f in files)
        # pkg/core.py is imported by api, util and main -> highest degree first
        assert files[0] == "pkg/core.py"
        core_row = result["modules"][0]
        assert core_row["imported_by"] == 3
        assert core_row["symbols"] == ["Engine", "run"]
        assert result["files_seen"] >= 5
        assert result["languages"]["python"] == 5
        assert result["languages"]["unknown"] == 1  # notes.txt

    def test_build_writes_one_project_scoped_memory_item(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        mapper = _mapper(tmp_path, memory, projects)
        first = asyncio.run(mapper.build(tenant_id=TENANT, project_id=project.id))
        items = memory.query(TENANT, scope=MemoryScope.PROJECT)
        assert len(items) == 1
        item = items[0]
        assert item.source == REPO_MAP_SOURCE == "repo.map"
        assert item.key == f"{REPO_MAP_KEY}:{project.id}"
        assert item.user_id is None  # project memory is tenant-shared
        assert 0.0 < item.confidence <= 1.0
        assert item.confidence == first["confidence"]
        assert item.evidence_count == 1
        # Recompute-on-demand updates in place (same id, evidence accumulates).
        asyncio.run(mapper.build(tenant_id=TENANT, project_id=project.id))
        again = memory.query(TENANT, scope=MemoryScope.PROJECT)
        assert len(again) == 1 and again[0].id == item.id and again[0].evidence_count == 2

    def test_truncated_listing_lowers_confidence(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        small = SourceReader(root=tmp_path, denied_patterns=DENIED_PATH_PATTERNS, max_entries=2)
        mapper = RepoMapper(reader=small, memory=memory, projects=projects)
        result = asyncio.run(mapper.build(tenant_id=TENANT, project_id=project.id))
        assert result["truncated"] is True
        assert result["confidence"] < 0.5

    def test_unknown_or_foreign_project_is_refused_before_any_read(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        foreign = _project(tenant=uuid4())
        asyncio.run(projects.put(foreign))
        mapper = _mapper(tmp_path, memory, projects)
        for pid in (uuid4(), foreign.id):
            with pytest.raises(ValueError, match="unknown project"):
                asyncio.run(mapper.build(tenant_id=TENANT, project_id=pid))
        assert memory.query(TENANT, scope=MemoryScope.PROJECT) == ()
        assert memory.query(foreign.tenant_id, scope=MemoryScope.PROJECT) == ()

    def test_map_value_is_bounded(self, tmp_path: Path) -> None:
        (tmp_path / "big").mkdir()
        for i in range(120):
            (tmp_path / "big" / f"m{i:03d}.py").write_text(f"def f{i}():\n    return {i}\n")
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        mapper = RepoMapper(reader=_reader(tmp_path), memory=memory, projects=projects, max_modules=50)
        result = asyncio.run(mapper.build(tenant_id=TENANT, project_id=project.id))
        assert len(result["modules"]) == 50
        assert result["modules_omitted"] == 70


class TestThroughTheRuntime:
    def test_tool_is_offered_with_source_read_only_and_runs_through_the_gate(
        self, tmp_path: Path
    ) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        world = AgentWorld(
            [
                model_says(tool_call(REPO_MAP_TOOL, project_id=str(project.id))),
                model_says(final("mapped", 1)),
            ]
        )
        composed = build_agent(
            router=world.router,
            execution_service=world.execution_service,
            store=type("S", (), {"put": staticmethod(world.stored.append)})(),
            audit=world.audit,
            usage=world.usage,
            repo_reader=_reader(tmp_path),
            repo_map=RepoMapper(reader=_reader(tmp_path), memory=memory, projects=projects),
        )
        grant_agent_tenant(composed.firewall, TENANT)
        offered = {e["name"]: e for e in composed.surface.offered()}
        assert REPO_MAP_TOOL in offered
        assert offered[REPO_MAP_TOOL]["permission"] == SOURCE_READ_PERMISSION
        spec = composed.surface.catalog[REPO_MAP_TOOL]
        assert spec.entitlement == AGENT_TOOLS_ENTITLEMENT
        assert set(spec.tool.permissions) == {SOURCE_READ_PERMISSION}  # no write authority

        with bind_repo_map_tenant(TENANT):
            outcome = asyncio.run(
                composed.surface.runtime.run(
                    tenant_id=TENANT,
                    user_id=USER,
                    task={"ask": "map the repo"},
                    tools=[spec],
                )
            )
        step = outcome.report.steps[0].observation
        assert step["status"] == "succeeded", step
        assert outcome.report.evidence[0]["result"]["modules"][0]["path"] == "pkg/core.py"
        items = memory.query(TENANT, scope=MemoryScope.PROJECT)
        assert len(items) == 1 and items[0].source == REPO_MAP_SOURCE

    def test_tool_refuses_without_a_bound_tenant(self, tmp_path: Path) -> None:
        _tree(tmp_path)
        memory, projects = InMemoryMemoryStore(), InMemoryProjectStore()
        project = _project()
        asyncio.run(projects.put(project))
        mapper = RepoMapper(reader=_reader(tmp_path), memory=memory, projects=projects)
        with pytest.raises(ValueError, match="tenant"):
            asyncio.run(mapper.handler({"project_id": str(project.id)}))
        # A caller-supplied tenant_id argument is NOT trusted.
        with pytest.raises(ValueError, match="tenant"):
            asyncio.run(mapper.handler({"project_id": str(project.id), "tenant_id": str(TENANT)}))
        assert memory.query(TENANT, scope=MemoryScope.PROJECT) == ()

    def test_absent_seam_means_no_tool(self, tmp_path: Path) -> None:
        world = AgentWorld([])
        composed = build_agent(
            router=world.router,
            execution_service=world.execution_service,
            store=type("S", (), {"put": staticmethod(world.stored.append)})(),
            audit=world.audit,
            usage=world.usage,
            repo_reader=_reader(tmp_path),
        )
        assert REPO_MAP_TOOL not in composed.surface.catalog


def test_runtime_profile_composes_repo_map_over_the_same_memory_and_reader() -> None:
    source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "RepoMapper(" in source
    assert "repo_map=" in source
    assert "bind_run_tenant(caller.tenant_id)" in Path("apps/api/app.py").read_text(
        encoding="utf-8"
    )


def test_memory_type_convention_sees_the_repo_map_writer() -> None:
    from tests.memory.test_memory_type_convention_r177 import (
        MEMORY_SOURCE_VOCABULARY,
        runtime_memory_item_sources,
    )

    assert REPO_MAP_SOURCE in MEMORY_SOURCE_VOCABULARY
    assert runtime_memory_item_sources().get("apps/composition/repo_map.py") == [REPO_MAP_SOURCE]
