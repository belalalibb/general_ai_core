"""AdminAgentService — AA-2 conversation loop, trace, diagnosis.

Conversation loop (doc A §3.2 "model proposes / deterministic code
disposes"):

1. ``_reason`` sends the admin's message through the platform's OWN
   execute path (no side-channel LLM). That call is itself an Execution —
   stored, labeled ``{"admin_agent": {"kind": "reasoning"}}``, billed.
2. The model's output is PARSED as a JSON proposal
   ``{"tool_calls": [...], "claims": [...]}``. Malformed output is INERT
   (honest note, nothing dispatched).
3. Proposed tool calls go through the deterministic dispatcher — capped at
   ``_MAX_TOOL_CALLS_PER_TURN`` (flood-bounded).
4. Claims are admitted ONLY if schema-valid (evidence min_length=1) AND
   every citation matches a record actually surfaced by THIS turn's tool
   results (``_EvidenceIndex``) — invented citations are refused.

``trace``/``diagnose`` are post-hoc readers over the recorded
ExecutionReport — deterministic, never model opinion (doc A §6/§7).
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from pydantic import ValidationError

from apps.admin_agent.contracts import (
    AgentAnswer,
    AgentClaim,
    Diagnosis,
    DiagnosisClaim,
    DiagnosisTier,
    EvidenceKind,
    EvidenceRef,
    ExecutionTrace,
    ToolCallRecord,
    TraceAttempt,
    TraceStage,
)
from apps.admin_agent.dispatcher import ToolDispatcher, ToolRegistry
from apps.admin_agent.secrecy import scrub_text
from apps.admin_agent.tools import AGENT_LABEL_KEY, AgentToolSurface
from apps.api.app import Principal
from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.execution.service import ExecutionReport
from core.providers.errors import ModelNotRegistered, ProviderNotRegistered
from core.routing.errors import FallbackNotConfigured, NoEligibleCandidates
from core.routing.router import UnsupportedPolicyType
from core.usage.errors import BudgetExceeded, EntitlementNotConfigured

#: Flood bound: a single ROUND may dispatch at most this many tool calls.
_MAX_TOOL_CALLS_PER_TURN = 8

#: Iteration bound: one converse() may run at most this many reasoning
#: rounds. Continuation is EXPLICIT (the model sets ``"continue": true``
#: after proposing tool calls) — deterministic code disposes: no tool
#: calls dispatched, or rounds exhausted, or a missing flag all terminate.
#: Every round's reasoning call is itself budget-bounded, so iteration can
#: never outrun the tenant's entitlement.
_MAX_ROUNDS = 3

#: The proposal protocol, stated to the model verbatim. Without this framing
#: a real model answers in prose and the loop is honestly inert (proven live
#: during the handoff review) — the parser refuses non-JSON, nothing
#: dispatches. The framing is pure composition data: the contract the parser
#: already enforces plus the registry's own describe() output. No new
#: capability, no relaxation of parsing/evidence rules.
_PROPOSAL_PROTOCOL = (
    "You are the platform's admin agent. Respond with ONLY one raw JSON "
    "object (no markdown fences, no prose before or after) of the shape:\n"
    '{"tool_calls": [{"tool": "<name>", "arguments": {...}}], '
    '"claims": [{"text": "<statement>", "evidence": '
    '[{"kind": "<kind>", "ref": "<id from THIS turn\'s tool results>"}]}]}\n'
    "Rules: use only the tools listed below with only their allowed "
    "arguments; at most {max_calls} tool calls; every claim must cite "
    "evidence refs that appear in this turn's tool results, otherwise the "
    "claim is refused; if no tool applies, return empty lists.\n"
    'Iteration: you may add "continue": true alongside tool_calls to '
    "observe their results and act again next round (at most {max_rounds} "
    "rounds); omit it to finalize this round.\n"
    "Available tools:\n{tools}\n"
    "Admin message:\n{message}"
)

#: Result-record keys that establish citable evidence, mapped to kinds.
_REF_KEYS: dict[str, EvidenceKind] = {
    "execution_id": EvidenceKind.EXECUTION,
    "audit_event_id": EvidenceKind.AUDIT_EVENT,
    "change_id": EvidenceKind.CONFIG_CHANGE,
    "model_key": EvidenceKind.MODEL,
    "provider_key": EvidenceKind.PROVIDER,
    "plan": EvidenceKind.USAGE_SUMMARY,
}


class _EvidenceIndex:
    """Which (kind, ref) pairs THIS turn's tool results actually surfaced."""

    def __init__(self) -> None:
        self._seen: set[tuple[EvidenceKind, str]] = set()

    def absorb(self, result: JsonObject | None) -> None:
        if result is None:
            return
        self._walk(result)

    def _walk(self, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                kind = _REF_KEYS.get(key)
                if kind is not None and isinstance(item, str):
                    self._seen.add((kind, item))
                self._walk(item)
        elif isinstance(value, list):
            for item in value:
                self._walk(item)

    def contains(self, ref: EvidenceRef) -> bool:
        return (ref.kind, ref.ref) in self._seen


class AdminAgentService:
    """Conversation loop + trace + diagnosis over injected platform seams."""

    def __init__(
        self,
        surface: AgentToolSurface,
        registry: ToolRegistry,
        dispatcher: ToolDispatcher,
    ) -> None:
        self._surface = surface
        self._registry = registry
        self._dispatcher = dispatcher

    # --- conversation --------------------------------------------------------

    async def converse(self, caller: Principal, message: str) -> AgentAnswer:
        """Bounded reason→act→observe→reassess loop (mandate §8).

        Round 1 is the historical single-turn behavior verbatim. The model
        OPTS INTO iteration by returning ``"continue": true`` next to tool
        calls; deterministic code disposes: continuation requires at least
        one dispatched tool call this round and a remaining round budget.
        The next round's ask carries the (already scrubbed) observations,
        so the second action can genuinely change because of the first
        result. Termination is structural: ``_MAX_ROUNDS``.
        """
        index = _EvidenceIndex()
        transcript: list[ToolCallRecord] = []
        claims: list[AgentClaim] = []
        reasoning_ids: list[UUID] = []
        observations: list[JsonObject] = []
        refused_claims = 0
        note: str | None = None
        rounds = 0
        stop_reason = "final"

        for round_no in range(1, _MAX_ROUNDS + 1):
            rounds = round_no
            raw, reasoning_id = await self._reason(
                caller, message, observations=observations, round_no=round_no
            )
            if reasoning_id is not None:
                reasoning_ids.append(reasoning_id)
            if raw is None:
                note = "reasoning execution failed; nothing to report"
                stop_reason = "reasoning_failed"
                break
            proposals, parse_note = self._parse_proposals(raw)
            if proposals is None:
                note = parse_note
                stop_reason = "invalid_proposal"
                break

            round_results: list[JsonObject] = []
            for call in proposals.get("tool_calls", [])[:_MAX_TOOL_CALLS_PER_TURN]:
                if not isinstance(call, dict):
                    continue
                tool = str(call.get("tool", ""))
                arguments = call.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                record = await self._dispatcher.dispatch(caller, tool, arguments)
                transcript.append(record)
                if record.ok:
                    index.absorb(record.result)
                # Observation = the record's own (already scrubbed) data.
                observation: JsonObject = {"tool": record.tool, "ok": record.ok}
                if record.result is not None:
                    observation["result"] = record.result
                if record.refusal is not None:
                    observation["refusal"] = record.refusal
                round_results.append(observation)

            for raw_claim in proposals.get("claims", []):
                admitted = self._admit_claim(raw_claim, index)
                if admitted is None:
                    refused_claims += 1
                else:
                    claims.append(admitted)

            # --- deterministic disposal of the continuation request ----------
            if proposals.get("continue") is not True:
                stop_reason = "final"
                break
            if not round_results:
                stop_reason = "continue_without_tools"
                break
            if round_no == _MAX_ROUNDS:
                stop_reason = "max_rounds"
                break
            observations.append({"round": round_no, "results": round_results})

        if note is None and refused_claims:
            note = f"{refused_claims} claim(s) refused: missing or unverifiable evidence"
        return AgentAnswer(
            claims=claims,
            tool_calls=transcript,
            reasoning_execution_ids=reasoning_ids,
            note=note,
            rounds=rounds,
            stop_reason=stop_reason,
        )

    async def _reason(
        self,
        caller: Principal,
        message: str,
        *,
        observations: list[JsonObject] | None = None,
        round_no: int = 1,
    ) -> tuple[str | None, UUID | None]:
        """The agent's model call — through the platform's OWN execute path."""
        ask = _PROPOSAL_PROTOCOL.replace(
            "{max_calls}", str(_MAX_TOOL_CALLS_PER_TURN)
        ).replace(
            "{max_rounds}", str(_MAX_ROUNDS)
        ).replace(
            "{tools}",
            json.dumps(self._registry.describe(), ensure_ascii=False),
        ).replace("{message}", message)
        if observations:
            ask += (
                "\nObservations from your previous rounds' tool calls "
                "(JSON):\n"
                + json.dumps(observations, ensure_ascii=False, default=str)
                + '\nDecide: call more tools (with "continue": true) or '
                "finalize with evidence-cited claims."
            )
        payload: JsonObject = {
            "ask": ask,
            "context": {
                "metadata": {
                    AGENT_LABEL_KEY: {
                        "kind": "reasoning",
                        "round": round_no,
                        "tools": self._registry.names(),
                    }
                }
            },
        }
        try:
            decision = self._surface.router.route(
                RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
            )
        except (NoEligibleCandidates, FallbackNotConfigured, UnsupportedPolicyType):
            return None, None
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        try:
            report = self._surface.execution_service
            result = await report.execute_single(
                tenant_id=caller.tenant_id,
                user_id=caller.user_id,
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload=payload,
                request_hash=request_hash,
            )
        except (BudgetExceeded, EntitlementNotConfigured):
            return None, None
        self._surface.execution_store.put(result)
        output = result.final_output
        if output is None:
            return None, result.execution.id
        content = output.get("content")
        if not isinstance(content, str):
            content = json.dumps(output)
        return content, result.execution.id

    @staticmethod
    def _parse_proposals(raw: str) -> tuple[JsonObject | None, str | None]:
        # Deterministic fence-stripping ONLY (real models routinely wrap JSON
        # in ```json fences — observed live). No repair, no guessing: if the
        # unfenced text is not valid JSON the proposal is refused exactly as
        # before.
        text = raw.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1 and text.endswith("```"):
                text = text[first_newline + 1 : -3].strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None, "model output was not a valid proposal; nothing dispatched"
        if not isinstance(parsed, dict):
            return None, "model output was not a valid proposal; nothing dispatched"
        return parsed, None

    @staticmethod
    def _admit_claim(raw_claim: object, index: _EvidenceIndex) -> AgentClaim | None:
        if not isinstance(raw_claim, dict):
            return None
        text = raw_claim.get("text")
        evidence_raw = raw_claim.get("evidence")
        if not isinstance(text, str) or not isinstance(evidence_raw, list):
            return None
        refs: list[EvidenceRef] = []
        for item in evidence_raw:
            if not isinstance(item, dict):
                return None
            try:
                ref = EvidenceRef(**item)
            except (ValidationError, TypeError):
                return None
            if not index.contains(ref):
                return None  # invented citation — refuse the whole claim
            refs.append(ref)
        if not refs:
            return None
        try:
            return AgentClaim(text=scrub_text(text)[:512], evidence=refs)
        except ValidationError:
            return None

    # --- trace (doc A §6, post-hoc "as recorded") -----------------------------

    def _model_key(self, model_id: UUID) -> str:
        try:
            return self._surface.models.get_by_id(model_id).model_key
        except ModelNotRegistered:
            return f"model:{model_id}"

    def _provider_key(self, provider_id: UUID) -> str:
        try:
            return self._surface.providers.get_by_id(provider_id).provider.provider_key
        except ProviderNotRegistered:
            return f"provider:{provider_id}"

    def trace(self, caller: Principal, execution_id: UUID) -> ExecutionTrace | None:
        try:
            report = self._surface.execution_store.get(caller.tenant_id, execution_id)
        except KeyError:
            return None
        stages: list[TraceStage] = []
        for node_report in report.nodes:
            attempts = [
                TraceAttempt(
                    attempt=a.attempt,
                    model_key=self._model_key(a.candidate.model_id),
                    provider_key=self._provider_key(a.candidate.provider_id),
                    succeeded=a.succeeded,
                    error_category=(
                        a.error.category.value if a.error is not None else None
                    ),
                    safe_message=(
                        scrub_text(a.error.safe_message)[:512]
                        if a.error is not None
                        else None
                    ),
                    latency_ms=a.latency_ms,
                )
                for a in node_report.attempts
            ]
            stages.append(
                TraceStage(
                    node_key=node_report.node.node_key,
                    status=node_report.node.status.value,
                    attempts=attempts,
                )
            )
        execution = report.execution
        return ExecutionTrace(
            execution_id=execution.id,
            status=execution.status.value,
            strategy=execution.strategy.value,
            created_at=execution.created_at,
            completed_at=execution.completed_at,
            stages=stages,
        )

    # --- diagnosis (doc A §7, deterministic tiers) ----------------------------

    def diagnose(self, caller: Principal, execution_id: UUID) -> Diagnosis | None:
        try:
            report = self._surface.execution_store.get(caller.tenant_id, execution_id)
        except KeyError:
            return None
        return self._diagnose_report(report)

    @staticmethod
    def _diagnose_report(report: ExecutionReport) -> Diagnosis:
        execution = report.execution
        ref = EvidenceRef(kind=EvidenceKind.EXECUTION, ref=str(execution.id))
        if execution.status is ExecutionStatus.SUCCEEDED:
            return Diagnosis(
                execution_id=execution.id,
                tier=DiagnosisTier.PROVEN_CAUSE,
                claims=[
                    DiagnosisClaim(
                        text="execution succeeded; no failure to diagnose",
                        evidence=[ref],
                    )
                ],
            )
        for node_report in report.nodes:
            for attempt in node_report.attempts:
                if not attempt.succeeded and attempt.error is not None:
                    error = attempt.error
                    text = (
                        f"first failed attempt: provider error category "
                        f"'{error.category.value}' — "
                        f"{scrub_text(error.safe_message)}"
                    )[:512]
                    return Diagnosis(
                        execution_id=execution.id,
                        tier=DiagnosisTier.PROVEN_CAUSE,
                        claims=[DiagnosisClaim(text=text, evidence=[ref])],
                    )
        return Diagnosis(
            execution_id=execution.id,
            tier=DiagnosisTier.UNDETERMINED,
            claims=[
                DiagnosisClaim(
                    text="execution did not succeed but no provider error was recorded",
                    evidence=[ref],
                )
            ],
            missing_evidence=["no failed AttemptRecord with a recorded ProviderError"],
        )
