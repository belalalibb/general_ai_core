"""R179 4.2 — self-description: every mounted operator surface is described by the shelf.

Two truths, both derived (never a documentation claim):

1. WIDENING 22 → 23: ``learning.custody_governance`` flips AVAILABLE exactly when
   ``create_admin_router`` mounts ``/v1/admin/learning/custody/*`` (admin + memory +
   custody port + audit) and stays INERT for every weaker composition — the same
   seam variables, one derivation, two consumers (route + agent tool).

2. COVERAGE: for the SHIPPED runtime profile (``build_runtime_profile``), every path
   FastAPI actually mounts under ``/v1/admin`` (the operator surface) must be matched
   by at least one shelf row's ``evidence`` route pattern. A mounted admin route no
   shelf row can name is a hidden operator surface — the exact gap this round closed.
   Non-admin API families are covered by a coarser family map (each mounted family
   must have a shelf row) so the whole mounted tree is accounted for.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from fastapi import FastAPI

from apps.api import create_app
from apps.api.capabilities import CAPABILITY_IDS
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryMemoryStore
from tests.api.test_admin_api import World, _no_sleep
from tests.api.test_capability_catalog_r177 import _get, _states, run

GOVERNANCE_PATHS = {
    "/v1/admin/learning/custody/revoke",
    "/v1/admin/learning/custody/sweep",
    "/v1/admin/learning/custody/release-legacy-hold",
}


class _Custody:
    """Minimal LearningCustodyPort stand-in: presence is what the seam checks."""

    def capture_external(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def capture_from_execution(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def get(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    def list(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        return ()

    def save(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def _app(world: World, **extra: Any) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=world.router, execution_service=service, principal=world.principal, **extra
    )


# --- 1. the widening is derived from the mount condition --------------------------


def test_governance_row_is_available_exactly_when_routes_are_mounted() -> None:
    world = World()
    app = _app(
        world,
        admin=replace(world.surface(), audit=world.audit),
        memory=InMemoryMemoryStore(),
        learning_custody=_Custody(),
    )
    assert GOVERNANCE_PATHS <= _paths(app)
    assert _states(app)["learning.custody_governance"] == "available"
    payload = run(_get(app, "/v1/admin/capabilities")).json()
    row = next(r for r in payload["capabilities"] if r["id"] == "learning.custody_governance")
    assert row["state"] == "available"
    assert "/v1/admin/learning/custody" in row["evidence"]
    assert set(row) == {"id", "state", "evidence"}  # frozen row shape (V7 pins)


def test_governance_row_is_inert_for_every_weaker_composition() -> None:
    world = World()
    weaker = {
        "no custody port": dict(
            admin=replace(world.surface(), audit=world.audit), memory=InMemoryMemoryStore()
        ),
        "no memory": dict(admin=replace(world.surface(), audit=world.audit)),
        "no audit": dict(
            admin=replace(world.surface(), audit=None),
            memory=InMemoryMemoryStore(),
            learning_custody=_Custody(),
        ),
    }
    for label, extra in weaker.items():
        app = _app(world, **extra)
        assert not (GOVERNANCE_PATHS & _paths(app)), label
        assert _states(app)["learning.custody_governance"] == "inert", label


# --- 2. every mounted operator surface has a describing shelf row --------------------


def _evidence_patterns(app: FastAPI) -> list[tuple[str, re.Pattern[str]]]:
    """Route patterns named in shelf evidence → regexes.

    Understands the evidence shorthand already in use: ``*`` wildcards,
    ``a|b`` alternatives on the last segment, and ``+ /relative`` suffixes that
    hang off the preceding absolute route's mount prefix (``/v1/admin``).
    """
    out: list[tuple[str, re.Pattern[str]]] = []
    for row in app.state.capability_catalog:
        prefix = ""
        for token in re.findall(r"(?:/v1|/healthz|\+ /)[\w/{}\-*.|]*", row.evidence):
            token = token.rstrip(".")
            if token.startswith("+ /"):
                if not prefix:
                    continue
                token = prefix + token[2:]
            else:
                # Mount prefix = the first two segments ("/v1/admin", "/v1/executions").
                prefix = "/".join(token.split("/")[:3]) if token.startswith("/v1/admin") else ""
            head, _, tail = token.rpartition("/")
            alternatives = tail.split("|") if "|" in tail else [tail]
            for alt in alternatives:
                pattern = f"{head}/{alt}" if head else alt
                if pattern.endswith("/*"):
                    pattern = pattern[:-2]  # "/family/*" ⇒ the family root and below
                rx = "^" + re.escape(pattern).replace(r"\*", ".*")
                rx = re.sub(r"\\\{[^}]*\\\}", r"\\{[^/]+\\}", rx) + "(/.*)?$"
                out.append((row.id, re.compile(rx)))
    return out


def _uncovered(app: FastAPI, prefix: str) -> list[str]:
    patterns = _evidence_patterns(app)
    return sorted(
        path
        for path in _paths(app)
        if path.startswith(prefix) and not any(rx.match(path) for _, rx in patterns)
    )


# The operator (admin) tree, family by family ⇒ the shelf row that owns it. The
# generic ``admin.control_plane`` row (evidence "/v1/admin/*") owns ONLY the
# T-IMPL-032 control-plane families; every other mounted admin family must be
# owned by a SPECIFIC row so the wildcard cannot hide a surface. A new admin
# route must be assigned here (test fails otherwise) — that is the drift guard.
ADMIN_FAMILY_OWNER = {
    "/v1/admin/audit": "admin.control_plane",
    "/v1/admin/capabilities": "admin.control_plane",
    "/v1/admin/changes": "admin.control_plane",
    "/v1/admin/context-lab": "admin.control_plane",
    "/v1/admin/models": "admin.control_plane",
    "/v1/admin/notifications": "admin.control_plane",
    "/v1/admin/plans": "admin.control_plane",
    "/v1/admin/providers": "admin.control_plane",
    "/v1/admin/routing": "admin.control_plane",
    "/v1/admin/scenarios": "admin.control_plane",
    "/v1/admin/self-review": "admin.control_plane",
    "/v1/admin/system": "admin.control_plane",
    "/v1/admin/usage": "admin.control_plane",
    "/v1/admin/evaluations": "evaluation.records",
    "/v1/admin/executions": "evaluation.records",
    "/v1/admin/learning/custody": "learning.custody_governance",
    "/v1/admin/learning": "learning.lifecycle",
    "/v1/admin/skills": "skills.import",
    "/v1/admin/source-changes": "sourcechange.workflow",
    "/v1/admin/engineering": "admin.control_plane",
}


def _owner(path: str, table: dict[str, str]) -> str | None:
    # Longest matching family wins (custody under learning).
    best = None
    for fam in table:
        if (path == fam or path.startswith(fam + "/")) and (best is None or len(fam) > len(best)):
            best = fam
    return table[best] if best else None


def test_shipped_runtime_mounts_no_admin_route_the_shelf_cannot_name() -> None:
    from apps.composition.runtime import build_runtime_profile

    profile = build_runtime_profile(environ={"DEV_DEMO_PRINCIPAL": "1"})
    # (a) pattern coverage by SPECIFIC rows — the wildcard row is excluded on purpose.
    specific = [
        (cid, rx) for cid, rx in _evidence_patterns(profile.app) if cid != "admin.control_plane"
    ]
    states = _states(profile.app)
    admin_paths = sorted(p for p in _paths(profile.app) if p.startswith("/v1/admin"))
    for path in admin_paths:
        owner = _owner(path, ADMIN_FAMILY_OWNER)
        assert owner is not None, f"mounted admin route with no shelf owner: {path}"
        assert states[owner] == "available", (path, owner, states[owner])
        if owner != "admin.control_plane":
            assert any(rx.match(path) for cid, rx in specific if cid == owner), (path, owner)
    # (b) the custody governance family is present in the shipped tree only when
    # composed — in this hermetic profile it is absent AND its row says so.
    assert not any(p.startswith("/v1/admin/learning/custody") for p in admin_paths)
    assert states["learning.custody_governance"] == "inert"


def test_shipped_runtime_every_mounted_family_has_a_shelf_row() -> None:
    from apps.composition.runtime import build_runtime_profile

    profile = build_runtime_profile(environ={"DEV_DEMO_PRINCIPAL": "1"})
    # Family ⇒ the shelf id that owns it (the coarse, non-admin map).
    family_owner = {
        "/healthz": "health.liveness",
        "/v1/auth": "auth.sessions",
        "/v1/execute": "execute.sync",
        "/v1/executions": "execute.sync",
        "/v1/models": "models.listing",
        "/v1/skills": "skills.listing",
        "/v1/usage": "usage.reporting",
        "/v1/webhooks": "webhooks.registration",
        "/v1/workspaces": "workspaces.projects",
        "/v1/projects": "workspaces.projects",
        "/v1/memory/preferences": "context.composition",
        "/v1/agent": "agent.runtime",
        "/v1/agent-tools": "agent.runtime",
        "/v1/dev": "dev.publish_modes",
        "/v1/admin": "admin.control_plane",
    }
    states = _states(profile.app)
    assert set(family_owner.values()) <= CAPABILITY_IDS
    unowned = []
    for path in _paths(profile.app):
        owner = next(
            (cid for fam, cid in family_owner.items() if path == fam or path.startswith(fam + "/")),
            None,
        )
        if owner is None:
            unowned.append(path)
        else:
            # A mounted family cannot be described as INERT/UNAVAILABLE.
            assert states[owner] == "available", (path, owner, states[owner])
    assert unowned == []
