"""R180 opening commit — Q5 thaw (R179 rulings: "let the console consume
``/capabilities/actions`` and drop the ``ADMIN_ACTIONS`` hand-list").

Static, hermetic reads of ``ui/admin/app.js`` (the R168 §6.5 posture: the UI is
never executed here) plus one served-app read so the console's ONLY source for
the admin verb set is the R179 4.3 discovery route:

* the hand-maintained ``ADMIN_ACTIONS`` array is GONE (no second list);
* the change form's ``<select>`` is populated from ``GET /v1/admin/capabilities/actions``
  (``actions[].action``), in the order the server publishes;
* per-action ``fields`` (Q4 ``PAYLOAD_FIELD_RULES``) are rendered as a hint next
  to the payload box — read from the SAME row, never typed;
* a failed discovery read renders the unified error verbatim and offers NO verbs
  (the console cannot fall back to a guessed list);
* ``/v1/`` occurrence count stays within the manifest ceiling N0 (the arithmetic
  binding the ruling named), and the new literal is served by the app.

F-R179-07 rides the same thaw: ``apps/admin_agent/tools.py`` annotates the port
(``UsageAccountingPort``) instead of the concrete in-memory class.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "ui" / "admin" / "app.js"
TOOLS_PY = ROOT / "apps" / "admin_agent" / "tools.py"
ACTIONS_ROUTE = "/v1/admin/capabilities/actions"


def _js() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _populate_body(code: str) -> str:
    start = code.index("async function populateActionSelect")
    return code[start : code.index("\n}\n", start)]


class TestHandListDropped:
    def test_admin_actions_hand_list_is_gone(self) -> None:
        code = _strip_js_comments(_js())
        assert re.search(r"const ADMIN_ACTIONS\s*=", code) is None
        # No AdminAction literal survives as an offered verb anywhere in code.
        from core.contracts.admin import AdminAction

        offered_literals = {a.value for a in AdminAction if f'"{a.value}"' in code}
        assert offered_literals == set(), offered_literals

    def test_console_reads_the_discovery_route(self) -> None:
        assert f'api("{ACTIONS_ROUTE}")' in _strip_js_comments(_js())

    def test_select_is_filled_from_server_rows_in_server_order(self) -> None:
        body = _populate_body(_strip_js_comments(_js()))
        assert ACTIONS_ROUTE in body
        assert "body.actions" in body
        assert ".sort(" not in body, "server order is the contract; the console does not reorder"
        assert "change-action" in body

    def test_only_active_areas_are_offered(self) -> None:
        body = _populate_body(_strip_js_comments(_js()))
        assert "body.areas" in body and ".active" in body


class TestFieldsHint:
    def test_payload_hint_is_read_from_the_same_row(self) -> None:
        code = _strip_js_comments(_js())
        assert "change-fields-hint" in code
        assert ".fields" in code
        # The hint names the declared source published by the server, never a UI copy.
        assert "field_rules" in code

    def test_html_carries_the_hint_element(self) -> None:
        html = (ROOT / "ui" / "admin" / "index.html").read_text(encoding="utf-8")
        assert 'id="change-fields-hint"' in html


class TestReadAfterSignIn:
    def test_discovery_read_is_not_fired_at_module_load(self) -> None:
        """F-R180-01 (live check): the route is admin-gated; a module-load call
        answers 401 before sign-in and the select stays empty. The read belongs
        to the Changes surface loader."""
        code = _strip_js_comments(_js())
        assert re.search(r"^populateActionSelect\(\);", code, re.M) is None
        start = code.index("async function loadChanges")
        body = code[start : code.index("\n}\n", start)]
        assert "populateActionSelect()" in body

    def test_re_read_replaces_and_refusal_clears(self) -> None:
        body = _populate_body(_strip_js_comments(_js()))
        assert "select.remove(1)" in body and "actionRows.clear()" in body
        # clearing happens BEFORE the ok-check so a refusal leaves no stale verb
        assert body.index("actionRows.clear()") < body.index("renderError(")


class TestRefusalIsContent:
    def test_failed_discovery_renders_error_and_offers_no_verbs(self) -> None:
        body = _populate_body(_strip_js_comments(_js()))
        assert "renderError(" in body
        assert "return;" in body.split("renderError(")[1]


class TestArithmeticBinding:
    def test_v1_count_within_manifest_ceiling(self) -> None:
        import json

        manifest = json.loads(
            (ROOT / "engineering/verification/green_manifest.json").read_text(encoding="utf-8")
        )
        n0 = int(manifest["ui_static_check"]["v1_count_ceiling_N0"])
        assert _js().count("/v1/") <= n0

    def test_actions_route_is_served(self) -> None:
        from apps.composition.runtime import build_runtime_profile

        profile = build_runtime_profile(environ={})
        assert ACTIONS_ROUTE in profile.app.openapi()["paths"]


class TestFR17907:
    def test_agent_tool_surface_annotates_the_usage_port(self) -> None:
        source = TOOLS_PY.read_text(encoding="utf-8")
        assert re.search(r"^\s+usage: UsageAccountingPort$", source, re.M), "F-R179-07 open"
        assert "usage: InMemoryUsageAccounting" not in source
        assert "from core.usage.ports import UsageAccountingPort" in source

    def test_runtime_call_site_needs_no_ignore(self) -> None:
        runtime = (ROOT / "apps/composition/runtime.py").read_text(encoding="utf-8")
        assert "type: ignore[arg-type]" not in runtime


class TestR180RulingScope:
    """R180 operator rulings (R180-DEC-02): the ``apps/admin_agent/`` thaw is
    ratified STRICTLY for the ``UsageAccountingPort`` annotation in ``tools.py``
    and must not generalize to other files under that tree. Pinned on the
    source, not on git: every other module under ``apps/admin_agent/`` must not
    reference the R180 thaw at all, and ``tools.py`` must reference the port in
    exactly the two places the ruling covers (import + annotation)."""

    def test_tools_py_thaw_is_exactly_the_port_annotation(self) -> None:
        source = TOOLS_PY.read_text(encoding="utf-8")
        assert source.count("UsageAccountingPort") == 2, "import + annotation, nothing more"
        assert "InMemoryUsageAccounting" not in source

    def test_no_other_admin_agent_module_carries_an_r180_edit_marker(self) -> None:
        tree = TOOLS_PY.parent
        others = sorted(p for p in tree.glob("*.py") if p.name != "tools.py")
        assert others, "admin_agent tree unexpectedly empty"
        for path in others:
            text = path.read_text(encoding="utf-8")
            assert "R180" not in text, f"{path.name}: R180 marker outside the ratified scope"
