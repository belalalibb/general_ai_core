"""UI-RECON-SHELL — static guard frame for the unified shell (ui/app/shell/).

Declared BEFORE the first shell file (R182 convention; UI-RECON-DEC-01 §C/§D)
from the manifest block ``ui_shell_static_check``. Fails CLOSED while the shell
does not exist (the FIRST RED test of the round).

Invariants pinned here (operator rulings OD-1 = B, OD-2, OD-3):

* the manifest file list IS the shell — every declared file exists and no
  undeclared production file lives under ``ui/app/shell/``;
* single transport: ``/v1/`` route literals live ONLY in ``api.js``; exactly
  one ``fetch(`` in the whole tree (inside ``api()``); every other module has
  ZERO ``/v1/`` literals; ``EventSource(`` is allowed (SSE) but only in
  ``api.js`` so the transport stays in one place;
* the ceiling for ``api.js`` is ``null`` until the first GREEN gate (OD-3),
  afterwards the measured count must never exceed it;
* prohibited markers: framework/CDN/bundler markers (ADR-0013 Alternative C),
  the word ``localStorage``, fabricated runtime states;
* capability-derivation (OD-1 = B): the shell holds NO literal capability id,
  NO capability-state roster, NO segment->surface map and NO evidence-prose
  parsing — the admin topology is rendered from the served records only, and
  non-admin Command renders no topology at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "engineering" / "verification" / "green_manifest.json"
SHELL = REPO / "ui" / "app" / "shell"

# The closed CapabilityState vocabulary + the closed capability id set are
# served facts (apps/api/capabilities.py); the shell must not spell them.
CAPABILITY_ID_PATTERN = re.compile(
    r"[\"'](?:execute|executions|conversations|context|models|skills|usage|webhooks|admin|"
    r"learning|rate_limits|auth|health|dev|agent|sourcechange|workspaces|evaluation|templates)"
    r"\.[a-z_]+[\"']"
)
FABRICATED_STATES = ("thinking", "speaking", "listening", "energized", "processing", "reasoning")
FRAMEWORK_MARKERS = (
    "cdn.",
    "unpkg",
    "jsdelivr",
    "react",
    "vue",
    "angular",
    "svelte",
    "htmx",
    "jquery",
    "three",
    "webpack",
    "vite",
    "require(",
    "node_modules",
)


def _manifest() -> dict[str, Any]:
    loaded: object = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def _block() -> dict[str, Any]:
    block = _manifest()["ui_shell_static_check"]
    assert isinstance(block, dict)
    return cast("dict[str, Any]", block)


def _files() -> list[Path]:
    return [REPO / f for f in _block()["files"]]


def _strip_js_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"(^|[^:\\])//[^\n]*", r"\1", code)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. the declared file list IS the shell -----------------------------------------


def test_manifest_block_is_declared_with_the_od3_ceiling_rule() -> None:
    block = _block()
    assert block["exception_count_ceiling"] == 0
    assert "OD-3" in block["v1_count_ceiling_rule"]
    assert block["files"], "the guard frame must name the shell files"
    assert all(f.startswith("ui/app/shell/") for f in block["files"])


def test_every_declared_shell_file_exists() -> None:
    missing = [str(p.relative_to(REPO)) for p in _files() if not p.is_file()]
    assert missing == [], f"shell files declared but absent (RED until implemented): {missing}"


def test_no_undeclared_production_file_under_the_shell_tree() -> None:
    assert SHELL.is_dir(), "ui/app/shell/ does not exist yet (RED until implemented)"
    declared = {str(p.relative_to(REPO)) for p in _files()}
    present = {
        str(p.relative_to(REPO))
        for p in SHELL.rglob("*")
        if p.is_file() and p.suffix in {".js", ".html", ".css"}
    }
    assert present == declared, f"undeclared/missing: {sorted(present ^ declared)}"


# --- 2. single transport -----------------------------------------------------------------


def test_v1_literals_live_only_in_api_js() -> None:
    offenders = {}
    for path in _files():
        if path.name == "api.js" or path.suffix != ".js":
            continue
        count = _strip_js_comments(_read(path)).count("/v1/")
        if count:
            offenders[str(path.relative_to(REPO))] = count
    assert offenders == {}, f"/v1/ literals outside api.js: {offenders}"


def test_html_and_css_carry_no_v1_routes() -> None:
    for path in _files():
        if path.suffix in {".html", ".css"}:
            assert "/v1/" not in _read(path), f"{path.name} must not carry route literals"


def test_exactly_one_fetch_and_it_is_inside_api_js() -> None:
    total = 0
    for path in _files():
        if path.suffix != ".js":
            continue
        n = _strip_js_comments(_read(path)).count("fetch(")
        if path.name != "api.js":
            assert n == 0, f"{path.name} must not call fetch( directly"
        total += n
    assert total == 1, f"exactly one fetch( in the shell (inside api()); found {total}"


def test_event_source_only_in_api_js() -> None:
    for path in _files():
        if path.suffix == ".js" and path.name != "api.js":
            assert "EventSource(" not in _strip_js_comments(_read(path)), path.name


def test_api_js_ceiling_null_until_first_green_or_respected() -> None:
    block = _block()
    api = REPO / "ui" / "app" / "shell" / "api.js"
    count = _strip_js_comments(_read(api)).count("/v1/")
    ceiling = block["v1_count_ceiling_api_js"]
    assert count > 0, "api.js must hold the served route literals"
    if ceiling is not None:
        assert count <= int(ceiling), f"api.js /v1/ drift: {count} > {ceiling}"


# --- 3. prohibited markers ----------------------------------------------------------------


@pytest.mark.parametrize("marker", FRAMEWORK_MARKERS)
def test_no_framework_or_cdn_markers(marker: str) -> None:
    for path in _files():
        text = _read(path).lower()
        assert marker not in text, f"{path.name}: framework/CDN marker {marker!r} (ADR-0013 C)"


def test_localstorage_word_never_appears() -> None:
    for path in _files():
        assert "localStorage" not in _read(path), f"{path.name}: never persist beyond the tab"


@pytest.mark.parametrize("word", FABRICATED_STATES)
def test_no_fabricated_runtime_states(word: str) -> None:
    for path in _files():
        code = _strip_js_comments(_read(path)) if path.suffix == ".js" else _read(path)
        hits = re.findall(rf"[\"'>]\s*{word}\b", code, flags=re.I)
        assert hits == [], f"{path.name}: fabricated state {word!r}"


def test_csrf_header_sent_by_the_single_transport() -> None:
    api = _strip_js_comments(_read(REPO / "ui" / "app" / "shell" / "api.js"))
    assert "X-Requested-With" in api and "QEVION" in api


# --- 4. capability-derivation invariant (OD-1 = B) ----------------------------------------


def test_no_literal_capability_ids_anywhere_in_the_shell() -> None:
    for path in _files():
        if path.suffix != ".js":
            continue
        hits = CAPABILITY_ID_PATTERN.findall(_strip_js_comments(_read(path)))
        assert hits == [], f"{path.name}: capability ids hardcoded: {hits}"


def test_no_capability_state_roster_or_segment_surface_map() -> None:
    banned = ("SURFACE_BY_SEGMENT", "ADMIN_SURFACE_BY_AREA", "STATUS_CLASSES", "CAPABILITY_STATES")
    for path in _files():
        if path.suffix != ".js":
            continue
        code = _strip_js_comments(_read(path))
        for name in banned:
            assert name not in code, f"{path.name}: client roster {name}"
        # no roster of the closed CapabilityState values
        assert not re.search(r"\[\s*[\"']available[\"']\s*,\s*[\"']inert[\"']", code), (
            f"{path.name}: CapabilityState roster"
        )


def test_no_evidence_prose_parsing_for_routing() -> None:
    for path in _files():
        if path.suffix != ".js":
            continue
        code = _strip_js_comments(_read(path))
        assert not re.search(r"evidence\s*\.\s*(match|split|indexOf|includes)\s*\(", code), (
            f"{path.name}: routing derived from evidence prose"
        )


def test_admin_topology_rendered_from_served_records_only() -> None:
    """The topology renderer iterates the served ``capabilities`` array and prints
    ``id``/``state``/``evidence`` from each record — nothing else feeds it."""
    command = _strip_js_comments(_read(REPO / "ui" / "app" / "shell" / "pages" / "command.js"))
    assert "capabilities" in command and ".state" in command and ".evidence" in command
    # non-admin Command renders NO topology (OD-1 = B): the renderer is gated on the
    # session's admin fact — either directly or through the ONE context helper
    # `isAdmin()` (context.js), which itself reads `session.is_admin`.
    assert "isAdmin()" in command or "is_admin" in command
    context = _strip_js_comments(_read(REPO / "ui" / "app" / "shell" / "context.js"))
    assert "is_admin === true" in context
