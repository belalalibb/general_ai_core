"""R179 4.3 — action discovery: a generic consumer learns which admin actions the
control-plane capability supports, DERIVED from the canonical vocabulary.

Rules pinned here:

- Source of truth is ``core.contracts.admin.ACTION_AREA`` (one owner per action)
  plus ``FINAL_ACTIVE_ADMIN_AREAS`` — the read model is a pure function of them.
  No hand-maintained action names exist in the producing module (proved by
  scanning it for enum literals).
- Drift is impossible: every ``AdminAction`` appears exactly once; every area in
  the closed ``AdminArea`` set appears exactly once; an action's area is ITS
  owner; inactive areas carry no actions.
- Payload-schema half is NOT exposed (DEC-A: design only) — the row carries the
  action name and its owner area, nothing about payload fields.
- Frozen consumers intact: the shelf row shape ``{id,state,evidence}`` is
  untouched; the discovery lives on its OWN route
  (``/v1/admin/capabilities/actions``), admin-gated like every ``/v1/admin/*`` route.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from fastapi import FastAPI

from apps.api.capabilities import CAPABILITY_IDS, admin_actions_json
from core.contracts.admin import ACTION_AREA, FINAL_ACTIVE_ADMIN_AREAS, AdminAction, AdminArea
from tests.api.test_admin_api import World
from tests.api.test_capability_catalog_r177 import _app, run

ROOT = Path(__file__).resolve().parents[2]
ROUTE = "/v1/admin/capabilities/actions"


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


# --- pure derivation ------------------------------------------------------------------


def test_read_model_is_a_pure_function_of_the_canonical_vocabulary() -> None:
    payload = admin_actions_json()
    assert payload["scope"] == "process"
    assert payload["capability"] == "admin.control_plane"
    assert payload["capability"] in CAPABILITY_IDS
    assert payload["vocabulary"] == "core.contracts.admin.ACTION_AREA"
    actions = payload["actions"]
    assert isinstance(actions, list)
    # Every action exactly once, sorted, owner == ACTION_AREA (one owner per action).
    assert [row["action"] for row in actions] == sorted(a.value for a in AdminAction)
    for row in actions:
        # R179 rulings Q4 (conscious pin update): DEC-A approved — the payload half
        # rides the SAME row as `fields`, read from core.admin.service.PAYLOAD_FIELD_RULES.
        assert set(row) == {"action", "area", "fields"}
        assert ACTION_AREA[AdminAction(row["action"])].value == row["area"]
    # Every area exactly once (the closed 21-value set), active flag from the
    # FINAL set, actions grouped under their owner, inactive areas empty.
    areas = payload["areas"]
    assert [row["area"] for row in areas] == sorted(a.value for a in AdminArea)
    for row in areas:
        assert set(row) == {"area", "active", "actions"}
        area = AdminArea(row["area"])
        assert row["active"] is (area in FINAL_ACTIVE_ADMIN_AREAS)
        expected = sorted(a.value for a, owner in ACTION_AREA.items() if owner is area)
        assert row["actions"] == expected
        if not row["active"]:
            assert row["actions"] == []


def test_no_hand_maintained_action_or_area_names_in_the_producer() -> None:
    source = (ROOT / "apps" / "api" / "capabilities.py").read_text(encoding="utf-8")
    body = source[source.index("def admin_actions_json") :]
    literals = set(re.findall(r'"([a-z_]+)"', body))
    assert literals.isdisjoint({a.value for a in AdminAction}), literals
    assert literals.isdisjoint({a.value for a in AdminArea}), literals


def test_drift_is_impossible_by_construction() -> None:
    # No second list exists: the read model IS the vocabulary, re-shaped.
    payload = admin_actions_json()
    assert len(payload["actions"]) == len(AdminAction) == len(ACTION_AREA)
    owners = {row["action"]: row["area"] for row in payload["actions"]}
    assert owners == {a.value: area.value for a, area in ACTION_AREA.items()}


# --- HTTP surface -------------------------------------------------------------------------


def test_route_serves_the_derived_read_model_admin_gated() -> None:
    app = _app(World())
    response = run(_get(app, ROUTE))
    assert response.status_code == 200
    assert response.json() == admin_actions_json()
    # Deny-by-default: a non-admin principal is refused like every /v1/admin/* read.
    denied = run(_get(_app(World(is_admin=False)), ROUTE))
    assert denied.status_code in (401, 403)


def test_shelf_row_shape_is_untouched_by_discovery() -> None:
    app = _app(World())
    catalog = run(_get(app, "/v1/admin/capabilities")).json()
    for row in catalog["capabilities"]:
        assert set(row) == {"id", "state", "evidence"}
    assert "actions" not in catalog
