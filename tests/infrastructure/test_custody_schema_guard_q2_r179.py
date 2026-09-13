"""R179 rulings Q2 (F-R179-05) — the smallest STRUCTURAL guard against an old writer.

Measured (4.6-b rolling pair): an OLD binary (pre-0020 code) restarted on the
0020 database lands custody rows under the legacy hold, because the hold is
enforced by the NEW repository code, not by the schema. Ruling: find the smallest
structural guard that makes an old writer fail AT THE DATABASE — no trigger, no
policy logic in DDL, no Python boot check.

Guard: ``learning_sample_custody.custody_schema_generation SMALLINT NOT NULL``
with NO server default (migration 0021). The current metadata supplies the value
through a CLIENT-side SQLAlchemy default, so the unchanged repository INSERT
names the column; an old writer's INSERT — compiled from its own metadata, which
does not know the column — omits it and is refused by ``NOT NULL``. The column
states a fact about the writer (which metadata generation compiled the row); it
encodes no policy.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import postgresql

from infrastructure.db.tables import CUSTODY_SCHEMA_GENERATION, learning_sample_custody

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "infrastructure" / "db" / "migrations" / "versions"
MIGRATION = VERSIONS / "0021_custody_schema_generation.py"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0021", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationShape:
    def test_0021_follows_0020_and_is_followed_only_by_0022(self) -> None:
        # R181 Q6 (conscious pin update): 0022 (usage ledger key, F-R179-06) is
        # the new head; 0021 keeps its place in the chain.
        versions = sorted(p.name for p in VERSIONS.glob("0*.py"))
        assert versions[-2:] == [
            "0021_custody_schema_generation.py",
            "0022_usage_ledger_key.py",
        ], versions[-2:]
        module = _load_migration()
        assert module.revision == "0021"
        assert module.down_revision == "0020"

    def test_no_trigger_no_function_no_policy_logic_in_ddl(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        body = source[source.index("def upgrade") :]
        for word in ("TRIGGER", "FUNCTION", "PROCEDURE", "POLICY", "learning_policy_revocations"):
            assert word not in body, word
        # Purely structural: ONE add_column with a backfill default, then the
        # default is dropped so the database itself demands the value.
        assert body.count("op.add_column(") == 1
        assert "server_default=None" in body
        assert "op.drop_column(" in source[source.index("def downgrade") :]

    def test_upgrade_backfills_existing_rows_to_generation_one(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        body = source[source.index("def upgrade") : source.index("def downgrade")]
        assert re.search(r'server_default=sa\.text\("1"\)', body), body
        assert "custody_schema_generation" in body


class TestMetadataMirror:
    def test_column_is_not_null_without_server_default(self) -> None:
        column = learning_sample_custody.c.custody_schema_generation
        assert column.nullable is False
        assert column.server_default is None
        assert column.default is not None  # client-side: the CURRENT writer supplies it

    def test_client_default_is_the_current_generation(self) -> None:
        column = learning_sample_custody.c.custody_schema_generation
        assert CUSTODY_SCHEMA_GENERATION == 2  # 1 = 0019/0020 world (backfilled); 2 = 0021+
        assert column.default is not None and column.default.arg == CUSTODY_SCHEMA_GENERATION
        assert str(column.type).upper().startswith("SMALLINT")

    def test_generation_is_a_writer_fact_not_a_policy(self) -> None:
        source = (ROOT / "infrastructure" / "db" / "tables.py").read_text(encoding="utf-8")
        block = source[source.index("learning_sample_custody = Table(") :]
        block = block[: block.index("\n)\n")]
        assert "custody_schema_generation" in block
        # No CheckConstraint mentions the generation: it constrains nothing but presence.
        checks = re.findall(r"CheckConstraint\(\s*\"([^\"]*)\"", block)
        assert all("custody_schema_generation" not in check for check in checks), checks


class TestOldWriterInsertIsRefusedStructurally:
    """An INSERT compiled from a pre-0021 metadata copy omits the column."""

    @staticmethod
    def _pre_0021_custody() -> Table:
        """The pre-0021 metadata: every custody column except the guard."""
        old = MetaData()
        columns = [
            Column(c.name, c.type, nullable=c.nullable)
            for c in learning_sample_custody.columns
            if c.name != "custody_schema_generation"
        ]
        return Table("learning_sample_custody", old, *columns)

    def test_current_metadata_insert_names_the_column(self) -> None:
        stmt = learning_sample_custody.insert().values(sample_id=None)
        assert "custody_schema_generation" in str(stmt.compile(dialect=postgresql.dialect()))

    def test_pre_0021_metadata_insert_omits_the_column(self) -> None:
        stmt = self._pre_0021_custody().insert().values(sample_id=None)
        assert "custody_schema_generation" not in str(stmt.compile(dialect=postgresql.dialect()))
        # ...and the 0021 DDL declares the column NOT NULL with no default, so the
        # database refuses that INSERT. Proven live by the rolling-pair probe
        # (tests_live/r179/test_deploy_truth_rolling_crash_postgres.py).

    def test_repository_insert_path_is_unchanged(self) -> None:
        """The guard rides the metadata default — the repository never names it."""
        source = (ROOT / "infrastructure" / "db" / "learning.py").read_text(encoding="utf-8")
        assert "custody_schema_generation" not in source
