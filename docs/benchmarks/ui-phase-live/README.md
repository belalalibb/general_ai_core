# UI-phase live proof (admin console bound to existing capabilities)

`drive.py` is a Playwright end-to-end driver that exercises the admin console
(`ui/admin/`) against a **live** `apps.main` process and asserts on the
*rendered text* only — no mocks, no fake states. Every button it clicks maps to
a route that already exists on the server; the backend was not modified for
this phase.

## Run

```bash
# 1. start the server (fresh workspace root, admin email allow-listed)
mkdir -p /tmp/ui && git init /tmp/ui/ws && git -C /tmp/ui/ws commit --allow-empty -m init
unset GSK_API_KEY OPENAI_API_KEY OPENAI_BASE_URL
ADMIN_EMAILS=ops@example.com AGENT_WORKSPACE_ROOT=/tmp/ui/ws \
AGENT_SOURCE_ROOT=$PWD AGENT_WORKSPACE_COMMANDS=python3,pytest \
python3 -m apps.main > /tmp/ui/server.log &

# 2. register + verify ops@example.com (token appears in server.log as
#    event email_verification_token_issued), then:
pip install playwright && python3 -m playwright install chromium
UI_PROOF_BASE=http://127.0.0.1:8000 UI_PROOF_OUT=/tmp/ui \
UI_PROOF_EMAIL=ops@example.com UI_PROOF_PASSWORD='Str0ng-Passw0rd-ops-2026' \
python3 docs/benchmarks/ui-phase-live/drive.py
```

Exit code is 1 on any failed assertion. Names are salted per run
(`RUN = uuid4().hex[:6]`) so the driver can be re-run against the same process.

## What the 32 assertions prove

| Surface | Checks |
|---|---|
| Session | header shows the signed-in admin; logout is server-confirmed |
| Execution | record / trace / diagnosis / evaluations tabs render server data |
| Intelligence | capability table shows `available` / `inert` / `unavailable` badges verbatim; Exercise renders the returned `evidence` JSON |
| Scenarios | save → replay → regression pack with `output_present` / `error_free_output` checks |
| Context Lab | validate renders the four checks; a budget of 0 surfaces the server 422 envelope |
| Changes | draft count increases by exactly one; detail / validate / preview render lifecycle state |
| Source (ADR-0009) | snapshot → propose → verify → approve `{cited_hash}` → apply; detail carries `content_sha256`, never bytes |
| Usage | plan read renders `task_units{limit,used,remaining}` |

Evidence from the last run is committed under `evidence/` (`results.json` with
32/32 `true`, plus screenshots `s1`, `s4`, `s5`, `s6`).
