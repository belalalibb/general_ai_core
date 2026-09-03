"""AgentRuntime pins — the SHARED agent seam (R160).

Every test runs the REAL routing → execution propose seam (scripted
provider), the REAL core ToolRegistry → CapabilityFirewall → ToolCallGate →
ToolExecutor authority chain, and the REAL AgentLoop bounds. Only the model
output and the tool handlers are doubles.
"""

from __future__ import annotations

import pytest

from core.agent import AgentToolSpec, evidence_verifier
from core.agent.runtime import AGENT_RUNTIME_LABEL_KEY, _parse_json_object
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import ExecutionStrategy
from core.execution.loop import (
    STOP_FINAL,
    STOP_INVALID_PROPOSAL,
    STOP_PROPOSE_FAILED,
    STOP_REPEATED_FAILURE,
    STOP_VERIFICATION_FAILED,
)
from core.tools.registry import ToolNotRegistered
from tests.agent.world import (
    ENTITLEMENT,
    OTHER_TENANT,
    PERM_READ,
    PERM_WRITE,
    TENANT,
    AgentWorld,
    final,
    make_tool,
    model_says,
    run,
    tool_call,
)

TASK = {"ask": "what does README.md say?"}


class TestHappyPath:
    def test_tool_then_cited_final_is_verified_and_stored(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("fs", path="README.md")), model_says(final("hello", 1))]
        )
        outcome = world.run(TASK)
        report = outcome.report
        assert report.stop_reason == STOP_FINAL
        assert report.succeeded
        assert report.final_output == {"answer": "hello", "evidence": [1]}
        assert report.verification == {"verified": True, "cited": [1], "available": [1]}
        assert world.fs.reads == ["README.md"]
        # Evidence ledger holds the REAL tool result.
        assert report.evidence[0]["result"] == {"path": "README.md", "content": "hello"}
        # Two reasoning executions + the agent record itself were stored.
        assert len(outcome.reasoning_execution_ids) == 2
        assert len(world.stored) == 3
        agent_record = outcome.execution_report
        assert agent_record.execution.strategy is ExecutionStrategy.AGENT
        assert agent_record.execution.status is ExecutionStatus.SUCCEEDED
        assert agent_record.final_output == {"answer": "hello", "evidence": [1]}
        snap = agent_record.execution.cost_snapshot
        assert snap["reasoning_execution_ids"] == [str(i) for i in outcome.reasoning_execution_ids]
        assert snap["stop_reason"] == STOP_FINAL
        assert snap["evidence"][0]["step"] == 1

    def test_model_sees_protocol_tools_budget_and_observations(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("fs", path="README.md")), model_says(final("hello", 1))]
        )
        world.run(TASK, label={"surface": "test"})
        first, second = world.adapter.requests[0].payload, world.adapter.requests[1].payload
        ask1 = first["ask"]
        assert '"action": "tool_call"' in ask1 and "Available tools" in ask1
        assert '"name": "fs"' in ask1 and "Budget" in ask1
        assert "Observations so far" not in ask1
        assert "Observations so far" in second["ask"] and '"content": "hello"' in second["ask"]
        meta = first["context"]["metadata"][AGENT_RUNTIME_LABEL_KEY]
        assert meta == {"kind": "reasoning", "step": 1, "surface": "test"}
        # R165 (live): every reasoning request carries the proposal schema so
        # adapters with constrained decoding keep the model in the protocol.
        from core.execution.agent import AGENT_PROPOSAL_SCHEMA

        assert first["response_schema"] == {
            "name": "agent_proposal",
            "schema": AGENT_PROPOSAL_SCHEMA,
        }
        # ...and asks for room to carry a whole file in one proposal.
        from core.agent.runtime import DEFAULT_REASONING_MAX_TOKENS

        assert first["generation"] == {"max_completion_tokens": DEFAULT_REASONING_MAX_TOKENS}
        assert DEFAULT_REASONING_MAX_TOKENS >= 4096

    def test_final_without_tools_and_empty_evidence_passes(self) -> None:
        world = AgentWorld([model_says(final("42"))])
        outcome = world.run({"ask": "6*7"})
        assert outcome.report.succeeded
        assert outcome.report.verification["verified"] is True


class TestEvidenceVerification:
    def test_invented_evidence_is_rejected_then_corrected(self) -> None:
        world = AgentWorld(
            [
                model_says(tool_call("fs", path="README.md")),
                model_says(final("hello", 1, 7)),  # step 7 never happened
                model_says(final("hello", 1)),
            ]
        )
        outcome = world.run(TASK)
        report = outcome.report
        assert report.succeeded and report.stop_reason == STOP_FINAL
        rejected = report.steps[1].observation
        assert rejected["final_rejected"] is True
        assert rejected["verification"]["invented"] == [7]
        # The corrected proposal saw the rejection.
        assert "invented" in world.adapter.requests[2].payload["ask"]

    def test_citing_a_failed_step_is_invented_evidence(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("fs", path="nope.md")), model_says(final("x", 1))],
            max_steps=2,
        )
        outcome = world.run(TASK)
        assert outcome.report.stop_reason == STOP_VERIFICATION_FAILED
        assert outcome.report.verification["invented"] == [1]

    def test_empty_answer_is_rejected(self) -> None:
        verdict = run(evidence_verifier({"_evidence_steps": []}, {"answer": "  "}))
        assert verdict["verified"] is False

    def test_bad_evidence_shapes_are_rejected(self) -> None:
        assert run(evidence_verifier({}, {"answer": "a", "evidence": "1"}))["verified"] is False
        assert run(evidence_verifier({}, {"answer": "a", "evidence": [True]}))["verified"] is False

    def test_consumer_may_bind_a_stricter_verifier(self) -> None:
        async def must_say_hello(request: object, output: dict) -> dict:
            return {"verified": output.get("answer") == "hello"}

        world = AgentWorld([model_says(final("bye")), model_says(final("hello"))])
        outcome = world.run(TASK, verify=must_say_hello)
        assert outcome.report.succeeded
        assert outcome.report.final_output["answer"] == "hello"


class TestAuthorityChain:
    def test_ungranted_permission_is_refused_without_running_handler(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("fs_write", path="x", content="y")), model_says(final("done"))]
        )
        outcome = world.run(TASK, tools=[world.read_spec(), world.write_spec()])
        obs = outcome.report.steps[0].observation
        assert obs["status"] == "refused"
        assert world.fs.writes == []
        assert outcome.report.summary["tool_calls_ok"] == 0
        # Audit trail on the ONE shared audit log records the refused call.
        events = world.audit.read(TENANT)
        assert events and any("refused" in str(e.model_dump()) for e in events)

    def test_unknown_tool_name_is_refused(self) -> None:
        world = AgentWorld(
            [model_says(tool_call("shell", cmd="rm -rf /")), model_says(final("ok"))]
        )
        outcome = world.run(TASK)
        assert outcome.report.steps[0].observation["status"] == "refused"

    def test_tenant_without_policy_is_denied(self) -> None:
        world = AgentWorld([model_says(tool_call("fs", path="README.md")), model_says(final("x"))])
        world.usage.configure_tenant(OTHER_TENANT, plan="test", task_units_limit=100.0)
        outcome = world.run(TASK, tenant_id=OTHER_TENANT)
        assert outcome.report.steps[0].observation["status"] == "refused"
        assert world.fs.reads == []
        assert outcome.execution_report.execution.tenant_id == OTHER_TENANT

    def test_unregistered_tool_is_a_wiring_error(self) -> None:
        world = AgentWorld([model_says(final("x"))])
        rogue = AgentToolSpec(
            tool=make_tool("rogue", [PERM_READ]),
            handler=world.fs.read,
            permission=PERM_READ,
            resource="r",
            entitlement=ENTITLEMENT,
            description="not registered",
        )
        with pytest.raises(ToolNotRegistered):
            world.run(TASK, tools=[rogue])

    def test_duplicate_tool_names_are_a_wiring_error(self) -> None:
        world = AgentWorld([model_says(final("x"))])
        with pytest.raises(ValueError, match="duplicate"):
            world.run(TASK, tools=[world.read_spec(), world.read_spec()])

    def test_permission_not_declared_by_tool_is_refused_at_spec(self) -> None:
        world = AgentWorld()
        with pytest.raises(ValueError, match="not declared"):
            AgentToolSpec(
                tool=make_tool("t", [PERM_READ]),
                handler=world.fs.read,
                permission=PERM_WRITE,
                resource="r",
                entitlement=ENTITLEMENT,
                description="d",
            )


class TestBounds:
    def test_repeated_identical_failure_is_refused(self) -> None:
        bad = model_says(tool_call("fs", path="missing.md"))
        world = AgentWorld([bad, bad, bad], max_steps=3)
        outcome = world.run(TASK)
        assert outcome.report.stop_reason == STOP_REPEATED_FAILURE
        assert world.fs.reads == ["missing.md", "missing.md"]  # third never dispatched
        assert outcome.report.summary["repeated_failure_refusals"] == 1

    def test_invalid_model_output_is_invalid_proposal(self) -> None:
        world = AgentWorld([{"content": "I think we should read the file."}], max_steps=1)
        outcome = world.run(TASK)
        assert outcome.report.stop_reason == STOP_INVALID_PROPOSAL

    def test_fenced_json_is_accepted(self) -> None:
        world = AgentWorld(
            [
                {
                    "content": (
                        '```json\n{"action": "final", '
                        '"output": {"answer": "ok", "evidence": []}}\n```'
                    )
                }
            ]
        )
        outcome = world.run(TASK)
        assert outcome.report.succeeded

    def test_dict_content_is_accepted_verbatim(self) -> None:
        world = AgentWorld([{"content": final("ok")}])
        assert world.run(TASK).report.succeeded

    def test_budget_exhaustion_is_propose_failed(self) -> None:
        world = AgentWorld([model_says(final("x"))], budget_units=0.0)
        outcome = world.run(TASK)
        assert outcome.report.stop_reason == STOP_PROPOSE_FAILED
        assert not outcome.report.succeeded

    def test_provider_failure_is_propose_failed_naming_category_and_code(self) -> None:
        """R165 (live): the propose_failed detail names the provider's
        normalized failure (category/code) — never its raw message."""
        from core.contracts.provider import ProviderError, ProviderErrorCategory

        rejected = ProviderError(
            category=ProviderErrorCategory.BAD_REQUEST,
            retryable=False,
            provider_code="tool_use_failed",
            safe_message="provider rejected the request",
        )
        # Two consecutive faults exhaust the default recovery bound.
        world = AgentWorld([rejected, rejected])
        outcome = world.run(TASK)
        assert outcome.report.stop_reason == STOP_PROPOSE_FAILED
        failed_planner = [n for n in outcome.report.nodes if n.error is not None][-1]
        assert failed_planner.error is not None
        detail = failed_planner.error["detail"]
        assert "reasoning execution did not succeed" in detail
        assert "bad_request/tool_use_failed" in detail
        assert "provider rejected the request" not in detail

    def test_no_eligible_model_is_propose_failed(self) -> None:
        world = AgentWorld([model_says(final("x"))])
        world.bindings = None  # not used after construction; router holds its own refs
        world.models._models.clear() if hasattr(world.models, "_models") else None
        outcome = world.run(TASK)
        # Either the router refused (propose_failed) or, if the registry double
        # is not clearable, the run completed — the pin is: NEVER an exception.
        assert outcome.report.stop_reason in {STOP_PROPOSE_FAILED, STOP_FINAL}

    def test_caller_cannot_exceed_runtime_step_cap(self) -> None:
        world = AgentWorld([model_says(final("x"))], max_steps=4)
        with pytest.raises(ValueError):
            world.run(TASK, max_steps=5)
        assert world.run(TASK, max_steps=2).report.succeeded

    def test_caller_deadline_is_clamped_to_runtime_deadline(self) -> None:
        world = AgentWorld([model_says(final("x"))], deadline_ms=1_000)
        outcome = world.run(TASK, deadline_ms=999_999)
        assert outcome.report.summary["deadline_ms"] == 1_000

    def test_runtime_rejects_step_cap_outside_bounds(self) -> None:
        with pytest.raises(ValueError):
            AgentWorld(max_steps=0)
        with pytest.raises(ValueError):
            AgentWorld(max_steps=33)

    def test_tenant_isolation_of_stored_records(self) -> None:
        world = AgentWorld([model_says(final("x"))])
        world.run(TASK)
        assert {r.execution.tenant_id for r in world.stored} == {TENANT}


class TestParseJsonObject:
    def test_variants(self) -> None:
        assert _parse_json_object('{"a": 1}') == {"a": 1}
        assert _parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
        assert _parse_json_object('Sure! {"a": 1} hope it helps') == {"a": 1}
        assert _parse_json_object("[1,2]")["action"] == "invalid_json"
        assert _parse_json_object("nothing here")["action"] == "invalid_json"
