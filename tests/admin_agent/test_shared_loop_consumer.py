"""R156 — converse is a CONSUMER of the shared core.execution.loop.AgentLoop.

Two pins only (minimal-change mandate):

1. Structural: the turn's loop object IS core.execution.loop.AgentLoop —
   no private loop class remains in the admin agent; a future IDE/SaaS
   surface can consume the same capability by binding its own propose/act
   seams.
2. Behavioral proof: reason → tool → observe → reassess → NEW action still
   works through the shared loop — round 2's model ask carries round 1's
   observations, and the round-2 action (a claim citing evidence surfaced
   by round 1's tool result) is admitted.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from core.execution.loop import AgentLoop
from tests.admin_agent.test_aa2_admin_agent import AgentWorld, _reasoning


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestSharedLoopConsumer:
    def test_turn_loop_is_the_shared_core_agent_loop(self) -> None:
        from apps.admin_agent.service import _TurnState

        world = AgentWorld([])
        loop = world.service._build_loop(  # noqa: SLF001 — structural pin
            world.admin_principal(), "structural check", _TurnState()
        )
        assert type(loop) is AgentLoop
        assert loop.__class__.__module__ == "core.execution.loop"

    def test_reason_tool_observe_reassess_new_action_via_shared_loop(self) -> None:
        world = AgentWorld(
            [
                # Round 1: reason → act (list_models) → observe, opt to continue.
                {
                    "content": json.dumps(
                        {
                            "tool_calls": [{"tool": "list_models", "arguments": {}}],
                            "claims": [],
                            "continue": True,
                        }
                    )
                },
                # Round 2 (reassess): a NEW action — a claim citing evidence
                # that ONLY round 1's tool result surfaced.
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
        answer = run(world.service.converse(world.admin_principal(), "check"))
        assert answer.rounds == 2
        assert answer.stop_reason == "final"
        assert len(answer.tool_calls) == 1
        assert len(answer.claims) == 1  # admitted on round-1 evidence
        # Reassessment proof: round 2's ask SAW round 1's observation.
        round2_ask = str(world.adapter.requests[1].payload["ask"])
        assert "Observations from your previous rounds" in round2_ask
        assert "list_models" in round2_ask


class TestSharedRuntimeReasoning:
    """R160: the Admin agent REASONS through the shared ``core.agent`` runtime."""

    def test_injected_runtime_is_the_reasoning_path(self) -> None:
        from apps.admin_agent.dispatcher import ToolDispatcher
        from apps.admin_agent.service import AdminAgentService
        from apps.admin_agent.tools import AGENT_LABEL_KEY, build_registry
        from core.agent import AgentRuntime
        from core.identity.devices import DeviceRegistry
        from core.security.firewall import CapabilityFirewall
        from core.tools import ToolRegistry as CoreToolRegistry

        world = AgentWorld([_reasoning()])
        world.grant_budget(100)
        admin = world.admin_principal()
        calls: list[dict[str, Any]] = []

        class SpyRuntime(AgentRuntime):
            async def reason(self, **kw: Any) -> Any:  # type: ignore[override]
                calls.append(kw)
                return await super().reason(**kw)

        runtime = SpyRuntime(
            router=world.surface.router,
            execution_service=world.surface.execution_service,
            tool_registry=CoreToolRegistry(),
            firewall=CapabilityFirewall(),
            devices=DeviceRegistry(),
            audit=world.surface.audit,
            usage=world.surface.usage,
            store_report=world.store.put,
        )
        registry = build_registry(world.surface)
        service = AdminAgentService(
            world.surface, registry, ToolDispatcher(registry, audit=world.audit), runtime=runtime
        )
        answer = run(service.converse(admin, "hello"))
        assert len(calls) == 1
        assert calls[0]["label_key"] == AGENT_LABEL_KEY
        assert calls[0]["label"]["round"] == 1
        assert "list_models" in calls[0]["label"]["tools"]
        # The reasoning execution is stored by the runtime's store seam and
        # labeled under the ADMIN key (traces still name the consumer).
        report = world.store.get(admin.tenant_id, answer.reasoning_execution_ids[0])
        input_ref = report.nodes[0].node.input_ref
        assert isinstance(input_ref, dict)
        assert input_ref["context"]["metadata"][AGENT_LABEL_KEY]["kind"] == "reasoning"

    def test_reasoning_failure_disposes_as_no_proposal_with_trace_id(self) -> None:
        from core.contracts.provider import ProviderError, ProviderErrorCategory

        world = AgentWorld(
            [
                ProviderError(
                    category=ProviderErrorCategory.QUOTA_EXCEEDED,
                    retryable=False,
                    safe_message="quota exhausted upstream",
                )
            ]
        )
        world.grant_budget(100)
        admin = world.admin_principal()
        answer = run(world.service.converse(admin, "hello"))
        assert answer.claims == []
        assert answer.stop_reason != "final" or answer.note is not None
        # The failed reasoning execution is still traceable (never invented).
        for execution_id in answer.reasoning_execution_ids:
            assert world.store.get(admin.tenant_id, execution_id) is not None
