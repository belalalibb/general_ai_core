"""R165: the admin trace exposes WHY an agent stage failed.

An agent record's plan/act nodes carry their failure object (``capability_denied``,
``invalid_proposal`` reason, ``propose_failed`` detail…). Before R165 the trace
derivation dropped it, so an operator reading ``/v1/agent/executions/{id}/trace``
for a public ``strategy=agent`` run saw ``act-1-…: failed`` and no cause (found
live in the R165 Groq proof). Pins, over the REAL route and the SAME store the
public runtime writes to: a failed act stage carries the scrubbed node error; a
succeeded stage carries none; the object is scrubbed (R4).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from tests.admin_agent.test_aa2_admin_agent import (
    ADMIN_EMAIL,
    AgentWorld,
    _client,
    _login,
    bearer,
    run,
)
from tests.agent.world import AgentWorld as PublicAgentWorld
from tests.agent.world import final, model_says, tool_call


def _store_public_agent_run(
    admin: AgentWorld, script: list[dict[str, Any]], *, tools: bool, max_steps: int = 8
) -> UUID:
    """Run the SHARED public runtime against the admin world's execution store
    under the admin's tenant — the record the trace route must explain."""
    public = PublicAgentWorld(script, max_steps=max_steps)
    public.runtime._store_report = admin.store.put  # noqa: SLF001 - one store, two writers
    principal = admin.admin_principal()
    public.usage.configure_tenant(principal.tenant_id, plan="test", task_units_limit=100)
    outcome = run(
        public.runtime.run(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            task={"ask": "x"},
            tools=[public.write_spec()] if tools else [],  # offered, never granted
        )
    )
    return outcome.report.execution.id


def _trace(admin: AgentWorld, execution_id: UUID) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        token = await _login(admin.app, ADMIN_EMAIL)
        async with _client(admin.app) as client:
            response = await client.get(
                f"/v1/agent/executions/{execution_id}/trace", headers=bearer(token)
            )
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    return run(go())


def test_failed_act_stage_carries_its_recorded_error() -> None:
    admin = AgentWorld([])
    execution_id = _store_public_agent_run(
        admin,
        [model_says(tool_call("fs_write", path="x", content="y")), model_says(final("done"))],
        tools=True,
    )
    trace = _trace(admin, execution_id)
    assert trace["strategy"] == "agent"
    stages = {s["node_key"]: s for s in trace["stages"]}
    assert stages["act-1-fs_write"]["status"] == "failed"
    assert stages["act-1-fs_write"]["error"]["reason"] == "capability_denied"
    assert stages["plan-1"]["status"] == "succeeded"
    assert stages["plan-1"].get("error") is None


def test_stage_error_is_scrubbed() -> None:
    # A model that answers with a leaked credential instead of JSON: the
    # invalid_proposal detail must not carry the secret to the operator.
    admin = AgentWorld([])
    leaked = "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
    execution_id = _store_public_agent_run(
        admin, [{"content": f"{leaked} is not json"}], tools=False, max_steps=1
    )
    trace = _trace(admin, execution_id)
    plan = next(s for s in trace["stages"] if s["node_key"] == "plan-1")
    assert plan["status"] == "failed"
    assert plan["error"]["reason"] == "invalid_proposal"
    assert leaked not in str(plan["error"])
