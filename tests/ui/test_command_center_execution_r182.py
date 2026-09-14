"""R182-IMPL M2 — first red test (declared in the M1 closing report, verbatim):

    tests/ui/test_command_center_execution_r182.py::
        test_stream_renders_only_the_five_emitted_event_types_never_delta

Scope of M2 = R182_HANDOFF §7 rows 8-11 only: execution graph (trace), live
progress (fetch-read SSE), runtime indicators, conversation. Same tree
(`ui/app/command/`), same guard frame (`ui_command_static_check`), same
`round_r182` budget 0/0 — zero production change.

Invariants proven here (text-level, ui/admin posture; browser proof extends
the M1 module):

  * the stream reader is a fetch-body reader on GET /v1/executions/{id}/events
    inside the single `api()` transport — NO `EventSource(`, NO `WebSocket(`;
  * the event vocabulary the UI can render is EXACTLY the five emitted types
    (`apps/api/streaming.py` `SseEvent`): execution_started, node_started,
    node_completed, final, error — `delta` is NEVER rendered, and there is no
    typing/partial-text/streaming-transcript code path (`execute.token_streaming`
    is `unavailable`; a `delta` frame is fabricated state);
  * stage node states ⊆ ExecutionNodeStatus ∪ {UNKNOWN}; execution states ⊆
    ExecutionStatus; progress comes from `progress.current_stage` /
    `progress.percent` only;
  * conversation renders `verification` as COUNTS and request/response turns —
    no streaming transcript; `as_recorded` is displayed, never assumed;
  * every new route literal is served by the app (OpenAPI) — the static-check
    module enforces this for the whole file; here the four M2 routes are pinned.

Expected first run: RED — the M2 sections do not exist in command.js yet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionNodeStatus

ROOT = Path(__file__).resolve().parents[2]
COMMAND_JS = ROOT / "ui" / "app" / "command" / "command.js"
COMMAND_HTML = ROOT / "ui" / "app" / "command" / "index.html"

#: apps/api/streaming.py `SseEvent` — the five types that ride the wire.
EMITTED_EVENT_TYPES = frozenset(
    {"execution_started", "node_started", "node_completed", "final", "error"}
)
#: Contract type that exists but is never emitted (R182_READINESS row 9).
NEVER_EMITTED = "delta"

FORBIDDEN_STREAM_WORDS = (
    "typing",
    "typewriter",
    "partial_text",
    "partialText",
    "transcript",
    "waveform",
    "equalizer",
    "speaking",
    "listening",
    "thinking",
)


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _js() -> str:
    return _strip_js_comments(COMMAND_JS.read_text(encoding="utf-8"))


def _frozen_map_keys(js: str, const_name: str) -> set[str]:
    match = re.search(rf"const {const_name} = Object\.freeze\(\{{(.*?)\}}\);", js, re.S)
    assert match is not None, f"{const_name} map absent from command.js"
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.M))


def test_stream_renders_only_the_five_emitted_event_types_never_delta() -> None:
    js = _js()

    # 1. The closed event vocabulary is declared as a frozen map and equals SseEvent.
    keys = _frozen_map_keys(js, "STREAM_EVENTS")
    assert keys == EMITTED_EVENT_TYPES, keys ^ EMITTED_EVENT_TYPES
    assert NEVER_EMITTED not in keys

    # 2. `delta` is never rendered and never special-cased anywhere in the source.
    assert re.search(r"[\"'`]delta[\"'`]", js) is None, "delta frame handled — never emitted"
    assert re.search(r"\.content\b", js) is None or "delta" not in js, "partial content path"

    # 3. Unknown frame types are refused LOUDLY (never silently ignored, never invented).
    assert re.search(r"STREAM_EVENTS\[|in STREAM_EVENTS|hasOwnProperty\.call\(STREAM_EVENTS", js), (
        "frame type must be looked up in STREAM_EVENTS"
    )
    assert re.search(r"unknown[_ ]event|UNKNOWN_EVENT|unknownFrame", js), (
        "no loud unknown-frame rendering"
    )

    # 4. The reader is a fetch-body stream through api() — single transport.
    assert len(re.findall(r"\bfetch\(", js)) == 1, "second fetch( — transport policy"
    for banned in ("EventSource(", "WebSocket(", "XMLHttpRequest", "axios"):
        assert banned not in js, banned
    assert re.search(r"api\(\s*[\"'`]/v1/executions/\$\{[^}]+\}/events[\"'`]", js), (
        "SSE route not read through api()"
    )
    assert re.search(r"getReader\(\)|\.body\b", js), "no fetch-body reader (stream=true path)"
    assert re.search(r"data:\s*", js) or "data: " in js, "SSE `data:` frame parser absent"

    # 5. No fabricated streaming affordances.
    for word in FORBIDDEN_STREAM_WORDS:
        assert re.search(rf"[\"'`.\-]{word}\b", js, flags=re.I) is None, (
            f"fabricated stream affordance in command.js: {word}"
        )
    html = COMMAND_HTML.read_text(encoding="utf-8")
    for word in FORBIDDEN_STREAM_WORDS:
        assert re.search(rf"\b{word}\b", html, flags=re.I) is None, f"in HTML: {word}"


def test_execution_graph_vocabulary_is_the_served_contract() -> None:
    js = _js()
    # Stage node vocabulary = ExecutionNodeStatus + loud UNKNOWN.
    stage_keys = _frozen_map_keys(js, "STAGE_STATES")
    allowed = {s.value for s in ExecutionNodeStatus} | {"UNKNOWN"}
    assert stage_keys <= allowed, stage_keys - allowed
    assert stage_keys >= {s.value for s in ExecutionNodeStatus}, "a stage status has no rendering"
    assert "UNKNOWN" in stage_keys
    # Execution vocabulary = ExecutionStatus + loud UNKNOWN.
    exec_keys = _frozen_map_keys(js, "EXECUTION_STATES")
    allowed_exec = {s.value for s in ExecutionStatus} | {"UNKNOWN"}
    assert exec_keys <= allowed_exec, exec_keys - allowed_exec
    assert exec_keys >= {s.value for s in ExecutionStatus}
    # Graph = trace.stages in order, keyed by node_key; attempts rendered from the record.
    assert re.search(r"\.stages\b", js), "trace.stages never read"
    assert re.search(r"\.node_key\b", js), "stage id not taken from node_key"
    assert re.search(r"\.attempts\b", js), "attempts not rendered from the record"
    assert re.search(r"\.as_recorded\b", js), "as_recorded not displayed"
    # Progress from the served fields only.
    assert re.search(r"progress\.current_stage\b", js) and re.search(r"progress\.percent\b", js)
    # No invented percent (no Math.random, no timers advancing a bar).
    assert "Math.random" not in js
    assert re.search(r"\bsetInterval\(", js) is None


def test_conversation_renders_counts_not_a_transcript() -> None:
    js = _js()
    assert re.search(r"api\(\s*[\"'`]/v1/agent/converse[\"'`]", js), "converse route absent"
    assert re.search(r"api\(\s*[\"'`]/v1/execute[\"'`]", js), "execute route absent"
    assert re.search(r"api\(\s*[\"'`]/v1/agent/executions/\$\{[^}]+\}/trace[\"'`]", js), (
        "trace route absent"
    )
    assert re.search(r"api\(\s*[\"'`]/v1/executions/\$\{[^}]+\}[\"'`]", js), (
        "GET /v1/executions/{id} absent"
    )
    # verification rendered as the five served counters, no derived score/percentage.
    for field in (
        "verification.verified",
        "verification.claims_admitted",
        "verification.claims_refused",
        "verification.tool_calls_ok",
        "verification.tool_calls_total",
    ):
        assert field in js, f"{field} not rendered"
    assert re.search(r"\.stop_reason\b", js) and re.search(r"\.rounds\b", js)
    assert re.search(r"\.reasoning_execution_ids\b", js)
    # Response body rendered as text content, never as HTML.
    assert re.search(r"\.innerHTML\s*=\s*[^`\"']*(content|message|result)", js) is None, (
        "server text injected as HTML"
    )


@pytest.mark.parametrize(
    "element_id",
    ["execution-graph", "execution-progress", "stream-log", "converse-form", "converse-turns"],
)
def test_m2_surfaces_exist_in_the_shell(element_id: str) -> None:
    html = COMMAND_HTML.read_text(encoding="utf-8")
    assert f'id="{element_id}"' in html, f"M2 surface #{element_id} missing from index.html"
