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

Skips (never fails) ONLY when the browser binary is not installed — that is a
sandbox condition, recorded loudly in the skip reason, not a silent pass.
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

playwright_sync = pytest.importorskip(
    "playwright.sync_api", reason="playwright not installed (D-4 dev dependency)"
)
from playwright.sync_api import Error as PlaywrightError  # noqa: E402

from apps.api.capabilities import CAPABILITY_IDS, CapabilityState  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
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
def server() -> Iterator[dict]:
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
    env.pop("DATABASE_URL", None)  # in-memory profile: the hermetic proof
    log_path = ROOT / "evidence" / "r182_impl" / "server_stdout.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
    console_errors: list[str] = []
    requests: list[tuple[str, str]] = []

    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except PlaywrightError as exc:  # browser binary absent in this sandbox
            pytest.skip(f"chromium not installed for playwright: {str(exc).splitlines()[0]}")
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
        browser.close()

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
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
