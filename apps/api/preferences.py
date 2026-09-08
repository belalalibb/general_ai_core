"""R177-FIX-04 — preference learning (13 §6) + memory visibility (13 §8).

F-R177-02 (evidence/r177/A06_vocabulary): ``PreferenceLearningGate`` was
exported, tested and never called; no route let a user see or delete learned
memory. This module is the ONE runtime writer of ``source="preference"``
items (docs/architecture/MEMORY_TYPES_MAPPING.md) and the ONE read/delete
surface for them.

Design (recorded):

- Observations are derived ONLY from what the caller explicitly sent on a
  SUCCEEDED ``/v1/execute`` (``context.language`` → ``preferred_language``,
  ``output.format`` → ``preferred_output_format``). Nothing is inferred from
  model output; failed executions are not evidence (13 §1 "evidence-based").
- The gate decides; the learner never bypasses it. ``policy_allows_memory`` is
  composition data (deny-by-default, 13 §6 condition 5).
- Admitted ⇒ ``MemoryItem(scope=TENANT, user_id=<caller>, source="preference",
  sensitivity=LOW)`` through the EXISTING ``MemoryStorePort.upsert`` — the
  13 §7 secret guard applies unchanged; a refused write is recorded as a
  refusal (``store_refused:…``), never retried silently.
- Per-user observation window is bounded (default 20) so memory use stays
  O(users × window); the window is data, not policy.
- Routes: ``GET /v1/memory/preferences`` (caller's own items, source filtered)
  and ``DELETE /v1/memory/preferences/{id}`` (owner only; a non-preference or
  foreign item is the SAME 404 — 20 §6). No cross-user read is possible: the
  store's ``query`` already excludes other users' items (13 §7).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from apps.api.errors import error_response
from core.contracts.base import JsonObject, utc_now
from core.contracts.errors import ErrorCode
from core.contracts.memory import MemoryItem, MemoryScope, MemorySensitivity
from core.memory.errors import MemoryStoreError
from core.memory.ports import MemoryStorePort
from core.memory.preferences import (
    LearningDecision,
    PreferenceLearningGate,
    PreferenceObservation,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.api.app import Principal

#: ``MemoryItem.source`` for learned preferences (MEMORY_TYPES_MAPPING.md §1).
PREFERENCE_SOURCE = "preference"

#: Observation keys, derived from explicit request fields only.
KEY_LANGUAGE = "preferred_language"
KEY_OUTPUT_FORMAT = "preferred_output_format"


@dataclass
class _UserObservations:
    """Bounded, per-(tenant, user) evidence window plus the last gate answer."""

    window: deque[PreferenceObservation]
    last_decision: LearningDecision | None = None
    decisions: dict[str, LearningDecision] = field(default_factory=dict)


class PreferenceLearner:
    """Feed explicit request facts to the 13 §6 gate; write admitted items."""

    def __init__(
        self,
        *,
        memory: MemoryStorePort,
        gate: PreferenceLearningGate,
        policy_allows_memory: bool = False,
        window: int = 20,
    ) -> None:
        if window < 2:
            raise ValueError("observation window must hold at least 2 observations")
        self._memory = memory
        self._gate = gate
        self._policy_allows_memory = policy_allows_memory
        self._window = window
        self._users: dict[tuple[UUID, UUID], _UserObservations] = {}

    # --- observation (called by the execute path on SUCCEEDED only) -------------

    def observe(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        language: str | None,
        output_format: str | None,
        succeeded: bool,
    ) -> None:
        """Record explicit facts of one execution; learn when the gate admits."""
        if not succeeded:
            return  # failed executions are not evidence (13 §1)
        facts: list[tuple[str, str]] = []
        if language:
            facts.append((KEY_LANGUAGE, language))
        if output_format:
            facts.append((KEY_OUTPUT_FORMAT, output_format))
        if not facts:
            return
        state = self._users.get((tenant_id, user_id))
        if state is None:
            state = _UserObservations(window=deque(maxlen=self._window))
            self._users[(tenant_id, user_id)] = state
        for key, value in facts:
            state.window.append(
                PreferenceObservation(key=key, value=value, scope=MemoryScope.TENANT)
            )
            self._learn(tenant_id, user_id, state, key, value)

    def _learn(
        self,
        tenant_id: UUID,
        user_id: UUID,
        state: _UserObservations,
        key: str,
        value: str,
    ) -> None:
        decision = self._gate.evaluate(
            key=key,
            value=value,
            sensitivity=MemorySensitivity.LOW,
            observations=list(state.window),
            policy_allows_memory=self._policy_allows_memory,
        )
        if decision.learnable:
            try:
                self._memory.upsert(
                    MemoryItem(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        scope=MemoryScope.TENANT,
                        key=key,
                        value=value,
                        source=PREFERENCE_SOURCE,
                        confidence=decision.confidence if decision.confidence is not None else 0.0,
                        evidence_count=1,
                        last_seen=utc_now(),
                        sensitivity=MemorySensitivity.LOW,
                    )
                )
            except MemoryStoreError as exc:
                # 13 §7 secret guard (or backend refusal): recorded, never bypassed.
                decision = LearningDecision(learnable=False, reason=f"store_refused:{exc}")
        state.decisions[key] = decision
        state.last_decision = decision

    def last_decision(self, tenant_id: UUID, user_id: UUID) -> LearningDecision | None:
        """The most recent gate answer for this user — explainability, not state."""
        state = self._users.get((tenant_id, user_id))
        return None if state is None else state.last_decision

    # --- visibility (13 §8) ---------------------------------------------------

    def list_for(self, tenant_id: UUID, user_id: UUID) -> tuple[MemoryItem, ...]:
        """The caller's OWN learned preferences (tenant-shared items excluded)."""
        return tuple(
            item
            for item in self._memory.query(tenant_id, user_id=user_id)
            if item.source == PREFERENCE_SOURCE and item.user_id == user_id
        )

    def delete_for(self, tenant_id: UUID, user_id: UUID, memory_id: UUID) -> bool:
        """Delete one OWN preference; False for absent/foreign/non-preference."""
        try:
            item = self._memory.get(tenant_id, memory_id)
        except MemoryStoreError:
            return False
        if item.user_id != user_id or item.source != PREFERENCE_SOURCE:
            return False
        try:
            self._memory.delete(tenant_id, memory_id)
        except MemoryStoreError:
            return False
        return True


def _item_json(item: MemoryItem) -> JsonObject:
    return {
        "id": str(item.id),
        "key": item.key,
        "value": item.value,
        "scope": item.scope.value,
        "source": item.source,
        "user_id": None if item.user_id is None else str(item.user_id),
        "confidence": item.confidence,
        "evidence_count": item.evidence_count,
        "last_seen": item.last_seen.isoformat(),
        "sensitivity": item.sensitivity.value,
    }


def create_preferences_router(
    learner: PreferenceLearner,
    *,
    resolve: Callable[[Request], Principal | JSONResponse],
) -> APIRouter:
    """``/v1/memory/preferences`` — the caller's own learned preferences (13 §8)."""
    router = APIRouter(prefix="/v1/memory/preferences")

    @router.get("")
    async def list_preferences(request: Request) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        rows = learner.list_for(caller.tenant_id, caller.user_id)
        return JSONResponse({"preferences": [_item_json(i) for i in rows]})

    @router.delete("/{memory_id}", status_code=204)
    async def delete_preference(request: Request, memory_id: str) -> Response:
        caller = resolve(request)
        if isinstance(caller, JSONResponse):
            return caller
        try:
            parsed = UUID(memory_id)
        except ValueError:
            parsed = None
        if parsed is None or not learner.delete_for(caller.tenant_id, caller.user_id, parsed):
            # Absent, foreign, other user's, or non-preference: one answer (20 §6).
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                "Unknown preference id.",
                details={"memory_id": memory_id[:100]},
                http_status=404,
            )
        return Response(status_code=204)

    return router
