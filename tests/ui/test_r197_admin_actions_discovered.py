"""R197-B (operator D3) — the three R195 admin actions are reachable from the console
WITHOUT a UI change: the R180 Q5 discovery-driven change form offers every action of
an ACTIVE area, and ``AdminArea.TOOLS`` is active.

This module is EVIDENCE, not a RED test (R197-DEC-01 says so explicitly): it pins
that the served discovery read model lists ``register_repo_binding`` /
``grant_remote_trust`` / ``revoke_remote_trust`` with their declared payload fields,
and that ``ui/admin/app.js`` still has no hand-list and stays at 73 = N0.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx

from apps.composition.runtime import build_runtime_profile
from core.contracts.admin import FINAL_ACTIVE_ADMIN_AREAS, AdminAction, AdminArea
from tests.security.test_r194_security_headers import ADMIN_EMAIL, _session

ROOT = Path(__file__).resolve().parents[2]
ADMIN_JS = ROOT / "ui" / "admin" / "app.js"
ACTIONS_ROUTE = "/v1/admin/capabilities/actions"
R195_ACTIONS = (
    AdminAction.REGISTER_REPO_BINDING,
    AdminAction.GRANT_REMOTE_TRUST,
    AdminAction.REVOKE_REMOTE_TRUST,
)


async def _get(app: Any, path: str, headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers)


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


class TestR195ActionsAreOfferedByDiscovery:
    def test_tools_area_is_active(self) -> None:
        assert AdminArea.TOOLS in FINAL_ACTIVE_ADMIN_AREAS

    def test_served_discovery_lists_the_three_actions_with_fields(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        admin = _session(profile, ADMIN_EMAIL)
        r = asyncio.run(_get(profile.app, ACTIONS_ROUTE, {"Authorization": f"Bearer {admin}"}))
        assert r.status_code == 200, r.text
        body = r.json()
        active = {row["area"] for row in body["areas"] if row["active"]}
        assert AdminArea.TOOLS.value in active
        rows = {row["action"]: row for row in body["actions"]}
        for action in R195_ACTIONS:
            row = rows[action.value]
            assert row["area"] == AdminArea.TOOLS.value
            assert row["fields"], f"{action.value} declares no payload fields"
        assert [f["name"] for f in rows["register_repo_binding"]["fields"]] == ["binding"]
        assert [f["name"] for f in rows["grant_remote_trust"]["fields"]] == [
            "target_tenant_id",
            "remote_url",
            "note",
        ]
        assert [f["name"] for f in rows["revoke_remote_trust"]["fields"]] == [
            "target_tenant_id",
            "remote_url",
        ]


class TestConsoleNeedsNoChange:
    def test_console_has_no_hand_list_and_reads_discovery(self) -> None:
        code = _strip_js_comments(ADMIN_JS.read_text(encoding="utf-8"))
        assert "ADMIN_ACTIONS" not in code
        for action in R195_ACTIONS:
            assert f'"{action.value}"' not in code, (
                "console must not name the verb; the server offers it"
            )
        assert f'api("{ACTIONS_ROUTE}")' in code

    def test_admin_console_is_frozen_at_n0(self) -> None:
        assert ADMIN_JS.read_text(encoding="utf-8").count("/v1/") == 73
