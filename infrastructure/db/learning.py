"""DEC03 transactional sample/subject/custody persistence; no inference or gates.

Capture uses INSERT, tenant-key advisory locking and uniqueness, never execution
upsert. Same-key retry returns the original row. All three writes commit together.
Payloads are immutable, scan-clean only; quarantine and redacted evidence persist.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from core.contracts.base import JsonObject, utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import Execution, ExecutionNode, ExecutionNodeType
from core.contracts.learning import LearningSample
from core.learning.storage import (
    LearningStorageConflict,
    LearningStorageError,
    PreparedCapture,
    RetentionPolicy,
    custody_descriptor_digest,
    prepare_capture,
    validate_custody_state,
)
from infrastructure.db.repositories.executions import _execution_values, _node_values
from infrastructure.db.tables import (
    execution_nodes,
    executions,
    learning_samples,
    users,
)
from infrastructure.db.tables import (
    learning_sample_custody as custody,
)


def _joined() -> Select[Any]:
    return select(
        custody,
        learning_samples.c.eligibility,
        learning_samples.c.sanitization_state,
        learning_samples.c.verification_level,
        learning_samples.c.dataset_id,
    ).join(
        learning_samples,
        and_(
            custody.c.sample_id == learning_samples.c.id,
            custody.c.tenant_id == learning_samples.c.tenant_id,
            custody.c.source_execution_id == learning_samples.c.source_execution_id,
        ),
    )


class LearningCustodyRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

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
    ) -> dict[str, Any]:
        tenant = sample.tenant_id
        if tenant is None or policy.tenant_id != tenant or execution.tenant_id != tenant:
            raise LearningStorageError("storage policy unavailable")
        if sample.source_execution_id != execution.id or source_kind not in {
            "external",
            "execution",
        }:
            raise LearningStorageError("invalid source binding")
        if not isinstance(rights_ref, UUID) or not isinstance(idempotency_key, UUID):
            raise LearningStorageError("explicit custody references required")
        if prepared.quarantined != (prepared.payload is None):
            raise LearningStorageError("invalid quarantine state")
        if prepared.payload is not None:
            checked = prepare_capture(
                policy=policy,
                tenant_id=tenant,
                policy_id=policy.policy_id,
                rights_ref=rights_ref,
                knowledge_key=prepared.payload["knowledge_key"],
                knowledge_value=prepared.payload["knowledge_value"],
                now=utc_now(),
            )
            if checked.quarantined or checked.content_digest != prepared.content_digest:
                raise LearningStorageError("payload integrity mismatch")
        descriptor = custody_descriptor_digest(
            tenant_id=tenant, policy_id=policy.policy_id, rights_ref=rights_ref,
            retention_seconds=policy.retention_seconds, source_kind=source_kind,
            source_execution_id=execution.id, content_digest=prepared.content_digest,
        )
        async with self._sessions.begin() as session:
            # Locks are transaction scoped and serialize the same tenant/key across processes.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"learning:{tenant}:{idempotency_key}"},
            )
            actor = await session.scalar(
                select(users.c.id).where(
                    users.c.id == execution.user_id, users.c.tenant_id == tenant
                )
            )
            if actor is None:
                raise LearningStorageError("admitted actor unavailable")
            existing = (
                (
                    await session.execute(
                        _joined().where(
                            custody.c.tenant_id == tenant,
                            custody.c.idempotency_key == idempotency_key,
                        )
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["descriptor_digest"] != descriptor:
                    raise LearningStorageConflict("idempotency descriptor conflict")
                return dict(existing)
            if source_kind == "external":
                if (
                    execution.status is not ExecutionStatus.SUCCEEDED
                    or len(nodes) != 1
                    or nodes[0].type is not ExecutionNodeType.VALIDATOR
                    or not isinstance(nodes[0].input_ref, dict)
                    or nodes[0].input_ref.get("sample_id") != str(sample.id)
                    or nodes[0].input_ref.get("content_sha256") != prepared.content_digest
                    or nodes[0].output_ref != prepared.receipt
                ):
                    raise LearningStorageError("invalid ingestion receipt")
                await session.execute(executions.insert().values(_execution_values(execution)))
                await session.execute(execution_nodes.insert(), [_node_values(n) for n in nodes])
            else:
                found = await session.scalar(
                    select(executions.c.id).where(
                        executions.c.id == execution.id, executions.c.tenant_id == tenant
                    )
                )
                if found is None:
                    raise LearningStorageError("source unavailable")
            await session.execute(
                learning_samples.insert().values(
                    id=sample.id, tenant_id=tenant, source_execution_id=execution.id
                )
            )
            await session.execute(
                custody.insert().values(
                    sample_id=sample.id,
                    tenant_id=tenant,
                    source_execution_id=execution.id,
                    idempotency_key=idempotency_key,
                    policy_id=policy.policy_id,
                    rights_ref=rights_ref,
                    retention_seconds=policy.retention_seconds,
                    created_at=execution.created_at if source_kind == "external" else utc_now(),
                    expires_at=prepared.expires_at,
                    content_digest=prepared.content_digest,
                    descriptor_digest=descriptor,
                    source_kind=source_kind,
                    payload=prepared.payload,
                    quarantined=prepared.quarantined,
                    state={"version": 1},
                    revision=0,
                    revoked=False,
                )
            )
            row = (
                (
                    await session.execute(
                        _joined().where(
                            custody.c.sample_id == sample.id, custody.c.tenant_id == tenant
                        )
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)

    async def get(self, tenant_id: UUID, sample_id: UUID) -> dict[str, Any]:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        _joined().where(
                            custody.c.tenant_id == tenant_id, custody.c.sample_id == sample_id
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LearningStorageError("unknown learning sample")
            return dict(row)

    async def list(self, tenant_id: UUID) -> tuple[dict[str, Any], ...]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        _joined()
                        .where(custody.c.tenant_id == tenant_id)
                        .order_by(custody.c.created_at, custody.c.sample_id)
                    )
                )
                .mappings()
                .all()
            )
            return tuple(dict(row) for row in rows)

    async def save(
        self, sample: LearningSample, state: JsonObject, *, expected_revision: int
    ) -> int:
        """CAS the lifecycle metadata, never payload/identity/policy. No secret snapshots."""
        sample = LearningSample.model_validate(sample.model_dump())
        state = validate_custody_state(state)
        async with self._sessions.begin() as session:
            row = (
                await session.execute(
                    update(custody)
                    .where(
                        custody.c.sample_id == sample.id,
                        custody.c.tenant_id == sample.tenant_id,
                        custody.c.source_execution_id == sample.source_execution_id,
                        custody.c.revision == expected_revision,
                        custody.c.revoked.is_(False),
                        custody.c.quarantined.is_(False),
                        custody.c.payload.is_not(None),
                        custody.c.expires_at > func.clock_timestamp(),
                    )
                    .values(state=state, revision=custody.c.revision + 1)
                    .returning(custody.c.revision)
                )
            ).first()
            if row is None:
                raise LearningStorageConflict("stale or unavailable learning sample")
            await session.execute(
                update(learning_samples)
                .where(
                    learning_samples.c.id == sample.id,
                    learning_samples.c.tenant_id == sample.tenant_id,
                    learning_samples.c.source_execution_id == sample.source_execution_id,
                )
                .values(
                    eligibility=sample.eligibility.value,
                    sanitization_state=sample.sanitization_state.value,
                    verification_level=sample.verification_level.value,
                    dataset_id=sample.dataset_id,
                )
            )
            return int(row[0])

    async def _invalidate(self, tenant_id: UUID, predicate: ColumnElement[bool]) -> int:
        async with self._sessions.begin() as session:
            ids = (
                (
                    await session.execute(
                        update(custody)
                        .where(
                            custody.c.tenant_id == tenant_id,
                            custody.c.revoked.is_(False),
                            predicate,
                        )
                        .values(payload=None, revoked=True, revision=custody.c.revision + 1)
                        .returning(custody.c.sample_id)
                    )
                )
                .scalars()
                .all()
            )
            if ids:
                await session.execute(
                    update(learning_samples)
                    .where(
                        learning_samples.c.tenant_id == tenant_id,
                        learning_samples.c.id.in_(ids),
                    )
                    .values(eligibility="ineligible", sanitization_state="failed")
                )
            return len(ids)

    async def expire(self, tenant_id: UUID, now: datetime) -> int:
        """Operator policy sweep: erase expired payload, retain redacted immutable lineage."""
        if now.utcoffset() is None:
            raise LearningStorageError("storage clock must be timezone aware")
        return await self._invalidate(tenant_id, custody.c.expires_at <= now)

    async def revoke_policy(self, tenant_id: UUID, policy_id: UUID) -> int:
        """Revoke existing custody without deleting sample, source or evaluation evidence."""
        return await self._invalidate(tenant_id, custody.c.policy_id == policy_id)
