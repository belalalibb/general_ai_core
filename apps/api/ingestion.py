"""Real per-row external-ingestion scan receipts over the execution store.

Completion means the deterministic scan ran, NOT that content is sanitized,
eligible, verified or model-generated. No provider is called. Receipts contain
hashes/counts, never raw knowledge or secret findings. The write-free builder
is available for atomic custody composition; runtime binding remains separate.
"""

from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from apps.api.store import ExecutionStorePort
from core.contracts.base import JsonObject, utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.execution.service import ExecutionReport, NodeReport
from core.learning.errors import LearningError
from core.learning.sanitizer import sanitize_knowledge


class ExternalIngestionRecorder:
    def __init__(
        self,
        store: ExecutionStorePort,
        *,
        default_actor: tuple[UUID, UUID] | None = None,
    ) -> None:
        self._store = store
        self._default_actor = default_actor

    def record(
        self,
        tenant_id: UUID,
        sample_id: UUID,
        actor_id: UUID | None,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> UUID:
        if actor_id is None:
            if self._default_actor is None or self._default_actor[0] != tenant_id:
                raise LearningError("external ingestion requires an admitted actor")
            actor_id = self._default_actor[1]

        report = build_external_ingestion_report(
            tenant_id, sample_id, actor_id, knowledge_key, knowledge_value
        )
        self._store.put(report)
        return report.execution.id


def build_external_ingestion_report(
    tenant_id: UUID,
    sample_id: UUID,
    actor_id: UUID | None,
    knowledge_key: str,
    knowledge_value: JsonObject,
) -> ExecutionReport:
    """Run the genuine scan and build metadata-only lineage WITHOUT persistence.

    The caller must admit the actor, policy and rights separately. This builder
    grants no storage permission or learning trust. Durable composition passes
    the execution/nodes to custody's atomic transaction; it must not call record.
    """
    if actor_id is None:
        raise LearningError("external ingestion requires an admitted actor")

    started = utc_now()
    canonical = json.dumps(
        {"key": knowledge_key, "value": knowledge_value},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    scan = sanitize_knowledge(knowledge_key, knowledge_value)
    execution_id = uuid4()
    node = ExecutionNode(
        id=uuid4(),
        execution_id=execution_id,
        node_key="external-ingestion-scan",
        type=ExecutionNodeType.VALIDATOR,
        status=ExecutionNodeStatus.SUCCEEDED,
        input_ref={
            "operation": "external_ingestion",
            "version": 1,
            "sample_id": str(sample_id),
            "content_sha256": digest,
        },
        output_ref={
            "scan_completed": True,
            "scan_clean": scan.clean,
            "finding_count": len(scan.findings),
            "scanned_paths": scan.scanned_paths,
            "verification_level": "RAW",
            "eligibility": "pending",
        },
        retry_count=0,
    )
    return ExecutionReport(
        execution=Execution(
            id=execution_id,
            tenant_id=tenant_id,
            user_id=actor_id,
            request_hash="sha256:" + digest,
            status=ExecutionStatus.SUCCEEDED,
            strategy=ExecutionStrategy.SINGLE,
            cost_snapshot={"estimated_units": 0},
            created_at=started,
            completed_at=utc_now(),
        ),
        nodes=(NodeReport(node=node, attempts=(), response=None),),
        status_history=(ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED),
    )
