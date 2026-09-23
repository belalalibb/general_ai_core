"""R200 — Command capability -> surface routing + non-admin Command posture.

Static guard frame, declared BEFORE the first UI edit (R200-DEC-01; operator
D1 = B, D2 = i, D3 = i incl. /admin receiver, D4 = defer, D5 as proposed).
Fails closed on the opening tree (evidence/r200/red.txt).

Pins:
- [D2 = i] routing is DERIVED from the served ``evidence`` route prefix — the
  module carries a ``surfaceForEvidence`` function and NO quoted capability id
  (the R182 guard keeps holding); every href it builds is a served mount + hash.
- [D1 = B] ``probeSession`` admits any authenticated session; ``loadCenter``
  branches on ``session.is_admin``; the tenant path never names ``/v1/admin/``
  or ``/v1/agent/`` and renders ONE locked admin node labelled from the
  session fact; the admin path keeps the R185 request set.
- [D5] affordances: available+owned -> link; admin-only for a tenant -> disabled
  link labelled admin; inert/unavailable -> no link; routeless -> "no surface".
- [D3 = i] boot-once hash receivers: ``#view=`` in ui/app/app.js (iff in VIEWS),
  ``#surface=`` in ui/admin/app.js (iff a rail item exists); no hashchange, no timers.
- [D4 = defer] no template read in command.js; counts hold: command.js 12 //v1//
  + one fetch(, ui/app/app.js 22 / 4, ui/admin/app.js 73.
- ceiling 0: round_r200 declared and unspent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ui" / "app"
COMMAND = APP / "command"
ADMIN = ROOT / "ui" / "admin"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"
FORBIDDEN_STATES = (
    "thinking",
    "speaking",
    "listening",
    "energized",
    "processing",
    "reasoning",
    "typing",
    "typewriter",
    "waveform",
    "equalizer",
    "standby",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _body(js: str, name: str) -> str:
    start = js.index(f"function {name}(")
    i = js.index("{", js.index(")", start))
    depth = 0
    for j in range(i, len(js)):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i : j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _command() -> str:
    return _strip(_read(COMMAND / "command.js"))


def _app() -> str:
    return _strip(_read(APP / "app.js"))


def _admin() -> str:
    return _strip(_read(ADMIN / "app.js"))


# ------------------------------------------------------------------ D2 = i


def test_routing_is_derived_from_evidence_route_prefix() -> None:
    js = _command()
    assert "function surfaceForEvidence(" in js, "no evidence-derived routing function"
    body = _body(js, "surfaceForEvidence")
    assert "evidence" in body
    # the route is PARSED out of the served evidence with an escaped regex (\/v1\/...),
    # never spelled as a quoted "/v1/" literal (the 12-literal ceiling is frozen);
    # the table is keyed by the parsed first route segment (served facts, never ids)
    assert re.search(r"\\/v1\\/", body), "evidence route is not parsed by regex"
    assert not re.search(r"[\"'`]/v1/", body), "a quoted /v1/ literal would breach 12"


def test_no_capability_id_literal_anywhere_in_command_js() -> None:
    from apps.api.capabilities import CAPABILITY_IDS

    js = _command()
    quoted = [c for c in sorted(CAPABILITY_IDS) if re.search(rf"[\"'`]{re.escape(c)}[\"'`]", js)]
    assert quoted == [], quoted


def test_routeless_rows_get_an_honest_no_surface_line() -> None:
    body = _body(_command(), "surfaceForEvidence")
    assert "no surface" in body.lower(), "routeless evidence must say so, not vanish"


def test_built_hrefs_are_served_mounts_with_hash_and_no_v1() -> None:
    js = _command()
    body = _body(js, "surfaceForEvidence")
    hrefs = re.findall(r"[\"'`](/(?:app|admin)/[^\"'`]*)[\"'`]", body)
    assert hrefs, "surface table builds no mount hrefs"
    for href in hrefs:
        assert "/v1/" not in href, href
        assert href.startswith(("/app/", "/admin/")), href
        assert "#" in href, f"target without a view/surface hash: {href}"


# ------------------------------------------------------------------ D1 = B


def test_probe_session_admits_any_authenticated_session() -> None:
    body = _body(_command(), "probeSession")
    assert "is_admin" not in body, "probeSession still gates on is_admin (D1 = B)"


def test_load_center_branches_on_session_is_admin() -> None:
    body = _body(_command(), "loadCenter")
    assert "is_admin" in body, "loadCenter does not branch on the session fact"


def test_tenant_path_never_names_admin_or_agent_routes() -> None:
    js = _command()
    assert "function loadTenantCenter(" in js, "no tenant centre"
    body = _body(js, "loadTenantCenter")
    assert "/v1/admin/" not in body
    assert "/v1/agent" not in body


def test_tenant_center_renders_one_locked_admin_node_from_the_session_fact() -> None:
    js = _command()
    body = _body(js, "loadTenantCenter") + _body(js, "renderTenantSurfaces")
    assert "is_admin" in body, "locked node must quote the session fact"
    html = _read(COMMAND / "index.html")
    assert 'id="tenant-view"' in html
    assert 'id="tenant-surfaces"' in html
    assert 'id="tenant-admin-node"' in html


def test_admin_path_request_set_unchanged() -> None:
    body = _body(_command(), "loadCenter") + _body(_command(), "loadAdminCenter")
    for route in ('"/healthz"', '"/v1/admin/system"', '"/v1/admin/capabilities"'):
        assert route in body, route
    assert "refreshExecutions()" in body and "loadUsage()" in body


# ---------------------------------------------------------------------- D5


def test_node_detail_carries_an_affordance_slot() -> None:
    html = _read(COMMAND / "index.html")
    assert 'id="detail-surface"' in html
    js = _command()
    body = _body(js, "selectNode")
    assert "detail-surface" in body
    # one function owns the derivation: selectNode -> renderAffordance -> surfaceForEvidence
    assert "renderAffordance(" in body
    assert "surfaceForEvidence(" in _body(js, "renderAffordance")


def test_disabled_affordance_is_labelled_not_hidden() -> None:
    js = _command()
    body = _body(js, "renderAffordance")
    assert "aria-disabled" in body, "admin-only for a tenant must be a DISABLED link, not absent"
    assert "admin" in body


def test_no_fabricated_vocabulary_introduced() -> None:
    js = _command()
    html = _read(COMMAND / "index.html")
    for word in FORBIDDEN_STATES:
        assert re.search(rf"[\"'`.\-]{word}\b", js, flags=re.I) is None, word
        assert re.search(rf"\b{word}\b", html, flags=re.I) is None, word


# ------------------------------------------------------------------ D3 = i


def test_workbench_boot_once_hash_receiver() -> None:
    js = _app()
    assert "location.hash" in js, "ui/app/app.js has no hash receiver"
    assert "hashchange" not in js, "receiver must be boot-once (no listener)"
    body = _body(js, "applyDeepLink")
    assert "VIEWS" in body and "showView(" in body


def test_admin_boot_once_hash_receiver() -> None:
    js = _admin()
    assert "location.hash" in js, "ui/admin/app.js has no hash receiver"
    assert "hashchange" not in js
    body = _body(js, "applyDeepLink")
    assert "data-surface" in body


def test_no_timers_added_anywhere() -> None:
    for js in (_command(), _app(), _admin()):
        for banned in ("setInterval(",):
            assert banned not in js, banned
    assert "setTimeout(" not in _command()


# --------------------------------------------------------- D4 + count pins


def test_counts_hold_as_ceilings() -> None:
    command_raw = _read(COMMAND / "command.js")
    assert command_raw.count("/v1/") == 12
    assert _command().count("fetch(") == 1
    app_raw = _read(APP / "app.js")
    # 22 at R200; 23 since R202-DEC-01 (operator-declared ceiling re-measure, flipped 1:1)
    assert app_raw.count("/v1/") == 23 and app_raw.count("fetch(") == 4
    assert _read(ADMIN / "app.js").count("/v1/") == 73


def test_no_template_read_in_command_js() -> None:
    assert "/v1/templates" not in _read(COMMAND / "command.js")


def test_html_and_css_carry_no_v1_routes() -> None:
    for tree in (COMMAND / "index.html", APP / "index.html", ADMIN / "index.html"):
        wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", _read(tree))
        assert wired == [], (tree.name, wired)
    assert "/v1/" not in _read(COMMAND / "command.css")


# ---------------------------------------------------------------- manifest


def test_round_r200_declared_ceiling_zero_and_unspent() -> None:
    block = json.loads(_read(MANIFEST))["change_budget"]["round_r200"]
    assert int(block["ceiling"]) == 0
    assert int(block["changes_used"]) == 0
    assert block["log"] == []


@pytest.mark.parametrize("tree", ["app", "admin"])
def test_receivers_add_no_route_literals(tree: str) -> None:
    js = _app() if tree == "app" else _admin()
    body = _body(js, "applyDeepLink")
    assert "/v1/" not in body and "fetch(" not in body
