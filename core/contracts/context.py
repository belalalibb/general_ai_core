"""Composed-context contract (MVP Phase 6 slice 3, T-IMPL-027).

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/13_MEMORY_AND_CONTEXT.md §5
  (Context Composer inputs and output contract — the output example shape
  ``{"context_blocks": [...], "excluded": [...]}`` is carried verbatim:
  a block carries type/content/source/confidence; an exclusion carries
  reason/memory_id).
- 13 §4 scope priority (the conflict chain lives as data in
  ``core.contracts.memory.SCOPE_PRIORITY``).
- 13 §9 retrieval rules (scope/recency/confidence/security classification —
  the MVP subset; semantic similarity is R044 boundary (c), deferred).
- 11 §14 explainability posture mirrored: everything the composer leaves
  OUT is named data (``ExcludedMemory``), exactly like router exclusions.

Recorded decisions (contract-level, not silent):

- Block types are a CLOSED set for the 13 §5 MVP inputs this composer
  actually composes: ``role`` (system-role objective), ``preference``
  (memory item — the 13 §5 example's own type value, verbatim),
  ``history`` (conversation turn), ``ask`` (the current request). New
  input families (skills, project documents, ...) extend the enum in
  their own slices — they are not smuggled in as free-form strings.
- Exclusion reasons are a CLOSED set so tests and operators can rely on
  them; ``irrelevant`` is the 13 §5 example's own value, verbatim.
- ``confidence`` is optional on a block: memory-backed blocks carry the
  item's confidence (13 §5 example: 0.92); role/history/ask blocks have
  no confidence dimension and carry None — never a fabricated number.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel

# --- Closed sets ----------------------------------------------------------------


class ContextBlockType(StrEnum):
    """Context block type — closed set for the 13 §5 MVP composition."""

    ROLE = "role"
    PREFERENCE = "preference"
    HISTORY = "history"
    ASK = "ask"


class ContextExclusionReason(StrEnum):
    """Why a memory item was left out — closed, explainable set (11 §14).

    - ``irrelevant``: not relevant to this request (13 §5 example value,
      verbatim). MVP relevance = caller-declared key allowlist plus the
      role-scope rule below; semantic relevance is deferred (R044 (c)).
    - ``low_confidence``: below the composer's confidence threshold
      (13 §9: "Do not include low-confidence memory unless marked as
      uncertain" — the MVP has no uncertainty marking, so low-confidence
      memory is excluded, recorded here as a decision).
    - ``high_sensitivity``: sensitivity=high and policy did not allow it
      (13 §9 security classification).
    - ``scope_conflict``: lost the 13 §4 scope-priority conflict for its
      key to a more specific (or higher-confidence) item.
    - ``over_budget``: relevant and eligible, but the context budget was
      exhausted (13 §5 context budget input; 13 §10 "context budget
      respected").
    """

    IRRELEVANT = "irrelevant"
    LOW_CONFIDENCE = "low_confidence"
    HIGH_SENSITIVITY = "high_sensitivity"
    SCOPE_CONFLICT = "scope_conflict"
    OVER_BUDGET = "over_budget"


# --- Output contract (13 §5, shape verbatim) --------------------------------------


class ContextBlock(ContractModel):
    """One composed context block (13 §5 output example, field-for-field).

    ``source`` is a provenance reference like ``memory:<id>`` /
    ``role:<id>`` / ``message:<id>`` / ``request`` — the 13 §5 example
    uses ``"memory:123"``.
    """

    type: ContextBlockType
    content: str = Field(min_length=1, max_length=200_000)
    source: BoundedStr
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ExcludedMemory(ContractModel):
    """One named exclusion (13 §5 output example: reason + memory_id)."""

    reason: ContextExclusionReason
    memory_id: UUID


class ComposedContext(ContractModel):
    """Context Composer output (13 §5): included blocks + named exclusions.

    Deterministic block order (recorded): role, then memory preferences in
    scope-priority rank order, then history oldest-first, then the ask —
    the same inputs always compose the same context.
    """

    context_blocks: list[ContextBlock] = Field(default_factory=list)
    excluded: list[ExcludedMemory] = Field(default_factory=list)


# --- Input contract (13 §5 inputs, MVP subset) -------------------------------------


class ContextComposeRequest(ContractModel):
    """Context Composer inputs (13 §5) — the MVP subset, recorded honestly.

    13 §5 lists: current request, conversation state, project context,
    user preferences, relevant past decisions, role requirements, skill
    requirements, security policy, context budget. This request carries:

    - ``ask``: the current request text.
    - ``conversation_id``: conversation state (history tail via the
      T-IMPL-025 ConversationStorePort); None = no history.
    - ``role_id``: role requirements (admitted via the T-IMPL-026
      RoleRegistry.select — only ACTIVE roles compose).
    - memory (user preferences + past decisions) is retrieved from the
      MemoryStorePort by tenant/user — not passed in.
    - ``allow_high_sensitivity``: the security-policy input (13 §9
      security classification); default deny (20 §4 posture).
    - ``context_budget``: maximum total characters across all block
      contents (13 §5 context budget; enforcement recorded in the
      composer).
    - ``relevant_keys``: MVP relevance filter — when given, only memory
      keys in this allowlist are relevant; everything else is excluded
      as ``irrelevant``. Semantic relevance is deferred (R044 (c)).
    - Skill requirements are NOT composed in this slice (the R044
      slicing decision scopes slice 3 to role + history + memory + ask);
      project context arrives implicitly via project-scoped memory.
    """

    tenant_id: UUID
    user_id: UUID
    ask: str = Field(min_length=1, max_length=200_000)
    role_id: UUID | None = None
    conversation_id: UUID | None = None
    history_limit: int = Field(default=20, ge=0, le=1_000)
    context_budget: int = Field(default=16_000, ge=1, le=2_000_000)
    allow_high_sensitivity: bool = False
    relevant_keys: list[BoundedStr] | None = None
