"""core.agent — the SHARED agent runtime (R160).

One composition-bound runtime that every consumer (the public
``/v1/execute`` agent strategy, the Admin agent, any future external app)
runs its agent turns through. It owns NO authority of its own: tools come
from the ONE core ``ToolRegistry``, admission from the ONE
``CapabilityFirewall`` via the ONE ``ToolCallGate``/``ToolExecutor``, the
model call from the ONE routing + execution path, and every bound
(steps, deadline, repeated-failure) from the shared ``AgentLoop``.
"""

from core.agent.runtime import (
    DEFAULT_AGENT_DEADLINE_MS,
    DEFAULT_AGENT_MAX_STEPS,
    MAX_AGENT_MAX_STEPS,
    AgentRunOutcome,
    AgentRuntime,
    AgentToolSpec,
    ReasoningFailed,
    ResultCheck,
    ToolResultRejected,
    agent_execution_report,
    build_agent_prompt,
    evidence_verifier,
)

__all__ = [
    "DEFAULT_AGENT_DEADLINE_MS",
    "DEFAULT_AGENT_MAX_STEPS",
    "MAX_AGENT_MAX_STEPS",
    "AgentRunOutcome",
    "AgentRuntime",
    "AgentToolSpec",
    "ReasoningFailed",
    "ResultCheck",
    "ToolResultRejected",
    "agent_execution_report",
    "build_agent_prompt",
    "evidence_verifier",
]
