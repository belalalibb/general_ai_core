"""R182-IMPL D-2 — static check of the Command Center (ui/app/command/*) read as text.

Mirror of tests/ui/test_admin_static_check.py for the NEW tree, driven by the
manifest block ``ui_command_static_check`` (declared BEFORE the first Command
Center file — R182_HANDOFF §14; R182-DEC-02).

Fails on:
  * file-list drift — the manifest lists EXACTLY the files present in ui/app/command/;
  * `/v1/` drift — `command.js` raw occurrence count may never exceed the declared
    ceiling; the ceiling is `null` until the first GREEN of M1 (guard fails closed),
    is set ONCE to the measured count, and may only move DOWN afterwards;
  * hand-written route literals the served OpenAPI does not expose;
  * more than one transport (one `fetch(` inside `async function api(`; EventSource /
    WebSocket / XMLHttpRequest / axios banned — inherited ui/admin policy);
  * quoted CAPABILITY_IDS, roster arrays, provider branching, duplicated schemas;
  * `/v1/` wired from HTML/CSS outside command.js;
  * ES-module posture (ADR-0013 Alternative C): no framework/bundler/CDN imports.

The `ui/admin` block, N0 = 73, and `test_manifest_lists_exactly_the_ui_files` are
untouched (HANDOFF §14).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "app" / "command"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"

PROVIDER_WORDS = ("groq", "gsk", "openai", "anthropic", "genspark")
FORBIDDEN_IMPORT_MARKERS = (
    "react",
    "three",
    "next/",
    "vue",
    "svelte",
    "lucide",
    "cdn.jsdelivr",
    "unpkg.com",
    "esm.sh",
    "node_modules",
)


def _block() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["ui_command_static_check"]


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _command_js() -> str:
    return (UI / "command.js").read_text(encoding="utf-8")


def _route_literals() -> list[str]:
    js = _strip_js_comments(_command_js())
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
    i = text.index("{", text.index(")", start))
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    raise AssertionError("unbalanced braces in command.js")


# ---------------------------------------------------------------- manifest


def test_manifest_lists_exactly_the_command_center_files() -> None:
    declared = sorted(_block()["files"])
    assert UI.is_dir(), "ui/app/command/ absent"
    present = sorted(
        str(p.relative_to(ROOT)) for p in UI.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    assert declared == present, f"manifest files {declared} != ui/app/command files {present}"
    assert declared == [
        "ui/app/command/command.css",
        "ui/app/command/command.js",
        "ui/app/command/index.html",
    ]


def test_command_exception_ceiling_is_zero() -> None:
    assert int(_block()["exception_count_ceiling"]) == 0


def test_v1_occurrence_count_never_exceeds_declared_ceiling() -> None:
    ceiling = _block()["v1_count_ceiling_command_js"]
    count = _command_js().count("/v1/")
    assert ceiling is not None, (
        f"ceiling not yet measured (null) — measured count now {count}; "
        "set it ONCE at the first GREEN of M1 (D-2), then down only"
    )
    assert count <= int(ceiling), f"/v1/ drift in command.js: {count} > ceiling={ceiling}"


# ---------------------------------------------------------------- routes


def test_command_route_literals_exist_on_served_app(tmp_path: Path) -> None:
    served = _openapi_paths(tmp_path)
    assert served, "served app exposes no OpenAPI paths"
    literals = _route_literals()
    assert literals, "no api('/v1/...') literals found — extractor broken"
    unknown = sorted({p for p in literals if not _ui_matches_served(p, served)})
    assert unknown == [], f"Command Center route literals not served by the app: {unknown}"
    assert not _ui_matches_served("/v1/definitely/not/served", served)


# ------------------------------------------------------------- transport


def test_single_transport_inside_api_function() -> None:
    js = _strip_js_comments(_command_js())
    fetch_calls = re.findall(r"\bfetch\(", js)
    assert len(fetch_calls) == 1, f"expected exactly one fetch( call, found {len(fetch_calls)}"
    head = js.index("async function api(")
    body = _brace_block(js, head)
    assert "fetch(" in body, "the single fetch( must live inside async function api("
    for banned in ("XMLHttpRequest", "EventSource(", "WebSocket(", "axios"):
        assert banned not in js, f"second transport in Command Center: {banned}"


def test_no_polling_theater() -> None:
    js = _strip_js_comments(_command_js())
    assert re.search(r"\bsetInterval\(", js) is None, "setInterval call (polling theater)"


# --------------------------------------------------------- branching/ids


@pytest.mark.parametrize("word", PROVIDER_WORDS)
def test_no_provider_branching(word: str) -> None:
    js = _strip_js_comments(_command_js())
    q = "[\"']"
    pattern = f"===\\s*{q}{word}{q}|{q}{word}{q}\\s*==="
    hits = re.findall(pattern, js, flags=re.I)
    assert hits == [], f"provider branching on '{word}' in command.js: {hits}"


def test_no_hardcoded_capability_ids() -> None:
    from apps.api.capabilities import CAPABILITY_IDS

    js = _strip_js_comments(_command_js())
    quoted = [
        cid for cid in sorted(CAPABILITY_IDS) if re.search(rf"[\"'`]{re.escape(cid)}[\"'`]", js)
    ]
    assert quoted == [], f"capability ids hardcoded in command.js: {quoted}"


def test_no_duplicated_schemas_or_sql() -> None:
    js = _strip_js_comments(_command_js())
    for marker in ("pydantic", "BaseModel", "sqlalchemy", "CREATE TABLE", "z.object("):
        assert marker not in js, f"schema duplicated into the UI: {marker}"


# ------------------------------------------------------------ ADR-0013 C


def test_vanilla_es_module_posture() -> None:
    """Alternative C: no framework, no bundler output, no CDN/runtime dependency."""
    js = _strip_js_comments(_command_js()).lower()
    html = (UI / "index.html").read_text(encoding="utf-8").lower()
    for marker in FORBIDDEN_IMPORT_MARKERS:
        assert marker not in js, f"runtime dependency marker in command.js: {marker}"
        assert marker not in html, f"runtime dependency marker in index.html: {marker}"
    assert re.search(r"\bimport\s+.*\bfrom\s+[\"']https?://", js) is None, "remote import"
    assert re.search(r"<script[^>]+src=[\"']https?://", html) is None, "remote script"
    assert re.search(r'<script[^>]+type="module"[^>]+src="command\.js"', html), (
        "index.html must load command.js as an ES module"
    )


def test_reduced_motion_collapse_declared() -> None:
    """Optional drawing layer enters only with a clean reduced-motion collapse (D-1)."""
    css = (UI / "command.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


# ------------------------------------------------------------ html / css


def test_html_and_css_carry_no_v1_routes() -> None:
    css = (UI / "command.css").read_text(encoding="utf-8")
    assert "/v1/" not in css
    html = (UI / "index.html").read_text(encoding="utf-8")
    wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", html)
    assert wired == [], f"index.html wires /v1/ routes outside command.js: {wired}"


def test_command_files_are_utf8() -> None:
    for name in _block()["files"]:
        (ROOT / name).read_text(encoding="utf-8")
