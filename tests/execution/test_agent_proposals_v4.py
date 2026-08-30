"""Phase V4 chunk 1: the R095 structured-output validator for agent mode.

Frozen V4 clause: "model proposes structured output → platform validates
(R095 attach-at-surface validators land in the same commit)". The parser
is deterministic and strict — no repair, no coercion, every refusal names
the violated rule (11 §14). P7: model output is untrusted input.

Hermetic — pure functions, zero I/O.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.execution.agent import (
    AgentToolBinding,
    FinalProposal,
    InvalidAgentProposal,
    ToolCallProposal,
    parse_agent_proposal,
)

# --- tool_call ------------------------------------------------------------------------


def test_valid_tool_call_parses() -> None:
    proposal = parse_agent_proposal(
        {
            "action": "tool_call",
            "tool": "github.read",
            "arguments": {"path": "README.md"},
            "reasoning": "need the readme",
        }
    )
    assert isinstance(proposal, ToolCallProposal)
    assert proposal.tool == "github.read"
    assert proposal.arguments == {"path": "README.md"}
    assert proposal.reasoning == "need the readme"


def test_tool_call_reasoning_optional() -> None:
    proposal = parse_agent_proposal(
        {"action": "tool_call", "tool": "t", "arguments": {}}
    )
    assert isinstance(proposal, ToolCallProposal)
    assert proposal.reasoning is None


def test_tool_call_requires_arguments() -> None:
    with pytest.raises(InvalidAgentProposal, match="tool_call requires arguments"):
        parse_agent_proposal({"action": "tool_call", "tool": "t"})


def test_tool_call_arguments_must_be_object() -> None:
    with pytest.raises(InvalidAgentProposal, match="arguments must be a JSON object"):
        parse_agent_proposal(
            {"action": "tool_call", "tool": "t", "arguments": ["not", "a", "dict"]}
        )


def test_tool_call_tool_must_be_nonempty_string() -> None:
    with pytest.raises(InvalidAgentProposal, match="tool must be a non-empty string"):
        parse_agent_proposal({"action": "tool_call", "tool": "", "arguments": {}})
    with pytest.raises(InvalidAgentProposal, match="tool must be a non-empty string"):
        parse_agent_proposal({"action": "tool_call", "tool": 7, "arguments": {}})


def test_tool_call_extra_keys_rejected() -> None:
    """extra=forbid posture — a smuggled key is a violation, never ignored."""
    with pytest.raises(InvalidAgentProposal, match=r"unexpected keys.*permission"):
        parse_agent_proposal(
            {
                "action": "tool_call",
                "tool": "t",
                "arguments": {},
                "permission": "admin.everything",  # authority injection attempt
            }
        )


# --- final ----------------------------------------------------------------------------


def test_valid_final_parses() -> None:
    proposal = parse_agent_proposal(
        {"action": "final", "output": {"answer": 42}, "reasoning": "done"}
    )
    assert isinstance(proposal, FinalProposal)
    assert proposal.output == {"answer": 42}
    assert proposal.reasoning == "done"


def test_final_requires_output() -> None:
    with pytest.raises(InvalidAgentProposal, match="final requires output"):
        parse_agent_proposal({"action": "final"})


def test_final_output_must_be_object() -> None:
    with pytest.raises(InvalidAgentProposal, match="output must be a JSON object"):
        parse_agent_proposal({"action": "final", "output": "just text"})


def test_final_extra_keys_rejected() -> None:
    with pytest.raises(InvalidAgentProposal, match=r"unexpected keys.*tool"):
        parse_agent_proposal({"action": "final", "output": {}, "tool": "x"})


# --- action vocabulary / shape ---------------------------------------------------------


def test_unknown_action_rejected() -> None:
    with pytest.raises(InvalidAgentProposal, match="action must be one of"):
        parse_agent_proposal({"action": "execute_anything", "arguments": {}})


def test_missing_action_rejected() -> None:
    with pytest.raises(InvalidAgentProposal, match="action must be one of"):
        parse_agent_proposal({"output": {}})


def test_non_object_rejected() -> None:
    for bad in ("final", 3, None, ["action", "final"]):
        with pytest.raises(InvalidAgentProposal, match="must be a JSON object"):
            parse_agent_proposal(bad)


def test_reasoning_must_be_string_when_present() -> None:
    with pytest.raises(InvalidAgentProposal, match="reasoning must be a string"):
        parse_agent_proposal(
            {"action": "final", "output": {}, "reasoning": {"chain": []}}
        )


def test_error_names_the_rule_and_carries_reason() -> None:
    """11 §14 — every refusal names the violated rule as data."""
    with pytest.raises(InvalidAgentProposal) as exc:
        parse_agent_proposal({"action": "nope"})
    assert exc.value.reason.startswith("action must be one of")
    assert "invalid agent proposal:" in str(exc.value)


# --- AgentToolBinding ------------------------------------------------------------------


def test_binding_is_frozen_composition_data() -> None:
    """The security binding is immutable — model output can never mutate it."""
    binding = AgentToolBinding(
        tool_id=uuid4(),
        permission="github.repo.read",
        resource="repo:owner/name",
        scope="project",
        entitlement="github_read",
        risk_level="low",
    )
    with pytest.raises(AttributeError):
        binding.permission = "admin.everything"  # type: ignore[misc]
    assert binding.approval_state is None
    assert binding.device_id is None
    assert binding.estimated_units == 0.0
