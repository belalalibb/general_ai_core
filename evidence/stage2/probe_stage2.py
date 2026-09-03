# ruff: noqa: E501 — evidence probe; long literal asks/verdict lines are intentional
"""R167-A §12 / §10 / §17 live probes against a running ``python3 -m apps.main``.

Two principals (ops = admin, dev = non-admin) are two tenants. Every request and
response is appended to ``OUT/stage2_transcript.log`` with bearer tokens and
provider key material redacted. Nothing here mutates the platform beyond
ordinary tenant traffic (executions, workspaces, projects, webhooks).

Usage::

    OUT=evidence/stage2 BASE=http://127.0.0.1:8000 \
    OPS_TOKEN_FILE=/tmp/ui/ops.tok DEV_TOKEN_FILE=/tmp/ui/dev.tok \
    SERVER_LOG=/tmp/ui/server.log python3 evidence/stage2/probe_stage2.py
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
OUT = Path(os.environ.get("OUT", "evidence/stage2"))
OUT.mkdir(parents=True, exist_ok=True)
OPS = Path(os.environ["OPS_TOKEN_FILE"]).read_text().strip()
DEV = Path(os.environ["DEV_TOKEN_FILE"]).read_text().strip()
GSK = os.environ.get("GSK_API_KEY", "")
SALT = "qevion-r167a-2026-09-03"

LOG = (OUT / "stage2_transcript.log").open("a", encoding="utf-8")
FINDINGS: list[dict[str, Any]] = []


def fp(v: str) -> str:
    return hashlib.sha256((SALT + v).encode()).hexdigest()[:12]


def redact(s: str) -> str:
    s = s.replace(OPS, "<OPS_TOKEN>").replace(DEV, "<DEV_TOKEN>")
    if GSK:
        s = s.replace(GSK, f"<GSK_API_KEY fp={fp(GSK)}>")
    return re.sub(r"Bearer [A-Za-z0-9._\-]+", "Bearer <REDACTED>", s)


def log(line: str) -> None:
    LOG.write(redact(line) + "\n")
    LOG.flush()


def call(
    who: str,
    method: str,
    path: str,
    body: Any | None = None,
    headers: dict[str, str] | None = None,
    limit: int = 1200,
) -> tuple[int, Any]:
    tok = {"ops": OPS, "dev": DEV, "anon": None}[who]
    h = dict(headers or {})
    if tok:
        h["authorization"] = f"Bearer {tok}"
    t0 = time.monotonic()
    r = httpx.request(method, BASE + path, json=body, headers=h, timeout=180)
    ms = int((time.monotonic() - t0) * 1000)
    try:
        payload: Any = r.json()
    except Exception:
        payload = r.text
    log(f"> {who} {method} {path} {json.dumps(body) if body is not None else ''}")
    log(f"< {r.status_code} {ms}ms {json.dumps(payload)[:limit]}")
    return r.status_code, payload


def note(text: str) -> None:
    log(f"# {text}")


def finding(pid: str, area: str, ok: bool, observed: str, expected: str, sev: str = "S2") -> None:
    verdict = "HELD" if ok else "DEFECT"
    FINDINGS.append(
        {
            "probe": pid,
            "area": area,
            "verdict": verdict,
            "severity": "-" if ok else sev,
            "observed": observed,
            "expected": expected,
        }
    )
    log(f"= {pid} {verdict} :: observed={observed} :: expected={expected}")


def execute(
    who: str, ask: str, extra: dict[str, Any] | None = None, headers=None
) -> tuple[int, Any]:
    body: dict[str, Any] = {"ask": ask}
    if extra:
        body.update(extra)
    return call(who, "POST", "/v1/execute", body, headers=headers)


def exec_id(p: Any) -> str | None:
    if not isinstance(p, dict):
        return None
    for k in ("execution_id", "id"):
        if isinstance(p.get(k), str):
            return p[k]
    if isinstance(p.get("execution"), dict):
        return p["execution"].get("id")
    e = p.get("error", {}) if isinstance(p.get("error"), dict) else {}
    return (e.get("details") or {}).get("execution_id")


def usage_units(who: str) -> float | None:
    st, u = call(who, "GET", "/v1/usage")
    if st != 200 or not isinstance(u, dict):
        return None
    tu = u.get("task_units") or {}
    return tu.get("used")


def _id(p: Any, *keys: str) -> str | None:
    if not isinstance(p, dict):
        return None
    for k in keys:
        if isinstance(p.get(k), str):
            return p[k]
    return None


# --------------------------------------------------------------------------- §12 P0
def p0_tenant_isolation() -> None:
    note(
        "§12 P0-1 tenant isolation: dev creates an execution; ops (admin, other tenant) tries to read it"
    )
    st, r = execute("dev", "Reply with the single word ISOLATION.")
    dev_eid = exec_id(r)
    note(f"dev execution id={dev_eid} status={st}")
    if not dev_eid:
        finding(
            "P0-1",
            "tenant isolation",
            False,
            f"no execution id from dev POST /v1/execute ({st})",
            "id returned",
            "S3",
        )
        return
    for path in (
        f"/v1/executions/{dev_eid}",
        f"/v1/executions/{dev_eid}/events",
        f"/v1/agent/executions/{dev_eid}/trace",
        f"/v1/agent/executions/{dev_eid}/diagnosis",
    ):
        st2, r2 = call("ops", "GET", path)
        finding(
            f"P0-1 {path.split('/')[-1] if not path.endswith(dev_eid) else 'by-id'}",
            "tenant isolation",
            st2 in (403, 404),
            f"ops GET {path} -> {st2}",
            "403/404 (foreign tenant indistinguishable from absent)",
            "S1",
        )
    st3, lst = call("ops", "GET", "/v1/executions")
    finding(
        "P0-1 list",
        "tenant isolation",
        dev_eid not in json.dumps(lst),
        f"ops GET /v1/executions contains dev id: {dev_eid in json.dumps(lst)}",
        "not listed",
        "S1",
    )
    st4, ev = call("ops", "GET", f"/v1/admin/executions/{dev_eid}/evaluations")
    note(
        f"admin evaluations for foreign execution -> {st4} (admin plane is cross-tenant by design; recorded, not judged)"
    )

    note("§12 P0-1b: dev tries to read/delete ops workspace/project/webhook objects")
    st, ws = call("ops", "POST", "/v1/workspaces", {"name": "ops-ws"})
    ws_id = _id(ws, "workspace_id", "id")
    st, pj = call("ops", "POST", "/v1/projects", {"name": "ops-project", "workspace_id": ws_id})
    pj_id = _id(pj, "project_id", "id")
    st, wh = call("ops", "POST", "/v1/webhooks", {"url": "https://example.invalid/hook"})
    wh_id = _id(wh, "id", "subscription_id")
    for label, oid, path in (
        ("workspace", ws_id, f"/v1/workspaces/{ws_id}"),
        ("project", pj_id, f"/v1/projects/{pj_id}"),
    ):
        if not oid:
            finding(
                f"P0-1b {label} create",
                "harness",
                False,
                f"ops could not create {label}: {json.dumps(locals().get('ws' if label == 'workspace' else 'pj'))[:160]}",
                "created",
                "S3",
            )
            continue
        st2, _ = call("dev", "GET", path)
        finding(
            f"P0-1b {label} read",
            "tenant isolation",
            st2 in (403, 404),
            f"dev GET {path} -> {st2}",
            "403/404",
            "S1",
        )
        st3, _ = call("dev", "DELETE", path)
        finding(
            f"P0-1b {label} delete",
            "tenant isolation",
            st3 in (403, 404),
            f"dev DELETE {path} -> {st3}",
            "403/404",
            "S1",
        )
        st4, _ = call("ops", "GET", path)
        finding(
            f"P0-1b {label} survives",
            "tenant isolation",
            st4 == 200,
            f"ops GET {path} after foreign delete -> {st4}",
            "200 (object intact)",
            "S1",
        )
    st5, lst = call("dev", "GET", "/v1/workspaces")
    finding(
        "P0-1b workspace list",
        "tenant isolation",
        not ws_id or ws_id not in json.dumps(lst),
        f"dev workspace list contains ops ws: {bool(ws_id) and ws_id in json.dumps(lst)}",
        "not listed",
        "S1",
    )
    st5, lst = call("dev", "GET", "/v1/projects")
    finding(
        "P0-1b project list",
        "tenant isolation",
        not pj_id or pj_id not in json.dumps(lst),
        f"dev project list contains ops project: {bool(pj_id) and pj_id in json.dumps(lst)}",
        "not listed",
        "S1",
    )
    if ws_id:
        st6, r6 = call(
            "dev", "POST", "/v1/projects", {"name": "dev-in-ops-ws", "workspace_id": ws_id}
        )
        finding(
            "P0-1b project into foreign workspace",
            "tenant isolation",
            st6 in (403, 404, 422),
            f"dev POST /v1/projects workspace_id=<ops> -> {st6} {json.dumps(r6)[:120]}",
            "denied",
            "S1",
        )
    if wh_id:
        st3, _ = call("dev", "DELETE", f"/v1/webhooks/{wh_id}")
        finding(
            "P0-1b webhook delete",
            "tenant isolation",
            st3 in (403, 404),
            f"dev DELETE /v1/webhooks/{wh_id} -> {st3}",
            "403/404",
            "S1",
        )
        st4, lst = call("dev", "GET", "/v1/webhooks")
        finding(
            "P0-1b webhook list",
            "tenant isolation",
            wh_id not in json.dumps(lst),
            f"dev webhook list contains ops subscription: {wh_id in json.dumps(lst)}",
            "not listed",
            "S1",
        )


def p0_authz_composition() -> None:
    note(
        "§12 P0-2 authz under composition: dev references ops project_id / conversation_id inside /v1/execute"
    )
    st, pj = call("ops", "POST", "/v1/projects", {"name": "ops-project-2"})
    pj_id = _id(pj, "project_id", "id")
    if pj_id:
        st2, r2 = execute("dev", "Reply OK.", {"project_id": pj_id})
        finding(
            "P0-2 project_id",
            "authz composition",
            st2 in (403, 404, 422),
            f"dev execute with ops project_id -> {st2} {json.dumps(r2)[:160]}",
            "denied (403/404/422), never executed under foreign project",
            "S1",
        )
    else:
        finding(
            "P0-2 project_id",
            "harness",
            False,
            f"ops project create failed: {json.dumps(pj)[:160]}",
            "created",
            "S3",
        )
    note("P0-2 conversation_id: dev seeds a conversation; ops reuses the same conversation_id")
    conv = "11111111-2222-4333-8444-555555555555"
    st3, r3 = execute("dev", "Remember the word PINEAPPLE.", {"conversation_id": conv})
    st4, r4 = execute(
        "ops",
        "What word did I ask you to remember? Reply with the word only.",
        {"conversation_id": conv},
    )
    body4 = json.dumps(r4)
    finding(
        "P0-2 conversation_id",
        "authz composition",
        "PINEAPPLE" not in body4.upper(),
        f"ops reuse of dev conversation_id -> {st4}; PINEAPPLE in body: {'PINEAPPLE' in body4.upper()}",
        "no cross-tenant history reuse",
        "S1",
    )
    note("P0-2 tools: dev requests tools not admitted for its tenant")
    st5, r5 = execute(
        "dev",
        "List files in the workspace.",
        {
            "execution_policy": {"strategy": "agent"},
            "tools": {"allowed": ["workspace.exec", "workspace.read"]},
        },
    )
    note(f"dev agent-tools request -> {st5} {json.dumps(r5)[:300]}")
    finding(
        "P0-2 unknown tools",
        "authz composition",
        st5 in (403, 422),
        f"-> {st5}",
        "named denial/validation, no execution",
        "S1",
    )
    st6, tools = call("dev", "GET", "/v1/agent/tools")
    note(f"dev GET /v1/agent/tools -> {st6} {json.dumps(tools)[:300]}")


def p0_credential_containment() -> None:
    note(
        "§12 P0-4 credential containment: scan responses/traces/errors/admin views/server log for provider key material"
    )
    if not GSK:
        note("GSK_API_KEY not in probe env -> containment NOT PROBED")
        return
    st, sys_ = call("ops", "GET", "/v1/admin/system", limit=3000)
    st2, prov = call("ops", "GET", "/v1/admin/providers", limit=3000)
    st3, aud = call("ops", "GET", "/v1/admin/audit", limit=3000)
    st4, mods = call("ops", "GET", "/v1/admin/models", limit=3000)
    blob = json.dumps([sys_, prov, aud, mods])
    finding(
        "P0-4 admin views",
        "credential containment",
        GSK not in blob,
        f"GSK_API_KEY value present in admin responses: {GSK in blob}",
        "never present",
        "S1",
    )
    st5, r5 = execute(
        "dev",
        "Say OK.",
        {"model_policy": {"type": "explicit_model", "model_id": "definitely-not-a-model"}},
    )
    eid = exec_id(r5)
    blob2 = json.dumps(r5)
    if eid:
        _, tr = call("dev", "GET", f"/v1/agent/executions/{eid}/trace", limit=3000)
        _, dg = call("dev", "GET", f"/v1/agent/executions/{eid}/diagnosis", limit=3000)
        _, ev = call("dev", "GET", f"/v1/executions/{eid}/events", limit=3000)
        blob2 += json.dumps([tr, dg, ev])
    finding(
        "P0-4 error surfaces",
        "credential containment",
        GSK not in blob2,
        f"GSK_API_KEY value present in failure/trace/diagnosis/events: {GSK in blob2}",
        "never present",
        "S1",
    )
    log_path = Path(os.environ.get("SERVER_LOG", "/tmp/ui/server.log"))
    if log_path.exists():
        text = log_path.read_text(errors="replace")
        finding(
            "P0-4 server log",
            "credential containment",
            GSK not in text,
            f"GSK_API_KEY value present in server.log: {GSK in text} (log bytes={len(text)})",
            "never present",
            "S1",
        )
    else:
        note("server log not found -> NOT PROBED")


def p0_atomicity() -> None:
    note("§12 P0-5 partial-success atomicity: usage before/after a failed execution")
    before = usage_units("dev")
    st, r = execute(
        "dev",
        "Say OK.",
        {"model_policy": {"type": "explicit_model", "model_id": "definitely-not-a-model"}},
    )
    after = usage_units("dev")
    note(f"failed explicit-model execute -> {st}; units before={before} after={after}")
    finding(
        "P0-5 failed-run billing",
        "atomicity",
        before is not None and after is not None and after == before,
        f"status {st}; units delta on failed execution = {None if before is None or after is None else after - before}",
        "0 units for a run that never succeeded",
        "S2",
    )


# --------------------------------------------------------------------------- §12 P1
def p1_idempotency() -> None:
    note(
        "§12 P1-1 idempotency: same tenant + same Idempotency-Key twice; different tenant same key"
    )
    key = "r167a-idem-" + str(int(time.time()))
    before = usage_units("dev")
    st1, r1 = execute("dev", "Reply with the word IDEMPOTENT.", headers={"Idempotency-Key": key})
    st2, r2 = execute("dev", "Reply with the word IDEMPOTENT.", headers={"Idempotency-Key": key})
    after = usage_units("dev")
    e1, e2 = exec_id(r1), exec_id(r2)
    finding(
        "P1-1 same id",
        "idempotency",
        e1 is not None and e1 == e2,
        f"ids {e1} / {e2}",
        "identical execution id on replay",
        "S2",
    )
    delta = None if before is None or after is None else after - before
    finding(
        "P1-1 single charge",
        "idempotency",
        delta is not None and delta <= 1.0,
        f"units delta across two calls = {delta}",
        "<= 1 billable unit",
        "S2",
    )
    st3, r3 = execute("ops", "Reply with the word IDEMPOTENT.", headers={"Idempotency-Key": key})
    e3 = exec_id(r3)
    finding(
        "P1-1 key scoped per tenant",
        "idempotency",
        e3 is not None and e3 != e1,
        f"ops with same key -> id {e3} (dev id {e1})",
        "distinct execution; key is tenant-scoped",
        "S1",
    )


def p1_quota_attribution() -> None:
    note("§12 P1-3 quota/cost attribution: ops units must not move when dev executes")
    ops_before = usage_units("ops")
    dev_before = usage_units("dev")
    execute("dev", "Reply with the word ATTRIBUTION.")
    ops_after = usage_units("ops")
    dev_after = usage_units("dev")
    finding(
        "P1-3 attribution",
        "quota/cost",
        ops_before == ops_after,
        f"ops units {ops_before}->{ops_after}; dev units {dev_before}->{dev_after}",
        "only the executing tenant is charged",
        "S1",
    )
    st, au = call("ops", "GET", "/v1/admin/usage", limit=800)
    note(
        f"admin usage view -> {st} keys={list(au)[:6] if isinstance(au, dict) else type(au).__name__}"
    )


def p1_pressure() -> None:
    note(
        "§12 P1-4 bounded pressure: 12 concurrent dev executes; expect no 5xx and consistent ledger"
    )
    before = usage_units("dev")

    def one(i: int) -> tuple[int, str | None]:
        st, r = execute("dev", f"Reply with the number {i}.")
        return st, exec_id(r)

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(one, range(12)))
    after = usage_units("dev")
    codes = [s for s, _ in results]
    ids = [e for _, e in results if e]
    finding(
        "P1-4 no 5xx",
        "pressure",
        all(c < 500 or c in (502, 503) for c in codes),
        f"status codes {codes}",
        "no unhandled 5xx (502/503 = honest provider failure)",
        "S2",
    )
    finding(
        "P1-4 distinct ids",
        "pressure",
        len(set(ids)) == len(ids),
        f"{len(ids)} ids, {len(set(ids))} distinct",
        "each request its own execution",
        "S2",
    )
    ok_count = sum(1 for c in codes if c == 200)
    delta = None if before is None or after is None else after - before
    finding(
        "P1-4 ledger",
        "pressure",
        delta is not None and delta <= ok_count + 0.0001,
        f"units delta {delta} vs successful {ok_count}",
        "charged <= successes",
        "S2",
    )


# --------------------------------------------------------------------------- §12 P2
def p2_auth_lifecycle() -> None:
    note("§12 P2-1 auth lifecycle: anonymous, malformed bearer, logged-out token")
    st, u = call("anon", "GET", "/v1/usage")
    finding(
        "P2-1 anon read", "auth lifecycle", st == 401, f"anon GET /v1/usage -> {st}", "401", "S2"
    )
    st, r = execute("anon", "Reply with the word ANON.")
    finding(
        "P2-1 anon execute",
        "auth lifecycle",
        st == 401,
        f"anon POST /v1/execute -> {st} {json.dumps(r)[:120]}",
        "401 (no work, no state for anonymous callers)",
        "S2",
    )
    st, _ = call("anon", "GET", "/v1/usage", headers={"authorization": "Bearer not-a-token"})
    finding("P2-1 malformed", "auth lifecycle", st == 401, f"malformed bearer -> {st}", "401", "S2")
    r = httpx.post(
        BASE + "/v1/auth/login",
        json={"email": "dev@example.com", "password": "Str0ng-Passw0rd-dev-2026"},
        timeout=30,
    )
    tok = r.json().get("token") if r.status_code == 200 else None
    if tok:
        s1 = httpx.get(
            BASE + "/v1/auth/session", headers={"authorization": f"Bearer {tok}"}, timeout=30
        ).status_code
        lo = httpx.post(
            BASE + "/v1/auth/logout", headers={"authorization": f"Bearer {tok}"}, timeout=30
        ).status_code
        s2 = httpx.get(
            BASE + "/v1/auth/session", headers={"authorization": f"Bearer {tok}"}, timeout=30
        ).status_code
        note(f"second session: before logout {s1}, logout {lo}, after logout {s2}")
        finding(
            "P2-1 logout revokes",
            "auth lifecycle",
            s2 == 401,
            f"session after logout -> {s2}",
            "401",
            "S2",
        )
    else:
        note(f"second login failed {r.status_code}; logout probe NOT PROBED")


def p2_input_robustness() -> None:
    note("§12 P2-2 input robustness")
    cases = [
        ("empty ask", {"ask": ""}),
        ("ask wrong type", {"ask": 12345}),
        ("huge ask", {"ask": "A" * 200_000}),
        ("unknown policy type", {"ask": "hi", "model_policy": {"type": "nonsense"}}),
        ("bad uuid project", {"ask": "hi", "project_id": "not-a-uuid"}),
        ("nul bytes", {"ask": "hi\u0000there"}),
    ]
    for label, body in cases:
        st, r = call("dev", "POST", "/v1/execute", body, limit=300)
        finding(
            f"P2-2 {label}",
            "input robustness",
            st in (200, 400, 413, 422, 502, 503),
            f"-> {st}",
            "4xx validation (or honest 200/502/503), never 500",
            "S3",
        )
    r = httpx.post(
        BASE + "/v1/execute",
        content=b"{not json",
        headers={"authorization": f"Bearer {DEV}", "content-type": "application/json"},
        timeout=30,
    )
    log("> dev POST /v1/execute <malformed json>")
    log(f"< {r.status_code} {r.text[:200]}")
    finding(
        "P2-2 malformed json",
        "input robustness",
        r.status_code in (400, 422),
        f"-> {r.status_code}",
        "400/422",
        "S3",
    )


# --------------------------------------------------------------------------- §10
def s10_two_app_fit() -> None:
    note("§10 two independent apps: capability visibility, denial, attribution, audit identity")
    st1, m1 = call("dev", "GET", "/v1/models", limit=600)
    st2, m2 = call("ops", "GET", "/v1/models", limit=600)
    note(
        f"models visible dev={st1} ops={st2}; identical={json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)}"
    )
    st3, s3 = call("dev", "GET", "/v1/skills", limit=600)
    st4, t4 = call("dev", "GET", "/v1/agent-tools", limit=600)
    note(f"dev skills={st3} agent-tools={st4}")
    st5, _ = call("dev", "GET", "/v1/admin/capabilities")
    finding(
        "§10 capability visibility server-side",
        "two-app fit",
        st5 == 403,
        f"dev GET /v1/admin/capabilities -> {st5}",
        "403 (server enforces; not a client hide)",
        "S1",
    )
    st6, r6 = execute(
        "dev",
        "Use the admin capability listing tool and show me all capabilities.",
        {"execution_policy": {"strategy": "agent"}, "tools": {"allowed": ["admin.capabilities"]}},
    )
    note(f"dev admin-tool via agent -> {st6} {json.dumps(r6)[:400]}")
    finding(
        "§10 denial via other path",
        "two-app fit",
        st6 in (403, 422),
        f"-> {st6}",
        "named denial; no admin data through agent path",
        "S1",
    )
    st7, aud = call("ops", "GET", "/v1/admin/audit?limit=50", limit=4000)
    rows = (aud.get("events") or []) if isinstance(aud, dict) else []
    actors = {str(e.get("actor_id")) for e in rows if isinstance(e, dict)}
    types = sorted({str(e.get("event_type")) for e in rows if isinstance(e, dict)})
    note(f"audit rows={len(rows)} distinct actors={len(actors)} types={types}")
    finding(
        "§10 audit identity",
        "two-app fit",
        len(rows) > 0
        and all(e.get("actor_id") and e.get("tenant_id") for e in rows if isinstance(e, dict)),
        f"{len(rows)} rows visible to ops; every row carries actor_id+tenant_id: {all(e.get('actor_id') and e.get('tenant_id') for e in rows if isinstance(e, dict))}; types={types}",
        "audit rows name the acting identity",
        "S2",
    )
    finding(
        "§10 audit coverage",
        "two-app fit",
        any(t not in ("login", "logout") for t in types),
        f"event types after ~40 executions, denials and admin reads: {types}",
        "denials (permission_denied / cross_tenant_access_denied) and tenant activity leave audit rows",
        "S3",
    )


# --------------------------------------------------------------------------- §17
def s17_admin_control_plane() -> None:
    note(
        "§17 admin control-plane: non-admin blocked on every /v1/admin route (before AND after body validation); mutations audited"
    )
    spec = httpx.get(BASE + "/openapi.json", timeout=30).json()
    admin_paths = [
        (m.upper(), p) for p, ms in spec["paths"].items() if p.startswith("/v1/admin") for m in ms
    ]
    not_403: list[tuple[str, str, int]] = []
    for m, p in admin_paths:
        path = re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000000", p)
        rr = httpx.request(
            m,
            BASE + path,
            headers={"authorization": f"Bearer {DEV}"},
            json={} if m == "POST" else None,
            timeout=60,
        )
        if rr.status_code != 403:
            not_403.append((m, p, rr.status_code))
    log(
        f"# admin routes probed with dev token (empty body): {len(admin_paths)}; non-403: {not_403}"
    )
    order_leak = [x for x in not_403 if x[2] == 422]
    finding(
        "§17 non-admin denied before validation",
        "admin control-plane",
        not order_leak,
        f"{len(order_leak)}/{len(admin_paths)} admin POST routes return 422 (body validation) to a NON-ADMIN before the admin gate: {[p for _, p, _ in order_leak]}",
        "403 first on every /v1/admin route regardless of body",
        "S3",
    )
    hard = [x for x in not_403 if x[2] not in (403, 422)]
    finding(
        "§17 non-admin never admitted",
        "admin control-plane",
        not hard,
        f"non-403/422 statuses for dev on admin routes: {hard}",
        "no 2xx/404/500 for non-admin",
        "S1",
    )
    # valid-body check: gate must still hold when the body is well-formed
    st_g, rg = call(
        "dev",
        "POST",
        "/v1/admin/engineering/grants",
        {"tenant_id": "00000000-0000-4000-8000-000000000001", "permissions": ["read"]},
    )
    finding(
        "§17 valid-body mutation by non-admin",
        "admin control-plane",
        st_g == 403,
        f"dev POST engineering/grants (valid body) -> {st_g}",
        "403",
        "S1",
    )
    rr = httpx.get(BASE + "/v1/admin/system", timeout=30)
    finding(
        "§17 anon admin",
        "admin control-plane",
        rr.status_code in (401, 403),
        f"anon GET /v1/admin/system -> {rr.status_code}",
        "401/403",
        "S1",
    )
    # mutation audited
    st1, before = call("ops", "GET", "/v1/admin/audit?limit=200", limit=200)
    n_before = before.get("total_recorded") if isinstance(before, dict) else None
    st2, g = call(
        "ops",
        "POST",
        "/v1/admin/engineering/grants",
        {"tenant_id": "00000000-0000-4000-8000-000000000001", "permissions": ["read"]},
    )
    note(f"ops engineering grant attempt -> {st2} {json.dumps(g)[:200]}")
    st3, after = call("ops", "GET", "/v1/admin/audit?limit=200", limit=3000)
    n_after = after.get("total_recorded") if isinstance(after, dict) else None
    finding(
        "§17 mutation audited",
        "admin control-plane",
        (n_after or 0) > (n_before or 0) or st2 not in (200, 201),
        f"grant status {st2}; audit total {n_before}->{n_after}",
        "a successful admin mutation lands in audit with actor/app/target/outcome",
        "S2",
    )
    st4, plan = call("ops", "GET", "/v1/admin/plans/00000000-0000-4000-8000-000000000000")
    note(f"admin plans view for random tenant -> {st4} (recorded)")


def main() -> None:
    log(
        f"### R167-A Stage 2 probes start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} base={BASE}"
    )
    for fn in (
        p0_tenant_isolation,
        p0_authz_composition,
        p0_credential_containment,
        p0_atomicity,
        p1_idempotency,
        p1_quota_attribution,
        p1_pressure,
        p2_auth_lifecycle,
        p2_input_robustness,
        s10_two_app_fit,
        s17_admin_control_plane,
    ):
        try:
            fn()
        except Exception as exc:  # record, never hide
            log(f"!! {fn.__name__} raised {type(exc).__name__}: {redact(str(exc))[:400]}")
            finding(
                fn.__name__,
                "harness",
                False,
                f"probe raised {type(exc).__name__}",
                "probe completes",
                "S3",
            )
    (OUT / "stage2_findings.json").write_text(json.dumps(FINDINGS, indent=2))
    held = sum(1 for f in FINDINGS if f["verdict"] == "HELD")
    log(f"### done: {held} HELD / {len(FINDINGS) - held} DEFECT")
    print(json.dumps({"held": held, "defect": len(FINDINGS) - held}))
    for f in FINDINGS:
        if f["verdict"] != "HELD":
            print("DEFECT", f["probe"], f["severity"], f["observed"][:200])


if __name__ == "__main__":
    main()
