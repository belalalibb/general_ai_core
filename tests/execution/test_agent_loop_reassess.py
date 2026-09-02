"""Agent intelligence bounds on the shared AgentLoop (R160).

Pins the three additive loop behaviors:

- REPEATED-FAILURE REFUSAL: the identical tool call (name + arguments) that
  already failed ``max_repeated_failures`` times is NOT dispatched again; the
  observation names the repetition so the model must change action or
  strategy. Different arguments are a different call (never refused).
- DEADLINE (S4): a run past ``deadline_ms`` stops with a closed reason
  BEFORE spending another model call; absent deadline = step-bound only.
- EVIDENCE LEDGER + SUMMARY: succeeded tool results ride the report as
  evidence; the summary/cost_snapshot carries the deterministic counters.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from core.contracts.base import JsonObject
from core.execution.loop import (
    STOP_DEADLINE_EXCEEDED,
    STOP_FINAL,
    STOP_MAX_STEPS,
    STOP_REPEATED_FAILURE,
    AgentLoop,
)
from tests.execution.test_agent_loop_v4 import (
    AgentWorld,
    EchoHandler,
    ScriptedProposer,
    _final,
    _tool_call,
    run,
)
from tests.tools.test_tool_fabric import TENANT


class _FlakyHandler:
    """Fails for the first ``fail_times`` calls, then echoes."""

    def __init__(self, fail_times: int) -> None:
        self.calls: list[JsonObject] = []
        self._fail_times = fail_times

    async def __call__(self, arguments: JsonObject) -> JsonObject:
        self.calls.append(arguments)
        if len(self.calls) <= self._fail_times:
            msg = "transient"
            raise RuntimeError(msg)
        return {"echo": arguments}


def _world_with(handler: Any) -> AgentWorld:
    world = AgentWorld()
    world.handler = handler
    world.executor._handlers[world.tool.id] = handler  # same executor, swapped handler
    return world


def _loop(
    world: AgentWorld, script: list[object], **kwargs: Any
) -> tuple[AgentLoop, ScriptedProposer]:
    proposer = ScriptedProposer(script)
    loop = AgentLoop(
        propose=proposer,
        tools=world.executor,
        bindings={"github.read": world.binding},
        max_steps=kwargs.pop("max_steps", 6),
        **kwargs,
    )
    return loop, proposer


def _execute(loop: AgentLoop) -> Any:
    return run(
        loop.execute(
            tenant_id=TENANT,
            user_id=uuid4(),
            request={"ask": "read the repo"},
            request_hash="h" * 8,
        )
    )


class TestRepeatedFailure:
    def test_identical_failed_call_is_refused_after_bound(self) -> None:
        handler = EchoHandler(error=RuntimeError("boom"))
        world = _world_with(handler)
        same = _tool_call(path="a.py")
        loop, proposer = _loop(world, [same, same, same, _final(answer="gave up")], max_steps=4)
        report = _execute(loop)
        # Two real dispatches failed; the third identical call never reached the handler.
        assert len(handler.calls) == 2
        third = report.steps[2]
        assert third.observation["status"] == "refused"
        assert third.observation["error"]["reason"] == STOP_REPEATED_FAILURE
        assert third.observation["error"]["prior_failures"] == 2
        # The model SAW the refusal before its next proposal (reassess input).
        last_obs = proposer.payloads[3]["observations"][-1]
        assert last_obs["error"]["reason"] == STOP_REPEATED_FAILURE
        assert report.stop_reason == STOP_FINAL
        assert report.summary["repeated_failure_refusals"] == 1
        assert report.summary["tool_calls_failed"] == 2

    def test_changed_arguments_are_a_new_call(self) -> None:
        handler = EchoHandler(error=RuntimeError("boom"))
        world = _world_with(handler)
        loop, _ = _loop(
            world,
            [_tool_call(path="a"), _tool_call(path="a"), _tool_call(path="b"), _final(ok=True)],
            max_steps=4,
        )
        report = _execute(loop)
        assert len(handler.calls) == 3  # 'b' was dispatched (different call)
        assert report.summary["repeated_failure_refusals"] == 0

    def test_success_resets_the_failure_count(self) -> None:
        handler = _FlakyHandler(fail_times=1)
        world = _world_with(handler)
        same = _tool_call(path="x")
        loop, _ = _loop(world, [same, same, same, _final(done=True)], max_steps=4)
        report = _execute(loop)
        assert len(handler.calls) == 3  # fail, ok, ok — never refused
        assert report.summary["tool_calls_ok"] == 2
        assert report.summary["repeated_failure_refusals"] == 0

    def test_refusal_on_last_step_is_the_stop_reason(self) -> None:
        handler = EchoHandler(error=RuntimeError("boom"))
        world = _world_with(handler)
        same = _tool_call(path="a.py")
        loop, _ = _loop(world, [same, same, same], max_steps=3)
        report = _execute(loop)
        assert report.stop_reason == STOP_REPEATED_FAILURE
        assert not report.succeeded

    def test_bound_is_configurable(self) -> None:
        handler = EchoHandler(error=RuntimeError("boom"))
        world = _world_with(handler)
        same = _tool_call(path="a.py")
        loop, _ = _loop(world, [same, same, _final(x=1)], max_steps=3, max_repeated_failures=1)
        report = _execute(loop)
        assert len(handler.calls) == 1
        assert report.summary["repeated_failure_refusals"] == 1

    def test_invalid_bound_refused(self) -> None:
        world = AgentWorld()
        with pytest.raises(ValueError):
            _loop(world, [], max_repeated_failures=0)


class TestDeadline:
    def test_deadline_stops_before_next_model_call(self) -> None:
        world = AgentWorld()
        # start, step1 check, step2 check, step3 check (late), end
        ticks = iter([0.0, 0.0, 0.5, 5.0, 5.0, 5.0])

        def clock() -> float:
            return next(ticks)

        loop, proposer = _loop(
            world,
            [_tool_call(path="a"), _tool_call(path="b"), _final(never=True)],
            max_steps=5,
            deadline_ms=1_000,
            clock=clock,
        )
        report = _execute(loop)
        assert report.stop_reason == STOP_DEADLINE_EXCEEDED
        assert not report.succeeded
        assert len(proposer.payloads) == 2  # the third proposal was never requested
        last = report.steps[-1].observation
        assert last["error"] == STOP_DEADLINE_EXCEEDED
        assert last["deadline_ms"] == 1_000
        assert report.summary["deadline_ms"] == 1_000

    def test_no_deadline_keeps_step_bound(self) -> None:
        world = AgentWorld()
        loop, _ = _loop(world, [_tool_call(path="a")] * 2, max_steps=2)
        report = _execute(loop)
        assert report.stop_reason == STOP_MAX_STEPS
        assert "deadline_ms" not in report.summary

    def test_invalid_deadline_refused(self) -> None:
        world = AgentWorld()
        with pytest.raises(ValueError):
            _loop(world, [], deadline_ms=0)


class TestEvidenceLedger:
    def test_succeeded_results_become_evidence_in_step_order(self) -> None:
        world = AgentWorld()
        loop, proposer = _loop(
            world, [_tool_call(path="a"), _tool_call(path="b"), _final(done=True)]
        )
        report = _execute(loop)
        assert [e["step"] for e in report.evidence] == [1, 2]
        assert report.evidence[0]["arguments"] == {"path": "a"}
        assert report.evidence[1]["result"] == {"echo": {"path": "b"}}
        assert report.summary["evidence_items"] == 2
        assert report.execution.cost_snapshot["evidence_items"] == 2
        # Budget awareness rides every proposal payload as data.
        assert proposer.payloads[0]["budget"] == {"step": 1, "max_steps": 6}

    def test_failed_results_are_not_evidence(self) -> None:
        handler = EchoHandler(error=RuntimeError("boom"))
        world = _world_with(handler)
        loop, _ = _loop(world, [_tool_call(path="a"), _final(done=True)])
        report = _execute(loop)
        assert report.evidence == ()
        assert report.summary["tool_calls_failed"] == 1
