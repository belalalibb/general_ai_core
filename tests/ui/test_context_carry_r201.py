"""R201 guard — Context-carrying execution (UI-only; ceiling 0).

Operator (verbatim): "APPROVE R201 with D1–D7 confirmed (recommended: D1=a, D2=i, D3=i,
D4=defer, D5=defer, D6=defer, D7=defer)".

Pins (all static; the real-browser proof lives in evidence/r201/):
- [D1 = a] command.js builds execution-carrying hrefs ONLY from the existing SURFACE_BY_SEGMENT
  hrefs ('<href>&execution=<id>'); admin tier shows Workbench/Admin affordances for the selected
  execution under the R200 permission rule; tenant tier lists the ALREADY-FETCHED rows as links
  (no new request). command.js stays 12 `/v1/` + one fetch( in api().
- [D1 = a, D3 = i] receivers accept an optional `&execution=<uuid>` and call the EXISTING
  openRun / openExecution; anchored regex; no hashchange, no timers, no new reads, no /v1/.
  No receiver parameter without an emitter (no project=/template= params).
- [D2 = i] ui/app/app.js self-restores NON-SECRET selection via sessionStorage
  'qevion.app.context'; never localStorage; never the token; hash wins over the stored view;
  restore runs after the served lists resolve; cleared on logout.
- counts: ui/app/app.js <= 22 / fetch 4; ui/admin/app.js 73; round_r201 ceiling 0 unspent.
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
UUID_CLASS = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
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
    marker = f"function {name}("
    assert marker in js, f"{name} is not defined"
    start = js.index(marker)
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
    return _read(COMMAND / "command.js")


def _app() -> str:
    return _strip(_read(APP / "app.js"))


def _admin() -> str:
    return _strip(_read(ADMIN / "app.js"))


def _app_raw() -> str:
    return _read(APP / "app.js")


def _admin_raw() -> str:
    return _read(ADMIN / "app.js")


def _block() -> dict:
    return json.loads(_read(MANIFEST))["change_budget"]["round_r201"]


# ------------------------------------------------------------------ R201-A (D1 = a)


def test_execution_href_is_built_from_existing_surface_hrefs() -> None:
    js = _command()
    body = _body(js, "executionHref")
    assert "&execution=" in body, "the carried parameter is &execution=<id>"
    assert "encodeURIComponent(" in body, "the id is encoded, never interpolated raw"
    assert "/v1/" not in body and "fetch(" not in body
    assert ".href" in body, "must start from the owner's existing href (SURFACE_BY_SEGMENT)"
    assert not re.search(r"[\"'`]/(?:app|admin)/", body), (
        "executionHref must not mint a second mount literal — reuse the routing table"
    )


def test_admin_record_offers_workbench_and_admin_affordances() -> None:
    js = _command()
    body = _body(js, "renderExecutionSurfaces")
    assert "executionHref(" in body
    assert "SURFACE_BY_SEGMENT.executions" in body, "Workbench runs owner from the table"
    assert "ADMIN_EXECUTIONS_OWNER" in body, "Admin executions owner is one named table entry"
    assert "/admin/#surface=executions" in js and "/v1/" not in body
    assert "is_admin" in body, "admin target labelled from the served session fact"
    assert "aria-disabled" in body, "non-admin: labelled, disabled admin link (nothing hidden)"
    show = _body(js, "showExecution")
    assert "renderExecutionSurfaces(" in show, "selected execution must render its affordances"


def test_tenant_tier_lists_served_rows_as_execution_links() -> None:
    js = _command()
    body = _body(js, "renderTenantSurfaces")
    assert "executionHref(" in body
    assert "execution_id" in body and "status" in body and "created_at" in body, (
        "row facts come from the served executions row only"
    )
    assert "api(" not in body and "fetch(" not in body and "/v1/" not in body, (
        "tenant list must reuse state.executions — no new request"
    )
    html = _read(COMMAND / "index.html")
    assert 'id="tenant-execution-list"' in html
    assert 'id="execution-surfaces"' in html


def test_command_counts_hold() -> None:
    raw = _command()
    assert raw.count("/v1/") == 12, "command.js /v1/ literal count is frozen at 12"
    assert _strip(raw).count("fetch(") == 1, "one fetch( — inside api()"
    for word in FORBIDDEN_STATES:  # the R185 rendering-context rule, verbatim
        assert re.search(rf"[\"'`.\-]{word}\b", raw, flags=re.I) is None, word


# ------------------------------------------------------------------ R201-B (D1 = a, D3 = i)


def test_workbench_receiver_accepts_execution_and_opens_the_run() -> None:
    js = _app()
    body = _body(js, "applyDeepLink")
    assert "execution=" in body, "receiver must accept &execution="
    assert re.search(r"\^#view=", body) and "$/" in body, "regex stays anchored"
    assert UUID_CLASS[:12] in body, "id is UUID-shaped or the whole hash is ignored"
    assert "VIEWS" in body and "showView(" in body, "R200 posture kept"
    assert "openRun(" in body, "reuse the EXISTING open-by-id function"
    assert '"runs"' in body, "the id is only consumed on the runs view"
    assert "/v1/" not in body and "fetch(" not in body and "api(" not in body
    assert "hashchange" not in js and "setInterval(" not in js


def test_admin_receiver_accepts_execution_and_opens_the_record() -> None:
    js = _admin()
    body = _body(js, "applyDeepLink")
    assert "execution=" in body
    assert re.search(r"\^#surface=", body) and "$/" in body
    assert UUID_CLASS[:12] in body
    assert "data-surface" in body, "R200 posture kept"
    assert "openExecution(" in body, "reuse the EXISTING open-by-id function"
    assert '"executions"' in body, "the id is only consumed on the executions surface"
    assert "/v1/" not in body and "fetch(" not in body and "api(" not in body
    assert "hashchange" not in js


@pytest.mark.parametrize("tree", ["app", "admin"])
def test_no_receiver_parameter_without_an_emitter(tree: str) -> None:
    body = _body(_app() if tree == "app" else _admin(), "applyDeepLink")
    for dead in ("project=", "template=", "workspace=", "model="):
        assert dead not in body, f"{dead} has no emitter — D3 = i forbids a dead receiver"


# ------------------------------------------------------------------ R201-C (D2 = i)


def test_workbench_context_key_is_session_scoped_and_never_the_token() -> None:
    js = _app()
    assert "qevion.app.context" in js
    assert "sessionStorage" in js
    assert "localStorage" not in _app_raw(), "never persist beyond the tab (not even in prose)"
    body = _body(js, "saveContext")
    assert "token" not in body, "the bearer token is NEVER part of the stored context"
    for key in ("view", "selectedWorkspace", "project", "template"):
        assert key in body, key


def test_workbench_restore_requires_served_membership_and_yields_to_hash() -> None:
    js = _app()
    body = _body(js, "restoreContext")
    assert "sessionStorage.getItem(" in body
    assert "state.workspaces" in body, "workspace restored only if the served list has it"
    assert "options" in body, "project/template restored only if the served option exists"
    assert "location.hash" in body, "an explicit hash wins over the stored view"
    main = _body(js, "enterMain")
    assert "await refreshWorkspaces()" in main and "await populateTemplateSelect()" in main, (
        "restore must run AFTER the served lists resolve"
    )
    assert main.index("restoreContext(") > main.index("await populateTemplateSelect()")
    assert "populateTemplateSelect(" in main, "R197 pin"
    assert "/v1/" not in body and "fetch(" not in body and "api(" not in body


def test_workbench_clears_context_on_logout() -> None:
    js = _app()
    logout = js[js.index('$("logout-button").addEventListener') :]
    logout = logout[: logout.index("\n  });") + 6]
    assert "clearContext(" in logout or "sessionStorage.removeItem(" in logout


# ------------------------------------------------------------------ counts / ceiling


def test_frozen_counts_and_ceiling() -> None:
    app_raw = _app_raw()
    assert app_raw.count("/v1/") <= 22 and app_raw.count("fetch(") == 4
    assert _admin_raw().count("/v1/") == 73
    assert "/v1/" not in _read(COMMAND / "command.css")
    html = _read(COMMAND / "index.html")
    wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", html)
    assert wired == [], wired
    block = _block()
    assert int(block["ceiling"]) == 0 and int(block["changes_used"]) == 0
    assert block["items"] and any("R201-A" in i for i in block["items"])
