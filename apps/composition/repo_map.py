"""R177-FIX-06 — ``repo_map``: a persisted, project-scoped repository model.

F-R177-05 (evidence/r177/A08_discovery): discovery happened live inside each
agent run and nothing persisted a project model. This OPTIONAL tool builds a
compact, ranked map of a source tree and writes it as ONE
``MemoryItem(scope=project, source="repo.map")`` per project through the
EXISTING ``MemoryStorePort`` (the composer already ranks project scope,
13 §4). Landscape pattern (A10): repo map = compact ranked context-selection
artefact (aider / tree-sitter style), here with stdlib ``ast`` for Python and
``unknown`` for other languages.

Authority (unchanged): the tool reads through the EXISTING jailed
``SourceReader`` (bounds + denylist — a denied path is never listed), needs
``source.read`` only, and confers NO execution or write authority. The tenant
is NEVER taken from tool arguments: the composition root binds the admitted
caller's tenant for the duration of the run (``bind_repo_map_tenant``), and
the project must resolve in that tenant (absent == foreign, 20 §6).

Staleness (recorded risk): every item carries ``confidence`` (lowered when
the listing was truncated or modules were omitted) and ``last_seen``;
recompute-on-demand updates the SAME item (evidence accumulates).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from apps.api.run_context import bind_run_tenant, current_run_tenant
from core.contracts.base import JsonObject, utc_now
from core.contracts.memory import MemoryItem, MemoryScope, MemorySensitivity
from core.memory.ports import MemoryStorePort
from core.tools.source_reader import SourceReader, SourceReadRefused

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.api.workspaces import ProjectStorePort

#: ``MemoryItem.source`` for repository maps (MEMORY_TYPES_MAPPING.md §1).
REPO_MAP_SOURCE = "repo.map"
#: ``MemoryItem.key`` prefix; the project id follows (one item per project).
REPO_MAP_KEY = "repo.map"
#: Agent-visible tool name.
REPO_MAP_TOOL = "repo_map"

#: Re-exported for composition/tests: the run-scoped tenant binding lives in
#: apps.api.run_context (the layer that admits the caller).
bind_repo_map_tenant = bind_run_tenant


@dataclass(frozen=True)
class _Module:
    path: str
    module: str | None  # dotted name for Python files, None otherwise
    language: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]


def _dotted(rel_posix: str) -> str:
    stem = rel_posix[: -len(".py")]
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def _parse_python(rel_posix: str, content: str) -> _Module:
    symbols: list[str] = []
    imports: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _Module(rel_posix, _dotted(rel_posix), "python", (), ())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            symbols.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            imports.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return _Module(
        rel_posix, _dotted(rel_posix), "python", tuple(sorted(set(symbols))), tuple(imports)
    )


class RepoMapper:
    """Build + persist a bounded repository map over the jailed reader."""

    def __init__(
        self,
        *,
        reader: SourceReader,
        memory: MemoryStorePort,
        projects: ProjectStorePort,
        max_modules: int = 200,
        max_symbols_per_module: int = 30,
    ) -> None:
        if max_modules < 1 or max_symbols_per_module < 1:
            raise ValueError("repo map bounds must be positive")
        self._reader = reader
        self._memory = memory
        self._projects = projects
        self._max_modules = max_modules
        self._max_symbols = max_symbols_per_module

    # --- the model ------------------------------------------------------------

    def _scan(self) -> tuple[list[_Module], bool, int]:
        listing = self._reader.list_files("", "**/*")
        files = listing["files"]
        truncated = bool(listing["truncated"])
        assert isinstance(files, list)
        modules: list[_Module] = []
        for rel in files:
            rel_posix = str(rel)
            if rel_posix.endswith(".py"):
                try:
                    content = str(self._reader.read_file(rel_posix)["content"])
                except SourceReadRefused:
                    continue  # denied at read time: honestly absent from the map
                modules.append(_parse_python(rel_posix, content))
            else:
                modules.append(_Module(rel_posix, None, "unknown", (), ()))
        return modules, truncated, len(files)

    def _rank(self, modules: list[_Module]) -> list[JsonObject]:
        by_name = {m.module: m for m in modules if m.module is not None}
        degree: dict[str, int] = {m.path: 0 for m in modules}
        for m in modules:
            targets: set[str] = set()
            for imp in m.imports:
                target = by_name.get(imp)
                if target is not None and target.path != m.path:
                    targets.add(target.path)
            for path in targets:
                degree[path] += 1
        ranked = sorted(modules, key=lambda m: (-degree[m.path], m.path))
        rows: list[JsonObject] = []
        for m in ranked:
            rows.append(
                {
                    "path": m.path,
                    "language": m.language,
                    "imported_by": degree[m.path],
                    "symbols": list(m.symbols[: self._max_symbols]),
                }
            )
        return rows

    async def build(self, *, tenant_id: UUID, project_id: UUID) -> JsonObject:
        """Resolve the project IN THIS TENANT, scan, rank, persist, return the map."""
        from apps.api.workspaces import ProjectNotFound

        try:
            await self._projects.get(tenant_id, project_id)
        except ProjectNotFound:
            raise ValueError(f"unknown project {project_id}") from None  # absent == foreign
        modules, truncated, files_seen = self._scan()
        rows = self._rank(modules)
        omitted = max(0, len(rows) - self._max_modules)
        rows = rows[: self._max_modules]
        languages: dict[str, int] = {}
        for m in modules:
            languages[m.language] = languages.get(m.language, 0) + 1
        confidence = 1.0
        if truncated:
            confidence *= 0.4
        if omitted:
            confidence *= max(0.5, 1.0 - omitted / max(1, len(modules)))
        confidence = round(min(1.0, max(0.0, confidence)), 3)
        value: JsonObject = {
            "project_id": str(project_id),
            "files_seen": files_seen,
            "truncated": truncated,
            "languages": dict(sorted(languages.items())),
            "modules": rows,
            "modules_omitted": omitted,
            "confidence": confidence,
        }
        self._memory.upsert(
            MemoryItem(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=None,  # project memory is tenant-shared (13 §4 project scope)
                scope=MemoryScope.PROJECT,
                key=f"{REPO_MAP_KEY}:{project_id}",
                value=value,
                source=REPO_MAP_SOURCE,
                confidence=confidence,
                evidence_count=1,
                last_seen=utc_now(),
                sensitivity=MemorySensitivity.LOW,
            )
        )
        return value

    # --- agent tool handler (arguments are the model's; tenant is bound) --------

    async def handler(self, arguments: JsonObject) -> JsonObject:
        tenant_id = current_run_tenant()
        if tenant_id is None:
            raise ValueError("repo_map: no admitted tenant bound for this run")
        raw = arguments.get("project_id")
        try:
            project_id = UUID(str(raw))
        except ValueError:
            raise ValueError("repo_map: project_id must be a UUID") from None
        try:
            return await self.build(tenant_id=tenant_id, project_id=project_id)
        except SourceReadRefused as exc:
            raise ValueError(f"source read refused: {exc}") from exc
