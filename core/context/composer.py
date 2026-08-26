"""Context composer service (MVP Phase 6 slice 3, T-IMPL-027).

Spec anchors:

- 13 §5: inputs/output contract — composes role + memory + history + ask
  into ``ComposedContext`` with NAMED exclusions.
- 13 §4: scope priority (Conversation > Project > Workspace > User >
  Tenant > Global), more-specific-wins-unless-low-confidence. The chain
  lives as data in ``core.contracts.memory.SCOPE_PRIORITY``; "User" rank
  is user OWNERSHIP within a scope tier (03 §3 has no user scope value).
- 13 §9 retrieval rules, MVP subset: scope + recency + confidence +
  security classification. Semantic similarity is DEFERRED (R044
  boundary (c)) — MVP relevance is the caller's key allowlist plus the
  role-scope rule below, recorded honestly.
- 11 §14 posture mirrored: everything left out is explainable data
  (``ExcludedMemory``), exactly like router exclusions.

Recorded decisions (this module):

- DETERMINISTIC composition: role → memory (scope-priority rank, then
  key, then id) → history oldest-first tail → ask. Same inputs, same
  output.
- ROLE-scoped memory sits OUTSIDE the 13 §4 conflict chain: it is
  relevant only when a role is composed (13 §9 role relevance) and it
  never competes in scope-priority conflicts — both facts inherited from
  the T-IMPL-025 contract-level decision.
- Gate order per item: relevance → sensitivity → confidence → scope
  conflict → budget. Each item is excluded at the FIRST failing gate
  with that gate's named reason.
- "More specific wins UNLESS low confidence" (13 §4) is realized by the
  confidence gate running BEFORE conflict resolution: a low-confidence
  specific item is excluded as ``low_confidence`` and the confident
  broader item wins its key.
- Budget (13 §5/§10): mandatory blocks (role + ask) must fit or the
  composer FAILS LOUDLY (``ContextBudgetExceeded``); optional blocks
  degrade gracefully — memory items that do not fit are excluded as
  ``over_budget``; history keeps the NEWEST contiguous tail that fits
  (a history gap would silently misrepresent the conversation, so the
  tail is contiguous by construction). Budget unit = characters of
  block content (model-agnostic; token budgeting binds with a tokenizer
  in a later phase — recorded, not smuggled).
- Dropped history turns carry no ``memory_id`` and the 13 §5 exclusion
  shape is memory-only, so they are trimmed without an exclusion row;
  the contiguous-tail rule keeps that trim predictable.
"""

from __future__ import annotations

import json

from core.context.errors import ContextBudgetExceeded
from core.contracts.context import (
    ComposedContext,
    ContextBlock,
    ContextBlockType,
    ContextComposeRequest,
    ContextExclusionReason,
    ExcludedMemory,
)
from core.contracts.conversation import Message
from core.contracts.memory import SCOPE_PRIORITY, MemoryItem, MemoryScope, MemorySensitivity
from core.memory.ports import ConversationStorePort, MemoryStorePort
from core.roles.registry import RoleRegistry

# ROLE scope is outside the 13 §4 chain: rank AFTER every chain scope so
# role-scoped blocks compose last among memory, never win conflicts.
_ROLE_SCOPE_RANK = len(SCOPE_PRIORITY)

_SCOPE_RANK: dict[MemoryScope, int] = {
    scope: index for index, scope in enumerate(SCOPE_PRIORITY)
}
_SCOPE_RANK[MemoryScope.ROLE] = _ROLE_SCOPE_RANK


def _render_memory(item: MemoryItem) -> str:
    """Render a memory item as a stable ``key = <json value>`` line."""
    return f"{item.key} = {json.dumps(item.value, ensure_ascii=False, sort_keys=True)}"


def _render_message(message: Message) -> str:
    """Render a history turn as ``<role>: <content>``."""
    return f"{message.role.value}: {message.content}"


class ContextComposer:
    """Composes 13 §5 context from the existing ports/registries.

    No new storage: memory arrives through the T-IMPL-025
    ``MemoryStorePort`` (tenant-scoped, cross-user-invisible per 13 §7),
    history through ``ConversationStorePort``, and the role through the
    T-IMPL-026 ``RoleRegistry.select`` admission (only ACTIVE roles
    compose; denial is the registry's own named error).
    """

    def __init__(
        self,
        memory_store: MemoryStorePort,
        conversation_store: ConversationStorePort,
        role_registry: RoleRegistry,
        min_confidence: float = 0.5,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be within [0.0, 1.0], got {min_confidence}"
            )
        self._memory = memory_store
        self._conversations = conversation_store
        self._roles = role_registry
        self._min_confidence = min_confidence

    def compose(self, request: ContextComposeRequest) -> ComposedContext:
        """Compose the context for one request (13 §5), deterministically."""
        excluded: list[ExcludedMemory] = []

        # --- mandatory blocks: role (if requested) + ask -------------------
        role_block: ContextBlock | None = None
        if request.role_id is not None:
            role = self._roles.select(request.role_id)  # named denial if not active
            role_block = ContextBlock(
                type=ContextBlockType.ROLE,
                content=role.objective,
                source=f"role:{role.id}",
            )
        ask_block = ContextBlock(
            type=ContextBlockType.ASK, content=request.ask, source="request"
        )

        mandatory_cost = len(ask_block.content) + (
            len(role_block.content) if role_block is not None else 0
        )
        if mandatory_cost > request.context_budget:
            raise ContextBudgetExceeded(mandatory_cost, request.context_budget)
        remaining = request.context_budget - mandatory_cost

        # --- memory: retrieve, gate, resolve conflicts, then fit budget ----
        eligible = self._gate_memory(request, excluded)
        winners = self._resolve_scope_conflicts(eligible, excluded)
        memory_blocks, remaining = self._fit_memory_budget(
            winners, remaining, excluded
        )

        # --- history: newest contiguous tail that fits ---------------------
        history_blocks = self._compose_history(request, remaining)

        blocks: list[ContextBlock] = []
        if role_block is not None:
            blocks.append(role_block)
        blocks.extend(memory_blocks)
        blocks.extend(history_blocks)
        blocks.append(ask_block)
        return ComposedContext(context_blocks=blocks, excluded=excluded)

    # --- gates (relevance → sensitivity → confidence) -----------------------

    def _gate_memory(
        self,
        request: ContextComposeRequest,
        excluded: list[ExcludedMemory],
    ) -> list[MemoryItem]:
        """Apply the per-item gates; each failure is a NAMED exclusion.

        Retrieval itself is already tenant-scoped and cross-user-invisible
        (13 §7 at the port): other tenants'/users' items never even reach
        the gates, so they produce NO exclusion rows (invisible, 20 §6).
        """
        items = self._memory.query(request.tenant_id, user_id=request.user_id)
        eligible: list[MemoryItem] = []
        # Deterministic gate order regardless of store recency ordering.
        for item in sorted(
            items, key=lambda m: (_SCOPE_RANK[m.scope], m.key, str(m.id))
        ):
            if not self._is_relevant(item, request):
                excluded.append(
                    ExcludedMemory(
                        reason=ContextExclusionReason.IRRELEVANT, memory_id=item.id
                    )
                )
                continue
            if (
                item.sensitivity is MemorySensitivity.HIGH
                and not request.allow_high_sensitivity
            ):
                excluded.append(
                    ExcludedMemory(
                        reason=ContextExclusionReason.HIGH_SENSITIVITY,
                        memory_id=item.id,
                    )
                )
                continue
            if item.confidence < self._min_confidence:
                excluded.append(
                    ExcludedMemory(
                        reason=ContextExclusionReason.LOW_CONFIDENCE,
                        memory_id=item.id,
                    )
                )
                continue
            eligible.append(item)
        return eligible

    @staticmethod
    def _is_relevant(item: MemoryItem, request: ContextComposeRequest) -> bool:
        """MVP relevance (semantic similarity deferred, R044 (c)).

        - ROLE-scoped memory is relevant only when a role is composed
          (13 §9 role relevance).
        - When the caller declares ``relevant_keys``, only those keys are
          relevant; without the allowlist, everything else is relevant.
        """
        if item.scope is MemoryScope.ROLE and request.role_id is None:
            return False
        if request.relevant_keys is not None and item.key not in request.relevant_keys:
            return False
        return True

    # --- 13 §4 scope-priority conflict resolution ---------------------------

    @staticmethod
    def _resolve_scope_conflicts(
        eligible: list[MemoryItem], excluded: list[ExcludedMemory]
    ) -> list[MemoryItem]:
        """One winner per key among chain scopes; losers are named.

        Rank: scope-priority tier first, then user ownership within the
        tier (13 §4 "User" rank — a user-owned item outranks a
        tenant-shared item of the same tier), then id for determinism.
        ROLE-scoped items never compete (outside the chain).
        """
        winners: list[MemoryItem] = []
        by_key: dict[str, list[MemoryItem]] = {}
        for item in eligible:
            if item.scope is MemoryScope.ROLE:
                winners.append(item)
                continue
            by_key.setdefault(item.key, []).append(item)
        for contenders in by_key.values():
            contenders.sort(
                key=lambda m: (
                    _SCOPE_RANK[m.scope],
                    0 if m.user_id is not None else 1,
                    str(m.id),
                )
            )
            winners.append(contenders[0])
            excluded.extend(
                ExcludedMemory(
                    reason=ContextExclusionReason.SCOPE_CONFLICT, memory_id=loser.id
                )
                for loser in contenders[1:]
            )
        winners.sort(key=lambda m: (_SCOPE_RANK[m.scope], m.key, str(m.id)))
        return winners

    # --- budget fitting ------------------------------------------------------

    @staticmethod
    def _fit_memory_budget(
        winners: list[MemoryItem],
        remaining: int,
        excluded: list[ExcludedMemory],
    ) -> tuple[list[ContextBlock], int]:
        """Include winners in composed order while they fit (13 §10)."""
        blocks: list[ContextBlock] = []
        for item in winners:
            content = _render_memory(item)
            if len(content) > remaining:
                excluded.append(
                    ExcludedMemory(
                        reason=ContextExclusionReason.OVER_BUDGET, memory_id=item.id
                    )
                )
                continue
            remaining -= len(content)
            blocks.append(
                ContextBlock(
                    type=ContextBlockType.PREFERENCE,
                    content=content,
                    source=f"memory:{item.id}",
                    confidence=item.confidence,
                )
            )
        return blocks, remaining

    def _compose_history(
        self, request: ContextComposeRequest, remaining: int
    ) -> list[ContextBlock]:
        """Newest contiguous history tail that fits, composed oldest-first."""
        if request.conversation_id is None or request.history_limit == 0:
            return []
        messages = self._conversations.get_history(
            request.tenant_id, request.conversation_id, limit=request.history_limit
        )
        kept: list[Message] = []
        for message in reversed(messages):  # newest first
            cost = len(_render_message(message))
            if cost > remaining:
                break  # contiguous tail: stop at the first turn that misses
            remaining -= cost
            kept.append(message)
        kept.reverse()  # compose oldest-first
        return [
            ContextBlock(
                type=ContextBlockType.HISTORY,
                content=_render_message(message),
                source=f"message:{message.id}",
            )
            for message in kept
        ]
