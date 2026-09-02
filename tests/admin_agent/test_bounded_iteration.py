"""Bounded multi-round converse — mandate §8 (real iterative behavior).

The model OPTS IN with ``"continue": true`` next to tool calls;
deterministic code disposes. Pins:

- default (no flag) = the historical single-round turn, verbatim shape;
- a second round SEES round 1's observations (the second action can
  change because of the first result — proven via the ask payload);
- termination is structural: max rounds, continue-without-tools, invalid
  proposal mid-loop, reasoning failure mid-loop — all closed stop reasons;
- every round's reasoning execution is stored (evidence, not fabrication);
- evidence admitted in ANY round stays citable at finalization;
- flood bound still applies PER ROUND.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from tests.admin_agent.test_aa2_admin_agent import (
    AgentWorld,
    _provider_error,
    _reasoning,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def _continuing(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    """A proposal that calls tools AND asks to continue."""
    return {"content": json.dumps({"tool_calls": tool_calls, "claims": [], "continue": True})}


LIST_MODELS = {"tool": "list_models", "arguments": {}}


class TestSingleRoundUnchanged:
    def test_no_flag_means_one_round_final(self) -> None:
        world = AgentWorld([_reasoning(tool_calls=[LIST_MODELS])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "models?"))
        assert answer.rounds == 1
        assert answer.stop_reason == "final"
        assert len(answer.reasoning_execution_ids) == 1
        assert len(answer.tool_calls) == 1


class TestIteration:
    def test_second_round_sees_first_round_observations(self) -> None:
        world = AgentWorld(
            [
                _continuing([LIST_MODELS]),
                _reasoning(
                    claims=[
                        {
                            "text": "model model-a is registered",
                            "evidence": [{"kind": "model", "ref": "model-a"}],
                        }
                    ]
                ),
            ]
        )
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "check models"))
        assert answer.rounds == 2
        assert answer.stop_reason == "final"
        assert len(answer.reasoning_execution_ids) == 2
        # The claim cites evidence surfaced in ROUND 1 — admitted at final.
        assert len(answer.claims) == 1
        # The round-2 ask carried round-1 observations (adapter saw them).
        round2_request = world.adapter.requests[1]
        ask = str(round2_request.payload["ask"])
        assert "Observations from your previous rounds" in ask
        assert "list_models" in ask

    def test_max_rounds_bound_enforced(self) -> None:
        world = AgentWorld([_continuing([LIST_MODELS]) for _ in range(5)])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "loop"))
        assert answer.rounds == 3  # _MAX_ROUNDS
        assert answer.stop_reason == "max_rounds"
        assert len(answer.reasoning_execution_ids) == 3
        assert len(answer.tool_calls) == 3

    def test_continue_without_tools_terminates(self) -> None:
        world = AgentWorld(
            [{"content": json.dumps({"tool_calls": [], "claims": [], "continue": True})}]
        )
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "loop"))
        assert answer.rounds == 1
        assert answer.stop_reason == "continue_without_tools"

    def test_invalid_proposal_mid_loop_stops_honestly(self) -> None:
        world = AgentWorld([_continuing([LIST_MODELS]), {"content": "prose, not JSON"}])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "go"))
        assert answer.rounds == 2
        assert answer.stop_reason == "invalid_proposal"
        assert answer.note is not None
        assert "not a valid proposal" in answer.note
        # Round 1's transcript is preserved — evidence, not rollback.
        assert len(answer.tool_calls) == 1
        assert len(answer.reasoning_execution_ids) == 2

    def test_reasoning_failure_mid_loop_stops_honestly(self) -> None:
        world = AgentWorld([_continuing([LIST_MODELS]), _provider_error()])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "go"))
        assert answer.rounds == 2
        assert answer.stop_reason == "reasoning_failed"
        assert answer.note is not None
        assert "failed" in answer.note
        # BOTH reasoning executions recorded (the failed one too).
        assert len(answer.reasoning_execution_ids) == 2

    def test_flood_bound_applies_per_round(self) -> None:
        flood = [LIST_MODELS for _ in range(50)]
        world = AgentWorld([_continuing(flood), _reasoning(tool_calls=[LIST_MODELS])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "flood"))
        assert answer.rounds == 2
        assert len(answer.tool_calls) == 9  # 8 (capped round 1) + 1 (round 2)

    def test_each_round_reasoning_labeled_with_round_number(self) -> None:
        world = AgentWorld([_continuing([LIST_MODELS]), _reasoning(tool_calls=[])])
        world.grant_budget(100)
        admin = world.admin_principal()
        answer = run(world.service.converse(admin, "go"))
        assert len(answer.reasoning_execution_ids) == 2
        for expected_round, execution_id in enumerate(answer.reasoning_execution_ids, start=1):
            report = world.store.get(admin.tenant_id, execution_id)
            input_ref = report.nodes[0].node.input_ref
            assert isinstance(input_ref, dict)
            label = input_ref["context"]["metadata"]["admin_agent"]
            assert label["kind"] == "reasoning"
            assert label["round"] == expected_round
