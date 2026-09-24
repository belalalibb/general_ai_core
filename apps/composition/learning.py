"""DEC03 explicit policy snapshot and sync adapter over atomic custody.

LEARNING_STORAGE_POLICIES is a JSON array of exact tenant_id, policy_id and
retention_seconds objects. Absence grants nothing. Runtime must pass its explicit
environment mapping; this module never reads ambient configuration. A configured
policy is a storage grant, NOT verified rights or training consent.

No cache or lifecycle transitions are owned here. Runtime/lifecycle binding,
durable policy-removal sweeps and derived-copy reconciliation remain separate;
reads already suppress unavailable content through the shared recovery codec.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from apps.api.ingestion import build_external_ingestion_report
from apps.composition.bridge import AsyncBridge
from apps.composition.database import DatabaseBindings
from core.contracts.base import JsonObject, utc_now
from core.contracts.execution import Execution, ExecutionNode
from core.contracts.learning import LearningSample
from core.learning.storage import (
    LearningStorageConflict,
    LearningStorageError,
    PreparedCapture,
    RecoveredCapture,
    RetentionPolicy,
    prepare_capture,
    recover_capture,
    validate_custody_state,
)
from infrastructure.db.learning import LearningCustodyRepository
from infrastructure.db.repositories.errors import ExecutionNotFound
from infrastructure.db.repositories.executions import ExecutionRecord, PostgresExecutionRepository


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _policy_index(
    policies: tuple[RetentionPolicy, ...],
) -> dict[tuple[UUID, UUID], RetentionPolicy]:
    index = {}
    for policy in policies:
        checked = RetentionPolicy(policy.tenant_id, policy.policy_id, policy.retention_seconds)
        key = (checked.tenant_id, checked.policy_id)
        if key in index:
            raise ValueError("duplicate policy")
        index[key] = checked
    return index


def learning_storage_policies_from_env(environ: Mapping[str, str]) -> tuple[RetentionPolicy, ...]:
    """Closed config; malformed/ambiguous input refuses without echoing content."""
    raw = environ.get("LEARNING_STORAGE_POLICIES")
    if raw is None:
        return ()
    try:
        if len(raw.encode("utf-8")) > 256 * 1024:
            raise ValueError
        values = json.loads(raw, object_pairs_hook=_closed_object)
        if not isinstance(values, list):
            raise ValueError
        policies = []
        for item in values:
            if not isinstance(item, dict) or set(item) != {
                "tenant_id",
                "policy_id",
                "retention_seconds",
            }:
                raise ValueError
            identities = []
            for field in ("tenant_id", "policy_id"):
                value = item[field]
                if not isinstance(value, str) or str(UUID(value)) != value:
                    raise ValueError
                identities.append(UUID(value))
            policies.append(
                RetentionPolicy(identities[0], identities[1], item["retention_seconds"])
            )
        result = tuple(policies)
        _policy_index(result)
        return result
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise LearningStorageError("invalid learning storage policies") from None


class CustodyRepositoryPort(Protocol):
    """Existing asynchronous repository, not a second persistence system."""

    async def capture(
        self,
        *,
        sample: LearningSample,
        execution: Execution,
        nodes: tuple[ExecutionNode, ...],
        prepared: PreparedCapture,
        policy: RetentionPolicy,
        rights_ref: UUID,
        idempotency_key: UUID,
        source_kind: str,
    ) -> dict[str, Any]: ...

    async def get(self, tenant_id: UUID, sample_id: UUID) -> dict[str, Any]: ...

    async def list(self, tenant_id: UUID) -> tuple[dict[str, Any], ...]: ...

    async def save(
        self,
        sample: LearningSample,
        state: JsonObject,
        *,
        expected_revision: int,
    ) -> int: ...

    async def revoke_policy(self, tenant_id: UUID, policy_id: UUID) -> int: ...

    async def expire(self, tenant_id: UUID, now: datetime) -> int: ...

    async def release_legacy_hold(self, tenant_id: UUID, *, reconciliation_ref: UUID) -> bool: ...

    async def list_revocations(self, tenant_id: UUID) -> tuple[Mapping[str, object], ...]: ...


class ExecutionSourcePort(Protocol):
    """Read existing tenant-scoped provenance; no execution writer is exposed."""

    async def get(self, tenant_id: UUID, execution_id: UUID) -> ExecutionRecord: ...


class DurableLearningCustody:
    def __init__(
        self,
        *,
        repository: CustodyRepositoryPort,
        bridge: AsyncBridge,
        policies: tuple[RetentionPolicy, ...],
        sources: ExecutionSourcePort | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        try:
            self._policies = _policy_index(policies)
        except (ValueError, TypeError, AttributeError):
            raise LearningStorageError("invalid learning storage policies") from None
        self._repository = repository
        self._sources = sources
        self._bridge = bridge
        self._clock = clock

    def _decode(self, row: Mapping[str, object], tenant_id: UUID) -> RecoveredCapture:
        policy_id = row.get("policy_id")
        policy = self._policies.get((tenant_id, policy_id)) if isinstance(policy_id, UUID) else None
        return recover_capture(row, tenant_id=tenant_id, policy=policy, now=self._clock())

    def capture_external(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID | None,
        policy_id: UUID | None,
        rights_ref: UUID | None,
        idempotency_key: UUID | None,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> RecoveredCapture:
        if not all(
            isinstance(v, UUID)
            for v in (
                tenant_id,
                actor_id,
                policy_id,
                rights_ref,
                idempotency_key,
            )
        ):
            raise LearningStorageError("explicit custody references required")
        # These checks also narrow the optional types for the repository contract.
        if actor_id is None or policy_id is None or rights_ref is None or idempotency_key is None:
            raise LearningStorageError("explicit custody references required")
        policy = self._policies.get((tenant_id, policy_id))
        if policy is None:
            raise LearningStorageError("storage policy unavailable")
        value = deepcopy(knowledge_value)
        prepared = prepare_capture(
            policy=policy,
            tenant_id=tenant_id,
            policy_id=policy_id,
            rights_ref=rights_ref,
            knowledge_key=knowledge_key,
            knowledge_value=value,
            now=self._clock(),
        )
        sample_id = uuid4()
        report = build_external_ingestion_report(
            tenant_id, sample_id, actor_id, knowledge_key, value
        )
        sample = LearningSample(
            id=sample_id, tenant_id=tenant_id, source_execution_id=report.execution.id
        )
        row = self._bridge.run(
            self._repository.capture(
                sample=sample,
                execution=report.execution,
                nodes=tuple(n.node for n in report.nodes),
                prepared=prepared,
                policy=policy,
                rights_ref=rights_ref,
                idempotency_key=idempotency_key,
                source_kind="external",
            )
        )
        # Stored identity owns retries/response loss, not the new candidate identity.
        return self._decode(row, tenant_id)

    def capture_from_execution(
        self,
        tenant_id: UUID,
        source_execution_id: UUID,
        *,
        policy_id: UUID | None,
        rights_ref: UUID | None,
        idempotency_key: UUID | None,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> RecoveredCapture:
        """Capture against real provenance, never synthesize or rewrite its source.

        Caller authentication/authorization remains the lifecycle/API's duty.
        The stored actor is source provenance, NOT a substitute requesting actor.
        Failed executions may supply RAW learning candidates; no status grants
        learning trust. Source read and custody write are separate transactions;
        capture rechecks source existence in-tenant and the database owns FKs.
        """
        if not all(
            isinstance(v, UUID)
            for v in (tenant_id, source_execution_id, policy_id, rights_ref, idempotency_key)
        ):
            raise LearningStorageError("explicit custody references required")
        if policy_id is None or rights_ref is None or idempotency_key is None:
            raise LearningStorageError("explicit custody references required")
        policy = self._policies.get((tenant_id, policy_id))
        if policy is None:
            raise LearningStorageError("storage policy unavailable")
        if self._sources is None:
            raise LearningStorageError("source unavailable")
        prepared = prepare_capture(
            policy=policy,
            tenant_id=tenant_id,
            policy_id=policy_id,
            rights_ref=rights_ref,
            knowledge_key=knowledge_key,
            knowledge_value=deepcopy(knowledge_value),
            now=self._clock(),
        )
        try:
            source = self._bridge.run(self._sources.get(tenant_id, source_execution_id))
        except ExecutionNotFound:
            raise LearningStorageError("source unavailable") from None
        execution = source.execution
        if execution.tenant_id != tenant_id or execution.id != source_execution_id:
            raise LearningStorageError("source unavailable")
        sample = LearningSample(
            id=uuid4(), tenant_id=tenant_id, source_execution_id=source_execution_id
        )
        row = self._bridge.run(
            self._repository.capture(
                sample=sample,
                execution=execution,
                nodes=(),
                prepared=prepared,
                policy=policy,
                rights_ref=rights_ref,
                idempotency_key=idempotency_key,
                source_kind="execution",
            )
        )
        restored = self._decode(row, tenant_id)
        if (
            restored.source_kind != "execution"
            or restored.sample.source_execution_id != source_execution_id
        ):
            raise LearningStorageError("invalid source binding")
        return restored

    def get(self, tenant_id: UUID, sample_id: UUID) -> RecoveredCapture:
        return self._decode(self._bridge.run(self._repository.get(tenant_id, sample_id)), tenant_id)

    def list(self, tenant_id: UUID) -> tuple[RecoveredCapture, ...]:
        return tuple(
            self._decode(row, tenant_id)
            for row in self._bridge.run(self._repository.list(tenant_id))
        )

    def save(self, sample: LearningSample, state: JsonObject, *, expected_revision: int) -> int:
        state = validate_custody_state(state)
        if sample.tenant_id is None or type(expected_revision) is not int or expected_revision < 0:
            raise LearningStorageConflict("stale or unavailable learning sample")
        current = self.get(sample.tenant_id, sample.id)
        if (
            current.payload is None
            or current.revision != expected_revision
            or current.sample.source_execution_id != sample.source_execution_id
        ):
            raise LearningStorageConflict("stale or unavailable learning sample")
        # Database CAS remains authoritative if availability changes after this read.
        return self._bridge.run(
            self._repository.save(sample, state, expected_revision=expected_revision)
        )


    # --- operator governance (core LearningGovernancePort) ----------------------

    def revoke_policy(self, tenant_id: UUID, policy_id: UUID) -> int:
        if not isinstance(tenant_id, UUID) or not isinstance(policy_id, UUID):
            raise LearningStorageError("explicit custody references required")
        return int(self._bridge.run(self._repository.revoke_policy(tenant_id, policy_id)))

    def expire(self, tenant_id: UUID, now: datetime) -> int:
        if not isinstance(tenant_id, UUID):
            raise LearningStorageError("explicit custody references required")
        return int(self._bridge.run(self._repository.expire(tenant_id, now)))

    def release_legacy_hold(self, tenant_id: UUID, *, reconciliation_ref: UUID) -> bool:
        if not isinstance(tenant_id, UUID) or not isinstance(reconciliation_ref, UUID):
            raise LearningStorageError("explicit custody references required")
        return bool(
            self._bridge.run(
                self._repository.release_legacy_hold(
                    tenant_id, reconciliation_ref=reconciliation_ref
                )
            )
        )

    def list_revocations(self, tenant_id: UUID) -> tuple[Mapping[str, object], ...]:
        """R179 4.7(a): read-only holds/revocations; decoded to plain values only."""
        if not isinstance(tenant_id, UUID):
            raise LearningStorageError("explicit custody references required")
        rows = self._bridge.run(self._repository.list_revocations(tenant_id))
        out: list[Mapping[str, object]] = []
        for row in rows:
            if row.get("tenant_id") != tenant_id:
                raise LearningStorageError("invalid custody record")
            policy_id = row.get("policy_id")
            reason = row.get("reason")
            if policy_id is not None and not isinstance(policy_id, UUID):
                raise LearningStorageError("invalid custody record")
            if reason not in ("legacy_unresolved", "revoked"):
                raise LearningStorageError("invalid custody record")
            out.append(
                {
                    "tenant_id": tenant_id,
                    "policy_id": policy_id,
                    "reason": reason,
                    "recorded_at": row.get("recorded_at"),
                }
            )
        return tuple(out)


def build_durable_learning_custody(
    bindings: DatabaseBindings,
    bridge: AsyncBridge,
    *,
    policies: tuple[RetentionPolicy, ...],
) -> DurableLearningCustody:
    return DurableLearningCustody(
        repository=LearningCustodyRepository(bindings.session_factory),
        sources=PostgresExecutionRepository(bindings.session_factory),
        bridge=bridge,
        policies=policies,
    )
