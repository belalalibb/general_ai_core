"""UI phase — live browser proof of every console binding added over the
EXISTING admin routes (no backend change). Runs against a real process:

    ADMIN_EMAILS=ops@example.com python3 -m apps.main   # providers=[local_echo]
    # register + verify ops@example.com (token appears in the server console)
    python3 docs/benchmarks/ui-phase-live/drive.py

Each step asserts on RENDERED text — what the admin actually sees — never on
the API response alone. Exit 1 on any FAIL. Screenshots + results.json land
in $UI_PROOF_OUT (default /tmp/ui). Re-runnable against the same process:
per-run names are unique.
"""

import asyncio
import json
import os
import sys
import uuid

from playwright.async_api import async_playwright

B = os.environ.get("UI_PROOF_BASE", "http://127.0.0.1:8000")
OUT = os.environ.get("UI_PROOF_OUT", "/tmp/ui")
EMAIL = os.environ.get("UI_PROOF_EMAIL", "ops@example.com")
PASSWORD = os.environ.get("UI_PROOF_PASSWORD", "Str0ng-Passw0rd-ops-2026")
RUN = uuid.uuid4().hex[:6]
results: list[tuple[str, bool, str]] = []


def ok(name: str, cond: object, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, ("\u2014 " + detail[:160]) if detail else "")


async def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1440, "height": 1100})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # Chromium logs every non-2xx response as a console "error"
        # ("Failed to load resource: ... 422/404"). Those are the intentional
        # refusals and absent seams this proof exercises on purpose — keep only
        # genuine script errors.
        pg.on(
            "console",
            lambda m: (
                errors.append(m.text)
                if m.type == "error" and not m.text.startswith("Failed to load resource")
                else None
            ),
        )

        await pg.goto(B + "/admin/", wait_until="networkidle")
        await pg.fill("#login-email", EMAIL)
        await pg.fill("#login-password", PASSWORD)
        await pg.click("#login-form button[type=submit]")
        await pg.wait_for_selector("#console-view:not([hidden])", timeout=10000)
        await pg.wait_for_timeout(800)
        who = await pg.inner_text("#session-who")
        ok("session-who shows email+tenant", EMAIL in who and "tenant" in who, who)

        async def go(surface: str) -> None:
            await pg.click(f'.rail-item[data-surface="{surface}"]')
            await pg.wait_for_timeout(1200)

        # --- Intelligence: capability exercise -------------------------------
        await go("intelligence")
        rows = await pg.locator("#capabilities-table tbody tr").count()
        ok("capabilities table has 16 rows", rows == 16, str(rows))
        inert_badge = await pg.locator("#capabilities-table .badge", has_text="inert").count()
        unknown = await pg.locator("#capabilities-table .badge.unknown").count()
        ok(
            "inert renders as a badge, no UNKNOWN badges",
            inert_badge >= 1 and unknown == 0,
            f"inert={inert_badge} unknown={unknown}",
        )
        ex_buttons = await pg.locator("#capabilities-table button", has_text="Exercise").count()
        not_ex = await pg.locator("#capabilities-table td", has_text="not exercisable").count()
        ok(
            "Exercise offered only for server-listed ids; others say so",
            ex_buttons >= 1 and ex_buttons + not_ex == 16,
            f"btn={ex_buttons} not={not_ex}",
        )
        row = pg.locator("#capabilities-table tbody tr", has_text="execute.sync")
        await row.locator("button", has_text="Exercise").click()
        await pg.wait_for_timeout(1500)
        ex = await pg.inner_text("#exercise-result")
        ok(
            "exercise execute.sync \u2192 real execution evidence",
            '"exercised": true' in ex and '"execution_id"' in ex,
            ex[:120],
        )
        has_open = await pg.locator("#exercise-result button", has_text="Open execution").count()
        ok("exercise result links to the execution", has_open == 1)
        await pg.screenshot(path=f"{OUT}/s1_intelligence_exercise.png", full_page=True)

        # --- Scenarios: save / refusal / replay / regression ------------------
        checks = await pg.locator('input[name="scenario-check"]').count()
        ok("scenario checks rendered from closed set (2)", checks == 2, str(checks))
        sc_name = f"echo smoke {RUN}"
        await pg.fill("#scenario-name", sc_name)
        await pg.fill("#scenario-ask", "ping the echo adapter")
        await pg.click("#scenario-form button[type=submit]")
        await pg.wait_for_timeout(1500)
        sc_rows = await pg.locator("#scenarios-table tbody tr", has_text=sc_name).count()
        ok("scenario saved and listed", sc_rows == 1, str(sc_rows))
        await pg.fill("#scenario-name", "bad")
        await pg.fill("#scenario-ask", "x")
        for cb in await pg.locator('input[name="scenario-check"]').all():
            await cb.uncheck()
        await pg.click("#scenario-form button[type=submit]")
        await pg.wait_for_timeout(1000)
        err = await pg.inner_text("#scenario-error")
        ok(
            "empty check set \u2192 server validation_error rendered verbatim",
            "validation_error" in err,
            err,
        )
        await (
            pg.locator("#scenarios-table tbody tr", has_text=sc_name)
            .locator("button", has_text="Replay")
            .click()
        )
        await pg.wait_for_timeout(2000)
        rep = await pg.inner_text("#scenario-result")
        ok(
            "replay \u2192 real execution + verdict",
            "execution" in rep and "verdict" in rep and ("passed" in rep or "failed" in rep),
            rep[:160],
        )
        await pg.click("#regression-pack")
        await pg.wait_for_timeout(2500)
        reg = await pg.inner_text("#scenario-result")
        ok(
            "regression pack \u2192 count + verdict",
            "scenario(s)" in reg and "regression" in reg,
            reg[:160],
        )
        await pg.screenshot(path=f"{OUT}/s2_scenarios.png", full_page=True)

        # --- Context lab -------------------------------------------------------
        lab_note = await pg.inner_text("#lab-checks")
        ok("lab checks listed from server", "ask_block_present" in lab_note, lab_note)
        await pg.fill("#lab-ask", "hello lab")
        await pg.click("#lab-form button[type=submit]")
        await pg.wait_for_timeout(1200)
        lab = await pg.inner_text("#lab-result")
        ok(
            "lab validate \u2192 checks + blocks summary",
            "ask_block_present" in lab and "context block" in lab,
            lab[:160],
        )
        # The input carries min=1 (mirrors the contract), so the browser's own
        # constraint check blocks 0 before any request. Strip it to reach the
        # server and prove its refusal renders verbatim.
        await pg.evaluate("document.getElementById('lab-budget').removeAttribute('min')")
        await pg.fill("#lab-budget", "0")
        await pg.click("#lab-form button[type=submit]")
        await pg.wait_for_timeout(1000)
        laberr = await pg.inner_text("#lab-error")
        ok(
            "lab budget 0 \u2192 server validation_error verbatim",
            "validation_error" in laberr,
            laberr,
        )
        await pg.fill("#lab-budget", "16000")
        await pg.evaluate("document.getElementById('lab-budget').setAttribute('min', '1')")

        # --- Executions: record + evaluations tabs -----------------------------
        await go("executions")
        n = await pg.locator("#executions-table tbody tr").count()
        ok("executions list shows the exercise/replay executions", n >= 3, str(n))
        await (
            pg.locator("#executions-table tbody tr")
            .first.locator("button", has_text="Open")
            .click()
        )
        await pg.wait_for_timeout(1500)
        rec = await pg.inner_text("#tab-record")
        ok("record tab shows status + stored result", "status:" in rec and "echo" in rec, rec[:120])
        await pg.click('#execution-detail .tab[data-tab="evaluations"]')
        ev = await pg.inner_text("#tab-evaluations")
        ok("evaluations tab honest empty", "No evaluation records" in ev, ev)
        await pg.screenshot(path=f"{OUT}/s3_execution_detail.png", full_page=True)

        # --- Changes: draft → validate → preview -----------------------------
        await go("changes")
        opts = await pg.locator("#change-action option").count()
        ok("action select has 13 closed verbs (+placeholder)", opts == 14, str(opts))
        before = await pg.locator("#changes-table tbody tr", has_text="disable_model").count()
        await pg.select_option("#change-action", "disable_model")
        await pg.fill("#change-payload", '{"model_key": "local-echo-1"}')
        await pg.click("#change-form button[type=submit]")
        await pg.wait_for_timeout(1200)
        after = await pg.locator("#changes-table tbody tr", has_text="disable_model").count()
        ok("change drafted and listed", after == before + 1, f"{before}\u2192{after}")
        row = (
            pg.locator("#changes-table tbody tr", has_text="draft")
            .filter(has_text="disable_model")
            .first
        )
        await row.locator("button", has_text="Validate").click()
        await pg.wait_for_timeout(1200)
        row = pg.locator("#changes-table tbody tr", has_text="disable_model").first
        st = await row.inner_text()
        ok(
            "validate \u2192 server state shown (validated or rejected)",
            "validated" in st or "rejected" in st,
            st[:160],
        )
        if "validated" in st:
            await row.locator("button", has_text="Preview").click()
            await pg.wait_for_timeout(1200)
            row = pg.locator("#changes-table tbody tr", has_text="disable_model").first
            pub = await row.locator("button", has_text="Publish").count()
            ok("preview \u2192 Publish offered", pub == 1)
        await row.locator("td button").first.click()
        await pg.wait_for_timeout(800)
        det = await pg.inner_text("#change-detail")
        ok("change detail rendered verbatim", '"action": "disable_model"' in det, det[:120])
        await pg.screenshot(path=f"{OUT}/s4_changes.png", full_page=True)

        # --- Source changes: snapshot → propose → verify → approve → apply -----
        await go("source")
        await pg.fill("#snapshot-files", json.dumps({f"README-{RUN}.md": "hello"}))
        await pg.click("#snapshot-form button[type=submit]")
        await pg.wait_for_timeout(1200)
        base = await pg.input_value("#propose-base")
        ok("snapshot created \u2192 64-char id filled", len(base) == 64, base[:16])
        rationale = f"ui-phase live proof {RUN}"
        await pg.select_option("#propose-kind", "modify_file")
        await pg.fill("#propose-path", f"README-{RUN}.md")
        await pg.fill("#propose-content", "hello world")
        await pg.fill("#propose-rationale", rationale)
        await pg.click("#propose-form button[type=submit]")
        await pg.wait_for_timeout(1200)
        prow = pg.locator("#source-table tbody tr", has_text=rationale)
        ok("proposal listed as draft", "draft" in await prow.inner_text())
        await prow.locator("button", has_text="Verify").click()
        await pg.wait_for_timeout(1500)
        prow = pg.locator("#source-table tbody tr", has_text=rationale)
        t = await prow.inner_text()
        ok("verify \u2192 verified", "verified" in t and "failed_verification" not in t, t[:120])
        await prow.locator("button", has_text="Approve").click()
        await pg.wait_for_timeout(1200)
        prow = pg.locator("#source-table tbody tr", has_text=rationale)
        t = await prow.inner_text()
        ok(
            "approve (cited hash) \u2192 approved + approval column filled",
            "approved" in t and "cited" in t,
            t[:160],
        )
        await prow.locator("button", has_text="Apply").click()
        await pg.wait_for_timeout(1500)
        prow = pg.locator("#source-table tbody tr", has_text=rationale)
        t = await prow.inner_text()
        serr = await pg.inner_text("#source-error")
        ok(
            "apply \u2192 applied (snapshot space) OR refusal verbatim",
            "applied" in t or serr,
            (t + " | " + serr)[:160],
        )
        await prow.locator("td button").first.click()
        await pg.wait_for_timeout(800)
        sdet = await pg.inner_text("#source-detail")
        ok(
            "proposal detail: sha256 + authoritative_apply, no bytes",
            '"content_sha256"' in sdet
            and '"authoritative_apply"' in sdet
            and "content_b64" not in sdet,
            sdet[:120],
        )
        await pg.screenshot(path=f"{OUT}/s5_source.png", full_page=True)

        # --- Usage: plan ---------------------------------------------------------
        await go("usage")
        plan = await pg.inner_text("#plan-body")
        ok(
            "plan cards from session tenant",
            "Plan" in plan and "Task units" in plan and "used of" in plan,
            plan.replace("\n", " ")[:160],
        )
        await pg.fill("#plan-tenant", "00000000-0000-0000-0000-000000000000")
        await pg.click("#plan-form button[type=submit]")
        await pg.wait_for_timeout(1000)
        perr = await pg.inner_text("#plan-error")
        pbody = await pg.inner_text("#plan-body")
        ok(
            "foreign tenant \u2192 server answer verbatim (error or plan)",
            perr or pbody,
            (perr or pbody).replace("\n", " ")[:120],
        )
        await pg.screenshot(path=f"{OUT}/s6_usage_plan.png", full_page=True)

        # --- Logout -----------------------------------------------------------------
        await pg.click("#logout")
        await pg.wait_for_timeout(800)
        login_visible = await pg.locator("#login-view:not([hidden])").count()
        ok("logout \u2192 login view; console hidden", login_visible == 1)
        await pg.screenshot(path=f"{OUT}/s7_logged_out.png")

        ok("zero page errors / script console errors", not errors, " | ".join(errors)[:300])
        await b.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    with open(f"{OUT}/results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    sys.exit(1 if failed else 0)


asyncio.run(main())
