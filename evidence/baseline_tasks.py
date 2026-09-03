"""Representative multi-step task set — the §5 baseline, re-runnable.

Runs the SHARED ``core.agent.AgentRuntime`` over the real routing/execution/
tool-gate chain with a scripted model (so the numbers measure the RUNTIME,
not a provider). Prints one JSON object; ``python3 evidence/baseline_tasks.py``
exits 0 always — the numbers are the result.

Categories (one row each): simple, multi_step, multi_tool_coding, artifact,
provider_transient (retryable error once), provider_hard (non-retryable error
once, second provider registered), tool_failure_recovery, verification_failure,
partial_success_budget (budget exhausted after real work), authz_denial.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any
from uuid import uuid4

sys.path.insert(0, ".")

from core.agent import AgentToolSpec  # noqa: E402
from core.contracts.base import JsonObject  # noqa: E402
from core.contracts.domain import (  # noqa: E402
    BindingAvailability,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import ProviderError, ProviderErrorCategory  # noqa: E402
from core.security.firewall import TenantPolicy  # noqa: E402
from tests.agent.world import (  # noqa: E402
    ENTITLEMENT,
    PERM_READ,
    PERM_WRITE,
    TENANT,
    AgentWorld,
    final,
    make_tool,
    model_says,
    tool_call,
)
from tests.execution.test_multi_model import ScriptedAdapter, _manifest  # noqa: E402

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TRANSIENT = ProviderError(
    category=ProviderErrorCategory.RETRYABLE_SERVER_ERROR,
    retryable=True,
    safe_message="scripted 503",
)
HARD = ProviderError(
    category=ProviderErrorCategory.BAD_REQUEST,
    retryable=False,
    safe_message="scripted 400",
)
OUTAGE = ProviderError(
    category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
    retryable=False,
    safe_message="scripted outage",
)


def _grant(world: AgentWorld, *perms: str) -> None:
    world.firewall.set_tenant_policy(
        TENANT,
        TenantPolicy(
            granted_permissions=frozenset(perms), granted_entitlements=frozenset({ENTITLEMENT})
        ),
    )


class Runner:
    def __init__(self, world: AgentWorld) -> None:
        self.world, self.runs = world, 0

    async def run(self, _: JsonObject) -> JsonObject:
        self.runs += 1
        ok = self.world.fs.files.get("calc.py") == FIXED
        return {"passed": ok, "failed": 0 if ok else 1}


def _tests_rule(result: JsonObject) -> str | None:
    return None if result.get("passed") is True else f"tests failed: {result.get('failed')}"


def coding_tools(world: AgentWorld) -> tuple[list[AgentToolSpec], Runner]:
    world.fs.files = {"calc.py": BUGGY, "test_calc.py": "from calc import add\n"}
    _grant(world, PERM_READ, PERM_WRITE)
    runner = Runner(world)
    tool = make_tool("run_tests", [PERM_READ])
    world.tool_registry.register(tool)
    spec = AgentToolSpec(
        tool=tool,
        handler=runner.run,
        permission=PERM_READ,
        resource="fs:workspace",
        entitlement=ENTITLEMENT,
        description="Run the tests.",
        verify_result=_tests_rule,
    )
    return [world.read_spec(), world.write_spec(), spec], runner


def add_second_provider(world: AgentWorld) -> ScriptedAdapter:
    """A second provider serving the SAME model (fallback route material)."""
    second = ScriptedAdapter([])
    provider = Provider(
        id=uuid4(),
        provider_key="prov_backup",
        display_name="prov_backup",
        status=ProviderStatus.ACTIVE,
        auth_types=["api_key"],
        supports_account_pool=False,
    )
    world.providers.register(provider, _manifest("prov_backup"))
    model = world.models.get("model-agent")
    world.bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name="vendor/model-agent",
            availability=BindingAvailability.AVAILABLE,
        )
    )
    world.execution_service._adapters[provider.id] = second  # type: ignore[index]
    world.execution_service._credential_refs[provider.id] = "secret-ref://backup"  # type: ignore[index]
    return second


def measure(
    name: str,
    world: AgentWorld,
    task: JsonObject,
    tools: list[AgentToolSpec],
    *,
    expect_success: bool,
    extra: dict[str, Any] | None = None,
    run_kwargs: dict[str, Any] | None = None,
) -> JsonObject:
    t0 = time.perf_counter()
    outcome = world.run(task, tools=tools, **(run_kwargs or {}))
    report = outcome.report
    prompt_chars = sum(len(str(r.payload.get("ask", ""))) for r in world.adapter.requests)
    row: JsonObject = {
        "task": name,
        "expected": "success" if expect_success else "bounded_failure",
        "stop_reason": report.stop_reason,
        "succeeded": report.succeeded,
        "steps": report.summary["steps"],
        "tool_calls_ok": report.summary["tool_calls_ok"],
        "tool_calls_failed": report.summary["tool_calls_failed"],
        "evidence_items": len(report.evidence),
        "verified": bool(report.verification and report.verification.get("verified")),
        "model_calls": len(world.adapter.requests),
        "prompt_chars_total": prompt_chars,
        "wall_ms": int((time.perf_counter() - t0) * 1000),
    }
    row["outcome"] = "pass" if report.succeeded == expect_success else "fail"
    if extra:
        row.update({k: (v() if callable(v) else v) for k, v in extra.items()})
    return row


def main() -> None:  # noqa: PLR0915
    rows: list[JsonObject] = []
    ask: JsonObject = {"ask": "fix calc.py so tests pass"}

    # 1 simple
    w = AgentWorld([model_says(final("42"))])
    rows.append(measure("simple", w, {"ask": "what is 6*7"}, [w.read_spec()], expect_success=True))

    # 2 multi_step (two reads then cited final)
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="README.md")),
            model_says(tool_call("fs", path="src/app.py")),
            model_says(final("summary", 1, 2)),
        ]
    )
    rows.append(
        measure("multi_step", w, {"ask": "summarize"}, [w.read_spec()], expect_success=True)
    )

    # 3 multi_tool_coding
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="calc.py")),
            model_says(tool_call("run_tests")),
            model_says(tool_call("fs_write", path="calc.py", content=FIXED)),
            model_says(tool_call("run_tests")),
            model_says(final("fixed", 1, 3, 4)),
        ]
    )
    tools, runner = coding_tools(w)
    rows.append(
        measure(
            "multi_tool_coding",
            w,
            ask,
            tools,
            expect_success=True,
            extra={"file_fixed": lambda: w.fs.files.get("calc.py") == FIXED},
        )
    )

    # 4 artifact production
    w = AgentWorld(
        [
            model_says(tool_call("fs_write", path="out/report.md", content="# r")),
            model_says(final("written", 1)),
        ]
    )
    _grant(w, PERM_READ, PERM_WRITE)
    rows.append(
        measure(
            "artifact",
            w,
            {"ask": "write report"},
            [w.read_spec(), w.write_spec()],
            expect_success=True,
            extra={"artifact_present": lambda: "out/report.md" in w.fs.files},
        )
    )

    # 5 provider transient: one retryable error mid-run (service retries once by default=0 here)
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="README.md")),
            TRANSIENT,
            model_says(final("ok", 1)),
        ]
    )
    rows.append(
        measure("provider_transient_midrun", w, {"ask": "x"}, [w.read_spec()], expect_success=True)
    )

    # 6 provider hard failure mid-run, a SECOND provider exists for the same model
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="README.md")),
            HARD,
            model_says(final("ok", 1)),
        ]
    )
    backup = add_second_provider(w)
    backup.script = [model_says(final("ok from backup", 1))]
    rows.append(
        measure(
            "provider_hard_midrun_backup_exists",
            w,
            {"ask": "x"},
            [w.read_spec()],
            expect_success=True,
            extra={"backup_used": lambda: len(backup.requests) > 0},
        )
    )

    # 6b persistent provider OUTAGE on the primary from step 2 on; backup provider exists
    w = AgentWorld([model_says(tool_call("fs", path="README.md"))] + [OUTAGE] * 6)
    backup = add_second_provider(w)
    backup.script = [model_says(final("ok from backup", 1))] * 3
    rows.append(
        measure(
            "provider_outage_persistent_backup_exists",
            w,
            {"ask": "x"},
            [w.read_spec()],
            expect_success=True,
            extra={"backup_used": lambda: len(backup.requests) > 0},
        )
    )

    # 7 tool failure -> recovery (bad path, then correct path)
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="missing.md")),
            model_says(tool_call("fs", path="README.md")),
            model_says(final("recovered", 2)),
        ]
    )
    rows.append(
        measure("tool_failure_recovery", w, {"ask": "x"}, [w.read_spec()], expect_success=True)
    )

    # 8 verification failure: invented evidence, never corrected -> must NOT succeed
    w = AgentWorld([model_says(final("done", 7))] * 3, max_steps=3)
    rows.append(
        measure(
            "verification_failure_not_success",
            w,
            {"ask": "x"},
            [w.read_spec()],
            expect_success=False,
        )
    )

    # 9 partial success: real work done, budget exhausted before final
    w = AgentWorld(
        [
            model_says(tool_call("fs", path="calc.py")),
            model_says(tool_call("fs_write", path="calc.py", content=FIXED)),
            model_says(tool_call("run_tests")),
            model_says(final("fixed", 1, 2, 3)),
        ],
        max_steps=3,
    )
    tools, runner = coding_tools(w)
    row = measure(
        "partial_success_budget_exhausted",
        w,
        ask,
        tools,
        expect_success=False,
        extra={"work_preserved": lambda: w.fs.files.get("calc.py") == FIXED},
    )
    # Can the work be RESUMED? Only if the runtime can seed a new run from the prior record.
    row["resumable_primitive_exists"] = hasattr(w.runtime, "resume") or False
    rows.append(row)

    # 10 authz denial: write not granted (default world grants read only)
    w = AgentWorld(
        [
            model_says(tool_call("fs_write", path="x", content="y")),
            model_says(
                final(
                    "could not write",
                )
            ),
        ]
    )
    rows.append(
        measure(
            "authz_denial",
            w,
            {"ask": "x"},
            [w.read_spec(), w.write_spec()],
            expect_success=True,
            extra={"handler_ran": lambda: bool(w.fs.writes)},
        )
    )

    summary = {
        "pass": sum(1 for r in rows if r["outcome"] == "pass"),
        "fail": sum(1 for r in rows if r["outcome"] == "fail"),
        "verified_completions": sum(1 for r in rows if r["succeeded"] and r["verified"]),
        "unverified_completions": sum(1 for r in rows if r["succeeded"] and not r["verified"]),
        "model_calls_total": sum(r["model_calls"] for r in rows),
        "prompt_chars_total": sum(r["prompt_chars_total"] for r in rows),
    }
    print(json.dumps({"summary": summary, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
