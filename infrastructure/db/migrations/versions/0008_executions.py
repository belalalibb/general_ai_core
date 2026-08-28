"""executions + execution_nodes — FINAL Phase 3 executions slice

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-28

Maps the 03 §5 entities in core/contracts/execution.py, field-for-field.
executions is TENANT-SCOPED: tenant_id FK + index (20 §6). The 10 §10
idempotency rule ("Same tenant + same idempotency key should not create
duplicate executions") is enforced by UNIQUE (tenant_id, idempotency_key)
with the Postgres DEFAULT null treatment (NULLS DISTINCT) — the key is
nullable BY SPEC and executions submitted WITHOUT a key must never
collide with each other (the opposite posture from the memory upsert
key in 0007; recorded, deliberate).

execution_nodes carries NO tenant_id BY SPEC (03 §5 defines none) —
isolation flows through the execution_id FK to its tenant-scoped parent
(RESTRICT; indexed — same recorded posture as messages in 0006).
UNIQUE (execution_id, node_key): the execution service already rejects
duplicate node_keys per run (InvalidPipeline) — the DB enforces the same
invariant. input_ref/output_ref are JSONB: the spec says ``string/json``
and the contract is ``BoundedStr | JsonObject`` — a bare JSON string is
valid JSONB, so ONE column carries both shapes without inventing a
discriminator. Downgrade drops both (40 §8.2), children first.

Closed-set CHECK constraints carry the contract enum values verbatim:

- executions.status IN ('queued', 'running', 'waiting_approval',
  'succeeded', 'failed', 'cancelled')                    (ExecutionStatus)
- executions.strategy IN ('single', 'parallel', 'pipeline', 'debate',
  'review_judge', 'map_reduce', 'agent', 'hybrid')     (ExecutionStrategy)
- execution_nodes.type IN ('model_call', 'tool_call', 'planner',
  'reviewer', 'tester', 'validator', 'aggregator')    (ExecutionNodeType)
- execution_nodes.status IN ('pending', 'running', 'succeeded',
  'failed', 'skipped', 'cancelled')                 (ExecutionNodeStatus)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "executions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("request_hash", sa.String(length=512), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("cost_snapshot", JSONB(), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'waiting_approval', "
            "'succeeded', 'failed', 'cancelled')",
            name="ck_executions_status_closed_set",
        ),
        sa.CheckConstraint(
            "strategy IN ('single', 'parallel', 'pipeline', 'debate', "
            "'review_judge', 'map_reduce', 'agent', 'hybrid')",
            name="ck_executions_strategy_closed_set",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_executions_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_executions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_executions_conversation_id_conversations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_executions"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_executions_idempotency_key",
        ),
    )
    op.create_index("ix_executions_tenant_id", "executions", ["tenant_id"])

    op.create_table(
        "execution_nodes",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_key", sa.String(length=512), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_ref", JSONB(), nullable=False),
        sa.Column("output_ref", JSONB(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", JSONB(), nullable=True),
        sa.CheckConstraint(
            "type IN ('model_call', 'tool_call', 'planner', 'reviewer', "
            "'tester', 'validator', 'aggregator')",
            name="ck_execution_nodes_type_closed_set",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'skipped', 'cancelled')",
            name="ck_execution_nodes_status_closed_set",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_execution_nodes_retry_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name="fk_execution_nodes_execution_id_executions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_execution_nodes"),
        sa.UniqueConstraint(
            "execution_id",
            "node_key",
            name="uq_execution_nodes_node_key",
        ),
    )
    op.create_index("ix_execution_nodes_execution_id", "execution_nodes", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_nodes_execution_id", table_name="execution_nodes")
    op.drop_table("execution_nodes")
    op.drop_index("ix_executions_tenant_id", table_name="executions")
    op.drop_table("executions")
