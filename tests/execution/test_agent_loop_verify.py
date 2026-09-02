"""Verify-before-finalize seam on the shared AgentLoop (R157 closure).

Closes the R154 known limitation: "provider success == node success; there
is no semantic verdict layer". The seam is composition-bound DETERMINISTIC
code (never the model), optional (P2: absent = prior behavior verbatim),
bounded (rejections consume the same ``max_steps`` budget), and fully
evidence-backed (VALIDATOR node per verdict, last verdict on the report).

Pins:

- absent verify ⇒ behavior byte-identical to the pre-seam loop;
- rejected final ⇒ observation the model can CORRECT against, then a
  RE-verified, admitted final (detect → correct → verify again);
- rejection at the step bound ⇒ ``verification_failed`` stop reason,
  run FAILED, no final output;
- verifier fault / non-dict verdict ⇒ rejecting verdict AS DATA (a broken
  verifier can never silently admit);
- every verdict is a VALIDATOR node (pass=SUCCEEDED, reject=FAILED);
- the admitting verdict rides the report (final evidence).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from core.contracts.base import JsonObject
from core.contracts.execution import ExecutionNodeStatus, ExecutionNodeType
from core.execution.loop import STOP_FINAL, STOP_VERIFICATION_FAILED, AgentLoop
from tests.execution.test_agent_loop_v4 import AgentWorld, ScriptedProposer

TENANT_USER = uuid4()


def run(coro: Any) -> Any:
    return asyncio.run(coro)


FINAL_BAD = {"action": "final", "output": {"answer": "wrong"}}
FINAL_GOOD = {"action": "final", "output": {"answer": "right"}}


def _loop_with_verify(
    world: AgentWorld,
    script: list[object],
    *,
    max_steps: int = 5,
    verify: Any,
) -> tuple[AgentLoop, ScriptedProposer]:
    proposer = ScriptedProposer(script)
    loop = AgentLoop(
        propose=proposer,
        tools=world.executor,
        bindings={"github": world.binding},
        max_steps=max_steps,
        verify=verify,
    )
    return loop, proposer


def _execute(loop: AgentLoop) -> Any:
    from tests.tools.test_tool_fabric import TENANT

    return run(
        loop.execute(
            tenant_id=TENANT,
            user_id=TENANT_USER,
            request={"task": "compute the right answer"},
            request_hash="h" * 64,
        )
    )


async def _answer_checker(request: JsonObject, output: JsonObject) -> JsonObject:
    """Deterministic verifier double: only 'right' passes."""
    if output.get("answer") == "right":
        return {"verified": True, "check": "answer == right"}
    return {
        "verified": False,
        "check": "answer == right",
        "got": output.get("answer"),
    }


class TestVerifySeam:
    def test_absent_verify_behaves_exactly_as_before(self) -> None:
        world = AgentWorld()
        loop, _ = _loop_with_verify(world, [FINAL_BAD], verify=None)
        report = _execute(loop)
        assert report.stop_reason == STOP_FINAL  # no verifier: admitted
        assert report.succeeded
        assert report.verification is None

    def test_rejected_final_is_corrected_and_reverified(self) -> None:
        """Detect failure → observation → correct → verify again → final."""
        world = AgentWorld()
        loop, proposer = _loop_with_verify(world, [FINAL_BAD, FINAL_GOOD], verify=_answer_checker)
        report = _execute(loop)
        assert report.stop_reason == STOP_FINAL
        assert report.succeeded
        assert report.final_output == {"answer": "right"}
        # The admitting verdict is the report's final evidence.
        assert report.verification == {"verified": True, "check": "answer == right"}
        # Step 2's proposer SAW the rejection observation (reassess input).
        second_payload = proposer.payloads[1]
        rejected = second_payload["observations"][-1]
        assert rejected["final_rejected"] is True
        assert rejected["verification"]["verified"] is False
        assert rejected["verification"]["got"] == "wrong"

    def test_rejection_at_step_bound_fails_with_named_reason(self) -> None:
        world = AgentWorld()
        loop, _ = _loop_with_verify(
            world, [FINAL_BAD, FINAL_BAD], max_steps=2, verify=_answer_checker
        )
        report = _execute(loop)
        assert report.stop_reason == STOP_VERIFICATION_FAILED
        assert not report.succeeded
        assert report.final_output is None
        # The LAST rejecting verdict is still evidence on the report.
        assert report.verification is not None
        assert report.verification["verified"] is False

    def test_verifier_fault_rejects_as_data_never_admits(self) -> None:
        async def broken(request: JsonObject, output: JsonObject) -> JsonObject:
            msg = "verifier crashed"
            raise RuntimeError(msg)

        world = AgentWorld()
        loop, _ = _loop_with_verify(world, [FINAL_GOOD], max_steps=1, verify=broken)
        report = _execute(loop)
        assert report.stop_reason == STOP_VERIFICATION_FAILED
        assert not report.succeeded
        assert report.verification["error"] == "verifier_failed"
        assert "RuntimeError" in report.verification["detail"]

    def test_non_dict_verdict_rejects_as_data(self) -> None:
        async def liar(request: JsonObject, output: JsonObject) -> Any:
            return True  # not a JSON object — refused

        world = AgentWorld()
        loop, _ = _loop_with_verify(world, [FINAL_GOOD], max_steps=1, verify=liar)
        report = _execute(loop)
        assert report.stop_reason == STOP_VERIFICATION_FAILED
        assert report.verification["error"] == "verifier_invalid"

    def test_every_verdict_is_a_validator_node(self) -> None:
        world = AgentWorld()
        loop, _ = _loop_with_verify(world, [FINAL_BAD, FINAL_GOOD], verify=_answer_checker)
        report = _execute(loop)
        validators = [n for n in report.nodes if n.type is ExecutionNodeType.VALIDATOR]
        assert len(validators) == 2
        assert validators[0].status is ExecutionNodeStatus.FAILED
        assert validators[0].output_ref["verified"] is False
        assert validators[1].status is ExecutionNodeStatus.SUCCEEDED
        assert validators[1].output_ref["verified"] is True
