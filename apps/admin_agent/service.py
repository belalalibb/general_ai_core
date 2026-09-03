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
from uuid import UUID, uuid4

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
from apps.admin_agent.secrecy import scrub_object, scrub_text
from apps.admin_agent.tools import AGENT_LABEL_KEY, AgentToolSurface
from apps.api.app import Principal
from core.agent import AgentRuntime, ReasoningFailed
from core.audit.memory import InMemoryAuditLog
from core.contracts.base import JsonObject
from core.contracts.execute import ExecutionStatus
from core.contracts.security import ActorKind
from core.contracts.tools import Tool
from core.execution.agent import AgentToolBinding
from core.execution.loop import (
    STOP_MAX_STEPS,
    STOP_VERIFICATION_FAILED,
    AgentLoop,
    AgentRunReport,
)
from core.execution.service import ExecutionReport
from core.identity.devices import DeviceRegistry
from core.providers.errors import ModelNotRegistered, ProviderNotRegistered
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.tools import ToolCallGate, ToolExecutor
from core.tools import ToolRegistry as CoreToolRegistry
from core.usage.memory import InMemoryUsageAccounting

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


#: The synthetic per-turn tool through which the shared AgentLoop runs one
#: ROUND of admin tool calls. It grants nothing: every real call inside the
#: round still passes the ToolDispatcher's admission individually.
_ROUND_TOOL_NAME = "admin_round"
_ROUND_PERMISSION = "admin_agent.round.dispatch"
_ROUND_ENTITLEMENT = "admin_agent"


class _ReasoningFailed(Exception):
    """Internal: propose-seam signal that the reasoning execution failed."""


class _TurnState:
    """Mutable accumulation for ONE converse turn (bridge <-> handler)."""

    def __init__(self) -> None:
        self.index = _EvidenceIndex()
        self.transcript: list[ToolCallRecord] = []
        self.claims: list[AgentClaim] = []
        self.reasoning_ids: list[UUID] = []
        self.refused_claims = 0
        self.note: str | None = None
        self.rounds = 0
        self.stop_reason = "final"
        self.pending_final = False


class AdminAgentService:
    """Conversation loop + trace + diagnosis over injected platform seams."""

    def __init__(
        self,
        surface: AgentToolSurface,
        registry: ToolRegistry,
        dispatcher: ToolDispatcher,
        runtime: AgentRuntime | None = None,
    ) -> None:
        self._surface = surface
        self._registry = registry
        self._dispatcher = dispatcher
        # R160: the Admin agent REASONS through the SHARED ``core.agent``
        # runtime (Admin owns no generic implementation). The composition
        # root passes the platform's one runtime; when a caller composes
        # the service alone, a runtime is derived from the SAME surface
        # seams (router / execution / store) — never a private model path.
        self._runtime = (
            runtime
            if runtime is not None
            else AgentRuntime(
                router=surface.router,
                execution_service=surface.execution_service,
                tool_registry=CoreToolRegistry(),
                firewall=CapabilityFirewall(),
                devices=DeviceRegistry(),
                audit=surface.audit,
                usage=surface.usage,
                store_report=surface.execution_store.put,
            )
        )

    # --- conversation --------------------------------------------------------

    async def converse(self, caller: Principal, message: str) -> AgentAnswer:
        """Bounded reason→act→observe→reassess loop (mandate §8) — R156:
        driven by the SHARED :class:`core.execution.loop.AgentLoop`, so the
        same agent capability is consumable by future surfaces (IDE/SaaS)
        without copying loop logic. This service contributes ONLY:

        - the propose seam (``_reason`` through the platform's own execute
          path + the admin wire-protocol parse + the historical disposal
          rules), and
        - ONE act handler that dispatches a whole round's batched tool
          calls through the EXISTING ToolDispatcher — which remains the
          single admission authority for real tools (registry membership,
          admin gate, arg check, audit). The V3 gate/executor the shared
          loop requires is per-turn plumbing over one synthetic
          round-dispatch tool; it grants nothing beyond reaching that
          handler, and its audit/usage ports are turn-private so the
          OBSERVABLE audit and billing streams stay exactly the historical
          ones (dispatcher audit + reasoning executions).

        Behavior is pinned verbatim: max ``_MAX_ROUNDS`` model rounds,
        per-round flood bound, explicit ``"continue": true`` opt-in,
        observations feeding the next round's ask, the closed stop-reason
        vocabulary, evidence-gated claim admission, scrubbing unchanged.
        """
        state = _TurnState()
        loop = self._build_loop(caller, message, state)
        payload: JsonObject = {"message": message}
        report: AgentRunReport | None = None
        try:
            report = await loop.execute(
                tenant_id=caller.tenant_id,
                user_id=caller.user_id,
                request=payload,
                request_hash=hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                actor=ActorKind.USER,
                actor_id=caller.user_id,
            )
        except _ReasoningFailed:
            # Already recorded on state by the propose seam; the shared
            # loop treated it as a propose fault and stopped — historical
            # outcome shape preserved below.
            pass

        note = state.note
        if note is None and state.refused_claims:
            note = f"{state.refused_claims} claim(s) refused: missing or unverifiable evidence"
        stop_reason = state.stop_reason
        verification: JsonObject | None = None
        if report is not None:
            verification = report.verification
            # The shared loop's own terminal outcomes surface verbatim when
            # they are the REAL reason the turn ended (closed vocabulary).
            if report.stop_reason in (STOP_VERIFICATION_FAILED, STOP_MAX_STEPS):
                stop_reason = report.stop_reason
        return AgentAnswer(
            claims=state.claims,
            tool_calls=state.transcript,
            reasoning_execution_ids=state.reasoning_ids,
            note=note,
            rounds=state.rounds,
            stop_reason=stop_reason,
            verification=verification,
            reasoning_trace=self._reasoning_traces(caller, state.reasoning_ids),
        )

    def _reasoning_traces(
        self, caller: Principal, execution_ids: list[UUID]
    ) -> list[ExecutionTrace]:
        """Per-round traces from the SAME store + converter trace() uses."""
        traces: list[ExecutionTrace] = []
        for execution_id in execution_ids:
            try:
                report = self._surface.execution_store.get(caller.tenant_id, execution_id)
            except KeyError:
                continue  # never fabricate a trace for an unrecorded id
            traces.append(self._trace_report(report))
        return traces

    def _build_loop(self, caller: Principal, message: str, state: _TurnState) -> AgentLoop:
        """Compose one turn's shared AgentLoop over the V3 gated runtime.

        The synthetic ``admin_round`` tool exists ONLY so every act passes
        the shared loop's gated executor; real authority is unchanged —
        each proposed call inside a round still goes through
        ``self._dispatcher.dispatch`` (the admin Tool Gate) individually.
        """
        round_tool = Tool.model_validate(
            {
                "id": uuid4(),
                "name": _ROUND_TOOL_NAME,
                "version": "1.0.0",
                "location": "server",
                "permissions": [_ROUND_PERMISSION],
                "approval_policy": {_ROUND_PERMISSION: "none"},
                "status": "active",
            }
        )
        core_registry = CoreToolRegistry()
        core_registry.register(round_tool)
        firewall = CapabilityFirewall()
        firewall.set_tenant_policy(
            caller.tenant_id,
            TenantPolicy(
                granted_permissions=frozenset({_ROUND_PERMISSION}),
                granted_entitlements=frozenset({_ROUND_ENTITLEMENT}),
            ),
        )
        usage = InMemoryUsageAccounting()
        usage.configure_tenant(caller.tenant_id, plan="admin_agent_turn", task_units_limit=1.0)

        async def dispatch_round(arguments: JsonObject) -> JsonObject:
            """One round's acts: batched calls through the REAL dispatcher."""
            calls = arguments.get("calls")
            round_results: list[JsonObject] = []
            if isinstance(calls, list):
                for call in calls[:_MAX_TOOL_CALLS_PER_TURN]:
                    if not isinstance(call, dict):
                        continue
                    tool = str(call.get("tool", ""))
                    call_args = call.get("arguments")
                    if not isinstance(call_args, dict):
                        call_args = {}
                    record = await self._dispatcher.dispatch(caller, tool, call_args)
                    state.transcript.append(record)
                    if record.ok:
                        state.index.absorb(record.result)
                    observation: JsonObject = {
                        "tool": record.tool,
                        "ok": record.ok,
                    }
                    if record.result is not None:
                        observation["result"] = record.result
                    if record.refusal is not None:
                        observation["refusal"] = record.refusal
                    round_results.append(observation)
            claims = arguments.get("claims")
            if isinstance(claims, list):
                for raw_claim in claims:
                    admitted = self._admit_claim(raw_claim, state.index)
                    if admitted is None:
                        state.refused_claims += 1
                    else:
                        state.claims.append(admitted)
            return {"round": state.rounds, "results": round_results}

        executor = ToolExecutor(
            gate=ToolCallGate(
                tools=core_registry,
                firewall=firewall,
                devices=DeviceRegistry(),
            ),
            handlers={round_tool.id: dispatch_round},
            audit=InMemoryAuditLog(),  # turn-private plumbing (see docstring)
            usage=usage,
        )
        binding = AgentToolBinding(
            tool_id=round_tool.id,
            permission=_ROUND_PERMISSION,
            resource="admin_agent:round",
            scope="tenant",
            entitlement=_ROUND_ENTITLEMENT,
            risk_level="low",
        )

        async def propose(payload: JsonObject) -> JsonObject:
            return await self._propose_round(caller, message, state, payload)

        async def verify(_request: JsonObject, _output: JsonObject) -> JsonObject:
            return self._verify_turn(state)

        return AgentLoop(
            propose=propose,
            tools=executor,
            bindings={_ROUND_TOOL_NAME: binding},
            # Worst case: _MAX_ROUNDS act steps + the terminal final step.
            max_steps=_MAX_ROUNDS + 1,
            # R159: the shared deterministic Verify stage (R157) now guards
            # THIS consumer's finalization too — the admin agent inherits the
            # strongest existing loop behavior instead of bypassing it.
            verify=verify,
            # R165: the admin round handler does its OWN proposal parsing and
            # signals "stop" by emitting an out-of-vocabulary action; a repair
            # retry would re-enter the round with nothing new — single-shot.
            max_invalid_proposals=1,
            # Same reasoning for a reasoning FAULT: the admin turn reports
            # ``reasoning_failed`` honestly instead of re-asking the model.
            max_propose_failures=1,
        )

    @staticmethod
    def _verify_turn(state: _TurnState) -> JsonObject:
        """Deterministic finalization verdict over THIS turn's own records.

        Code, never the model (P4). The admin turn's final output is the
        set of admitted claims + transcript already accumulated on
        ``state``; the verdict therefore judges the EVIDENCE POSTURE of the
        turn, not prose. It rejects exactly one condition: the model made
        claims and EVERY one was refused for missing/invented evidence
        while tools DID surface results — i.e. the model finalized against
        its own evidence. Turns with no claims (pure tool runs, honest
        "nothing to report") and turns where at least one claim was
        admitted are verified. The terminal admin step is the loop's last
        step by construction (max_steps = rounds + 1), so a rejection is
        the closed ``verification_failed`` stop — bounded, no extra model
        call, the verdict rides the answer as evidence (P6).
        """
        claims_admitted = len(state.claims)
        claims_refused = state.refused_claims
        tools_ok = sum(1 for r in state.transcript if r.ok)
        verified = not (claims_admitted == 0 and claims_refused > 0 and tools_ok > 0)
        verdict: JsonObject = {
            "verified": verified,
            "claims_admitted": claims_admitted,
            "claims_refused": claims_refused,
            "tool_calls_ok": tools_ok,
            "tool_calls_total": len(state.transcript),
        }
        if not verified:
            verdict["reason"] = (
                "all claims refused for missing or invented evidence while "
                "tool results were available"
            )
        return verdict

    async def _propose_round(
        self,
        caller: Principal,
        message: str,
        state: _TurnState,
        payload: JsonObject,
    ) -> JsonObject:
        """The loop's propose seam — model call + deterministic disposal.

        Emits the shared loop's closed proposal vocabulary. The disposal
        decision (continue / finalize / bound) is computed HERE from the
        admin wire protocol, exactly as the historical inline loop did;
        the shared loop enforces the step bound and runs the act.
        """
        if state.pending_final:
            # The previous round chose (or was bounded into) finalization;
            # its acts already ran — terminate the run without a model call.
            return {"action": "final", "output": {"stop": state.stop_reason}}

        # Rebuild the historical observations shape from the LOOP's own
        # observation stream (the round handler returns {"round","results"}).
        raw_observations = payload.get("observations")
        observations: list[JsonObject] = []
        if isinstance(raw_observations, list):
            for entry in raw_observations:
                if isinstance(entry, dict) and isinstance(entry.get("result"), dict):
                    observations.append(entry["result"])

        round_no = state.rounds + 1
        raw, reasoning_id = await self._reason(
            caller, message, observations=observations, round_no=round_no
        )
        state.rounds = round_no
        if reasoning_id is not None:
            state.reasoning_ids.append(reasoning_id)
        if raw is None:
            state.note = "reasoning execution failed; nothing to report"
            state.stop_reason = "reasoning_failed"
            raise _ReasoningFailed(state.note)
        proposals, parse_note = self._parse_proposals(raw)
        if proposals is None:
            state.note = parse_note
            state.stop_reason = "invalid_proposal"
            # Deliberately outside the closed action vocabulary: the shared
            # validator refuses it and the loop stops — honest, contained.
            return {"action": "invalid_admin_proposal"}

        calls = proposals.get("tool_calls")
        calls = calls if isinstance(calls, list) else []
        dispatchable = sum(1 for call in calls[:_MAX_TOOL_CALLS_PER_TURN] if isinstance(call, dict))

        # --- deterministic disposal (verbatim historical rules) ------------
        if proposals.get("continue") is not True:
            state.stop_reason = "final"
            state.pending_final = True
        elif dispatchable == 0:
            state.stop_reason = "continue_without_tools"
            state.pending_final = True
        elif round_no == _MAX_ROUNDS:
            state.stop_reason = "max_rounds"
            state.pending_final = True

        return {
            "action": "tool_call",
            "tool": _ROUND_TOOL_NAME,
            "arguments": {
                "calls": calls,
                "claims": proposals.get("claims", []),
            },
        }

    async def _reason(
        self,
        caller: Principal,
        message: str,
        *,
        observations: list[JsonObject] | None = None,
        round_no: int = 1,
    ) -> tuple[str | None, UUID | None]:
        """The agent's model call — through the platform's OWN execute path."""
        ask = (
            _PROPOSAL_PROTOCOL.replace("{max_calls}", str(_MAX_TOOL_CALLS_PER_TURN))
            .replace("{max_rounds}", str(_MAX_ROUNDS))
            .replace(
                "{tools}",
                json.dumps(self._registry.describe(), ensure_ascii=False),
            )
            .replace("{message}", message)
        )
        if observations:
            ask += (
                "\nObservations from your previous rounds' tool calls "
                "(JSON):\n"
                + json.dumps(observations, ensure_ascii=False, default=str)
                + '\nDecide: call more tools (with "continue": true) or '
                "finalize with evidence-cited claims."
            )
        try:
            return await self._runtime.reason(
                tenant_id=caller.tenant_id,
                user_id=caller.user_id,
                prompt=ask,
                label={"round": round_no, "tools": self._registry.names()},
                label_key=AGENT_LABEL_KEY,
            )
        except ReasoningFailed as exc:
            # Routing / budget / failed execution: the historical disposal is
            # "no proposal this round" — the stored (failed) execution id, if
            # any, still reaches the trace.
            return None, exc.execution_id

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
        return self._trace_report(report)

    def _trace_report(self, report: ExecutionReport) -> ExecutionTrace:
        """ONE ExecutionReport -> ExecutionTrace derivation (two consumers)."""
        stages: list[TraceStage] = []
        for node_report in report.nodes:
            attempts = [
                TraceAttempt(
                    attempt=a.attempt,
                    model_key=self._model_key(a.candidate.model_id),
                    provider_key=self._provider_key(a.candidate.provider_id),
                    succeeded=a.succeeded,
                    error_category=(a.error.category.value if a.error is not None else None),
                    safe_message=(
                        scrub_text(a.error.safe_message)[:512] if a.error is not None else None
                    ),
                    latency_ms=a.latency_ms,
                )
                for a in node_report.attempts
            ]
            node_error = node_report.node.error
            stages.append(
                TraceStage(
                    node_key=node_report.node.node_key,
                    status=node_report.node.status.value,
                    attempts=attempts,
                    error=scrub_object(dict(node_error)) if node_error else None,
                )
            )
        execution = report.execution
        ledger: JsonObject | None = None
        if report.usage is not None:
            ledger = {
                "status": report.usage.status.value,
                "units_reserved": report.usage.units_reserved,
                "units_settled": report.usage.units_settled,
            }
        return ExecutionTrace(
            execution_id=execution.id,
            status=execution.status.value,
            strategy=execution.strategy.value,
            created_at=execution.created_at,
            completed_at=execution.completed_at,
            stages=stages,
            ledger=ledger,
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
