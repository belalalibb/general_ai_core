"""Admin Agent contracts — AA-2 (doc C §4 AGT-1; doc A §3.3 tool taxonomy).

App-layer contracts (AA-2 adds NO new core modules). They reuse
:class:`core.contracts.base.ContractModel` (extra=forbid, frozen) so the
agent's own shapes obey the same closed-shape discipline as the platform.

Key honesty structures:

- ``ToolClass`` — the doc A §3.3 risk taxonomy as a CLOSED StrEnum.
  ``AA2_REGISTRABLE_CLASSES`` = {R0, R1} ONLY: the registry refuses to be
  CONSTRUCTED with anything above R1, so prompt injection cannot reach a
  mutation tool because none exists (structural, not behavioral).
- ``AgentClaim.evidence`` has ``min_length=1`` — a platform-fact claim
  without a machine-checkable citation cannot even be represented.
- ``ExecutionTrace.as_recorded`` is ``Literal[True]`` — the doc A §6
  "post-hoc, as recorded" label is part of the type, not a comment. There
  is no field for progress percentages; the shape cannot fake liveness.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject

# --- Tool risk taxonomy (doc A §3.3) ----------------------------------------------


class ToolClass(StrEnum):
    """Closed tool risk classes — doc A §3.3, verbatim ladder."""

    R0_READ = "r0_read"
    R1_EXECUTE_TEST = "r1_execute_test"
    R2_CONFIG_CHANGE = "r2_config_change"
    R3_SOURCE_CHANGE = "r3_source_change"
    R4_FORBIDDEN = "r4_forbidden"


#: AA-2 closed scope: ONLY read tools and budget-bounded test executions may
#: exist in the registry. R2/R3 belong to later phases; R4 never registers.
AA2_REGISTRABLE_CLASSES: frozenset[ToolClass] = frozenset(
    {ToolClass.R0_READ, ToolClass.R1_EXECUTE_TEST}
)

#: AA-3 closed scope (doc C §5): R2 config-change tools join the registry —
#: draft/validate/preview THROUGH the existing lifecycle ONLY. Publish and
#: rollback are NEVER agent tools (an explicit human UI act, criterion 2);
#: R3/R4 remain structurally unregistrable at any scope.
AA3_REGISTRABLE_CLASSES: frozenset[ToolClass] = AA2_REGISTRABLE_CLASSES | {
    ToolClass.R2_CONFIG_CHANGE
}

#: Classes that can NEVER register regardless of the phase's registrable set
#: (source changes are the operator-gated AA-4 track; R4 is forbidden by
#: definition). Enforced at registry construction unconditionally.
NEVER_REGISTRABLE_CLASSES: frozenset[ToolClass] = frozenset(
    {ToolClass.R3_SOURCE_CHANGE, ToolClass.R4_FORBIDDEN}
)


# --- Evidence (doc A §7: every platform-fact claim cites records) ------------------


class EvidenceKind(StrEnum):
    """What kind of platform record a citation points at — closed set."""

    EXECUTION = "execution"
    AUDIT_EVENT = "audit_event"
    CONFIG_CHANGE = "config_change"
    USAGE_SUMMARY = "usage_summary"
    MODEL = "model"
    PROVIDER = "provider"
    SYSTEM = "system"


class EvidenceRef(ContractModel):
    """One machine-checkable citation: kind + the record's own identifier."""

    kind: EvidenceKind
    ref: BoundedStr


class AgentClaim(ContractModel):
    """One platform-fact statement. Schema-enforced: evidence is mandatory."""

    text: BoundedStr
    evidence: list[EvidenceRef] = Field(min_length=1)


class ToolCallRecord(ContractModel):
    """One dispatched (or refused) tool call — the visible transcript row."""

    tool: BoundedStr
    tool_class: ToolClass
    arguments: JsonObject = Field(default_factory=dict)
    ok: bool
    result: JsonObject | None = None
    refusal: BoundedStr | None = None


class AgentAnswer(ContractModel):
    """One converse() turn: claims (all cited), transcript, reasoning ids."""

    claims: list[AgentClaim] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    reasoning_execution_ids: list[UUID] = Field(default_factory=list)
    note: BoundedStr | None = None
    #: How many bounded reason→act→observe rounds this turn ran.
    rounds: int = 1
    #: Closed stop vocabulary: final / max_rounds / continue_without_tools /
    #: invalid_proposal / reasoning_failed / verification_failed / max_steps
    #: — deterministic disposal, data.
    stop_reason: BoundedStr = "final"
    #: R159 — the shared loop's LAST deterministic verification verdict
    #: (``verified`` + counts + reason). None only when no final was ever
    #: proposed (reasoning_failed / invalid_proposal paths).
    verification: JsonObject | None = None
    #: R159 — per-round reasoning execution traces: the SAME derivation the
    #: /executions/{id}/trace route returns (model, provider, attempts,
    #: latency, ledger) — one converter, two consumers. Order = rounds.
    reasoning_trace: list[ExecutionTrace] = Field(default_factory=list)


# --- Diagnosis (doc A §7: tiered, evidence-cited, deterministic) -------------------


class DiagnosisTier(StrEnum):
    """Confidence tiers — assigned by RULE over records, never model opinion."""

    PROVEN_CAUSE = "proven_cause"
    LIKELY = "likely"
    POSSIBLE = "possible"
    UNDETERMINED = "undetermined"


class DiagnosisClaim(ContractModel):
    """One diagnosis statement with mandatory citations."""

    text: BoundedStr
    evidence: list[EvidenceRef] = Field(min_length=1)


class Diagnosis(ContractModel):
    """Deterministic post-hoc diagnosis of one recorded execution."""

    execution_id: UUID
    tier: DiagnosisTier
    claims: list[DiagnosisClaim] = Field(default_factory=list)
    missing_evidence: list[BoundedStr] = Field(default_factory=list)


# --- Trace (doc A §6: post-hoc, "as recorded", no fake progress) --------------------


class TraceAttempt(ContractModel):
    """One recorded provider attempt inside a stage."""

    attempt: int = Field(ge=1)
    model_key: BoundedStr
    provider_key: BoundedStr
    succeeded: bool
    error_category: BoundedStr | None = None
    safe_message: BoundedStr | None = None
    latency_ms: int | None = None


class TraceStage(ContractModel):
    """One recorded execution node with its attempt trail."""

    node_key: BoundedStr
    status: BoundedStr
    attempts: list[TraceAttempt] = Field(default_factory=list)


class ExecutionTrace(ContractModel):
    """The full post-hoc trace. ``as_recorded`` is structurally always True:
    this shape CANNOT represent live progress — doc A §6 honesty by type."""

    execution_id: UUID
    status: BoundedStr
    strategy: BoundedStr
    created_at: datetime
    completed_at: datetime | None = None
    stages: list[TraceStage] = Field(default_factory=list)
    #: R159 — resolved 03 §7 ledger (status/units) when usage accounting is
    #: bound; ``None`` = settlement pending / not bound (ledger-null honest,
    #: same shape as the executions-list row).
    ledger: JsonObject | None = None
    as_recorded: Literal[True] = True
