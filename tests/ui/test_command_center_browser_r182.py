"""R182-IMPL D-4 — browser proof of the Command Center against the REAL server.

Operator ruling (R182-DEC-02 D-4): Playwright is admitted as a DEV-ONLY dependency
in R182-IMPL and an actual run REPLACES NOT-EVALUATED #1 ("live-suite: browser
automation against the real server and real UI — missing dependency"). If the
environment cannot run it, the dependency is withdrawn — never left beside a
"missing dependency" line; a third NOT-EVALUATED line is refused either way.

What is proven (R182_HANDOFF §18 "browser proof"):
  * `python3 -m apps.main` (the operator entrypoint, in-memory profile, with
    ADMIN_EMAILS) serves /app/command/ — no test-only server;
  * a real Chromium loads the page as an ES module, signs in through the UI
    form, and the DOM ends up with EXACTLY one topology node per capability
    record the server returned from GET /v1/admin/capabilities (fetched
    independently by the test over HTTP);
  * every rendered node's data-state is in CapabilityState ∪ {UNKNOWN} and the
    Core text is in the closed §8 vocabulary;
  * the keyboard mirror list has the same ids as the graph;
  * no console errors, and every network request the page made is a GET/POST
    to routes the served OpenAPI exposes (single transport, no CDN, no APEX).

No skip path. NOT-EVALUATED #1 was removed because this proof runs; a skip would be
that removed line in disguise (and would push the gate's skipped count over its
ceiling anyway). A missing browser binary FAILS with the install command:
`python -m playwright install chromium` (+ `install-deps chromium` on bare hosts).
The canonical gate runs under `env -i … HOME=/tmp`, so the browser is installed INTO
the venv (`PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium`) and this
module selects that venv-local store when the variable is unset (OPERATIONS §10).
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

from apps.api.capabilities import CAPABILITY_IDS, CapabilityState

ROOT = Path(__file__).resolve().parents[2]


def _select_venv_local_browsers() -> None:
    """Hermetic browser store: `PLAYWRIGHT_BROWSERS_PATH=0` = inside the installed package.

    The gate strips the environment (`env -i`); without this, playwright would look
    under $HOME/.cache and fail even though the venv carries the browser.
    """
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    import playwright as _pw

    local_store = Path(_pw.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    if local_store.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


_select_venv_local_browsers()
ADMIN_EMAIL = "browser-admin@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential
CORE_STATES = {"idle", "running", "waiting_approval", "failed", "unreachable"}
NODE_STATES = {s.value for s in CapabilityState} | {"UNKNOWN"}


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
    """The operator entrypoint, as a real subprocess; token read from its console."""
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
    # Hermetic proof: the in-memory profile with the local_echo provider. The
    # runtime composes REAL providers when GROQ_API_KEY / GSK_API_KEY are present
    # (apps/composition/runtime.py), which is exactly what the canonical suite
    # strips with `env -u` (OPERATIONS §10) — strip the same names here so the
    # execute turn never reaches a live provider from a test.
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
    # The console log carries the one-time verification token: kept in tmp, never in evidence.
    log_path = tmp_path_factory.mktemp("command-center-server") / "server_stdout.txt"
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

        # Register the admin through the served API; the verification token is
        # printed to the process console (ConsoleEmailSender) — read it there.
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


def _served_catalog(base: str) -> dict:
    status, login = _http(
        "POST", f"{base}/v1/auth/login", {"email": ADMIN_EMAIL, "password": PASSWORD}
    )
    assert status == 200, (status, login)
    status, catalog = _http("GET", f"{base}/v1/admin/capabilities", token=login["token"])
    assert status == 200, (status, catalog)
    status, openapi = _http("GET", f"{base}/openapi.json")
    assert status == 200
    return {"catalog": catalog, "paths": set(openapi["paths"])}


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


def test_rendered_nodes_equal_served_capabilities_in_a_real_browser(server: dict) -> None:
    base = server["base"]
    served = _served_catalog(base)
    served_ids = {c["id"] for c in served["catalog"]["capabilities"]}
    assert served_ids == set(CAPABILITY_IDS)

    evidence_dir = ROOT / "evidence" / "r182_impl"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    requests: list[tuple[str, str]] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as exc:  # browser binary absent: FAIL loudly, never skip
            pytest.fail(
                "chromium not launchable for playwright — run `python -m playwright install "
                "chromium` (+ `sudo python -m playwright install-deps chromium`), and pass "
                "PLAYWRIGHT_BROWSERS_PATH into the gate env; first line: "
                + str(exc).splitlines()[0]
            )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("request", lambda r: requests.append((r.method, r.url)))

        page.goto(f"{base}/app/command/", wait_until="load")
        assert page.title() == "QEVION Control Plane — Command Center"
        assert page.locator("#center-view").is_hidden()

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

        graph_ids = page.eval_on_selector_all(
            "#topology-nodes g.node", "els => els.map(e => e.getAttribute('data-id'))"
        )
        graph_states = page.eval_on_selector_all(
            "#topology-nodes g.node", "els => els.map(e => e.getAttribute('data-state'))"
        )
        list_ids = page.eval_on_selector_all(
            "#topology-list button.list-node", "els => els.map(e => e.getAttribute('data-id'))"
        )
        core_state = page.get_attribute("#core", "data-state")
        core_text = page.text_content("#core-state-text")
        scope_badge = page.text_content("#scope-badge")
        status_nodes = page.text_content("#status-nodes")

        # Interaction: selecting a node shows the SERVED record verbatim.
        first = served["catalog"]["capabilities"][0]
        page.click(f"#topology-list button.list-node[data-id='{first['id']}']")
        detail_id = page.text_content("#detail-id")
        detail_state = page.text_content("#detail-state")
        detail_evidence = page.text_content("#detail-evidence")

        page.screenshot(path=str(evidence_dir / "command_center_m1.png"), full_page=True)

        # ---- M2 (HANDOFF §7 rows 8-11): one execute turn through the UI form. ----
        page.fill("#converse-message", "browser proof m2")
        page.check("input[name=converse-mode][value=execute]")
        page.click("#converse-form button[type=submit]")
        page.wait_for_function(
            "() => { const l = document.querySelectorAll('#stream-log li'); "
            "return l.length > 0 && ['final','error'].includes("
            "l[l.length - 1].getAttribute('data-type')); }",
            timeout=20000,
        )
        m2_frames = page.eval_on_selector_all(
            "#stream-log li", "els => els.map(e => e.getAttribute('data-type'))"
        )
        m2_stage_states = page.eval_on_selector_all(
            "#execution-graph .exec-stage", "els => els.map(e => e.getAttribute('data-state'))"
        )
        m2_stage_keys = page.eval_on_selector_all(
            "#execution-graph .exec-stage", "els => els.map(e => e.getAttribute('data-node-key'))"
        )
        m2_status = page.text_content("#progress-status")
        m2_percent = page.get_attribute("#progress-bar-track", "aria-valuenow")
        m2_stage = page.text_content("#progress-stage")
        m2_execution_id = page.text_content("#progress-execution-id")
        m2_record = page.text_content("#execution-record")
        m2_turns = page.eval_on_selector_all(
            "#converse-turns li", "els => els.map(e => e.className)"
        )
        page.screenshot(path=str(evidence_dir / "command_center_m2.png"), full_page=True)
        browser.close()

    # --- M2 assertions: the DOM equals the SERVED execution record ---------------
    status, m2_login = _http(
        "POST", f"{base}/v1/auth/login", {"email": ADMIN_EMAIL, "password": PASSWORD}
    )
    assert status == 200
    status, m2_exec = _http(
        "GET", f"{base}/v1/executions/{m2_execution_id}", token=m2_login["token"]
    )
    assert status == 200, (status, m2_exec)
    status, m2_trace = _http(
        "GET", f"{base}/v1/agent/executions/{m2_execution_id}/trace", token=m2_login["token"]
    )
    assert status == 200, (status, m2_trace)
    assert set(m2_frames) <= {
        "execution_started",
        "node_started",
        "node_completed",
        "final",
        "error",
    }
    assert "delta" not in m2_frames and "UNKNOWN_EVENT" not in m2_frames
    assert m2_frames[0] == "execution_started" and m2_frames[-1] in ("final", "error")
    assert m2_stage_keys == [s["node_key"] for s in m2_trace["stages"]]
    assert m2_stage_states == [s["status"] for s in m2_trace["stages"]]
    assert m2_status == m2_exec["status"]
    assert m2_stage == m2_exec["progress"]["current_stage"]
    assert m2_percent == str(m2_exec["progress"]["percent"])
    assert f"as_recorded: {str(m2_trace['as_recorded']).lower()}" in m2_record
    assert m2_turns == ["turn turn-request", "turn turn-response"]

    # --- assertions -------------------------------------------------------------
    assert len(graph_ids) == len(served_ids), (len(graph_ids), len(served_ids))
    assert set(graph_ids) == served_ids
    assert set(list_ids) == served_ids and len(list_ids) == len(served_ids)
    served_state = {c["id"]: c["state"] for c in served["catalog"]["capabilities"]}
    for cid, st in zip(graph_ids, graph_states, strict=True):
        assert st in NODE_STATES, st
        assert st == served_state[cid], (cid, st, served_state[cid])
    assert core_state in CORE_STATES and core_text in CORE_STATES, (core_state, core_text)
    assert scope_badge == f"scope: {served['catalog']['scope']}"
    assert status_nodes == f"nodes: {len(served_ids)}"
    assert detail_id == first["id"]
    assert detail_state == first["state"]
    assert detail_evidence == first["evidence"]
    assert console_errors == [], console_errors

    # Transport honesty: every request is same-origin, to served routes or the static tree.
    for method, url in requests:
        assert url.startswith(base), f"cross-origin request: {url}"
        path = url[len(base) :].split("?")[0]
        if path.startswith("/app/command/"):
            continue
        assert method in ("GET", "POST"), (method, path)
        assert _path_served(path, served["paths"]), (
            f"request to a route the app does not serve: {path}"
        )

    (evidence_dir / "browser_proof_m1.json").write_text(
        json.dumps(
            {
                "server": "python3 -m apps.main (in-memory profile, ADMIN_EMAILS)",
                "page": "/app/command/",
                "served_capabilities": len(served_ids),
                "rendered_graph_nodes": len(graph_ids),
                "rendered_list_nodes": len(list_ids),
                "core_state": core_state,
                "scope_badge": scope_badge,
                "requests": sorted({m + " " + u[len(base) :].split("?")[0] for m, u in requests}),
                "console_errors": console_errors,
                "m2": {
                    "stream_frames_in_order": m2_frames,
                    "stage_keys": m2_stage_keys,
                    "stage_states": m2_stage_states,
                    "execution_status": m2_status,
                    "progress_percent": m2_percent,
                    "as_recorded_shown": "as_recorded:" in m2_record,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
