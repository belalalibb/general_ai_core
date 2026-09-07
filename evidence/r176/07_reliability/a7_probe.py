"""A7 reliability wire probe (R176): idempotency on /v1/execute, oversized/flood behaviour,
process-local honesty. Expects the hermetic server on BASE. Tokens never written."""
from __future__ import annotations
import json, os, re, sys, time, urllib.error, urllib.request
BASE = os.environ.get("R176_BASE", "http://127.0.0.1:8177"); LOG = "/tmp/r176_sec.log"
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = []

def http(method, path, token=None, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if token: req.add_header("Authorization", f"Bearer {token}")
    if data is not None: req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()

def rec(label, code, text, limit=500): OUT.append(f"### {label}\n{text[:limit]} [{code}]\n")

def mk(email):
    http("POST", "/v1/auth/register", body={"email": email, "password": "Correct-Horse-9", "preferred_language": "en"}); time.sleep(0.4)
    tok = None
    for line in open(LOG, errors="ignore"):
        if email in line and "email_verification_token_issued" in line:
            m = re.search(r'"token": "([^"]+)"', line); tok = m.group(1) if m else tok
    http("POST", "/v1/auth/verify", body={"token": tok})
    return json.loads(http("POST", "/v1/auth/login", body={"email": email, "password": "Correct-Horse-9"})[1])["token"]

U = mk(f"u7-{int(time.time())}@r176.test")
# idempotency: same key twice (async path is where the key is carried, app.py:1192)
h = {"Idempotency-Key": "r176-idem-1"}
c1, t1 = http("POST", "/v1/execute", U, {"ask": "idem", "execution_policy": {"async": True}}, h); rec("R-01 async execute with Idempotency-Key #1", c1, t1)
c2, t2 = http("POST", "/v1/execute", U, {"ask": "idem", "execution_policy": {"async": True}}, h); rec("R-02 same key #2 (expect same execution_id or 200/202 replay, never a second job)", c2, t2)
try:
    same = json.loads(t1).get("execution_id") == json.loads(t2).get("execution_id")
except Exception: same = None
OUT.append(f"### R-02b same execution_id on replay: {same}\n")
c3, t3 = http("POST", "/v1/execute", U, {"ask": "DIFFERENT body", "execution_policy": {"async": True}}, h); rec("R-03 same key, different body => expect 409/422 conflict", c3, t3)
time.sleep(1)
c, t = http("GET", "/v1/usage", U); rec("R-04 usage after idempotent pair (+1 conflict): expect 1 or 2 units, not 3", c, t)
# sync path with key
c4, t4 = http("POST", "/v1/execute", U, {"ask": "idem-sync"}, {"Idempotency-Key": "r176-idem-2"}); rec("R-05 sync execute with key #1", c4, t4, 200)
c5, t5 = http("POST", "/v1/execute", U, {"ask": "idem-sync"}, {"Idempotency-Key": "r176-idem-2"}); rec("R-06 sync replay #2", c5, t5, 200)
try: OUT.append(f"### R-06b sync replay same execution_id: {json.loads(t4).get('execution_id')==json.loads(t5).get('execution_id')}\n")
except Exception: pass
# burst: 40 async in a tight loop — admission/backpressure behaviour
codes = {}
for i in range(40):
    c, _ = http("POST", "/v1/execute", U, {"ask": f"burst-{i}", "execution_policy": {"async": True}}); codes[c] = codes.get(c, 0) + 1
OUT.append(f"### R-07 burst 40 async submits: status histogram {codes}\n")
time.sleep(2)
c, t = http("GET", "/v1/executions", U); n = len(json.loads(t)["executions"]); st = {}
for e in json.loads(t)["executions"]: st[e["status"]] = st.get(e["status"], 0) + 1
OUT.append(f"### R-08 executions listed for tenant after burst: {n}; status histogram {st}\n")
c, t = http("GET", "/healthz"); rec("R-09 healthz scope (process-local honesty)", c, t)
open(os.path.join(HERE, "wire_probes.txt"), "w").write("\n".join(OUT)); print("\n".join(o[:300] for o in OUT))
