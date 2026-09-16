"""R186 — guard frame + browser proof for the two recorded Command Center findings.

Declared BEFORE code in ``green_manifest.json`` ``change_budget.round_r186.ceiling_history``
and ``R186_HANDOFF.md`` §1-§3 (R186-DEC-01). This module is the round's first RED test.

Authority (nothing here is invented): ``evidence/r185_findings_ledger.md`` rows
F-R185-L01 / F-R185-L02 and their root-cause notes under
``evidence/r185/live_preview_e2e/``.

Static part (reads ui/app/command/* as text):

* **L01** — every element that renders SERVED text as one token (the stream frame
  ``.frame``, the error boxes ``.error``, ``.turn-fields dd``, ``.evidence``,
  ``.detail-id``) declares a wrapping rule (``overflow-wrap: anywhere`` or
  ``word-break: break-all|break-word``). The live defect: ``.frame`` had none, the
  ``error`` frame JSON has no break opportunity → 513 px overflow at 390 px.
* **L02** — ``command.js`` never stringifies a field of a possibly-null
  ``verification`` (the ``String(v.<field>)`` pattern is absent) and names the
  not-available case citing ``stop_reason`` (``AgentAnswer.verification`` is
  ``JsonObject | None`` — apps/admin_agent/contracts.py:118-122 — None only on
  reasoning_failed / invalid_proposal). The contract is frozen; the UI must render
  the null honestly instead of the literal ``undefined``.
* the ``ui_command_static_check`` frame is untouched (files, ``/v1/`` ≤ 12).

Browser part (real ``python3 -m apps.main``, hermetic profile, Chromium) — the
ORIGINAL failure conditions are exercised, not approximated:

* (a) a REAL failed execution: ``execution_policy.strategy = "agent"`` on the echo
  adapter cannot yield a valid proposal → ``invalid_proposal`` → ExecutionStatus
  FAILED → the events stream closes with an ``error`` frame carrying a JSON payload.
  The Command Center replays that stream when the execution is selected; at 390 px
  ``scrollWidth - clientWidth`` must be 0.
* (b) a converse response with ``verification: null`` — the hermetic profile always
  proposes a final, so the ONE ``/v1/agent/converse`` response body is substituted at
  the browser network layer with the served shape (``AgentAnswer``, ``stop_reason``
  ``reasoning_failed``). This is a RENDERING proof and is recorded as such. No rendered
  field may contain the token ``undefined``.

Expected first run: RED — ``.frame`` has no wrapping rule; ``String(v.verified)`` exists.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui" / "app" / "command"
JS = UI / "command.js"
CSS = UI / "command.css"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"

ADMIN_EMAIL = "browser-admin-r186@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential

# Elements that render served text as ONE token (the R185 live defect was `.frame`).
TOKEN_RENDERING_SELECTORS = (".frame", ".error", ".turn-fields dd", ".evidence", ".detail-id")
WRAP_RULE = re.compile(r"overflow-wrap\s*:\s*anywhere|word-break\s*:\s*(break-all|break-word)")


def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _js() -> str:
    return _strip_js_comments(JS.read_text(encoding="utf-8"))


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _rules_for(selector: str, css: str) -> str:
    """Concatenated declaration blocks of every rule whose selector list contains
    ``selector`` as a whole selector (``.a, .b { … }`` counts for both)."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [s.strip() for s in m.group(1).split(",")]
        if selector in selectors:
            out.append(m.group(2))
    return "\n".join(out)


# ---------------------------------------------------------------------------------
# Static guard
# ---------------------------------------------------------------------------------


@pytest.mark.parametrize("selector", TOKEN_RENDERING_SELECTORS)
def test_l01_token_rendering_elements_declare_a_wrapping_rule(selector: str) -> None:
    css = _css()
    rules = _rules_for(selector, css)
    assert rules, f"{selector} has no rule in command.css"
    assert WRAP_RULE.search(rules), (
        f"{selector} renders served text as one token but declares no wrapping rule "
        "(F-R185-L01: the error frame JSON overflowed 513 px at 390 px)"
    )


def test_l02_no_stringified_field_of_a_nullable_verification() -> None:
    js = _js()
    assert not re.search(r"String\(\s*v\.\w+\s*\)", js), (
        "command.js stringifies a field of `verification` that the contract allows to "
        "be null (apps/admin_agent/contracts.py:118-122) — this rendered the literal "
        "`undefined` (F-R185-L02)"
    )


def test_l02_null_verification_is_named_and_cites_stop_reason() -> None:
    js = _js()
    # The rendering names the case instead of leaking `undefined`, and says why
    # (stop_reason is the served reason: reasoning_failed / invalid_proposal).
    assert re.search(r"verification\s*(===|==)\s*null|verification\s*==\s*null|!r\.verification", js), (
        "command.js does not branch on a null verification"
    )
    assert re.search(r"no verification|not verified|verification unavailable", js, re.I), (
        "command.js does not NAME the null-verification case"
    )


def test_ui_command_static_check_frame_untouched() -> None:
    block = json.loads(MANIFEST.read_text(encoding="utf-8"))["ui_command_static_check"]
    assert block["files"] == [
        "ui/app/command/command.css",
        "ui/app/command/command.js",
        "ui/app/command/index.html",
    ]
    assert int(block["v1_count_ceiling_command_js"]) == 12
    assert JS.read_text(encoding="utf-8").count("/v1/") <= 12


# ---------------------------------------------------------------------------------
# Browser proof — the original failure conditions
# ---------------------------------------------------------------------------------

try:
    import playwright as _pw  # noqa: F401
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except Exception:  # pragma: no cover - environment dependent
    _HAS_PLAYWRIGHT = False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http(
    method: str, url: str, body: dict | None = None, token: str | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    if not _HAS_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    port = _free_port()
    env = dict(os.environ)
    env.update(
        {
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "ADMIN_EMAILS": ADMIN_EMAIL,
            "LOG_LEVEL": "warning",
            "PYTHONUNBUFFERED": "1",
        }
    )
    for name in list(env):
        if name in ("DATABASE_URL", "REDIS_URL") or name.startswith(
            ("GROQ_API_KEY", "GSK_API_KEY", "GW_GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        ):
            env.pop(name, None)
    log_path = tmp_path_factory.mktemp("command-center-r186") / "server_stdout.txt"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "apps.main"],
            cwd=str(ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 30
        while time.time() < deadline:
            with contextlib.suppress(Exception):
                status, body = _http("GET", f"{base}/healthz")
                if status == 200 and body.get("status") == "alive":
                    break
            if proc.poll() is not None:
                pytest.fail(f"server exited early: see {log_path}")
            time.sleep(0.2)
        else:
            proc.kill()
            pytest.fail(f"server did not become alive: see {log_path}")
        status, body = _http(
            "POST", f"{base}/v1/auth/register", {"email": ADMIN_EMAIL, "password": PASSWORD}
        )
        assert status == 201, (status, body)
        token = None
        deadline = time.time() + 10
        while time.time() < deadline and token is None:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if '"email_verification_token_issued"' in line and ADMIN_EMAIL in line:
                    token = json.loads(line)["token"]
            time.sleep(0.1)
        assert token, "verification token not issued to the console sender"
        status, body = _http("POST", f"{base}/v1/auth/verify", {"token": token})
        assert status in (200, 204), (status, body)
        try:
            yield {"base": base, "log": log_path}
        finally:
            proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=10)
            if proc.poll() is None:
                proc.kill()


def _admin_token(base: str) -> str:
    status, login = _http(
        "POST", f"{base}/v1/auth/login", {"email": ADMIN_EMAIL, "password": PASSWORD}
    )
    assert status == 200, (status, login)
    return str(login["token"])


OVERFLOW_JS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
RECORDED_LIVE_EVENTS = (ROOT / "evidence" / "r185" / "live_preview" / "events.txt").read_text(
    encoding="utf-8"
)

# Served shape of AgentAnswer on the reasoning_failed path (contracts.py:106-126):
# verification is None ONLY when no final was ever proposed.
NULL_VERIFICATION_ANSWER = {
    "claims": [],
    "tool_calls": [],
    "reasoning_execution_ids": [],
    "note": "reasoning execution failed; nothing to report",
    "rounds": 1,
    "stop_reason": "reasoning_failed",
    "verification": None,
    "reasoning_trace": [],
}


def test_error_frame_and_null_verification_in_a_real_browser(server: dict) -> None:
    base = server["base"]
    evidence_dir = ROOT / "evidence" / "r186"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    token = _admin_token(base)

    # ---- (a) a REAL failed execution with an `error` frame carrying JSON -------------
    status, body = _http(
        "POST",
        f"{base}/v1/execute",
        {"ask": "r186 error-frame proof", "execution_policy": {"strategy": "agent"}},
        token=token,
    )
    assert status == 502, (status, body)
    assert body["error"]["code"] == "execution_failed", body
    failed_id = body["error"]["details"]["execution_id"]
    status, record = _http("GET", f"{base}/v1/executions/{failed_id}", token=token)
    assert status == 200 and record["status"] == "failed", record

    console_errors: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as exc:
            pytest.fail(
                "chromium not launchable for playwright — run `python -m playwright install "
                "chromium`; first line: " + str(exc).splitlines()[0]
            )
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        page.goto(f"{base}/app/command/", wait_until="load")
        page.fill("#login-email", ADMIN_EMAIL)
        page.fill("#login-password", PASSWORD)
        page.click("#login-form button[type=submit]")
        page.wait_for_selector("#center-view:not([hidden])", timeout=15000)
        page.wait_for_function(
            "() => document.querySelectorAll('#execution-orbit .exec-dot').length > 0",
            timeout=15000,
        )
        overflow_before = page.evaluate(OVERFLOW_JS)

        # Select the failed execution from the orbit → the events stream is replayed.
        dot = page.locator(f"#execution-orbit .exec-dot[data-id='{failed_id}']")
        assert dot.count() == 1, "failed execution not in the orbit"
        assert dot.get_attribute("data-state") == "failed"
        dot.focus()
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => { const l = document.querySelectorAll('#stream-log li'); "
            "return l.length > 0 && l[l.length - 1].getAttribute('data-type') === 'error'; }",
            timeout=20000,
        )
        error_frame_text = page.text_content("#stream-log li[data-type=error]") or ""
        assert error_frame_text.startswith("error {"), error_frame_text
        assert "invalid_proposal" in error_frame_text, error_frame_text
        error_frame_width = page.evaluate(
            "() => document.querySelector('#stream-log li[data-type=error]').scrollWidth"
        )
        overflow_after_error_frame = page.evaluate(OVERFLOW_JS)
        page.screenshot(path=str(evidence_dir / "error_frame_390.png"), full_page=True)

        # The hermetic invalid_proposal payload contains spaces (break opportunities), so
        # it proves the PATH but not the WIDTH condition. Replay the RECORDED live error
        # frame (evidence/r185/live_preview/events.txt — the served Groq
        # invalid_credential frame that produced the 513 px overflow) through the same
        # stream reader: the longest token is ~120 characters without a break.
        def _recorded_events(route):  # type: ignore[no-untyped-def]
            route.fulfill(status=200, content_type="text/event-stream", body=RECORDED_LIVE_EVENTS)

        page.route("**/v1/executions/*/events", _recorded_events)
        dot.focus()
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => { const l = document.querySelector('#stream-log li[data-type=error]'); "
            "return l && l.textContent.includes('organization_restricted'); }",
            timeout=20000,
        )
        page.unroute("**/v1/executions/*/events")
        live_frame_text = page.text_content("#stream-log li[data-type=error]") or ""
        live_frame_width = page.evaluate(
            "() => document.querySelector('#stream-log li[data-type=error]').scrollWidth"
        )
        overflow_after_live_frame = page.evaluate(OVERFLOW_JS)
        page.screenshot(path=str(evidence_dir / "live_error_frame_390.png"), full_page=True)

        # ---- (b) verification: null rendering (network-layer substitution) ----------
        def _null_verification(route):  # type: ignore[no-untyped-def]
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(NULL_VERIFICATION_ANSWER),
            )

        page.route("**/v1/agent/converse", _null_verification)
        page.fill("#converse-message", "r186 null-verification rendering proof")
        page.click("#converse-form button[type=submit]")
        page.wait_for_function(
            "() => document.querySelectorAll('#converse-turns .turn-response').length > 0",
            timeout=15000,
        )
        page.unroute("**/v1/agent/converse")
        fields = page.evaluate(
            "() => { const dl = document.querySelector('#converse-turns .turn-response dl');"
            " const out = {}; if (!dl) return out; const dts = dl.querySelectorAll('dt');"
            " dts.forEach(dt => { out[dt.textContent] = dt.nextElementSibling.textContent; });"
            " return out; }"
        )
        overflow_after_turn = page.evaluate(OVERFLOW_JS)
        page.screenshot(path=str(evidence_dir / "null_verification_390.png"), full_page=True)
        browser.close()

    # ---- assertions: the ORIGINAL failure conditions -----------------------------------
    assert overflow_before == 0, overflow_before
    undefined_fields = {k: v for k, v in fields.items() if "undefined" in v}
    problems = []
    if overflow_after_error_frame != 0 or overflow_after_live_frame != 0:
        problems.append(
            f"F-R185-L01 still present: {overflow_after_error_frame}px overflow at 390px after "
            f"the real invalid_proposal frame (scrollWidth {error_frame_width}px); "
            f"{overflow_after_live_frame}px after the recorded live invalid_credential frame "
            f"(scrollWidth {live_frame_width}px)"
        )
    if undefined_fields:
        problems.append(f"F-R185-L02 still present: {undefined_fields}")
    assert not problems, "; ".join(problems)
    assert overflow_after_turn == 0, overflow_after_turn
    assert fields, "no response turn fields rendered"
    assert fields.get("stop_reason") == "reasoning_failed", fields
    verification_values = {k: v for k, v in fields.items() if k.startswith("verification")}
    assert verification_values, fields
    assert any("reasoning_failed" in v for v in verification_values.values()), (
        "the null-verification rendering does not cite stop_reason",
        verification_values,
    )
    assert console_errors == [], console_errors

    (evidence_dir / "browser_proof_r186.json").write_text(
        json.dumps(
            {
                "failed_execution_id": failed_id,
                "failed_execution_status": record["status"],
                "error_frame_text": error_frame_text[:300],
                "error_frame_scroll_width_px": error_frame_width,
                "recorded_live_error_frame_text": live_frame_text[:300],
                "recorded_live_error_frame_scroll_width_px": live_frame_width,
                "recorded_live_error_frame_source": (
                    "evidence/r185/live_preview/events.txt replayed through the events route "
                    "(network-layer substitution) — the hermetic invalid_proposal payload has "
                    "break opportunities and does not reach the width condition"
                ),
                "overflow_px": {
                    "before": overflow_before,
                    "after_real_invalid_proposal_frame": overflow_after_error_frame,
                    "after_recorded_live_invalid_credential_frame": overflow_after_live_frame,
                    "after_null_verification_turn": overflow_after_turn,
                },
                "null_verification_fields": fields,
                "null_verification_source": (
                    "network-layer substitution of ONE /v1/agent/converse response with the "
                    "served AgentAnswer shape (verification: null, stop_reason reasoning_failed) — "
                    "RENDERING proof; the hermetic echo profile always proposes a final"
                ),
                "console_errors": console_errors,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
