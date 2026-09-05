#!/usr/bin/env python3
"""R173 §1.5 — §6 seven exercises E1–E7 against a RUNNING platform process.

Records HTTP facts only (status, error code/category, stage names, counts).
Never records a token, a key, or a response body verbatim; every line is
scanned against every secret-shaped environment value before it is written.

Env (all required):
  R173_BASE           http://127.0.0.1:<port>
  R173_ADMIN_TOKEN    session token for an is_admin user
  R173_USER_TOKEN     session token for a non-admin user
  R173_LABEL          composition label (hermetic_local_echo | live_genspark_llm)
  R173_E_OUT          output jsonl path

Exercises (R148 §6 vocabulary):
  E1 agent turn WITH tools.allowed=[source_list, source_read]
  E2 agent turn WITHOUT tools
  E3 exercisable listing -> exercise execute.sync -> unknown capability id
  E4 console auth boundary (anon / garbage bearer / non-admin / admin)
  E5 existence oracle (unknown uuid + malformed id on record/trace/diagnosis)
  E6 unknown tool name up front (validation_error, no execution created)
  E7 composed source reader denylist (via source_read on the platform agent)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

BASE = os.environ["R173_BASE"].rstrip("/")
ADMIN = os.environ["R173_ADMIN_TOKEN"]
USER = os.environ["R173_USER_TOKEN"]
LABEL = os.environ["R173_LABEL"]
OUT = Path(os.environ["R173_E_OUT"])
OUT.parent.mkdir(parents=True, exist_ok=True)

_SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)
_SECRET_PREFIX_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|gsk-[A-Za-z0-9._-]{20,}")
_SECRETS = [v for k, v in os.environ.items() if _SECRET_NAME_RE.search(k) and len(v) >= 12]
_SECRETS += [ADMIN, USER]


def record(section: str, **facts: Any) -> None:
    line = json.dumps({"section": section, "label": LABEL, "utc": datetime.now(UTC).isoformat(timespec="seconds"), **facts}, sort_keys=True)
    for s in _SECRETS:
        assert s not in line, f"secret value would leak into evidence ({section})"
    assert not _SECRET_PREFIX_RE.search(line), f"secret-shaped literal in evidence ({section})"
    with OUT.open("a") as fh:
        fh.write(line + "\n")
    print(line)


def bearer(tok: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"} if tok else {}


C = httpx.Client(base_url=BASE, timeout=180.0)


def err(r: httpx.Response) -> dict[str, Any]:
    try:
        e = r.json().get("error") or {}
    except Exception:
        return {}
    return {k: e.get(k) for k in ("code", "message", "category", "details") if k in e}


def agent_turn(name: str, ask: str, tools: list[str] | None) -> None:
    body: dict[str, Any] = {"ask": ask, "execution_policy": {"strategy": "agent", "max_steps": 4}}
    if tools is not None:
        body["tools"] = {"allowed": tools}
    t0 = time.perf_counter()
    r = C.post("/v1/execute", json=body, headers=bearer(ADMIN))  # admin: trace is tenant-scoped
    ms = int((time.perf_counter() - t0) * 1000)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    exec_id = j.get("execution_id") or (j.get("error") or {}).get("details", {}).get("execution_id")
    facts: dict[str, Any] = {"http": r.status_code, "latency_ms": ms, "status": j.get("status"), "stop_reason": j.get("stop_reason"), "error": err(r), "execution_id": exec_id}
    if exec_id:
        rec = C.get(f"/v1/executions/{exec_id}", headers=bearer(ADMIN))
        tr = C.get(f"/v1/agent/executions/{exec_id}/trace", headers=bearer(ADMIN))
        stages: list[str] = []
        if tr.status_code == 200:
            tj = tr.json()
            for st in tj.get("stages") or tj.get("trace") or []:
                if isinstance(st, dict):
                    stages.append(str(st.get("node_key") or st.get("name")))
        facts.update(record_http=rec.status_code, record_status=(rec.json() or {}).get("status") if rec.status_code == 200 else None,
                     trace_http=tr.status_code, stage_count=len(stages), act_stages=sum(1 for s in stages if s.startswith("act")), stages=stages[:12])
    record(name, **facts)


# ---------------------------------------------------------------- E1 / E2
agent_turn("E1.agent_with_tools", "List the files under core/agent and read the first one's docstring.", ["source_list", "source_read"])
agent_turn("E2.agent_no_tools", "Reply with the single word PONG.", None)

# ---------------------------------------------------------------- E3
r = C.get("/v1/admin/capabilities/exercisable", headers=bearer(ADMIN))
ex_ids = [e if isinstance(e, str) else e.get("capability_id") or e.get("id") for e in (r.json().get("exercisable") if r.status_code == 200 else [])]
record("E3.exercisable", http=r.status_code, count=len(ex_ids), ids=ex_ids)
target = "execute.sync" if "execute.sync" in ex_ids else (ex_ids[0] if ex_ids else "execute.sync")
r = C.post(f"/v1/admin/capabilities/{target}/exercise", json={}, headers=bearer(ADMIN))
j = r.json() if r.status_code == 200 else {}
res = j.get("result") or {}
ev = res.get("evidence") or {}
record("E3.exercise", http=r.status_code, capability_id=j.get("capability_id"), exercised=res.get("exercised"),
       evidence_status=ev.get("status") if isinstance(ev, dict) else None, result_keys=sorted(res.keys())[:10], error=err(r))
r = C.post("/v1/admin/capabilities/no.such.capability/exercise", json={}, headers=bearer(ADMIN))
record("E3.exercise_unknown", http=r.status_code, error=err(r))

# ---------------------------------------------------------------- E4
anon = C.get("/v1/admin/system")
garbage = C.get("/v1/admin/system", headers=bearer("not-a-real-session-token-" + uuid4().hex))
nonadmin = C.get("/v1/admin/system", headers=bearer(USER))
admin_sys = C.get("/v1/admin/system", headers=bearer(ADMIN))
admin_audit = C.get("/v1/admin/audit", headers=bearer(ADMIN))
record("E4.console_boundary", anon=anon.status_code, anon_error=err(anon), garbage=garbage.status_code, garbage_error=err(garbage),
       anon_garbage_identical=(anon.status_code == garbage.status_code and anon.text == garbage.text),
       nonadmin=nonadmin.status_code, nonadmin_error=err(nonadmin), admin_system=admin_sys.status_code, admin_audit=admin_audit.status_code)

# ---------------------------------------------------------------- E5
unknown = str(uuid4())
rows = {}
for label, path in {"record_unknown": f"/v1/executions/{unknown}", "record_malformed": "/v1/executions/not-a-uuid",
                    "trace_unknown": f"/v1/agent/executions/{unknown}/trace", "trace_malformed": "/v1/agent/executions/not-a-uuid/trace",
                    "diag_unknown": f"/v1/agent/executions/{unknown}/diagnosis", "diag_malformed": "/v1/agent/executions/not-a-uuid/diagnosis"}.items():
    rr = C.get(path, headers=bearer(ADMIN))
    rows[label] = {"http": rr.status_code, "error": err(rr)}
record("E5.existence_oracle", **rows)

# ---------------------------------------------------------------- E6
r = C.post("/v1/execute", json={"ask": "x", "execution_policy": {"strategy": "agent"}, "tools": {"allowed": ["shell_exec"]}}, headers=bearer(USER))
record("E6.unknown_tool", http=r.status_code, error=err(r), execution_created=bool((r.json() if r.status_code < 500 else {}).get("execution_id")))

# ---------------------------------------------------------------- E7 (in-process reader, same object the runtime composes)
sys.path.insert(0, os.getcwd())
from apps.composition.runtime import _source_reader  # noqa: E402

reader = _source_reader(os.environ.get("AGENT_SOURCE_ROOT", os.getcwd()))
probes = [".env", ".git/config", "secrets.pem", "id_rsa.key", "../../etc/passwd", ".ENV", ".e\u200bnv", "core/agent/runtime.py",
          "engineering/verification/green_manifest.json", "core/providers/accounts.py", "infrastructure/security/password.py"]
results = {}
for p in probes:
    try:
        reader.read_file(p)  # type: ignore[union-attr]
        results[p] = "admitted"
    except Exception as e:  # noqa: BLE001
        results[p] = type(e).__name__
record("E7.source_reader_denylist", reader_patterns=len(reader.denied_patterns) if reader else None, probes=results)
record("done", exercises=7)
