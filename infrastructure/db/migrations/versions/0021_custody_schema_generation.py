"""R179 rulings Q2 (F-R179-05): structural guard against pre-0021 custody writers.

Measured: an OLD binary restarted on the 0020 database landed custody rows under
the legacy hold — the hold was enforced by the NEW repository code, not by the
schema (evidence/r179/deploy_truth_rolling_crash.json → rolling_pair).

This migration adds ONE column, ``custody_schema_generation SMALLINT NOT NULL``,
with NO server default once existing rows are backfilled. The current metadata
(infrastructure/db/tables.py) supplies the value client-side; a writer compiled
from any earlier metadata omits the column and its INSERT is refused by the
database with a NOT NULL violation. No trigger, no function, no policy in DDL:
the column records which metadata generation wrote the row, nothing else.

Downgrade drops the column — structural, no custody evidence is touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows were written by the 0019/0020 world: generation 1.
    op.add_column(
        "learning_sample_custody",
        sa.Column(
            "custody_schema_generation",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    # Drop the default: from here on the WRITER must supply the value, which is
    # exactly what an old writer cannot do.
    op.alter_column("learning_sample_custody", "custody_schema_generation", server_default=None)


def downgrade() -> None:
    op.drop_column("learning_sample_custody", "custody_schema_generation")
