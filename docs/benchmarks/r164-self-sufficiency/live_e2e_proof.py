"""R164 live E2E proof — the SHARED runtime engineers a REAL workspace under Admin authorization.

Runs the composed platform (``build_runtime_profile``) against a real git workspace
with a bare remote. The ONLY substitution is the model's words (a scripted adapter
on the SAME ExecutionService) because the sandbox's LLM proxy refuses free-plan
credits — every other component is the production one: ONE ToolRegistry, ONE
CapabilityFirewall, ONE AuthorizationLedger, real filesystem, real subprocess,
real git.

Usage:  python3 docs/benchmarks/r164-self-sufficiency/live_e2e_proof.py /path/to/workspace
The workspace must be a git checkout with a pushable ``origin``.
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

from apps.composition.engineering import grant_engineering_writes  # noqa: E402
from apps.composition.runtime import build_runtime_profile  # noqa: E402
from core.contracts.engineering import EngineeringAct  # noqa: E402
from core.engineering import EngineeringBundle  # noqa: E402
from tests.agent.world import final, model_says, tool_call  # noqa: E402
from tests.execution.test_multi_model import ScriptedAdapter  # noqa: E402

WS = os.path.abspath(sys.argv[1])
env = dict(os.environ)
env.pop("GSK_API_KEY", None)
env.pop("GROQ_API_KEY", None)
env.update({"AGENT_WORKSPACE_ROOT": WS, "AGENT_WORKSPACE_COMMANDS": "python3,pytest"})
profile = build_runtime_profile(env)
agent = profile.agent
assert agent is not None and profile.demo_principal is not None
rt = agent.surface.runtime
p = profile.demo_principal
svc = rt._execution  # noqa: SLF001 — proof script substitutes ONLY the model output
scripted = ScriptedAdapter()
for pid in list(svc._adapters):  # noqa: SLF001
    svc._adapters[pid] = scripted  # type: ignore[index]  # noqa: SLF001
bundle = next(o for o in gc.get_objects() if isinstance(o, EngineeringBundle))
ledger = bundle.ledger


def run(task: str, tools: list[str]):  # type: ignore[no-untyped-def]
    return asyncio.run(
        rt.run(
            tenant_id=p.tenant_id,
            user_id=p.user_id,
            task={"ask": task},
            tools=[agent.surface.catalog[n] for n in tools],
        )
    )


def show(out, n=None) -> None:  # type: ignore[no-untyped-def]
    for s in out.report.steps[:n]:
        ob = s.observation
        print(
            "   step",
            s.index,
            ob.get("tool"),
            ob.get("status"),
            json.dumps(ob.get("result") or ob.get("error"))[:150],
        )


def exists(name: str) -> bool:
    return os.path.exists(os.path.join(WS, name))


print("== 1. NEGATIVE: tenant holds READ permissions only -> firewall REFUSES ws_write")
scripted.script = [
    model_says(tool_call("ws_write", path="NOTE.md", content="hello\n")),
    model_says(final("done")),
]
out = run("write NOTE.md", ["ws_write"])
show(out, 1)
print("   NOTE.md exists:", exists("NOTE.md"))
assert out.report.steps[0].observation["status"] == "refused" and not exists("NOTE.md")

print("== 2. Admin grants workspace.write + git.write, still NO ticket -> handler FAILS as data")
grant_engineering_writes(agent.firewall, p.tenant_id, frozenset({"workspace.write", "git.write"}))
scripted.script = [
    model_says(tool_call("ws_write", path="NOTE.md", content="hello\n")),
    model_says(final("done")),
]
out = run("write NOTE.md", ["ws_write"])
show(out, 1)
print("   NOTE.md exists:", exists("NOTE.md"))
assert out.report.steps[0].observation["status"] == "failed" and not exists("NOTE.md")

print("== 3. Admin issues ticket [fs.write, git.commit, git.push] uses=3")
ticket = ledger.issue(
    tenant_id=p.tenant_id,
    workspace=bundle.workspace_label,
    acts=[EngineeringAct.FS_WRITE, EngineeringAct.GIT_COMMIT, EngineeringAct.GIT_PUSH],
    issued_by=p.user_id,
    uses=3,
    note="R164 live proof",
)
tid = str(ticket.id)
print("   ticket", tid[:8], "uses", ticket.uses_remaining)

print(
    "== 4. POSITIVE: write -> status -> commit -> push -> log (real fs, real git, real subprocess)"
)
scripted.script = [
    model_says(
        tool_call("ws_write", path="NOTE.md", content="hello from agent\n", authorization_id=tid)
    ),
    model_says(tool_call("git_status")),
    model_says(
        tool_call(
            "git_commit",
            message="feat: NOTE.md written by the shared agent runtime",
            authorization_id=tid,
        )
    ),
    model_says(tool_call("git_push", branch="main", authorization_id=tid)),
    model_says(tool_call("git_log", limit=2)),
    model_says(final("wrote, committed and pushed NOTE.md", 1, 3, 4)),
]
out = run(
    "add NOTE.md, commit, push", ["ws_write", "git_status", "git_commit", "git_push", "git_log"]
)
show(out)
print(
    "   stop:",
    out.report.stop_reason,
    "| ok/failed:",
    out.report.summary["tool_calls_ok"],
    out.report.summary["tool_calls_failed"],
)
assert out.report.summary["tool_calls_ok"] == 5 and out.report.summary["tool_calls_failed"] == 0

print("== 5. Ticket exhausted -> next privileged act refused as data")
print("   uses_remaining:", ledger.list_for_tenant(p.tenant_id)[0].uses_remaining)
scripted.script = [
    model_says(tool_call("ws_write", path="AGAIN.md", content="x", authorization_id=tid)),
    model_says(final("done")),
]
out = run("write again", ["ws_write"])
show(out, 1)
print("   AGAIN.md exists:", exists("AGAIN.md"))
assert not exists("AGAIN.md")

print("== 6. Jail + command policy bind even WITH a valid ticket and exec permission")
t2 = ledger.issue(
    tenant_id=p.tenant_id,
    workspace=bundle.workspace_label,
    acts=[EngineeringAct.FS_WRITE, EngineeringAct.CMD_RUN],
    issued_by=p.user_id,
    uses=5,
)
grant_engineering_writes(agent.firewall, p.tenant_id, frozenset({"workspace.exec"}))
scripted.script = [
    model_says(
        tool_call("ws_write", path="../escape.txt", content="x", authorization_id=str(t2.id))
    ),
    model_says(tool_call("ws_write", path=".env", content="SECRET=1", authorization_id=str(t2.id))),
    model_says(tool_call("ws_run", argv=["bash", "-lc", "id"], authorization_id=str(t2.id))),
    model_says(tool_call("ws_run", argv=["python3", "calc.py"], authorization_id=str(t2.id))),
    model_says(final("done")),
]
out = run("try escapes", ["ws_write", "ws_run"])
show(out, 4)
escaped = os.path.exists(os.path.join(os.path.dirname(WS), "escape.txt"))
t2_left = ledger.list_for_tenant(p.tenant_id)[1].uses_remaining
print(
    "   escape.txt outside jail exists:",
    escaped,
    "| .env exists:",
    exists(".env"),
    "| t2 uses left:",
    t2_left,
)
assert not escaped and not exists(".env") and t2_left == 4

print("== 7. Audit trail (surface=engineering_authorization)")
ev = [
    e.details
    for e in ledger._audit.read(p.tenant_id)
    if e.details.get("surface") == "engineering_authorization"
]  # noqa: SLF001
print(
    "   ",
    dict(Counter(str(d.get("act")) for d in ev)),
    "| refusal reasons:",
    sorted({str(d.get("reason")) for d in ev if d.get("act") == "refuse"}),
)
print("PROOF OK")
