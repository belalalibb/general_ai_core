"""R185 (D-R184-2) — browser proof of the Command Center EXPERIENCE against the REAL server.

Same posture as tests/ui/test_command_center_browser_r182.py (R182-DEC-02 D-4): a real
Chromium drives `python3 -m apps.main` (in-memory profile, ADMIN_EMAILS); no skip path;
a missing browser FAILS with the install command. Evidence is written to
``evidence/r185/`` (browser_proof_r185.json + screenshots) — the R182 files are not
touched by this module.

What is proven (R185_HANDOFF §3):
  * after one execute turn, the execution orbit has EXACTLY one dot per row of
    GET /v1/executions, each dot's data-state equals the served status;
  * the rendered evaluation_status for the selected execution equals the served
    GET /v1/admin/usage row (R184 contract rendered truthfully, never defaulted);
  * the Core is keyboard-operable: focus + Enter opens the overview dialog whose
    fields equal GET /v1/admin/system / healthz; Escape closes it and focus returns
    to the Core; the tap performed no write (request log has no new POST);
  * a graph node is keyboard-operable (Tab/Enter) and opens the detail dialog;
  * under `prefers-reduced-motion: reduce` no CSS animation is running on the page;
    without it, the Core rings ARE animating (the experience is alive when allowed);
  * layout is responsive: at 390 px wide nothing overflows horizontally;
  * no console errors; every request is same-origin to a served route.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from core.contracts.evaluation import EvaluationStatus
from core.contracts.execute import ExecutionStatus

ROOT = Path(__file__).resolve().parents[2]


def _select_venv_local_browsers() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    import playwright as _pw

    local_store = Path(_pw.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    if local_store.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


_select_venv_local_browsers()
ADMIN_EMAIL = "browser-admin-r185@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential
CORE_STATES = {"idle", "running", "waiting_approval", "failed", "unreachable"}
EXEC_STATES = {s.value for s in ExecutionStatus} | {"UNKNOWN"}
EVAL_STATES = {s.value for s in EvaluationStatus} | {"UNKNOWN"}


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
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
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
            (
                "GROQ_API_KEY",
                "GSK_API_KEY",
                "GW_GROQ_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
        ):
            env.pop(name, None)
    log_path = tmp_path_factory.mktemp("command-center-r185") / "server_stdout.txt"
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
            "POST",
            f"{base}/v1/auth/register",
            {"email": ADMIN_EMAIL, "password": PASSWORD, "preferred_language": "en"},
        )
        assert status == 201, (status, body)
        token = None
        deadline = time.time() + 10
        while time.time() < deadline and token is None:
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if '"email_verification_token_issued"' in line:
                    token = json.loads(line[line.index("{") :])["token"]
            time.sleep(0.1)
        assert token, "verification token never appeared on the server console"
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


def _path_served(path: str, served: set[str]) -> bool:
    segs = path.rstrip("/").split("/")
    for s in served:
        ss = s.rstrip("/").split("/")
        if len(ss) != len(segs):
            continue
        if all(
            a == b or (a.startswith("{") and a.endswith("}")) for a, b in zip(ss, segs, strict=True)
        ):
            return True
    return False


RUNNING_ANIMATIONS_JS = (
    "() => document.getAnimations().filter(a => a.playState === 'running').length"
)


def test_command_center_experience_in_a_real_browser(server: dict) -> None:
    base = server["base"]
    evidence_dir = ROOT / "evidence" / "r185"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    requests: list[tuple[str, str]] = []
    status, openapi = _http("GET", f"{base}/openapi.json")
    assert status == 200
    served_paths = set(openapi["paths"])

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as exc:
            pytest.fail(
                "chromium not launchable for playwright — run `python -m playwright install "
                "chromium` (+ `sudo python -m playwright install-deps chromium`); first line: "
                + str(exc).splitlines()[0]
            )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("request", lambda r: requests.append((r.method, r.url)))

        page.goto(f"{base}/app/command/", wait_until="load")
        assert page.title() == "QEVION · Command"  # R199-A (D3)
        page.fill("#login-email", ADMIN_EMAIL)
        page.fill("#login-password", PASSWORD)
        page.click("#login-form button[type=submit]")
        page.wait_for_selector("#center-view:not([hidden])", timeout=15000)
        page.wait_for_function(
            "() => document.querySelectorAll('#topology-nodes g.node').length > 0", timeout=15000
        )
        page.wait_for_function(
            "() => document.getElementById('core').getAttribute('data-state') !== 'unreachable'",
            timeout=15000,
        )

        # ---- alive when allowed: the Core rings animate (CSS-only) --------------------
        running_before = page.evaluate(RUNNING_ANIMATIONS_JS)
        core_state_initial = page.get_attribute("#core", "data-state")

        # ---- one execute turn -> the orbit gains a dot, evaluation_status renders -----
        page.fill("#converse-message", "browser proof r185")
        page.check("input[name=converse-mode][value=execute]")
        posts_before = sum(1 for m, _ in requests if m == "POST")
        page.click("#converse-form button[type=submit]")
        page.wait_for_function(
            "() => { const l = document.querySelectorAll('#stream-log li'); "
            "return l.length > 0 && ['final','error'].includes("
            "l[l.length - 1].getAttribute('data-type')); }",
            timeout=20000,
        )
        page.wait_for_function(
            "() => document.querySelectorAll('#execution-orbit .exec-dot').length > 0",
            timeout=15000,
        )
        page.wait_for_function(
            "() => { const e = document.getElementById('execution-evaluation'); "
            "return e && e.getAttribute('data-evaluation-status'); }",
            timeout=15000,
        )
        execution_id = page.text_content("#progress-execution-id")
        dot_ids = page.eval_on_selector_all(
            "#execution-orbit .exec-dot", "els => els.map(e => e.getAttribute('data-id'))"
        )
        dot_states = page.eval_on_selector_all(
            "#execution-orbit .exec-dot", "els => els.map(e => e.getAttribute('data-state'))"
        )
        eval_attr = page.get_attribute("#execution-evaluation", "data-evaluation-status")
        eval_text = page.text_content("#execution-evaluation")
        status_evaluation = page.text_content("#status-evaluation")
        page.screenshot(path=str(evidence_dir / "command_center_r185_desktop.png"), full_page=True)

        # ---- Core: keyboard opens the overview dialog; Escape returns focus; no write --
        posts_before_core = sum(1 for m, _ in requests if m == "POST")
        page.focus("#core")
        page.keyboard.press("Enter")
        page.wait_for_selector("#overview-dialog:not([hidden])", timeout=5000)
        overview_profile = page.text_content("#overview-profile")
        overview_scope = page.text_content("#overview-scope")
        overview_health = page.text_content("#overview-health")
        focused_in_dialog = page.evaluate(
            "() => document.getElementById('overview-dialog').contains(document.activeElement)"
        )
        page.keyboard.press("Escape")
        page.wait_for_selector("#overview-dialog[hidden]", state="attached", timeout=5000)
        focus_back_on_core = page.evaluate("() => document.activeElement.id === 'core'")
        posts_after_core = sum(1 for m, _ in requests if m == "POST")
        core_state_after_tap = page.get_attribute("#core", "data-state")

        # ---- node: keyboard operable -> detail dialog; close returns focus -----------
        first_node = page.locator("#topology-nodes g.node").first
        first_node_id = first_node.get_attribute("data-id")
        first_node.focus()
        page.keyboard.press("Enter")
        page.wait_for_selector("#node-detail:not([hidden])", timeout=5000)
        detail_id = page.text_content("#detail-id")
        page.click("#detail-close")
        focus_back_on_node = page.evaluate(
            f"() => document.activeElement.getAttribute('data-id') === {json.dumps(first_node_id)}"
        )

        # ---- responsive: narrow viewport has no horizontal overflow -------------------
        page.set_viewport_size({"width": 390, "height": 844})
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        page.screenshot(path=str(evidence_dir / "command_center_r185_mobile.png"), full_page=False)
        page.set_viewport_size({"width": 1280, "height": 900})

        # ---- reduced motion: nothing animates -----------------------------------------
        page.emulate_media(reduced_motion="reduce")
        running_reduced = page.evaluate(RUNNING_ANIMATIONS_JS)
        page.emulate_media(reduced_motion="no-preference")
        browser.close()

    # ---- server truth ------------------------------------------------------------------
    token = _admin_token(base)
    status, executions = _http("GET", f"{base}/v1/executions", token=token)
    assert status == 200, (status, executions)
    status, usage = _http("GET", f"{base}/v1/admin/usage", token=token)
    assert status == 200, (status, usage)
    status, system = _http("GET", f"{base}/v1/admin/system", token=token)
    assert status == 200
    status, health = _http("GET", f"{base}/healthz")
    assert status == 200

    served_rows = {e["execution_id"]: e["status"] for e in executions["executions"]}
    assert set(dot_ids) == set(served_rows), (sorted(dot_ids), sorted(served_rows))
    assert len(dot_ids) == len(served_rows)
    for did, dst in zip(dot_ids, dot_states, strict=True):
        assert dst in EXEC_STATES and dst == served_rows[did], (did, dst, served_rows[did])

    usage_row = next(r for r in usage["usage"] if r["execution_id"] == execution_id)
    assert eval_attr in EVAL_STATES
    assert eval_attr == usage_row["evaluation_status"], (eval_attr, usage_row)
    assert usage_row["evaluation_status"] in eval_text
    assert status_evaluation is not None and eval_attr in status_evaluation

    assert overview_profile == system["profile"]
    assert overview_scope == system["scope"]
    assert overview_health == health["status"]
    assert focused_in_dialog is True
    assert focus_back_on_core is True
    assert posts_after_core == posts_before_core, "Core tap performed a write"
    assert core_state_after_tap in CORE_STATES
    assert core_state_initial in CORE_STATES

    assert detail_id == first_node_id
    assert focus_back_on_node is True

    assert overflow <= 0, f"horizontal overflow at 390px: {overflow}px"
    assert running_before > 0, "no running animation when motion is allowed"
    assert running_reduced == 0, f"{running_reduced} animations still running under reduced motion"
    assert console_errors == [], console_errors
    assert sum(1 for m, _ in requests if m == "POST") > posts_before  # the execute turn itself

    for method, url in requests:
        assert url.startswith(base), f"cross-origin request: {url}"
        path = url[len(base) :].split("?")[0]
        if path.startswith("/app/command/"):
            continue
        assert method in ("GET", "POST"), (method, path)
        assert _path_served(path, served_paths), f"request to an unserved route: {path}"

    (evidence_dir / "browser_proof_r185.json").write_text(
        json.dumps(
            {
                "server": "python3 -m apps.main (in-memory profile, ADMIN_EMAILS)",
                "page": "/app/command/",
                "served_executions": len(served_rows),
                "rendered_orbit_dots": len(dot_ids),
                "evaluation_status_rendered": eval_attr,
                "evaluation_status_served": usage_row["evaluation_status"],
                "overview": {
                    "profile": overview_profile,
                    "scope": overview_scope,
                    "health": overview_health,
                    "focus_in_dialog": focused_in_dialog,
                    "focus_returned_to_core": focus_back_on_core,
                    "writes_performed_by_core_tap": posts_after_core - posts_before_core,
                },
                "node_keyboard": {"detail_id": detail_id, "focus_returned": focus_back_on_node},
                "responsive_overflow_px_at_390": overflow,
                "running_animations_allowed": running_before,
                "running_animations_reduced_motion": running_reduced,
                "console_errors": console_errors,
                "requests": sorted({m + " " + u[len(base) :].split("?")[0] for m, u in requests}),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
