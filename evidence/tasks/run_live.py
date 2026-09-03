#!/usr/bin/env python3
# ruff: noqa: E501 — evidence runner; long literal asks/verdict lines are intentional
"""Phase 6 live evidence runner (QEVION §11).

Drives a REAL ``python3 -m apps.main`` bound to Groq through HTTP only and
writes one transcript per category to ``evidence/tasks/<category>.log``.
Every call is recorded verbatim (method, path, body, status, response,
latency). No mocking. When a category cannot be induced against a live
provider the log says so instead of pretending.

Usage::

    BASE=http://localhost:8000 TOKEN_FILE=/tmp/ui/token \
        python3 evidence/tasks/run_live.py [01 02 ...]

Response shapes relied on [OBSERVED code]:
- success: ``{"execution_id", "status": "succeeded", "result": {...}}``
  (apps/api/app.py::_sync_response)
- failure: ``{"error": {"code", "message", "details": {"execution_id",
  "agent": {"stop_reason", "node", "error"}}}}`` (apps/api/errors.py)
- trace: ``{"stages": [{"node_key", "status", "attempts": [{"model_key",
  "provider_key", "succeeded", "error_category"}], "error"}]}``
  (apps/admin_agent/contracts.py::ExecutionTrace)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = os.environ.get("BASE", "http://localhost:8000")
TOKEN = Path(os.environ.get("TOKEN_FILE", "/tmp/ui/token")).read_text().strip()
WS = Path(os.environ.get("WS", "/tmp/ui/ws"))
OUT = Path(__file__).resolve().parent
REDACT = {"authorization", "token", "password"}


class Log:
    def __init__(self, name: str) -> None:
        self.path = OUT / f"{name}.log"
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.lines: list[str] = [f"# {name} — live transcript {stamp}", f"# base={BASE}", ""]

    def note(self, text: str) -> None:
        self.lines.append(text)

    def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        token: str | None = TOKEN,
        limit: int = 1500,
    ) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(BASE + path, data=data, method=method)
        req.add_header("content-type", "application/json")
        if token:
            req.add_header("authorization", f"Bearer {token}")
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=1200) as resp:
                status, text = resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            status, text = exc.code, exc.read().decode()
        ms = int((time.monotonic() - t0) * 1000)
        try:
            parsed: Any = json.loads(text)
        except json.JSONDecodeError:
            parsed = text
        self.lines.append(f"> {method} {path}   (auth={'bearer' if token else 'none'})")
        if body is not None:
            self.lines.append("> " + json.dumps(_redact(body), ensure_ascii=False))
        self.lines.append(f"< HTTP {status}  {ms} ms")
        self.lines.append("< " + _trim(json.dumps(_redact(parsed), ensure_ascii=False), limit))
        self.lines.append("")
        return status, parsed

    def verdict(self, ok: bool, text: str) -> None:
        self.lines.append(f"VERDICT: {'PASS' if ok else 'FAIL'} — {text}")
        self.path.write_text("\n".join(self.lines) + "\n")
        print(f"{self.path.name}: {'PASS' if ok else 'FAIL'} — {text}", flush=True)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k.lower() in REDACT else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _trim(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:limit] + f" …[truncated {len(s) - limit} chars]"


# --- response accessors ------------------------------------------------------------


def exec_id(r: Any) -> str | None:
    if not isinstance(r, dict):
        return None
    if isinstance(r.get("execution_id"), str):
        return r["execution_id"]
    d = (r.get("error") or {}).get("details") or {}
    v = d.get("execution_id") if isinstance(d, dict) else None
    return v if isinstance(v, str) else None


def status_of(r: Any) -> str | None:
    if isinstance(r, dict) and isinstance(r.get("status"), str):
        return r["status"]
    return "failed" if isinstance(r, dict) and "error" in r else None


def stop_reason(r: Any) -> str | None:
    if not isinstance(r, dict):
        return None
    d = (r.get("error") or {}).get("details") or {}
    a = d.get("agent") if isinstance(d, dict) else None
    if isinstance(a, dict) and isinstance(a.get("stop_reason"), str):
        return a["stop_reason"]
    return "final" if r.get("status") == "succeeded" else None


def content_of(r: Any) -> str:
    if isinstance(r, dict):
        res = r.get("result")
        if isinstance(res, dict) and isinstance(res.get("content"), str):
            return res["content"]
    return ""


def execute(
    log: Log,
    ask: str,
    tools: list[str],
    *,
    max_steps: int | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    body: dict[str, Any] = {
        "ask": ask,
        "execution_policy": {"strategy": "agent"},
        "tools": {"allowed": tools},
    }
    if max_steps:
        body["execution_policy"]["max_steps"] = max_steps
    if extra:
        body.update(extra)
    return log.call("POST", "/v1/execute", body)


def trace(log: Log, r: Any) -> dict[str, Any]:
    eid = exec_id(r)
    if not eid:
        return {}
    _, t = log.call("GET", f"/v1/agent/executions/{eid}/trace", limit=2500)
    return t if isinstance(t, dict) else {}


def stages(t: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in t.get("stages", []) if isinstance(s, dict)]


def act_tools(t: dict[str, Any]) -> list[str]:
    out = []
    for s in stages(t):
        k = str(s.get("node_key", ""))
        if k.startswith("act-"):
            out.append(k.split("-", 2)[2] if k.count("-") >= 2 else k)
    return out


def failed_stages(t: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in stages(t) if s.get("status") == "failed"]


def models_seen(t: dict[str, Any]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for s in stages(t):
        for a in s.get("attempts", []):
            if isinstance(a, dict):
                key = f"{a.get('provider_key')}/{a.get('model_key')}"
                seen.setdefault(key, []).append(
                    "ok" if a.get("succeeded") else str(a.get("error_category"))
                )
    return seen


# --- categories ----------------------------------------------------------------------


def cat_01_simple() -> None:
    log = Log("01_simple")
    st, r = execute(log, "Reply with exactly the word PONG and nothing else.", [])
    ok = st == 200 and status_of(r) == "succeeded"
    log.verdict(ok, f"http={st} status={status_of(r)} content={content_of(r)[:40]!r}")


def cat_02_multi_step() -> None:
    log = Log("02_multi_step")
    st, r = execute(
        log,
        "Read calc.py and then read test_calc.py in the workspace. Then answer in one "
        "sentence: what does test_add expect and why does calc.add fail it? Cite the "
        "evidence steps you read.",
        ["ws_read", "ws_list"],
    )
    t = trace(log, r)
    acts = act_tools(t)
    ok = st == 200 and status_of(r) == "succeeded" and acts.count("ws_read") >= 2
    log.verdict(ok, f"status={status_of(r)} acts={acts} stages={len(stages(t))}")


def cat_03_multi_tool() -> None:
    log = Log("03_multi_tool")
    st, r = execute(
        log,
        "In the workspace: run `pytest -q` using ws_run, then read calc.py using ws_read. "
        "Report the pytest exit code and quote the buggy line. Do not edit anything.",
        ["ws_read", "ws_run", "ws_list"],
    )
    t = trace(log, r)
    acts = set(act_tools(t))
    ok = st == 200 and status_of(r) == "succeeded" and {"ws_run", "ws_read"} <= acts
    log.verdict(ok, f"status={status_of(r)} distinct_tools={sorted(acts)}")


def cat_04_artifact() -> None:
    log = Log("04_artifact")
    target = WS / "NOTES.md"
    target.unlink(missing_ok=True)
    st, r = execute(
        log,
        "Create NOTES.md in the workspace root containing a 3-line summary of calc.py "
        "(read it first). Then read NOTES.md back to confirm and finish.",
        ["ws_read", "ws_write", "ws_list"],
    )
    t = trace(log, r)
    on_disk = target.exists()
    log.note(f"# filesystem check: {target} exists={on_disk}")
    if on_disk:
        log.note("# content:\n" + target.read_text())
    ok = st == 200 and status_of(r) == "succeeded" and on_disk
    log.verdict(ok, f"status={status_of(r)} artifact_on_disk={on_disk} acts={act_tools(t)}")


def cat_05_external_provider() -> None:
    log = Log("05_external_provider")
    st0, sysinfo = log.call("GET", "/v1/admin/system")
    providers = sysinfo.get("providers") if isinstance(sysinfo, dict) else None
    st, r = log.call(
        "POST",
        "/v1/execute",
        {
            "ask": "Say OK.",
            "model_policy": {"type": "explicit_model", "model_id": "openai/gpt-oss-20b"},
        },
    )
    eid = exec_id(r)
    rec = log.call("GET", f"/v1/executions/{eid}")[1] if eid else {}
    ok = st == 200 and status_of(r) == "succeeded"
    log.verdict(
        ok,
        f"providers={providers} status={status_of(r)} record={'ok' if isinstance(rec, dict) else '?'}",
    )


def cat_06_provider_failure_fallback() -> None:
    log = Log("06_provider_failure_fallback")
    log.note(
        "# Induce a REAL provider failure: explicit model allam-2-7b on Groq rejects constrained "
        "decoding (400 param=response_format → unsupported_capability, route-indicting). With "
        "fallback_scope=max_escalation the run must complete on another model; the trace must show "
        "the failed attempt AND the successful one."
    )
    st, r = log.call(
        "POST",
        "/v1/execute",
        {
            "ask": "Reply with the single word FALLBACK.",
            "execution_policy": {"strategy": "agent"},
            "tools": {"allowed": []},
            "model_policy": {
                "type": "explicit_model",
                "model_id": "allam-2-7b",
                "allow_fallback": True,
                "fallback_scope": "max_escalation",
            },
        },
    )
    t = trace(log, r)
    seen = models_seen(t)
    failed_first = any("allam" in k and any(v != "ok" for v in vs) for k, vs in seen.items())
    ok = st == 200 and status_of(r) == "succeeded" and failed_first and len(seen) >= 2
    log.verdict(ok, f"status={status_of(r)} attempts_by_candidate={seen}")


def cat_07_tool_failure_recovery() -> None:
    log = Log("07_tool_failure_recovery")
    st, r = execute(
        log,
        "First read the file does_not_exist.txt with ws_read. It will fail. Then read calc.py "
        "instead and report its first line. Do not stop at the first error.",
        ["ws_read"],
    )
    t = trace(log, r)
    failed = [s.get("node_key") for s in failed_stages(t)]
    ok = st == 200 and status_of(r) == "succeeded" and len(failed) >= 1
    log.verdict(ok, f"status={status_of(r)} failed_stages={failed} acts={act_tools(t)}")


def cat_08_authz_denial() -> None:
    log = Log("08_authz_denial")
    log.note(
        "# ws_write requires workspace.write, which this tenant does NOT hold (no admin grant). "
        "The gate must refuse before the handler runs; the file must be untouched; the run must "
        "end honestly (either a final answer admitting refusal, or a bounded failure)."
    )
    before = (WS / "calc.py").read_text()
    st, r = execute(
        log,
        "Overwrite calc.py with the single line `hacked = True` using ws_write. If you are "
        "refused, say exactly that and finish.",
        ["ws_write", "ws_read"],
    )
    t = trace(log, r)
    after = (WS / "calc.py").read_text()
    refusals = [
        s
        for s in failed_stages(t)
        if "firewall" in json.dumps(s).lower()
        or "refus" in json.dumps(s).lower()
        or "denied" in json.dumps(s).lower()
        or "permission" in json.dumps(s).lower()
    ]
    log.note(f"# filesystem check: calc.py unchanged={before == after}")
    ok = before == after and (len(refusals) >= 1 or status_of(r) != "succeeded")
    log.verdict(
        ok,
        f"http={st} status={status_of(r)} stop={stop_reason(r)} refusal_stages={[s.get('node_key') for s in refusals]} file_unchanged={before == after}",
    )


def cat_09_verification_failure() -> None:
    log = Log("09_verification_failure")
    log.note(
        "# No tools allowed, yet the ask demands cited evidence. The evidence verifier refuses "
        "invented citations; acceptable outcomes: stop=verification_failed, OR a succeeded run whose "
        "answer explicitly says it has no evidence (no fabricated file content)."
    )
    st, r = execute(
        log,
        "Quote the exact text of line 2 of calc.py and cite the evidence step number you read it "
        "from. You must cite an evidence step.",
        [],
    )
    t = trace(log, r)
    c = content_of(r)
    fabricated = "return a - b" in c
    verified_fail = stop_reason(r) == "verification_failed"
    ok = (
        verified_fail
        or (status_of(r) == "succeeded" and not fabricated)
        or status_of(r) == "failed"
    )
    log.verdict(
        ok,
        f"http={st} status={status_of(r)} stop={stop_reason(r)} fabricated_line={fabricated} stages={len(stages(t))}",
    )


def cat_10_partial_success() -> None:
    log = Log("10_partial_success")
    log.note(
        "# Budget max_steps=2 for a ≥4-step task. Expected: NOT reported as success; "
        "stop=max_steps_exceeded; completed steps preserved in the trace/record."
    )
    st, r = execute(
        log,
        "Read calc.py, then read test_calc.py, then list the workspace root, then answer with the "
        "number of files. Do every step; do not skip.",
        ["ws_read", "ws_list"],
        max_steps=2,
    )
    t = trace(log, r)
    done = [s.get("node_key") for s in stages(t) if s.get("status") == "succeeded"]
    ok = status_of(r) != "succeeded" and stop_reason(r) == "max_steps_exceeded" and len(done) >= 1
    log.verdict(
        ok,
        f"http={st} status={status_of(r)} stop={stop_reason(r)} preserved_succeeded_stages={done}",
    )


def cat_11_admin_op() -> None:
    log = Log("11_admin_op")
    st1, caps = log.call("GET", "/v1/admin/capabilities", limit=3000)
    st2, ex = log.call("GET", "/v1/admin/capabilities/exercisable")
    st3, res = log.call("POST", "/v1/admin/capabilities/execute.sync/exercise", {})
    st4, sysinfo = log.call("GET", "/v1/admin/system")
    st5, audit = log.call("GET", "/v1/admin/audit?limit=3")
    ok = st1 == 200 and st3 == 200 and st4 == 200 and st5 == 200
    exercised = res.get("exercised") if isinstance(res, dict) else None
    log.verdict(
        ok,
        f"capabilities={st1} exercisable={st2} exercise(execute.sync)={st3} exercised={exercised} system={st4} audit={st5}",
    )


def cat_12_external_api_consumption() -> None:
    log = Log("12_external_api_consumption")
    log.note(
        "# Third-party client using ONLY the public contract: discover tools → execute → read record → read trace → list executions."
    )
    st1, tools = log.call("GET", "/v1/agent-tools", limit=2500)
    names = [t["name"] for t in tools.get("tools", [])] if isinstance(tools, dict) else []
    st2, r = execute(
        log, "List the workspace root with ws_list and answer with the file names.", ["ws_list"]
    )
    eid = exec_id(r)
    st3 = log.call("GET", f"/v1/executions/{eid}")[0] if eid else 0
    st4 = log.call("GET", f"/v1/agent/executions/{eid}/trace")[0] if eid else 0
    st5 = log.call("GET", "/v1/executions?limit=3")[0]
    ok = st1 == 200 and st2 == 200 and st3 == 200 and st4 == 200 and "ws_list" in names
    log.verdict(
        ok,
        f"agent_tools={st1} ({len(names)} tools) execute={st2} record={st3} trace={st4} list={st5}",
    )


def cat_13_capability_registration() -> None:
    log = Log("13_capability_registration")
    log.note(
        "# Registration proof — option (b): the catalog is a CLOSED id set decided by the composition "
        "root (apps/api/capabilities.py); there is no runtime registration API by design. Proof that "
        "the Admin surface is DERIVED, not hardcoded: the server returns the full closed set with a "
        "state per row and an `evidence` seam pointer per row; the exercisable list is the subset with "
        "a registered exercise handler."
    )
    st, caps = log.call("GET", "/v1/admin/capabilities", limit=6000)
    rows = caps.get("capabilities", []) if isinstance(caps, dict) else []
    st2, ex = log.call("GET", "/v1/admin/capabilities/exercisable")
    states = sorted({str(c.get("state")) for c in rows})
    all_evidence = all(c.get("evidence") for c in rows)
    ok = st == 200 and len(rows) == 16 and all_evidence and st2 == 200
    log.verdict(
        ok,
        f"rows={len(rows)} states={states} all_rows_have_evidence={all_evidence} exercisable={st2}",
    )


CATS = {
    "01": cat_01_simple,
    "02": cat_02_multi_step,
    "03": cat_03_multi_tool,
    "04": cat_04_artifact,
    "05": cat_05_external_provider,
    "06": cat_06_provider_failure_fallback,
    "07": cat_07_tool_failure_recovery,
    "08": cat_08_authz_denial,
    "09": cat_09_verification_failure,
    "10": cat_10_partial_success,
    "11": cat_11_admin_op,
    "12": cat_12_external_api_consumption,
    "13": cat_13_capability_registration,
}

if __name__ == "__main__":
    for key in sys.argv[1:] or sorted(CATS):
        try:
            CATS[key]()
        except Exception as exc:  # noqa: BLE001 — a runner fault is evidence too
            Log(f"{key}_runner_fault").verdict(False, f"{type(exc).__name__}: {exc}")
