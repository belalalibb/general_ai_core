"""R174 §4 — live E2E through the GATEWAY PROCESS ONLY (not the upstream directly).

Talks to uvicorn on 127.0.0.1:8800 exactly the way the platform's
RemoteGatewayAdapter would: gateway secret header + opaque route token header +
canonical RequestEnvelope. The AssemblyAI key is NOT here — it lives in the
gateway process env (GW_ASSEMBLYAI_API_KEY, platform credential mode); the
caller has no way to learn it.

Calls (≤3 paid, actual 2):
  A. success   — qwen3.5-4b-32k-fast, tiny prompt, max_tokens=8
  B. bad model — 'no-such-model-r174' → expect succeeded=false, model_unavailable
Plus 2 free control calls (no upstream spend):
  C. wrong route token → 4xx (route addressing only via header)
  D. describe → manifest projection for the assemblyai slug

Evidence is written key-redacted (the key is not known to this script; a grep
guard still runs against the gateway secret and the well-known key shape).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

GW = "http://127.0.0.1:8800"
OUT = Path(__file__).parent
SECRET = os.environ["GW_SECRET_CURRENT"]
HEADERS = {
    "X-Gateway-Secret": SECRET,
    "X-Gateway-Secret-Version": os.environ.get("GW_SECRET_CURRENT_VERSION", "1"),
    "X-Route-Token": "rt_aai_r174",
    "Content-Type": "application/json",
}


def envelope(model: str, request_id: str) -> dict:
    return {
        "operation": "generate_text",
        "model": model,
        "request_id": request_id,
        "tenant_id": "tenant-r174",
        "credential": {"mode": "platform"},
        "payload": {
            "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
            "max_tokens": 8,
            "temperature": 0,
        },
        "timeout_ms": 30000,
    }


def record(name: str, resp: httpx.Response, body_sent: dict | None) -> dict:
    try:
        parsed = resp.json()
    except ValueError:
        parsed = {"_raw_text": resp.text[:500]}
    rec = {
        "name": name,
        "http_status": resp.status_code,
        "request_headers": {k: ("<redacted>" if k == "X-Gateway-Secret" else v) for k, v in HEADERS.items()},
        "request_body": body_sent,
        "response_headers": {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "retry-after")},
        "response_body": parsed,
    }
    text = json.dumps(rec)
    assert SECRET not in text, "gateway secret leaked into evidence"
    assert not re.search(r"\b[0-9a-f]{32}\b", text), "32-hex token (AssemblyAI key shape) in evidence"
    (OUT / f"{name}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    return rec


def main() -> int:
    client = httpx.Client(timeout=60)
    results = []

    t = time.time()
    a = envelope("qwen3.5-4b-32k-fast", f"r174-a-{int(t)}")
    ra = client.post(f"{GW}/v1/execute", headers=HEADERS, json=a)
    results.append(record("A_success", ra, a))

    b = envelope("no-such-model-r174", f"r174-b-{int(t)}")
    rb = client.post(f"{GW}/v1/execute", headers=HEADERS, json=b)
    results.append(record("B_unknown_model", rb, b))

    bad_route = dict(HEADERS, **{"X-Route-Token": "rt_does_not_exist"})
    rc = client.post(f"{GW}/v1/execute", headers=bad_route, json=a)
    rec_c = record("C_bad_route_token", rc, None)
    rec_c["request_headers"]["X-Route-Token"] = "rt_does_not_exist"
    (OUT / "C_bad_route_token.json").write_text(json.dumps(rec_c, indent=2) + "\n")
    results.append(rec_c)

    rd = client.get(f"{GW}/v1/describe", headers=HEADERS)
    results.append(record("D_describe", rd, None))

    ok = True
    A = results[0]["response_body"]
    B = results[1]["response_body"]
    checks = {
        "A.http_200": results[0]["http_status"] == 200,
        "A.succeeded": A.get("succeeded") is True,
        "A.output.text_nonempty": bool((A.get("output") or {}).get("text")),
        "A.usage.tokens_present": (A.get("usage") or {}).get("input_tokens") is not None,
        "B.http_200": results[1]["http_status"] == 200,
        "B.succeeded_false": B.get("succeeded") is False,
        "B.category_model_unavailable": (B.get("error") or {}).get("category") == "model_unavailable",
        "B.retryable_false": (B.get("error") or {}).get("retryable") is False,
        "C.route_rejected_4xx": 400 <= results[2]["http_status"] < 500,
        "D.describe_200": results[3]["http_status"] == 200,
    }
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
        ok &= v
    (OUT / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
