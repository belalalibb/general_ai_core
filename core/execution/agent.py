"""Agent-mode structured proposals (MASTER VISION v2 roadmap, Phase V4).

The frozen definition, verbatim: "Bounded plan→act→observe: model proposes
structured output → platform validates (R095 attach-at-surface validators
land in the same commit) → gate admits → executor runs → observation
appended; bounded by budget/step-count/admission. Model proposes;
deterministic code disposes. `ExecutionStrategy.AGENT` stops being
vocabulary."

This module is the VALIDATION half (the R095 same-commit validator):

- :func:`parse_agent_proposal` is the single deterministic parser that
  turns raw model output (untrusted, P7) into one of the two closed
  proposal shapes — or raises :class:`InvalidAgentProposal` naming the
  exact violation. The loop (ExecutionService.execute_agent) contains
  that error as node data; it never re-prompts silently and never guesses.
- :class:`AgentToolBinding` is the composition-declared security binding
  for ONE tool exposed to an agent run: the model proposes a tool NAME
  and arguments; permission / resource / scope / entitlement / risk_level
  are FIXED at composition and can never be influenced by model output
  (20 §1: the LLM is untrusted for authority decisions). Disposal builds
  the FirewallDecisionInput from this binding, verbatim.

Proposal wire shape (what the model must emit as its structured output):

.. code-block:: json

    {"action": "tool_call", "tool": "<name>", "arguments": {...},
     "reasoning": "optional string"}
    {"action": "final", "output": {...}, "reasoning": "optional string"}

Strictness mirrors the ContractModel posture (extra=forbid): any key
outside the declared set for the chosen action is a violation. The single
deliberate allowance is the optional ``reasoning`` string — inert
explanation data, recorded but never acted on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from core.contracts.base import JsonObject

#: The closed action vocabulary (deterministic disposal switch).
_ACTION_TOOL_CALL = "tool_call"
_ACTION_FINAL = "final"

_TOOL_CALL_KEYS = frozenset({"action", "tool", "arguments", "reasoning"})
_FINAL_KEYS = frozenset({"action", "output", "reasoning"})


class InvalidAgentProposal(Exception):
    """The model's structured output violates the proposal contract.

    Every instance NAMES the violated rule (11 §14 explainable outcomes).
    The agent loop contains this as node error data — an invalid proposal
    is a failed disposal, never a silent skip or a guessed repair (P4:
    model proposes, code disposes; a proposal code cannot dispose of is
    evidence of failure).
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid agent proposal: {reason}")


@dataclass(frozen=True)
class ToolCallProposal:
    """Validated ``action=tool_call`` proposal — a REQUEST, never authority.

    ``tool`` is a catalog NAME resolved against the composition-declared
    :class:`AgentToolBinding` mapping by the loop; an unknown name is a
    refused observation, not an error the model can exploit.
    """

    tool: str
    arguments: JsonObject
    reasoning: str | None = None


@dataclass(frozen=True)
class FinalProposal:
    """Validated ``action=final`` proposal — the run's terminal output."""

    output: JsonObject
    reasoning: str | None = None


AgentProposal = ToolCallProposal | FinalProposal


@dataclass(frozen=True)
class AgentToolBinding:
    """Composition-declared security binding for ONE agent-visible tool.

    Everything the Capability Firewall needs (20 §4 decision inputs) is
    fixed HERE, at composition, per tool — the model's proposal contributes
    ONLY the tool name and the arguments payload. ``estimated_units`` is
    the per-call reservation the V3 ToolExecutor holds before the handler
    runs (03 §7).
    """

    tool_id: UUID
    permission: str
    resource: str
    scope: str
    entitlement: str
    risk_level: str
    approval_state: Literal["approved"] | None = None
    device_id: UUID | None = None
    estimated_units: float = 0.0


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidAgentProposal(f"{field} must be a non-empty string")
    return value


def _optional_reasoning(data: JsonObject) -> str | None:
    reasoning = data.get("reasoning")
    if reasoning is None:
        return None
    if not isinstance(reasoning, str):
        raise InvalidAgentProposal("reasoning must be a string when present")
    return reasoning


def parse_agent_proposal(output: object) -> AgentProposal:
    """Validate raw model output into a proposal — the R095 validator.

    Deterministic and strict: the output must be a JSON object carrying
    ``action`` from the closed vocabulary; each action admits EXACTLY its
    declared keys (plus optional ``reasoning``); anything else raises
    :class:`InvalidAgentProposal` naming the violation. No repair, no
    coercion, no defaults — model proposes, code disposes (P4).
    """
    if not isinstance(output, dict):
        raise InvalidAgentProposal("proposal must be a JSON object")
    action = output.get("action")
    if action == _ACTION_TOOL_CALL:
        extra = set(output) - _TOOL_CALL_KEYS
        if extra:
            raise InvalidAgentProposal(f"unexpected keys for tool_call: {sorted(extra)}")
        if "arguments" not in output:
            raise InvalidAgentProposal("tool_call requires arguments")
        arguments = output["arguments"]
        if not isinstance(arguments, dict):
            raise InvalidAgentProposal("arguments must be a JSON object")
        return ToolCallProposal(
            tool=_require_str(output.get("tool"), "tool"),
            arguments=arguments,
            reasoning=_optional_reasoning(output),
        )
    if action == _ACTION_FINAL:
        extra = set(output) - _FINAL_KEYS
        if extra:
            raise InvalidAgentProposal(f"unexpected keys for final: {sorted(extra)}")
        if "output" not in output:
            raise InvalidAgentProposal("final requires output")
        final_output = output["output"]
        if not isinstance(final_output, dict):
            raise InvalidAgentProposal("output must be a JSON object")
        return FinalProposal(output=final_output, reasoning=_optional_reasoning(output))
    raise InvalidAgentProposal(f"action must be one of ['final', 'tool_call'], got {action!r}")
