"""R168 §6.5 — static check of the admin UI (ui/admin/*) read as text.

The UI files are never executed here. The tests read them as text and fail on:
  * `/v1/` drift — the raw occurrence count may never exceed the R168 baseline N0
    (green_manifest.baseline.json → ui.v1_count_N0); the manifest ceiling may only
    move down.
  * hand-written route literals that the served OpenAPI does not expose
    (routes must be derived from the app, not typed by hand).
  * hardcoded capability ids (apps/api/capabilities.py CAPABILITY_IDS).
  * provider / capability branching inside the UI.
  * duplicated schemas (pydantic / sqlalchemy / DDL / zod) inside the UI.
  * more than one transport (a single `fetch(` inside `async function api(` is the
    declared exception).

The manifest is the single authority for which files are checked and for the
exception ceiling (0).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "admin"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"
BASELINE = ROOT / "engineering" / "verification" / "green_manifest.baseline.json"

PROVIDER_WORDS = ("groq", "gsk", "openai", "anthropic", "genspark")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _app_js() -> str:
    return (UI / "app.js").read_text(encoding="utf-8")


def _route_literals() -> list[str]:
    js = _strip_js_comments(_app_js())
    return re.findall(r"api\(\s*[\"'`](/v1/[^\"'`?]*)", js)


def _openapi_paths(tmp_path: Path) -> set[str]:
    from apps.composition.runtime import build_runtime_profile

    ws = tmp_path / "ws"
    ws.mkdir()
    environ = dict(os.environ)
    environ.update(
        {
            "AGENT_WORKSPACE_ROOT": str(ws),
            "AGENT_WORKSPACE_COMMANDS": "python3",
            "GATEWAY_BASE_URL": "http://localhost:9999",
            "GATEWAY_SECRET": "unused-test-binding",
            "GATEWAY_SECRET_VERSION": "1",
        }
    )
    profile = build_runtime_profile(environ)
    return set(profile.app.openapi()["paths"])


def _ui_matches_served(ui_path: str, served: set[str]) -> bool:
    ui_segs = ui_path.rstrip("/").split("/")
    for s in served:
        segs = s.rstrip("/").split("/")
        if len(segs) != len(ui_segs):
            continue
        ok = True
        for served_seg, ui_seg in zip(segs, ui_segs, strict=True):
            if ui_seg.startswith("${"):
                continue
            if served_seg.startswith("{") and served_seg.endswith("}"):
                continue
            if served_seg != ui_seg:
                ok = False
                break
        if ok:
            return True
    return False


def _brace_block(text: str, start: int) -> str:
    """Return the function body `{...}` — the first `{` after the closing `)` of the head."""
    i = text.index("{", text.index(")", start))
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise AssertionError("unbalanced braces in app.js")


# ---------------------------------------------------------------- routes


def test_ui_route_literals_exist_on_served_app(tmp_path: Path) -> None:
    served = _openapi_paths(tmp_path)
    assert served, "served app exposes no OpenAPI paths"
    literals = _route_literals()
    assert literals, "no api('/v1/...') literals found — extractor broken"
    unknown = sorted({p for p in literals if not _ui_matches_served(p, served)})
    assert unknown == [], f"UI route literals not served by the app: {unknown}"
    # negative control: the matcher must reject a route that is not served
    assert not _ui_matches_served("/v1/definitely/not/served", served)


def test_v1_occurrence_count_never_exceeds_N0() -> None:
    n0_baseline = int(_baseline()["ui"]["v1_count_N0"])
    n0_manifest = int(_manifest()["ui_static_check"]["v1_count_ceiling_N0"])
    assert n0_manifest <= n0_baseline, "manifest N0 ceiling may only move down"
    count = _app_js().count("/v1/")
    assert count <= n0_manifest, f"/v1/ drift in app.js: {count} > N0={n0_manifest}"


def test_ui_exception_ceiling_is_zero() -> None:
    assert int(_manifest()["ui_static_check"]["exception_count_ceiling"]) == 0


def test_manifest_lists_exactly_the_ui_files() -> None:
    declared = sorted(_manifest()["ui_static_check"]["files"])
    present = sorted(
        str(p.relative_to(ROOT)) for p in UI.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    assert declared == present, f"manifest files {declared} != ui/admin files {present}"


# ------------------------------------------------------------- transport


def test_single_transport_inside_api_function() -> None:
    js = _strip_js_comments(_app_js())
    fetch_calls = re.findall(r"\bfetch\(", js)
    assert len(fetch_calls) == 1, f"expected exactly one fetch( call, found {len(fetch_calls)}"
    head = js.index("async function api(")
    body = _brace_block(js, head)
    assert "fetch(" in body, "the single fetch( must live inside async function api("
    for banned in ("XMLHttpRequest", "EventSource(", "WebSocket(", "axios"):
        assert banned not in js, f"second transport in UI: {banned}"


# --------------------------------------------------------- branching/ids


@pytest.mark.parametrize("word", PROVIDER_WORDS)
def test_no_provider_branching(word: str) -> None:
    js = _strip_js_comments(_app_js())
    q = "[\"']"
    pattern = f"===\\s*{q}{word}{q}|{q}{word}{q}\\s*==="
    hits = re.findall(pattern, js, flags=re.I)
    assert hits == [], f"provider branching on '{word}' in app.js: {hits}"


def test_no_hardcoded_capability_ids() -> None:
    from apps.api.capabilities import CAPABILITY_IDS

    assert CAPABILITY_IDS, "CAPABILITY_IDS empty — guard has nothing to check"
    js = _strip_js_comments(_app_js())
    quoted = [
        cid for cid in sorted(CAPABILITY_IDS) if re.search(rf"[\"'`]{re.escape(cid)}[\"'`]", js)
    ]
    assert quoted == [], f"capability ids hardcoded in app.js: {quoted}"


def test_no_duplicated_schemas_or_sql() -> None:
    js = _strip_js_comments(_app_js())
    for marker in ("pydantic", "BaseModel", "sqlalchemy", "CREATE TABLE", "z.object("):
        assert marker not in js, f"schema duplicated into the UI: {marker}"


# ------------------------------------------------------------ html / css


def test_html_and_css_carry_no_v1_routes() -> None:
    css = (UI / "styles.css").read_text(encoding="utf-8")
    assert "/v1/" not in css
    html = (UI / "index.html").read_text(encoding="utf-8")
    wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", html)
    assert wired == [], f"index.html wires /v1/ routes outside app.js: {wired}"


def test_ui_files_are_utf8() -> None:
    for name in _manifest()["ui_static_check"]["files"]:
        (ROOT / name).read_text(encoding="utf-8")
