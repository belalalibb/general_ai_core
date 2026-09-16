"""R187 — RED test for the two CS1 browser findings in the Command Center.

Declared BEFORE code in ``green_manifest.json`` ``change_budget.round_r187`` (ceiling 0,
ui-only) and ``docs/ai_orchestration_pack/R187_HANDOFF.md`` (R187-DEC-01). This module is
the round's first RED test; it was written before any change to ``ui/app/command/*``.

Authority (nothing here is invented): ``evidence/cs1/CS1_CURRENT_STATE_CERTIFICATION.md``
findings F-CS1-01 and F-CS1-02 with their root causes in ``evidence/cs1/browser/``.

* **F-CS1-01** — the admin session is lost on reload: the bearer token lives only in
  ``state.token`` (JS memory). Recorded fix design: keep the token in ``sessionStorage``
  (tab-scoped, never ``localStorage``), probe the EXISTING ``/v1/auth/session`` route at
  boot through one shared function, and clear the stored token on logout / failed probe.
  No new route, no new ``fetch(``, no timers.
* **F-CS1-02** — on a 1440 px desktop the Core sits 178 px left of the viewport centre
  because ``.center`` reserves a fixed 340 px second column for the (hidden) detail panel.
  Recorded fix design: ``.center`` is a single centred column and the detail panel reserves
  no width when it is closed or open.

Static part reads the three thawed files as text; browser part (Playwright, skipped when the
browser is unavailable) proves both fixes against a real ``apps.main`` server and writes
``evidence/r187/browser_proof_r187.json`` + a 1440 px screenshot with the detail open.
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
ADMIN_EMAIL = "browser-admin-r187@example.test"
PASSWORD = "correct horse battery staple"


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


# ---------------------------------------------------------------- static: F-CS1-01 ----


def test_f01_token_is_kept_in_session_storage_never_local_storage() -> None:
    code = _strip_js_comments(_js())
    assert "sessionStorage" in code, "F-CS1-01: token custody must survive a reload"
    assert "localStorage" not in code, "F-CS1-01: never persist the bearer token beyond the tab"


def test_f01_boot_probes_the_existing_session_route_through_one_shared_function() -> None:
    code = _strip_js_comments(_js())
    assert re.search(r"sessionStorage\.getItem\(", code), "boot must read the stored token"
    # exactly one literal keeps the ui_command_static_check /v1/ ceiling (12) intact
    assert code.count('"/v1/auth/session"') == 1
    match = re.search(r"async function (\w+)\([^)]*\)\s*\{[^}]*\"/v1/auth/session\"", code)
    assert match, "the session probe must be a named async function"
    probe = match.group(1)
    calls = re.findall(rf"\b{probe}\(", code)
    assert len(calls) >= 3, f"{probe} must be defined and called at boot AND after login"


def test_f01_logout_and_failed_probe_clear_the_stored_token() -> None:
    code = _strip_js_comments(_js())
    assert len(re.findall(r"sessionStorage\.removeItem\(", code)) >= 1


# ---------------------------------------------------------------- static: F-CS1-02 ----


def test_f02_center_grid_does_not_reserve_a_fixed_second_column() -> None:
    css = _css()
    blocks = re.findall(r"\.center\s*\{([^}]*)\}", css)
    assert blocks, ".center rule missing"
    for block in blocks:
        cols = re.search(r"grid-template-columns\s*:\s*([^;]+);", block)
        if cols:
            assert not re.search(r"\d+px", cols.group(1)), (
                f"F-CS1-02: .center reserves a fixed column: {cols.group(1).strip()}"
            )


def test_f02_detail_panel_reserves_no_layout_width() -> None:
    css = _css()
    block = re.search(r"\n\.detail\s*\{([^}]*)\}", css)
    assert block, ".detail rule missing"
    assert re.search(r"position\s*:\s*fixed", block.group(1)), (
        "F-CS1-02: the detail panel must be an overlay (position: fixed) on desktop"
    )


# ---------------------------------------------------------------- guard frame ----------


def test_ui_command_static_check_frame_untouched() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    block = manifest["ui_command_static_check"]
    assert sorted(block["files"]) == sorted(
        ["ui/app/command/command.css", "ui/app/command/command.js", "ui/app/command/index.html"]
    )
    assert int(block["v1_count_ceiling_command_js"]) == 12
    js = _js()
    assert js.count("/v1/") <= 12
    assert js.count("fetch(") == 2  # one in the header comment, one inside api()
    assert _strip_js_comments(js).count("fetch(") == 1
    banned_tokens = (
        "EventSource",
        "WebSocket",
        "XMLHttpRequest",
        "axios",
        "setInterval",
        "setTimeout",
    )
    for banned in banned_tokens:
        assert banned not in _strip_js_comments(js), banned
    round_block = manifest["change_budget"]["round_r187"]
    assert int(round_block["ceiling"]) == 0
    assert int(round_block["changes_used"]) == 0


# ---------------------------------------------------------------- browser proof --------

try:  # pragma: no cover - environment dependent
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
            (
                "GROQ_API_KEY",
                "GSK_API_KEY",
                "GW_",
                "GATEWAY_",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            )
        ):
            env.pop(name, None)
    log_path = tmp_path_factory.mktemp("command-center-r187") / "server_stdout.txt"
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


CORE_OFFSET_JS = """() => {
  const r = document.getElementById('core').getBoundingClientRect();
  return (r.left + r.width / 2) - document.documentElement.clientWidth / 2;
}"""
OVERFLOW_JS = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
STORAGE_JS = """() => ({
  session: Object.keys(window.sessionStorage),
  local: Object.keys(window.localStorage),
})"""


def _login(page, base: str) -> None:
    page.goto(f"{base}/app/command/", wait_until="load")
    page.fill("#login-email", ADMIN_EMAIL)
    page.fill("#login-password", PASSWORD)
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#center-view:not([hidden])", timeout=15000)
    page.wait_for_selector("#core[data-state]", timeout=15000)


def _open_detail(page) -> None:
    nodes = page.query_selector_all("#topology-nodes [data-id]")
    if nodes:
        nodes[0].focus()
        page.keyboard.press("Enter")
    else:  # no served capability to select — measure the panel geometry only
        page.evaluate("() => { document.getElementById('node-detail').hidden = false; }")
    page.wait_for_selector("#node-detail:not([hidden])", timeout=5000)


@pytest.mark.skipif(not _HAS_PLAYWRIGHT, reason="playwright not installed")
def test_session_survives_reload_and_core_is_centred_in_a_real_browser(server: dict) -> None:
    base = server["base"]
    out_dir = ROOT / "evidence" / "r187"
    out_dir.mkdir(parents=True, exist_ok=True)
    proof: dict = {"round": "R187", "base": base, "checks": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        _login(page, base)

        # F-CS1-01 — reload keeps the admin session (token custody in sessionStorage only)
        page.reload(wait_until="load")
        page.wait_for_selector("#center-view:not([hidden])", timeout=15000)
        storage = page.evaluate(STORAGE_JS)
        proof["checks"].append({"id": "F-CS1-01/reload_keeps_session", "storage": storage})
        assert storage["session"], "token must be in sessionStorage after login"
        assert storage["local"] == [], "localStorage must stay empty"
        assert page.is_visible("#logout")

        # F-CS1-02 — Core is centred with the detail closed AND open (desktop 1440)
        offset_closed = page.evaluate(CORE_OFFSET_JS)
        _open_detail(page)
        offset_open = page.evaluate(CORE_OFFSET_JS)
        overflow_1440 = page.evaluate(OVERFLOW_JS)
        page.screenshot(path=str(out_dir / "desktop_1440_detail_open.png"))
        proof["checks"].append(
            {
                "id": "F-CS1-02/desktop_1440",
                "core_offset_closed_px": offset_closed,
                "core_offset_open_px": offset_open,
                "overflow_px": overflow_1440,
            }
        )
        assert abs(offset_closed) <= 8, f"Core off-centre (closed): {offset_closed:.1f}px"
        assert abs(offset_open) <= 8, f"Core off-centre (detail open): {offset_open:.1f}px"
        assert overflow_1440 == 0
        page.keyboard.press("Escape")

        # logout clears custody; a reload must land on the login view
        page.click("#logout")
        page.wait_for_selector("#login-view:not([hidden])", timeout=10000)
        page.reload(wait_until="load")
        page.wait_for_selector("#login-view:not([hidden])", timeout=10000)
        storage_after = page.evaluate(STORAGE_JS)
        proof["checks"].append({"id": "F-CS1-01/logout_clears", "storage": storage_after})
        assert storage_after["session"] == []
        assert page.is_hidden("#center-view")

        # mobile 390 unchanged (R186 posture): centred, no horizontal overflow
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        _login(mobile, base)
        _open_detail(mobile)
        offset_390 = mobile.evaluate(CORE_OFFSET_JS)
        overflow_390 = mobile.evaluate(OVERFLOW_JS)
        proof["checks"].append(
            {"id": "F-CS1-02/mobile_390", "core_offset_px": offset_390, "overflow_px": overflow_390}
        )
        assert abs(offset_390) <= 8, f"Core off-centre at 390: {offset_390:.1f}px"
        assert overflow_390 == 0
        browser.close()
    proof["result"] = "PASS"
    (out_dir / "browser_proof_r187.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
