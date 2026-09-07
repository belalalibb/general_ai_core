"""A10 external-consumption probe (R176): two materially different independent consumers built ONLY from
the public HTTP contract (no platform imports), against the running hermetic server; plus the repo's own
examples/minimal-platform-app/client.py as consumer #0. Tokens never written."""
from __future__ import annotations
import json, os, re, subprocess, sys, time, urllib.error, urllib.request
BASE = os.environ.get("R176_BASE", "http://127.0.0.1:8177"); LOG = "/tmp/r176_sec.log"
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "../../..")); OUT = []
def http(m, p, tok=None, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m)
    if tok: r.add_header("Authorization", f"Bearer {tok}")
    if d is not None: r.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=15) as x: return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
def rec(l, c, t, n=450): OUT.append(f"### {l}\n{t[:n]} [{c}]\n")
def bootstrap(email):
    http("POST", "/v1/auth/register", body={"email": email, "password": "Correct-Horse-9", "preferred_language": "en"}); time.sleep(0.4)
    tok = None
    for line in open(LOG, errors="ignore"):
        if email in line and "email_verification_token_issued" in line:
            m = re.search(r'"token": "([^"]+)"', line); tok = m.group(1) if m else tok
    http("POST", "/v1/auth/verify", body={"token": tok})
    return json.loads(http("POST", "/v1/auth/login", body={"email": email, "password": "Correct-Horse-9"})[1])["token"]

ts = int(time.time())
T0 = bootstrap(f"ex0-{ts}@r176.test")
p = subprocess.run([sys.executable, "examples/minimal-platform-app/client.py"], cwd=ROOT,
                   env={**os.environ, "PLATFORM_URL": BASE, "PLATFORM_TOKEN": T0}, capture_output=True, text=True, timeout=60)
OUT.append(f"### X-00 examples/minimal-platform-app/client.py exit={p.returncode}\n{(p.stdout+p.stderr)[-1200:]}\n")

T1 = bootstrap(f"ticketapp-{ts}@r176.test")
c, t = http("GET", "/v1/models", T1); rec("X-11 discovery: models", c, t)
c, t = http("GET", "/v1/agent-tools", T1); rec("X-12 discovery: tools", c, t)
c, t = http("GET", "/v1/skills", T1); rec("X-13 discovery: skills", c, t)
c, t = http("POST", "/v1/workspaces", T1, {"name": "tickets"}); rec("X-14 workspace", c, t); ws = json.loads(t)["workspace_id"]
c, t = http("POST", "/v1/projects", T1, {"workspace_id": ws, "name": "q3"}); rec("X-15 project", c, t)
pj = json.loads(t).get("project_id") or json.loads(t).get("id")
c, t = http("POST", "/v1/execute", T1, {"ask": "Summarise: customer cannot log in after password reset.", "project_id": pj}); rec("X-16 execute (sync, project-scoped)", c, t)
c, t = http("GET", "/v1/usage", T1); rec("X-17 usage after 1 call", c, t)
c, t = http("POST", "/v1/webhooks", T1, {"url": "https://ticketapp.example.com/hook", "events": ["execution.succeeded"]}); rec("X-18 webhook subscription", c, t)

T2 = bootstrap(f"batchapp-{ts}@r176.test")
ids = []
for i in range(5):
    c, t = http("POST", "/v1/execute", T2, {"ask": f"doc-{i}", "execution_policy": {"async": True}}); ids.append(json.loads(t)["execution_id"])
time.sleep(1.5)
done = sum(1 for i in ids if json.loads(http("GET", f"/v1/executions/{i}", T2)[1]).get("status") == "succeeded")
OUT.append(f"### X-21 async fan-out 5 -> succeeded {done}/5\n")
c, t = http("POST", "/v1/execute", T2, {"ask": "continue", "conversation_id": "conv-batch-1"}); rec("X-22 conversation_id continuity (shape)", c, t, 300)
c, t = http("POST", "/v1/execute", T2, {"ask": "x", "execution_policy": {"strategy": "agent"}, "tools": {"allowed": ["git_push"]}}); rec("X-23 asks for capability it does not have => loud refusal", c, t)
c, t = http("GET", f"/v1/executions/{ids[0]}", T1); rec("X-24 consumer #1 reads consumer #2 execution => 404", c, t)
c, t = http("GET", "/v1/admin/system", T2); rec("X-25 consumer tries admin => 403", c, t)
c, t = http("GET", "/openapi.json"); rec("X-26 /openapi.json (machine-readable contract)", c, t, 200)
c, t = http("GET", "/docs"); rec("X-27 /docs", c, t, 120)
c, t = http("GET", "/v1/version"); rec("X-28 /v1/version (versioning discovery?)", c, t, 200)
open(os.path.join(HERE, "consumer_probes.txt"), "w").write("\n".join(OUT)); print("\n".join(o[:200] for o in OUT))
