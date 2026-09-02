"""R159 — the admin agent consumes the shared Verify stage + exposes trace.

GAP-1 (verified real before fixing: ``AgentLoop(...)`` in
apps/admin_agent/service.py passed no ``verify=``): the R157 deterministic
verification-before-finalization now guards the admin consumer's turn.

GAP-2 (verified real: AgentAnswer carried ids only; model/provider/attempt/
latency/ledger lived solely in the stored ExecutionReport): the answer now
carries the SAME ExecutionTrace derivation the /executions/{id}/trace route
returns (one converter, two consumers) plus the loop's verification verdict.

Hermetic; asyncio.run (ADR-0001); AgentWorld scripted adapter.
"""

from __future__ import annotations

from typing import Any

from core.execution.loop import STOP_VERIFICATION_FAILED
from tests.admin_agent.test_aa2_admin_agent import (
    ADMIN_EMAIL,
    AgentWorld,
    _client,
    _login,
    _provider_error,
    _reasoning,
    bearer,
    run,
)
from tests.admin_agent.test_bounded_iteration import _continuing

LIST_MODELS = {"tool": "list_models", "arguments": {}}
UNCITED = {"text": "all models healthy", "evidence": []}
CITED = {
    "text": "model model-a is registered",
    "evidence": [{"kind": "model", "ref": "model-a"}],
}


class TestVerifyStageWired:
    def test_all_claims_refused_with_tool_evidence_is_verification_failed(
        self,
    ) -> None:
        """The model finalized AGAINST its own evidence -> shared loop stop."""
        world = AgentWorld([_reasoning(tool_calls=[LIST_MODELS], claims=[UNCITED])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "status?"))
        assert answer.claims == []
        assert answer.stop_reason == STOP_VERIFICATION_FAILED
        assert answer.verification is not None
        assert answer.verification["verified"] is False
        assert answer.verification["claims_refused"] == 1
        assert answer.verification["tool_calls_ok"] == 1
        assert "reason" in answer.verification
        # Historical honesty note preserved alongside the verdict.
        assert answer.note is not None and "refused" in answer.note

    def test_cited_claim_is_verified_final(self) -> None:
        world = AgentWorld([_reasoning(tool_calls=[LIST_MODELS], claims=[CITED])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "models?"))
        assert answer.stop_reason == "final"
        assert answer.verification == {
            "verified": True,
            "claims_admitted": 1,
            "claims_refused": 0,
            "tool_calls_ok": 1,
            "tool_calls_total": 1,
        }

    def test_no_tools_no_evidence_context_stays_final(self) -> None:
        """Nothing to verify against -> not a verification failure (the
        claim is still refused by the evidence gate; the verdict records it)."""
        world = AgentWorld([_reasoning(claims=[UNCITED])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "status?"))
        assert answer.claims == []
        assert answer.stop_reason == "final"
        assert answer.verification is not None
        assert answer.verification["verified"] is True
        assert answer.verification["claims_refused"] == 1

    def test_reasoning_failure_has_no_verdict(self) -> None:
        """No final was ever proposed -> verification honestly absent."""
        world = AgentWorld([_provider_error()])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "hello"))
        assert answer.stop_reason == "reasoning_failed"
        assert answer.verification is None
        # The failed reasoning execution is still traced (evidence).
        assert len(answer.reasoning_trace) == 1
        assert answer.reasoning_trace[0].status == "failed"


class TestTraceExposure:
    def test_answer_trace_matches_trace_route_derivation(self) -> None:
        world = AgentWorld([_reasoning(tool_calls=[LIST_MODELS], claims=[CITED])])
        world.grant_budget(100)
        admin = world.admin_principal()
        answer = run(world.service.converse(admin, "models?"))
        assert len(answer.reasoning_trace) == len(answer.reasoning_execution_ids) == 1
        inline = answer.reasoning_trace[0]
        via_route = world.service.trace(admin, answer.reasoning_execution_ids[0])
        assert via_route is not None
        assert inline == via_route  # ONE derivation, two consumers
        attempt = inline.stages[0].attempts[0]
        assert attempt.model_key == "model-a"
        assert attempt.provider_key == "prov_a"
        assert attempt.succeeded is True
        assert inline.ledger is not None
        assert inline.ledger["status"] in {"settled", "reserved"}
        assert inline.as_recorded is True

    def test_multi_round_trace_is_per_round_in_order(self) -> None:
        world = AgentWorld([_continuing([LIST_MODELS]), _reasoning(claims=[CITED])])
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "go"))
        assert answer.rounds == 2
        assert [t.execution_id for t in answer.reasoning_trace] == (answer.reasoning_execution_ids)

    def test_trace_rides_the_http_answer(self) -> None:
        world = AgentWorld([_reasoning(tool_calls=[LIST_MODELS], claims=[CITED])])
        world.grant_budget(100)

        async def go() -> dict[str, Any]:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as client:
                response = await client.post(
                    "/v1/agent/converse",
                    json={"message": "models?"},
                    headers=bearer(token),
                )
            assert response.status_code == 200, response.text
            body: dict[str, Any] = response.json()
            return body

        body = run(go())
        assert body["verification"]["verified"] is True
        assert body["reasoning_trace"][0]["stages"][0]["attempts"][0]["model_key"] == "model-a"
        assert body["reasoning_trace"][0]["ledger"] is not None
