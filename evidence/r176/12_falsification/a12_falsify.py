# ruff: noqa: E501, E741  -- R176 Phase-A probe script (evidence, not product code)
"""A12 self-falsification probes (R176): for each major PASS, the cheapest counter-probe that would break it.
Hermetic server on BASE. Tokens never written."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8177"
LOG = "/tmp/r176_sec.log"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []


def http(m, p, tok=None, body=None, raw_auth=None, extra=None, raw_data=None):
    d = (
        raw_data
        if raw_data is not None
        else (json.dumps(body).encode() if body is not None else None)
    )
    r = urllib.request.Request(BASE + p, data=d, method=m)
    if raw_auth is not None:
        r.add_header("Authorization", raw_auth)
    elif tok:
        r.add_header("Authorization", f"Bearer {tok}")
    if d is not None:
        r.add_header("content-type", "application/json")
    for k, v in (extra or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=15) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def rec(l, c, t, n=400):
    OUT.append(f"### {l}\n{t[:n]} [{c}]\n")


def bootstrap(email):
    http(
        "POST",
        "/v1/auth/register",
        body={"email": email, "password": "Correct-Horse-9", "preferred_language": "en"},
    )
    time.sleep(0.4)
    tok = None
    for line in open(LOG, errors="ignore"):
        if email in line and "email_verification_token_issued" in line:
            m = re.search(r'"token": "([^"]+)"', line)
            tok = m.group(1) if m else tok
    http("POST", "/v1/auth/verify", body={"token": tok})
    return json.loads(
        http("POST", "/v1/auth/login", body={"email": email, "password": "Correct-Horse-9"})[1]
    )["token"]


ts = int(time.time())
A = bootstrap(f"fa-{ts}@r176.test")
B = bootstrap(f"fb-{ts}@r176.test")

c, t = http("POST", "/v1/execute", A, {"ask": "A-private"})
ea = json.loads(t)["execution_id"]
c, t = http("GET", f"/v1/executions/{ea.upper()}", B)
rec("F1a B reads A's id upper-cased", c, t)
c, t = http("GET", f"/v1/executions/{ea}/", B)
rec("F1b trailing slash", c, t)
c, t = http("GET", f"/v1/executions?execution_id={ea}", B)
rec("F1c list with query filter", c, t)
OUT.append(f"### F1c-b A's id appears in B's list: {ea in t}\n")

for label, h in [
    ("F2a lowercase bearer", f"bearer {A}"),
    ("F2b Basic scheme", "Basic dXNlcjpwYXNz"),
    ("F2c empty Bearer", "Bearer "),
    ("F2d token+junk", f"Bearer {A}x"),
]:
    c, t = http("GET", "/v1/models", raw_auth=h)
    rec(label, c, t, 160)

c, t = http("POST", "/v1/admin/changes", B, raw_data=b"{not json")
rec("F3 non-admin POST admin route with malformed JSON => still 403?", c, t, 200)

c, t0 = http("GET", "/v1/usage", A)
u0 = json.loads(t0)["task_units"]["used"]
http("POST", "/v1/execute", A, {"ask": "x", "bogus": 1})
http(
    "POST",
    "/v1/execute",
    A,
    {"ask": "x", "model_policy": {"type": "explicit_model", "model_id": "ghost"}},
)
c, t1 = http("GET", "/v1/usage", A)
u1 = json.loads(t1)["task_units"]["used"]
OUT.append(
    f"### F4 usage before failed calls {u0} -> after one 422 + one 503: {u1} (must be equal)\n"
)

for host in [
    "http://127.1/x",
    "http://0x7f000001/x",
    "http://localhost/x",
    "http://[::1]/x",
    "http://169.254.169.254/latest",
    "http://10.0.0.1/x",
    "http://2130706433/x",
    "http://example.com/x",
]:
    c, t = http("POST", "/v1/webhooks", A, {"url": host, "events": ["execution.succeeded"]})
    OUT.append(f"### F5 webhook {host} -> [{c}] {t[:90]}\n")

c, t = http("POST", "/v1/execute", A, {"ask": "x", "execution_policy": {"bogus": 1}})
rec("F6 nested unknown field => 422?", c, t, 200)

k = {"Idempotency-Key": f"shared-{ts}"}
c, t = http(
    "POST", "/v1/execute", A, {"ask": "A-idem", "execution_policy": {"async": True}}, extra=k
)
ida = json.loads(t)["execution_id"]
c, t = http(
    "POST", "/v1/execute", B, {"ask": "B-idem", "execution_policy": {"async": True}}, extra=k
)
idb = json.loads(t)["execution_id"]
OUT.append(
    f"### F7 same Idempotency-Key across tenants: same_execution={ida == idb} (must be False)\n"
)
time.sleep(1)
c, t = http("GET", f"/v1/executions/{idb}", B)
OUT.append(f"### F7b B's result has B's ask: {'B-idem' in t}; A's ask leaked: {'A-idem' in t}\n")
open(os.path.join(HERE, "falsification_probes.txt"), "w").write("\n".join(OUT))
print("\n".join(o[:220] for o in OUT))
