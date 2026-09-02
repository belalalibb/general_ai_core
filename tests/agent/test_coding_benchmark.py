"""Coding as the flagship benchmark for the SHARED runtime (R160).

A fix-the-failing-test task runs end to end through ``AgentRuntime`` with
three narrow, typed tools (read / write / run_tests) over the ONE authority
chain. The model is scripted so every pin isolates the RUNTIME's behavior,
not a provider's. Each scenario states the capability it proves — or the
weakness it exposes (recorded as data in ``WEAKNESSES`` so the report never
claims more than what is pinned).

Weaknesses exposed by this benchmark (honest, not fixed here):

- W1  The runtime cannot tell that ``run_tests`` SUCCEEDED-as-a-tool while
      the tests FAILED: tool status is transport-level. A final may cite a
      "succeeded" run_tests step whose result says ``passed: False``.
      Semantic verification of tool results is a consumer verifier concern
      (``verify=``) — pinned below as the ONLY way to catch it today.
- W2  Repeated-failure refusal keys on FAILED (tool, args): a model that
      keeps rewriting the SAME wrong content passes (each write succeeds)
      and burns the step budget. The loop stops at ``max_steps_exceeded`` —
      bounded, but late.
- W3  No plan artifact: the runtime records observations, not the model's
      plan, so a reviewer cannot see WHY a step was chosen beyond the
      ``reasoning`` string the proposal carried.
"""

from __future__ import annotations

from typing import Any

from core.agent import AgentToolSpec
from core.contracts.base import JsonObject
from core.execution.loop import (
    STOP_FINAL,
    STOP_MAX_STEPS,
    STOP_PROPOSE_FAILED,
    STOP_VERIFICATION_FAILED,
)
from core.security.firewall import TenantPolicy
from tests.agent.world import (
    ENTITLEMENT,
    PERM_READ,
    PERM_WRITE,
    TENANT,
    AgentWorld,
    FakeFs,
    final,
    make_tool,
    model_says,
    tool_call,
)

WEAKNESSES = ("W1", "W2", "W3")

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
TASK = {"ask": "test_calc.py fails; fix calc.py so the suite passes"}


class FakeRunner:
    """run_tests double: passes iff calc.py holds the FIXED body."""

    def __init__(self, fs: FakeFs) -> None:
        self.fs = fs
        self.runs = 0

    async def run(self, _: JsonObject) -> JsonObject:
        self.runs += 1
        passed = self.fs.files.get("calc.py") == FIXED
        return {"passed": passed, "failed": 0 if passed else 1, "total": 1}


def _grant(world: AgentWorld, *permissions: str) -> None:
    world.firewall.set_tenant_policy(
        TENANT,
        TenantPolicy(
            granted_permissions=frozenset(permissions),
            granted_entitlements=frozenset({ENTITLEMENT}),
        ),
    )


def _coding_world(
    script: list[object], **kw: Any
) -> tuple[AgentWorld, FakeRunner, list[AgentToolSpec]]:
    world = AgentWorld(script, **kw)
    world.fs.files = {"calc.py": BUGGY, "test_calc.py": TEST}
    _grant(world, PERM_READ, PERM_WRITE)  # coding needs write (default grants read)
    runner = FakeRunner(world.fs)
    run_tool = make_tool("run_tests", [PERM_READ])
    world.tool_registry.register(run_tool)
    tools = [
        world.read_spec(),
        world.write_spec(),
        AgentToolSpec(
            tool=run_tool,
            handler=runner.run,
            permission=PERM_READ,
            resource="fs:workspace",
            entitlement=ENTITLEMENT,
            description="Run the test suite; returns passed/failed counts.",
        ),
    ]
    return world, runner, tools


async def verify_tests_passed(request: JsonObject, output: JsonObject) -> JsonObject:
    """Consumer verifier closing W1 for THIS task shape."""
    return {"verified": bool(output.get("tests_passed")), "rule": "tests_passed"}


class TestHappyPath:
    def test_read_fix_verify_finalize(self) -> None:
        world, runner, tools = _coding_world(
            [
                model_says(tool_call("fs", path="test_calc.py")),
                model_says(tool_call("fs", path="calc.py")),
                model_says(tool_call("run_tests")),  # observe the failure first
                model_says(tool_call("fs_write", path="calc.py", content=FIXED)),
                model_says(tool_call("run_tests")),
                model_says(final("fixed add()", 1, 2, 3, 4, 5)),
            ]
        )
        outcome = world.run(TASK, tools=tools)
        report = outcome.report
        assert report.stop_reason == STOP_FINAL and report.succeeded
        assert world.fs.files["calc.py"] == FIXED
        assert runner.runs == 2
        # The evidence ledger keeps BOTH run results — failing then passing.
        results = [e["result"] for e in report.evidence if e["tool"] == "run_tests"]
        assert [r["passed"] for r in results] == [False, True]
        assert report.summary["tool_calls_ok"] == 5
        assert len(outcome.reasoning_execution_ids) == 6  # each stored (P6)
        assert len(world.stored) == 7  # 6 reasoning records + the agent record


class TestWeaknessW1:
    def test_default_verifier_accepts_final_citing_a_failed_test_run(self) -> None:
        """W1 exposed: run_tests 'succeeded' as a tool though tests failed."""
        world, _, tools = _coding_world(
            [model_says(tool_call("run_tests")), model_says(final("done", 1))]
        )
        outcome = world.run(TASK, tools=tools)
        assert outcome.report.succeeded  # <- the weakness, pinned honestly
        assert outcome.report.evidence[0]["result"]["passed"] is False

    def test_consumer_verifier_closes_w1(self) -> None:
        world, _, tools = _coding_world(
            [
                model_says(tool_call("run_tests")),
                model_says(
                    {"action": "final", "output": {"answer": "done", "tests_passed": False}}
                ),
            ],
            max_steps=2,
        )
        outcome = world.run(TASK, tools=tools, verify=verify_tests_passed)
        assert outcome.report.stop_reason == STOP_VERIFICATION_FAILED
        assert not outcome.report.succeeded


class TestWeaknessW2:
    def test_same_wrong_rewrite_burns_budget_until_max_steps(self) -> None:
        wrong = tool_call("fs_write", path="calc.py", content="def add(a, b):\n    return 0\n")
        world, _, tools = _coding_world([model_says(wrong)] * 4, max_steps=4)
        outcome = world.run(TASK, tools=tools)
        assert outcome.report.stop_reason == STOP_MAX_STEPS  # bounded, but late
        assert outcome.report.summary["repeated_failure_refusals"] == 0  # W2: undetected
        assert len(world.fs.writes) == 4


class TestAuthority:
    def test_write_without_grant_is_refused_and_file_untouched(self) -> None:
        world, _, tools = _coding_world(
            [
                model_says(tool_call("fs_write", path="calc.py", content=FIXED)),
                model_says(final("could not write")),
            ]
        )
        _grant(world, PERM_READ)  # revoke write
        outcome = world.run(TASK, tools=tools)
        assert outcome.report.steps[0].observation["status"] == "refused"
        assert world.fs.files["calc.py"] == BUGGY
        assert world.fs.writes == []
        assert outcome.report.succeeded  # honest final citing no evidence


class TestBudget:
    def test_reasoning_budget_exhaustion_stops_run_not_process(self) -> None:
        world, _, tools = _coding_world(
            [model_says(tool_call("fs", path="calc.py"))] * 3 + [model_says(final("x"))],
            budget_units=2.0,
        )
        outcome = world.run(TASK, tools=tools)
        assert not outcome.report.succeeded
        assert outcome.report.stop_reason == STOP_PROPOSE_FAILED
