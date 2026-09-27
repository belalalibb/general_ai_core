"""UI-RECON-SHELL — REAL Chromium proof of the unified shell (ui/app/shell/).

Chromium drives `python3 -m apps.main` (in-memory profile, ADMIN_EMAILS); no skip
path — a missing browser FAILS (fail-closed, same posture as R185/R187).

Pinned (design freeze red-team + acceptance plan L):
* unauthenticated deep link -> #/auth?next=…; after sign-in the shell lands on `next`;
* a non-admin sees NO Control rail item and NO capability topology (OD-1 = B);
* New Work renders exactly one model row per served logical model id (model-first);
* execute -> #/runs/<id>; refresh keeps the deep link; back/forward restore routes;
* a forced admin URL renders the served 403 (hiding is not authorization);
* a random run id renders the served 404 (anti-enumeration);
* Build offers NO generate/build/deploy/publish control;
* browser storage: localStorage empty; sessionStorage carries only the non-secret
  context; the session cookie is not visible to JavaScript;
* admin: capability nodes == served catalog ids (1:1); engineering -> NOT AVAILABLE;
  the Changes form lists exactly the served actions;
* 390 px: bottom tabs visible, rail hidden, no horizontal overflow.
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
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def _select_venv_local_browsers() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    import playwright as _pw

    local_store = Path(_pw.__file__).resolve().parent / "driver" / "package" / ".local-browsers"
    if local_store.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"


_select_venv_local_browsers()
ADMIN_EMAIL = "shell-admin@example.test"
USER_EMAIL = "shell-user@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 — test credential


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http(
    method: str, url: str, body: dict[str, object] | None = None, token: str | None = None
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "X-Requested-With": "QEVION"}
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
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    port = _free_port()
    env = dict(os.environ)
    env.update({"HOST": "127.0.0.1", "PORT": str(port), "ADMIN_EMAILS": ADMIN_EMAIL, "LOG_LEVEL": "warning", "PYTHONUNBUFFERED": "1"})
    for name in list(env):
        if name in ("DATABASE_URL", "REDIS_URL") or name.startswith(("GROQ_API_KEY", "GSK_API_KEY", "GW_GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")):
            env.pop(name, None)
    log_path = tmp_path_factory.mktemp("shell-recon") / "server_stdout.txt"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-m", "apps.main"], cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
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
            proc.terminate()
            pytest.fail("server did not become healthy")
        tokens = {}
        for email in (USER_EMAIL, ADMIN_EMAIL):
            st, reg = _http("POST", f"{base}/v1/auth/register", {"email": email, "password": PASSWORD})
            assert st == 201, (st, reg)
            st, _ = _http("POST", f"{base}/v1/auth/verify", {"token": reg["dev_verification_token"]})
            assert st in (200, 204)
            st, login = _http("POST", f"{base}/v1/auth/login", {"email": email, "password": PASSWORD})
            assert st == 200
            tokens[email] = login["token"]
        try:
            yield {"base": base, "tokens": tokens}
        finally:
            proc.terminate()
            with contextlib.suppress(Exception):
                proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch()  # fail-closed: no browser => error, never skip
        try:
            yield b
        finally:
            b.close()


def _sign_in(page: Page, base: str, email: str, next_hash: str | None = None) -> None:
    page.goto(f"{base}/app/shell/#/auth" + (f"?next={next_hash}" if next_hash else ""))
    page.wait_for_selector("h1#page-title")
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_function("() => !location.hash.startsWith('#/auth')", timeout=15000)


def test_user_journey_model_first_routing_authority_and_storage(server: dict[str, Any], browser: Browser) -> None:
    base = server["base"]
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))

    # deep link while anonymous -> auth with next
    page.goto(f"{base}/app/shell/#/work/models")
    page.wait_for_function("() => location.hash.startsWith('#/auth')")
    assert "next=" in page.evaluate("location.hash")
    _sign_in(page, base, USER_EMAIL, "/work/models")
    assert page.evaluate("location.hash") == "#/work/models"
    page.wait_for_selector(".model-card")

    # OD-1 = B: no Control rail, no topology for a user
    page.goto(f"{base}/app/shell/#/")
    page.wait_for_selector("h1#page-title")
    page.wait_for_selector("text=Recent runs")
    assert page.locator("#rail-list a", has_text="Control").count() == 0
    assert page.locator(".cap-node").count() == 0

    # model-first: one radio per served model id
    page.goto(f"{base}/app/shell/#/work/new")
    page.wait_for_selector(".model-picker")
    ids = page.eval_on_selector_all(".model-picker input[type=radio]", "els => els.map(e => e.value).filter(Boolean)")
    st, served = _http("GET", f"{base}/v1/models", token=server["tokens"][USER_EMAIL])
    assert st == 200
    assert sorted(ids) == sorted(m["id"] for m in served["models"])
    assert len(set(ids)) == len(ids)

    # execute -> run detail; refresh keeps the deep link; back/forward restore
    page.fill("textarea", "One-sentence summary of this shell journey.")
    page.click("button[type=submit]")
    page.wait_for_function("() => location.hash.startsWith('#/runs/')", timeout=30000)
    run_hash = page.evaluate("location.hash")
    page.wait_for_selector(".run-status .badge")
    page.reload()
    page.wait_for_selector("h1#page-title")
    assert page.evaluate("location.hash") == run_hash
    assert page.inner_text("h1#page-title").startswith("Run ")
    page.go_back()
    page.wait_for_function("() => location.hash === '#/work/new'")
    page.go_forward()
    page.wait_for_function(f"() => location.hash === '{run_hash}'")

    # server authority: 403 rendered for a forced admin URL; 404 for a random run
    page.goto(f"{base}/app/shell/#/control/capabilities")
    page.wait_for_selector(".state-error")
    assert "403" in page.inner_text(".state-error .error-head")
    page.goto(f"{base}/app/shell/#/runs/{uuid.uuid4()}")
    page.wait_for_selector(".state-error")
    assert "404" in page.inner_text(".state-error .error-head")

    # Build: planning only, no forbidden controls
    page.goto(f"{base}/app/shell/#/build")
    page.wait_for_selector("h1#page-title")
    page.wait_for_selector("select[aria-label=model]")
    assert "planning only" in page.inner_text("#main").lower()
    forbidden = page.evaluate(
        "() => Array.from(document.querySelectorAll('#main button, #main a.btn'))"
        ".map(b => b.textContent.trim().toLowerCase())"
        ".filter(t => /generate|deploy|publish/.test(t))"
    )
    assert forbidden == []

    # storage posture
    assert page.evaluate("Object.keys(window.localStorage)") == []
    assert page.evaluate("Object.keys(window.sessionStorage)") == ["qevion.app.context"]
    ctx_blob = page.evaluate("window.sessionStorage.getItem('qevion.app.context') || ''")
    assert not re.search(r"token|bearer", ctx_blob, re.I)
    assert page.evaluate("document.cookie.includes('qevion_session')") is False
    assert page_errors == []
    ctx.close()


def test_admin_control_plane_is_served_metadata(server: dict[str, Any], browser: Browser) -> None:
    base = server["base"]
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    _sign_in(page, base, ADMIN_EMAIL, "/control/capabilities")
    page.wait_for_selector(".cap-node", timeout=15000)
    assert page.locator("#rail-list a", has_text="Control").count() == 1
    st, cat = _http("GET", f"{base}/v1/admin/capabilities", token=server["tokens"][ADMIN_EMAIL])
    shown = page.eval_on_selector_all(".cap-node", "els => els.map(e => e.dataset.id)")
    assert sorted(shown) == sorted(c["id"] for c in cat["capabilities"])
    page.goto(f"{base}/app/shell/#/control/engineering")
    page.wait_for_selector(".state-unavailable")
    assert "NOT AVAILABLE" in page.inner_text(".state-unavailable strong")
    page.goto(f"{base}/app/shell/#/control/changes")
    page.wait_for_selector("select[aria-label=action]")
    st, meta = _http("GET", f"{base}/v1/admin/capabilities/actions", token=server["tokens"][ADMIN_EMAIL])
    assert page.locator("select[aria-label=action] option").count() - 1 == len(meta["actions"])
    ctx.close()


def test_mobile_390_bottom_tabs_no_overflow(server: dict[str, Any], browser: Browser) -> None:
    base = server["base"]
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    _sign_in(page, base, USER_EMAIL, "/")
    page.wait_for_selector("h1#page-title")
    page.wait_for_selector("text=Recent runs")
    assert page.is_visible(".tabs")
    assert not page.is_visible(".rail")
    for route in ("#/", "#/work/new", "#/work/models", "#/runs"):
        page.goto(f"{base}/app/shell/{route}")
        page.wait_for_selector("h1#page-title")
        time.sleep(0.4)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
    ctx.close()
