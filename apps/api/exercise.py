"""Capability Exercise Surface — Vision V7 chunk 2 (frozen-roadmap clause).

The frozen definition pairs the Catalog with a "Capability Exercise
Surface": prove a capability claim by EXERCISING it — a real probe over
the real path, returning machine-checkable evidence. Recorded derivations:

- CLOSED both ways: an exerciser can only be registered for an id in
  ``CAPABILITY_IDS`` (construction-time ValueError otherwise), and the
  set of exercisable ids is exactly the registered handlers — a
  capability WITHOUT a real probe is honestly not exercisable (a fake
  "exercised ok" without touching the machinery would violate 41 §49).
- REAL PROBES ONLY: an exerciser runs the SAME machinery a user request
  runs (e.g. ``execute.sync`` exercises via ExecutionService
  .execute_single with the caller's OWN tenant budget — the probe is a
  real, budget-bounded, labeled execution, identical in posture to the
  agent's R1 ``run_test_execution``). Evidence is the resulting RECORD
  (execution id + stored status), never a narration.
- CALLER-SCOPED: the exerciser receives the admitted Principal — probes
  bill and record against the caller's tenant like any real request
  (no service account, no invented identity).
- CONSUMERS (P3): the admin route (POST /v1/admin/capabilities/{id}/
  exercise) and the agent's R1 ``exercise_capability`` tool both
  dispatch through THIS surface — one registry, two consumers.

This module is pure registry + typing: no FastAPI dependency, no I/O of
its own — the handlers close over composed services in create_app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING

from apps.api.capabilities import CAPABILITY_IDS
from core.contracts.base import JsonObject

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.api.app import Principal

#: One capability probe: runs a REAL request-shaped operation as the
#: admitted caller and returns evidence (record ids / stored statuses).
#: Handlers must NEVER fabricate success — errors are honest evidence too.
ExerciseHandler = Callable[["Principal"], Awaitable[JsonObject]]

#: The metadata key that labels exercise-probe executions — same posture
#: as the agent's R1 label (machine-checkable from the stored record).
EXERCISE_LABEL_KEY = "capability_exercise"


class ExerciseSurface:
    """Closed registry of capability probes — unknown ids refused at build."""

    def __init__(self, handlers: Mapping[str, ExerciseHandler]) -> None:
        unknown = set(handlers) - CAPABILITY_IDS
        if unknown:
            raise ValueError(
                f"exercisers for unknown capability ids: {sorted(unknown)}; "
                "the catalog id set is closed"
            )
        self._handlers: dict[str, ExerciseHandler] = dict(handlers)

    def exercisable(self) -> list[str]:
        """The ids that have a REAL probe — sorted, honest, closed."""
        return sorted(self._handlers)

    def get(self, capability_id: str) -> ExerciseHandler | None:
        return self._handlers.get(capability_id)
