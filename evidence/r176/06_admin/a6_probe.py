"""A6 admin control-plane probe (R176). Starts nothing; expects the hermetic server on
BASE with ADMIN_EMAILS=admin@r176.test. Creates its own principals. Tokens never written.
Re-run: python3 evidence/r176/06_admin/a6_probe.py  -> writes admin_probes.txt next to it."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("R176_BASE", "http://127.0.0.1:8177")
LOG = os.environ.get("R176_SERVER_LOG", "/tmp/r176_sec.log")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT: list[str] = []
MARKER = "sk-SHOULD-NOT-BE-STORED"


def http(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def rec(label, code, text, limit=700):
    text = text.replace(MARKER, "<marker>")
    OUT.append(f"### {label}\n{text[:limit]} [{code}]\n")


def mk(email):
    http("POST", "/v1/auth/register", body={"email": email, "password": "Correct-Horse-9", "preferred_language": "en"})
    time.sleep(0.4)
    tok = None
    for line in open(LOG, encoding="utf-8", errors="ignore"):
        if email in line and "email_verification_token_issued" in line:
            m = re.search(r'"token": "([^"]+)"', line)
            if m:
                tok = m.group(1)
    if not tok:
        print("no verification token for", email); sys.exit(2)
    http("POST", "/v1/auth/verify", body={"token": tok})
    c, t = http("POST", "/v1/auth/login", body={"email": email, "password": "Correct-Horse-9"})
    return json.loads(t)["token"]


ADM = mk(f"admin@r176.test")
USER = mk(f"u6-{int(time.time())}@r176.test")

for label, path in [("M-01 providers", "/v1/admin/providers"), ("M-02 models", "/v1/admin/models"),
                    ("M-03 routing/weights", "/v1/admin/routing/weights"), ("M-04 capabilities", "/v1/admin/capabilities"),
                    ("M-05 learning/dashboard", "/v1/admin/learning/dashboard"), ("M-06 changes", "/v1/admin/changes")]:
    c, t = http("GET", path, ADM); rec(label, c, t)

c, t = http("PUT", "/v1/admin/routing/weights", ADM, {"version": "x", "quality": 0.5}); rec("M-07 PUT routing/weights (no direct mutation route expected)", c, t)

# lifecycle
c, t = http("GET", "/v1/models", USER); rec("L-00 user /v1/models BEFORE", c, t)
c, t = http("POST", "/v1/admin/changes", ADM, {"action": "disable_model", "payload": {"model_key": "local-echo-1"}}); rec("L-01 draft disable_model", c, t)
cid = json.loads(t)["id"]
c, t = http("POST", f"/v1/admin/changes/{cid}/validate", ADM); rec("L-02 validate", c, t)
c, t = http("POST", f"/v1/admin/changes/{cid}/preview", ADM); rec("L-03 preview", c, t)
c, t = http("POST", f"/v1/admin/changes/{cid}/publish", USER); rec("L-04 non-admin publish => 403", c, t)
c, t = http("POST", f"/v1/admin/changes/{cid}/publish", ADM); rec("L-05 publish", c, t)
c, t = http("GET", "/v1/models", USER); rec("L-06 user /v1/models AFTER publish (stale-config: next request)", c, t)
c, t = http("POST", "/v1/execute", USER, {"ask": "post-disable"}); rec("L-07 execute AFTER disable => model_unavailable, no silent echo", c, t)
c, t = http("POST", f"/v1/admin/changes/{cid}/rollback", ADM); rec("L-08 rollback", c, t)
c, t = http("GET", "/v1/models", USER); rec("L-09 user /v1/models AFTER rollback", c, t)
c, t = http("POST", "/v1/execute", USER, {"ask": "post-rollback"}); rec("L-10 execute AFTER rollback", c, t, 300)
c, t = http("GET", "/v1/admin/audit?limit=8", ADM); rec("L-11 audit tail (publish/rollback attributed?)", c, t, 1200)
c, t = http("POST", f"/v1/admin/changes/{cid}/publish", ADM); rec("L-12 publish after rollback => state-machine refusal", c, t)
c, t = http("POST", "/v1/admin/changes", ADM, {"action": "set_plan", "payload": {}}); rec("L-13 draft set_plan empty payload", c, t)
c, t = http("POST", "/v1/admin/changes", ADM, {"action": "register_provider", "payload": {"provider_key": "evil", "api_key": MARKER}}); rec("L-14 draft register_provider WITH credential in payload", c, t)
eid = json.loads(t).get("id")
if eid:
    c, t = http("POST", f"/v1/admin/changes/{eid}/validate", ADM); rec("L-14b validate", c, t)
    c, t2 = http("GET", f"/v1/admin/changes/{eid}", ADM); rec("L-14c read back", c, t2)
    c, t3 = http("GET", "/v1/admin/audit?limit=30", ADM)
    OUT.append(f"### L-14e marker string echoed in change read-back: {MARKER in t2}; present in audit: {MARKER in t3}\n")
# cross-tenant admin: user (non-admin) cannot see admin's changes; admin sees only own tenant's
c, t = http("GET", "/v1/admin/changes", USER); rec("L-15 non-admin GET changes => 403", c, t)

open(os.path.join(HERE, "admin_probes.txt"), "w").write("\n".join(OUT))
print("\n".join(o[:260] for o in OUT))
