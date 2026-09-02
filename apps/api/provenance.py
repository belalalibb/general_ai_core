"""Context provenance — R161 Phase 3 evidence, derived from STORED execution truth.

ONE derivation, N consumers (P3): the sync ``/v1/execute`` response, the
``GET /v1/executions/{id}`` read, and the admin capability re-test all
read the SAME function over the SAME stored ``input_ref``.

Phase 3 (real learning improvement) requires that GOLD knowledge reaching a
production answer be MEASURABLE, not asserted. The composed 13 §5 context
already rides the node's ``input_ref["context"]``. This reads it back and
names, per memory block, the memory id + its ``source`` label
(``learning.gold`` for promoted knowledge) — never the content (that
already rode the payload once; re-echoing it would widen the surface).

Deny-by-default: no composed context ⇒ no artifact (``None``); an
unresolvable memory id ⇒ ``source: null`` (honest, no fabrication).
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.base import JsonObject
from core.execution.service import ExecutionReport
from core.learning import GOLD_KNOWLEDGE_SOURCE
from core.memory.errors import MemoryStoreError
from core.memory.ports import MemoryStorePort

__all__ = ["CONTEXT_PROVENANCE_ARTIFACT", "context_provenance", "gold_keys_in_report"]

#: Artifact type label for the R161 context-provenance evidence.
CONTEXT_PROVENANCE_ARTIFACT = "context_provenance"


def _memory_blocks(report: ExecutionReport) -> list[JsonObject] | None:
    """The stored context blocks of the final node, or None when absent."""
    if not report.nodes:
        return None
    input_ref = report.nodes[-1].node.input_ref
    if not isinstance(input_ref, dict):
        return None
    context = input_ref.get("context")
    if not isinstance(context, dict):
        return None
    blocks = context.get("context_blocks")
    if not isinstance(blocks, list):
        return None
    return [b for b in blocks if isinstance(b, dict)]


def context_provenance(
    report: ExecutionReport,
    tenant_id: UUID,
    memory: MemoryStorePort | None,
) -> JsonObject | None:
    """Derive the ``context_provenance`` artifact (ids + labels, never content)."""
    blocks = _memory_blocks(report)
    if blocks is None:
        return None
    memory_blocks: list[JsonObject] = []
    gold_count = 0
    for block in blocks:
        source = block.get("source")
        if not isinstance(source, str) or not source.startswith("memory:"):
            continue
        memory_id = source.removeprefix("memory:")
        origin: str | None = None
        if memory is not None:
            try:
                origin = memory.get(tenant_id, UUID(memory_id)).source
            except (ValueError, MemoryStoreError):
                origin = None
        if origin == GOLD_KNOWLEDGE_SOURCE:
            gold_count += 1
        memory_blocks.append({"memory_id": memory_id, "source": origin, "type": block.get("type")})
    input_ref = report.nodes[-1].node.input_ref
    context = input_ref.get("context") if isinstance(input_ref, dict) else None
    excluded = context.get("excluded") if isinstance(context, dict) else None
    return {
        "type": CONTEXT_PROVENANCE_ARTIFACT,
        "blocks_total": len(blocks),
        "memory_blocks": memory_blocks,
        "gold_blocks": gold_count,
        "excluded": len(excluded) if isinstance(excluded, list) else 0,
    }


def gold_keys_in_report(
    report: ExecutionReport, tenant_id: UUID, memory: MemoryStorePort
) -> frozenset[str]:
    """The GOLD memory KEYS that rode this execution's model input.

    Used by the capability re-test to measure, per probe key, whether the
    learned knowledge reached REAL executions — the production counterpart
    of the isolated ``ask_learned`` verdict.
    """
    blocks = _memory_blocks(report)
    if blocks is None:
        return frozenset()
    keys: set[str] = set()
    for block in blocks:
        source = block.get("source")
        if not isinstance(source, str) or not source.startswith("memory:"):
            continue
        try:
            item = memory.get(tenant_id, UUID(source.removeprefix("memory:")))
        except (ValueError, MemoryStoreError):
            continue
        if item.source == GOLD_KNOWLEDGE_SOURCE:
            keys.add(item.key)
    return frozenset(keys)
