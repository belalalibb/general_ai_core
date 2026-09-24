"""R199 — Unified Shell Foundation (UI-only, layer A; R199-DEC-01, operator D1-D5).

Static guard frame over the three served UI trees, read as text. Declared BEFORE
the first UI edit; fails closed on the opening tree (evidence/r199/red.txt).

Pins (operator rulings in brackets):
- [D3] one brand string per surface: ``QEVION · Workbench`` (ui/app), ``QEVION · Command``
  (ui/app/command), ``QEVION · Admin`` (ui/admin) — in <title> and the sign-in <h1>.
- [R199-B] command.css uses the shared token set (--accent / --accent-2 / --unknown /
  --bg-0 ...) and no longer carries the divergent hex values.
- [R199-C] each tree links to the other two served mounts with plain <a href>; no href
  carries /v1/ (inherited rule); admin-only destinations are labelled.
- [D4] /app Models renders ``providers`` from the served GET /v1/models row and a
  truth strip computed from that same response only — no second read, no provider
  branching, no invented vocabulary.
- [D1 = A] Command keeps its admin-only gate; command.js is byte-identical to main
  (12 = /v1/ count) and ui/admin/app.js too (73 = N0).
- ceiling 0: round_r199 declared and unspent.
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

BRAND = {
    "workbench": "QEVION · Workbench",
    "command": "QEVION · Command",
    "admin": "QEVION · Admin",
}
TREES = [
    ("workbench", APP / "index.html"),
    ("command", COMMAND / "index.html"),
    ("admin", ADMIN / "index.html"),
]
DIVERGENT_HEX = ("#7dd3fc", "#38bdf8")
SHARED_TOKENS = (
    "--accent:",
    "--accent-2:",
    "--unknown:",
    "--bg-0:",
    "--ink:",
    "--ok:",
    "--warn:",
    "--err:",
)
PROVIDER_WORDS = ("groq", "gsk", "openai", "anthropic", "genspark")
FABRICATED_STATES = ("thinking", "speaking", "listening", "energized", "processing", "reasoning")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


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


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, flags=re.S)
    assert m, "no <title>"
    return m.group(1).strip()


def _hrefs(html: str) -> list[str]:
    return re.findall(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", html)


# ------------------------------------------------------------------ D3 brand


@pytest.mark.parametrize(("tree", "html_path"), TREES)
def test_title_is_the_ruled_brand_string(tree: str, html_path: Path) -> None:
    assert _title(_read(html_path)) == BRAND[tree]


@pytest.mark.parametrize(("tree", "html_path"), TREES)
def test_sign_in_heading_carries_the_brand_string(tree: str, html_path: Path) -> None:
    html = _read(html_path)
    h1s = re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, flags=re.S)
    flat = [re.sub(r"<[^>]+>", "", h).strip() for h in h1s]
    assert any(BRAND[tree] in h for h in flat), flat


def test_legacy_brand_strings_left_the_titles() -> None:
    for _tree, path in TREES:
        title = _title(_read(path))
        assert "Control Plane" not in title, (path.name, title)
        assert "Command Center" not in title, (path.name, title)
        assert "Admin Console" not in title, (path.name, title)


# ------------------------------------------------------------ R199-B tokens


def test_command_css_uses_the_shared_token_set() -> None:
    css = _read(COMMAND / "command.css")
    for token in SHARED_TOKENS:
        assert token in css, f"command.css lacks shared token {token}"


def test_command_css_dropped_the_divergent_hex_values() -> None:
    css = _read(COMMAND / "command.css").lower()
    for hexval in DIVERGENT_HEX:
        assert hexval not in css, f"divergent brand hex still in command.css: {hexval}"


def test_shared_root_tokens_identical_between_app_and_admin() -> None:
    def root_block(css: str) -> str:
        m = re.search(r":root\s*\{.*?\}", css, flags=re.S)
        assert m
        return re.sub(r"/\*.*?\*/", "", m.group(0), flags=re.S)

    app = root_block(_read(APP / "styles.css"))
    admin = root_block(_read(ADMIN / "styles.css"))
    command = re.sub(r"\s+", " ", root_block(_read(COMMAND / "command.css")))
    assert re.sub(r"\s+", "", app) == re.sub(r"\s+", "", admin)
    for token in ("--accent: #4fd6ff", "--accent-2: #8b7bff", "--unknown: #ff45e0"):
        assert token in command, token


# --------------------------------------------------------- R199-C cross-links


@pytest.mark.parametrize(
    ("html_path", "expected_others"),
    [
        (APP / "index.html", ("/app/command/", "/admin/")),
        (COMMAND / "index.html", ("/app/", "/admin/")),
        (ADMIN / "index.html", ("/app/", "/app/command/")),
    ],
)
def test_each_tree_links_to_the_other_two_mounts(
    html_path: Path, expected_others: tuple[str, ...]
) -> None:
    hrefs = set(_hrefs(_read(html_path)))
    for other in expected_others:
        assert other in hrefs, f"{html_path.relative_to(ROOT)} lacks a link to {other}: {hrefs}"


def test_no_href_carries_a_v1_route() -> None:
    for _tree, path in TREES:
        for href in _hrefs(_read(path)):
            assert "/v1/" not in href, (path.name, href)


def test_admin_only_destinations_are_labelled_where_linked() -> None:
    """Links to /admin/ and /app/command/ from the Workbench name the admin requirement."""
    html = _read(APP / "index.html")
    for target in ("/admin/", "/app/command/"):
        pattern = rf"<a\b[^>]*href=[\"']{re.escape(target)}[\"'][^>]*>(.*?)</a>"
        m = re.search(pattern, html, flags=re.S)
        assert m, target
        anchor_tag = html[m.start() : m.end()]
        assert re.search(r"admin", anchor_tag, flags=re.I), f"{target} lacks an admin label"


# ------------------------------------------------------- D4 provider truth


def test_workbench_renders_served_providers_in_refresh_models() -> None:
    body = _function_body(_strip_js_comments(_read(APP / "app.js")), "refreshModels")
    assert "model.providers" in body, "refreshModels does not read the served providers[]"


def test_truth_strip_element_exists_and_is_filled_from_the_models_response() -> None:
    html = _read(APP / "index.html")
    assert 'id="models-truth"' in html
    js = _strip_js_comments(_read(APP / "app.js"))
    body = _function_body(js, "refreshModels")
    assert "models-truth" in body
    # one read only: the strip is derived from result.body.models inside refreshModels
    assert body.count('api("/v1/models")') == 1


def test_truth_strip_has_no_invented_vocabulary() -> None:
    js = _strip_js_comments(_read(APP / "app.js"))
    body = _function_body(js, "refreshModels").lower()
    for word in PROVIDER_WORDS:
        assert word not in body, f"provider branching in refreshModels: {word}"
    for word in ("real model", "live model", "production", "mock", "fake", "simulated"):
        assert word not in body, f"invented truth vocabulary: {word}"
    for state in FABRICATED_STATES:
        assert not re.search(rf"[\"'`]{state}[\"'`]", body), state


def test_workbench_static_guard_unchanged_22_4() -> None:
    js = _read(APP / "app.js")
    # R199 added no literal (22); R202-DEC-01 declared 23; COMPLETION-V2-DEC declared 32 / 6
    # (nine served literals + two raw sites — lineage in the manifest rules) — flipped 1:1
    assert js.count("/v1/") == 32, "ui/app/app.js /v1/ count moved beyond the declared ceiling"
    assert js.count("fetch(") == 6, "ui/app/app.js fetch( count moved beyond the declared ceiling"


# -------------------------------------------------- D1 = A frozen js trees


def test_command_js_and_admin_js_frozen_by_count() -> None:
    assert _read(COMMAND / "command.js").count("/v1/") == 12
    assert _read(ADMIN / "app.js").count("/v1/") == 73


def test_command_sign_in_names_the_admin_requirement_and_links_the_workbench() -> None:
    html = _read(COMMAND / "index.html")
    login = re.search(r'<section id="login-view".*?</section>', html, flags=re.S)
    assert login
    assert re.search(r"admin", login.group(0), flags=re.I)
    assert 'href="/app/"' in login.group(0), "Command sign-in lacks the Workbench link"


# ---------------------------------------------------------------- manifest


def test_round_r199_declared_ceiling_zero_and_unspent() -> None:
    manifest = json.loads(_read(MANIFEST))
    block = manifest["change_budget"]["round_r199"]
    assert int(block["ceiling"]) == 0
    assert int(block["changes_used"]) == 0
    assert block["log"] == []
