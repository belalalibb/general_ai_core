"""R181 Q6 (F-R179-06): the usage ledger key is NOT a foreign key.

Measured (evidence/r179/F06_usage_ledger_fk_violation.txt): binding the durable
usage ledger made EVERY /v1/execute fail 500 because
``usage_ledger.execution_id`` was a NOT NULL FK to ``executions.id`` while
ExecutionService reserves usage BEFORE the executions row exists (03 s7
refuse-before-work) and the tool executor reserves under a ``call_id`` that
never becomes an executions row.

This migration drops ONLY that foreign key. ``execution_id`` stays NOT NULL and
UNIQUE: the ledger is still keyed one row per execution/call id
(core/usage/memory.py semantics) — it simply no longer claims a row-level
relationship the reserve-before-work ordering cannot honour. No data is
touched; no column, default, or check changes.

Downgrade restores the same constraint (name, target, ondelete). It fails
closed on any ledger row whose key is not an executions id — that is the
correct outcome: such rows are exactly what the FK could never represent.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_usage_ledger_execution_id_executions", "usage_ledger", type_="foreignkey"
    )


def downgrade() -> None:
    op.create_foreign_key(
        "fk_usage_ledger_execution_id_executions",
        "usage_ledger",
        "executions",
        ["execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
