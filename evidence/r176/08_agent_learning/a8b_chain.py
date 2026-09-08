# ruff: noqa: E501, E741  -- R176 Phase-A probe script (evidence, not product code)
"""A8b: drive the learning lifecycle with the REAL act bodies (sanitize/admit/promote verdicts) on a
sample carrying a Groq-shaped secret the sanitizer does not recognise (see sanitizer_gap_check.txt).
Question: can it reach GOLD and retrieval? Second sample carries an sk- token (recognised) to show the gate working."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8177"
LOG = "/tmp/r176_sec.log"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []
GSK = "gsk_" + "F" * 28
SK = "sk-" + "A" * 40


def http(m, p, tok=None, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m)
    if tok:
        r.add_header("Authorization", f"Bearer {tok}")
    if d is not None:
        r.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def rec(l, c, t, n=500):
    OUT.append(f"### {l}\n{t.replace(GSK, '<gsk-marker>').replace(SK, '<sk-marker>')[:n]} [{c}]\n")


def login(email):
    c, t = http("POST", "/v1/auth/login", body={"email": email, "password": "Correct-Horse-9"})
    return json.loads(t)["token"]


ADM = login("admin@r176.test")


def chain(tag, secret):
    c, t = http(
        "POST",
        "/v1/admin/learning/samples",
        ADM,
        {"knowledge_key": f"r176-{tag}", "knowledge_value": {"text": f"the key is {secret}"}},
    )
    rec(f"{tag}-01 capture", c, t)
    sid = json.loads(t)["id"]
    c, t = http("POST", f"/v1/admin/learning/samples/{sid}/scan", ADM)
    rec(f"{tag}-02 scan", c, t)
    c, t = http("POST", f"/v1/admin/learning/samples/{sid}/sanitize", ADM, {"passed": True})
    rec(f"{tag}-03 sanitize passed=True (reviewer act; must be REFUSED if scan had findings)", c, t)
    c, t = http(
        "POST", f"/v1/admin/learning/samples/{sid}/evaluate", ADM, {"output": {"text": "ok"}}
    )
    rec(f"{tag}-04 evaluate", c, t, 300)
    c, t = http(
        "POST",
        f"/v1/admin/learning/samples/{sid}/admit",
        ADM,
        {"privacy_policy_allows": True, "tenant_user_policy_allows": True},
    )
    rec(f"{tag}-05 admit", c, t)
    c, t = http(
        "POST",
        f"/v1/admin/learning/samples/{sid}/promote",
        ADM,
        {"offline_eval_pass": True, "regression_pass": True},
    )
    rec(f"{tag}-06 promote", c, t)
    c, t = http("GET", "/v1/admin/learning/learned", ADM)
    rec(f"{tag}-07 GOLD keys", c, t)
    c, t = http("POST", "/v1/admin/learning/ask", ADM, {"key": f"r176-{tag}"})
    rec(f"{tag}-08 learning/ask retrieval", c, t)
    OUT.append(f"### {tag}-08b secret in retrieval: {secret in t}\n")
    c, t = http("POST", "/v1/execute", ADM, {"ask": f"tell me about r176-{tag}"})
    OUT.append(
        f"### {tag}-09 execute gold_blocks: {re.findall(r'gold_blocks\":(\\d+)', t)}; secret in result: {secret in t}\n"
    )


chain("gskshape", GSK)
chain("skshape", SK)
open(os.path.join(HERE, "learning_chain.txt"), "w").write("\n".join(OUT))
print("\n".join(o[:240] for o in OUT))
