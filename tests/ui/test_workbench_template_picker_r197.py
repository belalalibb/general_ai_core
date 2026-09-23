"""R197 (UI closure, operator D1/D2/D4) — static check of the Workbench template picker.

The Workbench (``ui/app/``) is read as TEXT, never executed (ADR-0013 posture;
mirror of ``tests/ui/test_command_center_static_check_r182.py``), driven by the
manifest block ``ui_workbench_static_check`` declared BEFORE the first Workbench
edit (R197-DEC-01). One served-app read confirms the route literal exists.

Fails on:
  * file-list drift — the manifest lists EXACTLY the files present in ``ui/app/``
    (regular files only; the ``command/`` sub-tree has its own block);
  * ``/v1/`` drift — ``app.js`` raw occurrence count may never exceed the declared
    ceiling; the ceiling is ``null`` until the first GREEN (guard fails closed), is
    set ONCE to the measured count, and may only move DOWN afterwards;
  * ``fetch(`` drift — the measured pre-round count (4) is a ceiling, down only;
  * the picker not being wired: ``<select id="ask-template">`` in the HTML; the
    ONLY template source ``GET /v1/templates``; ``execution_strategy`` sent as
    ``{mode: "template", template_id: <ref>}`` ONLY when a ref is chosen;
  * the read fired at module load (F-R180-01 pattern: after the session);
  * a failed read that leaves options behind or does not render the unified error;
  * hardcoded template ids/refs, quoted CAPABILITY_IDS, provider branching,
    fabricated states, banned transports, framework/CDN imports;
  * ``/v1/`` wired from HTML/CSS; ``/v1/templates/{ref}`` consumed (D4: not in R197);
  * the frozen trees moving: ``ui/admin/app.js`` count 73 = N0, ``command.js`` 12.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "app"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"
TEMPLATES_ROUTE = "/v1/templates"
PROVIDER_WORDS = ("groq", "gsk", "openai", "anthropic", "genspark")
FABRICATED_STATES = ("thinking", "speaking", "listening", "energized", "processing", "reasoning")
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


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _block() -> dict:
    return _manifest()["ui_workbench_static_check"]


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _app_js() -> str:
    return (UI / "app.js").read_text(encoding="utf-8")


def _html() -> str:
    return (UI / "index.html").read_text(encoding="utf-8")


def _code() -> str:
    return _strip_js_comments(_app_js())


def _function_body(js: str, name: str) -> str:
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


def _top_level_statements(js: str) -> str:
    """Module-level code only (everything outside any brace block)."""
    out: list[str] = []
    depth = 0
    for ch in js:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------- manifest


def test_manifest_lists_exactly_the_workbench_files() -> None:
    declared = sorted(_block()["files"])
    present = sorted(
        str(p.relative_to(ROOT)) for p in UI.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    assert declared == present, f"manifest files {declared} != ui/app files {present}"
    assert declared == ["ui/app/app.js", "ui/app/index.html", "ui/app/styles.css"]


def test_workbench_exception_ceiling_is_zero() -> None:
    assert int(_block()["exception_count_ceiling"]) == 0


def test_v1_occurrence_count_never_exceeds_declared_ceiling() -> None:
    ceiling = _block()["v1_count_ceiling_app_js"]
    count = _app_js().count("/v1/")
    assert ceiling is not None, (
        f"ceiling not yet measured (null) — measured count now {count}; "
        "set it ONCE at the first GREEN of R197 (D2), then down only"
    )
    assert count <= int(ceiling), f"/v1/ drift in ui/app/app.js: {count} > ceiling={ceiling}"


def test_fetch_count_never_exceeds_measured_ceiling() -> None:
    ceiling = int(_block()["fetch_count_ceiling_app_js"])
    count = len(re.findall(r"\bfetch\(", _code()))
    assert count <= ceiling, f"fetch( drift in ui/app/app.js: {count} > ceiling={ceiling}"


def test_round_r197_ceiling_is_zero_and_unspent() -> None:
    rnd = _manifest()["change_budget"]["round_r197"]
    assert rnd["ceiling"] == 0
    assert rnd["changes_used"] == 0
    assert rnd["log"] == []


# ------------------------------------------------------------------ picker


def test_html_carries_the_template_select() -> None:
    html = _html()
    assert 'id="ask-template"' in html, "Workbench composer has no <select id=ask-template>"
    select = re.search(r"<select id=\"ask-template\"[^>]*>(.*?)</select>", html, flags=re.S)
    assert select is not None
    options = re.findall(r"<option[^>]*>", select.group(1))
    assert len(options) == 1, (
        "the HTML may carry ONLY the empty default option; refs come from the server"
    )
    assert 'value=""' in options[0]


def test_templates_route_is_the_only_template_source() -> None:
    code = _code()
    assert f'api("{TEMPLATES_ROUTE}")' in code, "Workbench does not read GET /v1/templates"
    # R197 D4 kept the detail route unconsumed; R202-DEC-01 (operator D1 = a) consumes it EXACTLY
    # once (loadTemplateDetail). Flipped 1:1 — the count, not the posture, is what is pinned.
    assert _app_js().count("/v1/templates/") == 1, "R202: /v1/templates/{ref} has exactly ONE consumer"
    assert "app_factory" not in _app_js().lower(), "hardcoded template id/ref in the Workbench"
    # options are built from the server rows (server order), keyed by ref
    body = _function_body(code, "populateTemplateSelect")
    assert TEMPLATES_ROUTE in body
    assert "templates" in body and ".ref" in body


def test_execution_strategy_is_sent_only_when_a_ref_is_chosen() -> None:
    body = _function_body(_code(), "submitAsk")
    assert "execution_strategy" in body
    assert 'mode: "template"' in body
    assert "template_id" in body
    # conditional: the assignment sits inside an `if (<ref>)` guard
    assert re.search(r"if\s*\(\s*templateRef\s*\)\s*body\.execution_strategy\s*=", body), (
        "execution_strategy must be set ONLY when a template ref is chosen"
    )


def test_template_read_is_not_fired_at_module_load() -> None:
    code = _code()
    top = _top_level_statements(code)
    calls_at_top = re.findall(r"(?<!function )\bpopulateTemplateSelect\(", top)
    assert calls_at_top == [], "template read must not run at module load"
    assert "populateTemplateSelect(" in _function_body(code, "enterMain"), (
        "template read must run once the session is established (enterMain), F-R180-01 pattern"
    )


def test_failed_read_renders_unified_error_and_offers_no_option() -> None:
    body = _function_body(_code(), "populateTemplateSelect")
    # stale options are cleared BEFORE the result is inspected; a refusal renders verbatim
    clear_at = body.index("select.remove(1)")
    check_at = body.index("if (!result.ok)")
    assert clear_at < check_at, (
        "stale template options must be cleared before the result is inspected"
    )
    assert "renderError(" in body


# --------------------------------------------------------------- transport


def test_banned_transports_absent() -> None:
    code = _code()
    for banned in ("EventSource(", "WebSocket(", "XMLHttpRequest", "axios"):
        assert banned not in code, f"banned transport in ui/app/app.js: {banned}"


@pytest.mark.parametrize("word", PROVIDER_WORDS)
def test_no_provider_branching(word: str) -> None:
    assert not re.search(rf"[\"'`]{word}[\"'`]", _code(), flags=re.I), f"provider literal {word!r}"


def test_no_hardcoded_capability_ids_or_fabricated_states() -> None:
    code = _code()
    assert "CAPABILITY_IDS" not in code
    for state in FABRICATED_STATES:
        assert not re.search(rf"[\"'`]{state}[\"'`]", code), f"fabricated state literal {state!r}"


def test_vanilla_es_module_posture() -> None:
    lowered = (_app_js() + _html()).lower()
    for marker in FORBIDDEN_IMPORT_MARKERS:
        assert marker not in lowered, f"framework/CDN marker {marker!r} in the Workbench"


def test_html_and_css_carry_no_v1_routes() -> None:
    """Inherited ui/admin rule: no WIRED /v1/ outside app.js (a comment may name one)."""
    assert "/v1/" not in (UI / "styles.css").read_text(encoding="utf-8")
    wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", _html())
    assert wired == [], f"index.html wires /v1/ routes outside app.js: {wired}"


def test_workbench_files_are_utf8() -> None:
    for name in _block()["files"]:
        (ROOT / name).read_text(encoding="utf-8")


# ------------------------------------------------------------ frozen trees


def test_frozen_ui_trees_unchanged() -> None:
    admin = (ROOT / "ui" / "admin" / "app.js").read_text(encoding="utf-8")
    assert admin.count("/v1/") == 73, "ui/admin/app.js moved — it is FROZEN in R197 (73 = N0)"
    command = (ROOT / "ui" / "app" / "command" / "command.js").read_text(encoding="utf-8")
    assert command.count("/v1/") == 12, "command.js moved — it is FROZEN in R197 (12)"


# ------------------------------------------------------------------ served


def test_templates_route_is_served() -> None:
    from apps.composition.runtime import build_runtime_profile

    profile = build_runtime_profile(environ={})
    assert TEMPLATES_ROUTE in profile.app.openapi()["paths"]
