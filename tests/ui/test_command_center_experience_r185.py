"""R185 (D-R184-2) — static guard frame of the Command Center EXPERIENCE.

Reads ui/app/command/* as text.

Declared BEFORE code in ``green_manifest.json`` ``change_budget.round_r185.ceiling_history``
and ``R185_HANDOFF.md`` §1-§4 (R185-DEC-01). This module is the round's first RED test.

What it pins (every rule is a derivation from an existing record, cited inline):

* ``evaluation_status`` (R184, Q7 (a)) is rendered from ``GET /v1/admin/usage`` rows,
  through a closed ``EVALUATION_STATUSES`` map = ``EvaluationStatus`` values + a LOUD
  ``UNKNOWN`` (R182 posture for every closed set), joined by ``execution_id`` (a key,
  not an FK — R182_READINESS §4 row 18), never defaulted;
* the execution orbit is drawn from ``GET /v1/executions`` rows (R182_READINESS row 1);
* NO timer-driven or random "alive" theater: ``setTimeout`` / ``setInterval`` /
  ``Math.random`` are absent (APEX ApexHeroOrb 8 s cycle and ReasoningWeb random
  spawns are DISCARDED — R182_READINESS §5); motion is CSS-only and bound to
  ``data-state`` attributes derived from served fields;
* every animated class collapses under ``prefers-reduced-motion`` (READINESS row 29/34);
* the Core is a keyboard-operable ``role="button"`` that opens a ``role="dialog"``
  (APEX ApexWorld focus-return pattern REUSED-CONCEPTUALLY, READINESS row 34);
  it never mutates runtime state (READINESS row 2 → DISCARD "energize");
* graph nodes are keyboard-reachable (``tabindex="0"`` + Enter/Space handling);
* fabricated states stay absent (R182_HANDOFF §9) — including the new surfaces;
* the ``ui_command_static_check`` frame is untouched (files, ``/v1/`` ≤ 12).

Expected first run: RED — the maps / attributes / hooks do not exist yet.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.contracts.evaluation import EvaluationStatus
from core.contracts.execute import ExecutionStatus

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "app" / "command"
JS = UI / "command.js"
HTML = UI / "index.html"
CSS = UI / "command.css"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"

#: R182_HANDOFF §9 + tests/ui/test_command_center_execution_r182.py FORBIDDEN_STREAM_WORDS.
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


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _js() -> str:
    return _strip_js_comments(JS.read_text(encoding="utf-8"))


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


def _frozen_map_keys(js: str, const_name: str) -> set[str]:
    match = re.search(rf"const {const_name} = Object\.freeze\(\{{(.*?)\}}\);", js, re.S)
    assert match is not None, f"{const_name} map absent from command.js"
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.M))


# ------------------------------------------------------------ evaluation_status (R184)


def test_evaluation_status_vocabulary_is_the_r184_contract_plus_loud_unknown() -> None:
    js = _js()
    keys = _frozen_map_keys(js, "EVALUATION_STATUSES")
    contract = {s.value for s in EvaluationStatus}
    assert keys >= contract, f"a served evaluation_status has no rendering: {contract - keys}"
    assert keys <= contract | {"UNKNOWN"}, f"invented evaluation status: {keys - contract}"
    assert "UNKNOWN" in keys, "no loud UNKNOWN fallback for evaluation_status"


def test_evaluation_status_is_read_from_admin_usage_rows_joined_by_execution_id() -> None:
    js = _js()
    assert re.search(r"api\(\s*[\"'`]/v1/admin/usage[\"'`]", js), "usage route literal absent"
    assert re.search(r"\.evaluation_status\b", js), "evaluation_status never read from the row"
    assert re.search(r"\.usage\b", js), "usage[] never read"
    # Join key is execution_id; never a positional zip of two lists.
    assert re.search(r"row\.execution_id|\.execution_id\b", js)
    # Absence is its own state ("no usage row"), never a default to NEVER_EVALUATED.
    assert "no usage row" in js, "missing-row case is not rendered as its own state"
    assert re.search(r"(\|\||\?\?)\s*[\"'`]NEVER_EVALUATED[\"'`]", js) is None, (
        "evaluation_status defaulted to NEVER_EVALUATED when the row is absent"
    )


def test_evaluation_status_surface_exists_in_the_shell() -> None:
    html = _html()
    assert "data-evaluation-status" in html or 'id="execution-evaluation"' in html, (
        "no evaluation_status surface in index.html"
    )


# ------------------------------------------------------------ execution orbit


def test_execution_orbit_is_drawn_from_served_executions() -> None:
    js = _js()
    html = _html()
    assert 'id="execution-orbit"' in html, "execution orbit group absent from the SVG"
    assert re.search(r"\.executions\b", js), "executions[] never read"
    # One dot per row; its class is the closed ExecutionStatus vocabulary (+UNKNOWN).
    assert re.search(r"exec-dot", js), "no execution dot rendering"
    exec_keys = _frozen_map_keys(js, "EXECUTION_STATES")
    assert exec_keys == {s.value for s in ExecutionStatus} | {"UNKNOWN"}


# ------------------------------------------------------------ no theater


def test_no_timer_or_random_driven_aliveness() -> None:
    js = _js()
    for banned in (r"\bsetInterval\(", r"\bsetTimeout\(", r"Math\.random"):
        assert re.search(banned, js) is None, f"timer/random-driven theater: {banned}"
    assert "requestAnimationFrame" not in js, "JS animation loop — motion must be CSS-only"


@pytest.mark.parametrize("word", FORBIDDEN_STATES)
def test_no_fabricated_state_vocabulary_anywhere(word: str) -> None:
    js = _js()
    assert re.search(rf"[\"'`.\-]{word}\b", js, flags=re.I) is None, f"in command.js: {word}"
    assert re.search(rf"\b{word}\b", _html(), flags=re.I) is None, f"in index.html: {word}"
    assert re.search(rf"\b{word}\b", _css(), flags=re.I) is None, f"in command.css: {word}"


def test_core_vocabulary_unchanged() -> None:
    """R182_HANDOFF §8 closed Core set — R185 adds motion, never states."""
    assert _frozen_map_keys(_js(), "CORE_STATES") == {
        "idle",
        "running",
        "waiting_approval",
        "failed",
        "unreachable",
    }


def test_pending_indicator_is_labelled_as_transport_state_not_runtime_state() -> None:
    js = _js()
    html = _html()
    assert "aria-busy" in js, "no aria-busy request-pending indicator"
    assert re.search(r"is-pending", js), "no is-pending class toggled around api()"
    # It must never be written into the Core's data-state (a runtime derivation).
    assert re.search(r"data-state[\"'],\s*[\"'`]pending", js) is None
    assert 'id="transport-indicator"' in html
    assert re.search(r"request (in flight|pending)", html, flags=re.I), (
        "the pending indicator must say what it is: a request, not the Core"
    )


# ------------------------------------------------------------ motion + reduced motion


def test_every_animated_class_collapses_under_reduced_motion() -> None:
    css = _css()
    animated = set(
        re.findall(r"^\s*([.#][\w\-\.\[\]=\"' >:()]+?)\s*\{[^}]*\banimation:", css, re.M)
    )
    assert animated, "no CSS animation declared — the experience needs ambient motion"
    reduced_blocks = re.findall(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", css, flags=re.S
    )
    assert reduced_blocks, "no prefers-reduced-motion block"
    reduced = "\n".join(reduced_blocks)
    # Universal collapse: every animation and transition is neutralised, not a subset.
    assert re.search(r"\*[^{]*\{[^}]*animation:\s*none\s*!important", reduced) or re.search(
        r"\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation", reduced
    ), "reduced-motion block must neutralise animation for every element (`*`)"
    assert "transition" in reduced, "transitions must collapse too"


def test_motion_is_bound_to_served_state_attributes() -> None:
    css = _css()
    # Core ring speed follows the Core's data-state (a derivation of ExecutionStatus).
    assert re.search(r"\.core-running[^{]*\{[^}]*animation-duration", css) or re.search(
        r"\[data-state=\"running\"\][^{]*\{[^}]*animation", css
    ), "running state has no motion binding"
    assert re.search(
        r"\.core-unreachable[^{]*\{[^}]*animation(-play-state)?:\s*(none|paused)", css
    ), "unreachable Core must not animate as alive"
    # Layered rings + orbit dots exist (APEX pattern REBUILT).
    for cls in ("core-ring-cw", "core-ring-ccw", "orbit-dot"):
        assert cls in css, f"missing layered motion element: {cls}"
    # Node pulse binds to the live class set only on node_started (execution stage).
    assert re.search(r"\.exec-stage\.live[^{]*\{[^}]*animation", css)


# ------------------------------------------------------------ keyboard / dialogs


def test_core_is_a_keyboard_button_opening_a_dialog_and_never_mutates_runtime() -> None:
    html = _html()
    js = _js()
    core = re.search(r"<g id=\"core\"[^>]*>", html)
    assert core is not None
    assert 'role="button"' in core.group(0), "Core must be role=button"
    assert 'tabindex="0"' in core.group(0), "Core must be focusable"
    assert "aria-label" in core.group(0)
    assert re.search(r'<[^>]+id="overview-dialog"[^>]*role="dialog"', html), (
        "system overview dialog absent"
    )
    assert re.search(r"aria-modal=\"true\"", html)
    # Enter / Space open; Escape closes; focus returns to the opener.
    assert re.search(r"key === [\"']Enter[\"']", js) and re.search(r"key === [\"'] [\"']", js)
    assert re.search(r"key === [\"']Escape[\"']", js)
    assert re.search(r"\.focus\(\)", js), "no focus management"
    # The Core click handler must not POST anything (no 'energize').
    core_handler = re.search(r"function openOverview\([^)]*\)\s*\{(.*?)\n\}", js, re.S)
    assert core_handler is not None, "openOverview() absent"
    assert "method" not in core_handler.group(1), "Core tap performs a write — forbidden"


def test_graph_nodes_are_keyboard_reachable() -> None:
    js = _js()
    assert re.search(r"tabindex:\s*[\"']0[\"']", js), "SVG nodes are not focusable (tabindex 0)"
    assert re.search(r"role:\s*[\"']button[\"']", js), "SVG nodes lack role=button"
    assert re.search(r"[\"']aria-label[\"']", js), "SVG nodes lack aria-label"
    assert re.search(r"addEventListener\(\s*[\"']keydown[\"']", js), "no keydown handling"


def test_node_detail_is_a_dialog_with_close_control() -> None:
    html = _html()
    detail = re.search(r"<[^>]+id=\"node-detail\"[^>]*>", html)
    assert detail is not None
    assert 'role="dialog"' in detail.group(0)
    assert re.search(r'id="detail-close"', html), "no close control on the detail dialog"


# ------------------------------------------------------------ responsive


def test_responsive_breakpoints_declared() -> None:
    css = _css()
    breakpoints = re.findall(r"@media \(max-width:\s*(\d+)px\)", css)
    assert len(set(breakpoints)) >= 2, f"need ≥2 breakpoints, found {breakpoints}"
    assert 'name="viewport"' in _html()


# ------------------------------------------------------------ frame untouched


def test_ui_command_static_check_frame_untouched() -> None:
    block = json.loads(MANIFEST.read_text(encoding="utf-8"))["ui_command_static_check"]
    assert block["files"] == [
        "ui/app/command/command.css",
        "ui/app/command/command.js",
        "ui/app/command/index.html",
    ]
    assert int(block["v1_count_ceiling_command_js"]) == 12
    assert int(block["exception_count_ceiling"]) == 0
    assert JS.read_text(encoding="utf-8").count("/v1/") <= 12
