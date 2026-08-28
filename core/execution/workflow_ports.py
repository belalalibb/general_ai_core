"""Durable Workflow Runtime port — the seam to an EXTERNAL workflow engine
(41 §12; 12 §9).

41 §12 verbatim: "the Workflow Runtime owns state. We do not build our own
Workflow Engine." 12 §9 verbatim: the system relies on a durable workflow
runtime for "state persistence / node progression / timeouts / retries /
crash recovery / long-running jobs" and "Do not build an ad-hoc workflow
engine inside Core."

Therefore Core defines ONLY this port. Recorded derivation decisions:

- SHAPE: the docs list the runtime's six responsibilities but define no
  interface, so the port is the MINIMAL seam that lets Core submit a graph
  and observe/steer it: submit / status / node states / cancel / signal
  approval. Nothing engine-specific (task queues, workflow histories,
  activity options) leaks into Core.
- NODE STATES are reported in the 12 §6 eight-state graph lifecycle
  (``GraphNodeLifecycle``) — the runtime normalizes its internal states to
  the platform lifecycle, exactly the 12 §23.3 posture already applied to
  provider-agent events.
- ``signal_approval`` exists because approval gates (12 §11) suspend nodes
  in ``waiting_approval``; the approval RESULT reaches the runtime as a
  signal and "must be auditable" — the port carries the decision and an
  auditable actor reference, storage of the audit record stays with the
  audit subsystem.
- IDEMPOTENT SUBMISSION (12 §10): ``submit`` takes an idempotency key;
  resubmitting the same key MUST return the same workflow id, never a
  duplicate run (the Execution entity already carries ``idempotency_key``,
  03 §5).
- NO real engine binding exists in this repo. Binding one (e.g. Temporal)
  is a NEW DEPENDENCY and therefore requires an operator-ACCEPTED ADR
  (repo governance); until then the port has in-memory/test implementations
  only, and no durable-runtime functionality is claimed (41 §49).
"""

from __future__ import annotations

from typing import Protocol

from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.execution_graph import ExecutionGraphSpec, GraphNodeLifecycle


class WorkflowRuntimePort(Protocol):
    """Seam to the external durable workflow runtime (12 §9).

    The runtime OWNS state, node progression, timeouts, retries, crash
    recovery, and long-running jobs. Core submits and observes.
    """

    async def submit(
        self,
        graph: ExecutionGraphSpec,
        *,
        idempotency_key: str,
        inputs: JsonObject,
    ) -> str:
        """Start (or idempotently re-attach to) a workflow; returns its id.

        The same ``idempotency_key`` MUST return the same workflow id
        (12 §10) — duplicate submission never duplicates a run.
        """
        ...

    async def status(self, workflow_id: str) -> ExecutionStatus:
        """The workflow's current status in the shared 6-state set."""
        ...

    async def node_states(self, workflow_id: str) -> dict[str, GraphNodeLifecycle]:
        """Per-node lifecycle states, normalized to the 12 §6 closed set."""
        ...

    async def cancel(self, workflow_id: str) -> None:
        """Request cancellation (12 §12 'execution cancellation')."""
        ...

    async def signal_approval(
        self,
        workflow_id: str,
        node_id: str,
        *,
        granted: bool,
        approver_ref: str,
    ) -> None:
        """Deliver an approval decision to a waiting_approval node (12 §11).

        ``approver_ref`` is the auditable actor reference — the approval
        result must be auditable (12 §11 verbatim).
        """
        ...
