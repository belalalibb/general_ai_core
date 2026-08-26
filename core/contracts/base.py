"""Base contract primitives shared by every contract model.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md
Rule (41 Phase 1): no Contract imports a specific Implementation.

Every contract model inherits :class:`ContractModel`, which fixes the
validation posture for the whole contract layer:

- ``extra="forbid"``   — unknown fields are rejected (deny-by-default posture).
- ``frozen=True``      — contract instances are immutable value objects.
- ``strict=False``     — standard Pydantic coercion for JSON-boundary types
  (e.g. ISO strings -> datetime), matching an HTTP JSON API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Root of all contract models (single validation posture)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Shared identifier / scalar aliases -------------------------------------
# Entity IDs are UUIDs (03_DOMAIN_MODEL; API examples use "uuid").

TenantId = UUID
UserId = UUID
ExecutionId = UUID

# Non-empty, bounded human-readable string (defensive default for names/labels).
BoundedStr = Annotated[str, Field(min_length=1, max_length=512)]

# trace_id is an opaque observability correlation token, not a UUID (10 §9).
TraceId = Annotated[str, Field(min_length=1, max_length=128)]

# Arbitrary JSON-object payloads (schemas that carry open "details"/"data").
JsonObject = dict[str, Any]

# Any JSON value (object, array, string, number, bool, null) — for contract
# fields the spec types as bare "json" (e.g. 03 §3 MemoryItem.value).
JsonValue = Any


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp source for contract defaults."""
    return datetime.now(UTC)
