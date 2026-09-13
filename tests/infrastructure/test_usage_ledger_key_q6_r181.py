"""R181 Q6 (F-R179-06): the usage ledger key is NOT a foreign key.

Measured in R179 (evidence/r179/F06_usage_ledger_fk_violation.txt): binding the
durable usage ledger made EVERY /v1/execute fail 500 because
``usage_ledger.execution_id`` was a NOT NULL FK to ``executions.id`` while
ExecutionService reserves BEFORE the executions row exists (03 s7
refuse-before-work) and the tool executor reserves under a ``call_id`` that
never becomes an executions row.

Ruling (R181 option b): migration 0022 drops the FK and keeps NOT NULL +
UNIQUE — the ledger key stays "one row per execution/call id" without claiming
a row-level relationship the reserve-before-work ordering cannot honour. The
runtime then binds the ALREADY-COMPOSED ``DurableUsageAccounting`` in the
DATABASE_URL profile (one-name flip, as documented at the R179 decision point).

These tests are hermetic: migration shape, metadata mirror, runtime source pins.
The live proof (usage survives SIGKILL on real PostgreSQL) is
tests_live/r179/test_durability_measured_postgres.py (P4).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from infrastructure.db.tables import usage_ledger

VERSIONS = Path("infrastructure/db/migrations/versions")
MIGRATION = VERSIONS / "0022_usage_ledger_key.py"
RUNTIME_PY = Path("apps/composition/runtime.py")
FK_NAME = "fk_usage_ledger_execution_id_executions"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0022", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrationShape:
    def test_0022_is_the_head_and_follows_0021(self) -> None:
        versions = sorted(p.name for p in VERSIONS.glob("0*.py"))
        assert versions[-1] == "0022_usage_ledger_key.py", versions[-1]
        module = _load_migration()
        assert module.revision == "0022"
        assert module.down_revision == "0021"

    def test_structural_only_drop_fk_keep_not_null_and_unique(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        up = source[source.index("def upgrade"): source.index("def downgrade")]
        down = source[source.index("def downgrade"):]
        # Upgrade: exactly the named FK is dropped — nothing else changes.
        assert "op.drop_constraint(" in up
        assert f'"{FK_NAME}", "usage_ledger", type_="foreignkey"' in up
        assert "alter_column" not in up and "drop_column" not in up
        assert "nullable" not in up and "unique" not in up.lower()
        assert not re.search(r"op\.(execute|drop_table|create_table)", up)
        # Downgrade restores the SAME constraint (name, target, ondelete).
        assert "op.create_foreign_key(" in down
        assert f'"{FK_NAME}"' in down
        assert '"executions"' in down
        assert 'ondelete="RESTRICT"' in down


class TestMetadataMirror:
    def test_execution_id_is_a_not_null_unique_key_without_a_foreign_key(self) -> None:
        column = usage_ledger.columns["execution_id"]
        assert not column.nullable
        assert column.unique
        assert list(column.foreign_keys) == []
        # tenant_id keeps its FK: only the execution key is relaxed.
        tenant_fks = {fk.column.table.name for fk in usage_ledger.columns["tenant_id"].foreign_keys}
        assert tenant_fks == {"tenants"}

    def test_offline_ddl_names_no_reference_to_executions(self) -> None:
        ddl = str(CreateTable(usage_ledger).compile(dialect=postgresql.dialect()))
        assert "REFERENCES executions" not in ddl
        assert "REFERENCES tenants" in ddl
        assert re.search(r"execution_id UUID NOT NULL", ddl), ddl
        assert re.search(r"UNIQUE \(execution_id\)", ddl), ddl


class TestRuntimeBinding:
    def test_durable_profile_binds_the_composed_durable_usage(self) -> None:
        source = RUNTIME_PY.read_text(encoding="utf-8")
        bind_at = source.index("audit, usage = build_durable_audit_usage(bindings, bridge)")
        durable_branch = source.index("if settings is not None:\n        bridge = AsyncBridge()")
        else_branch = source.index(
            "    else:\n        # In-memory profile: process-local audit + usage, unchanged."
        )
        assert durable_branch < bind_at < else_branch
        # The R179 "composed but not bound" residue is gone.
        assert "del durable_usage" not in source
        assert "durable_usage" not in source
        # The ONLY in-memory usage construction is the in-memory profile.
        assert source.count("InMemoryUsageAccounting()") == 1
        assert source.index("InMemoryUsageAccounting()") > else_branch
        # The structural annotation admits both bindings.
        assert "    usage: UsageBinding\n    audit: AuditLogPort\n" in source
        # The closure is cited at the decision point (finding stays traceable).
        assert "F-R179-06" in source

    def test_in_memory_profile_is_unchanged(self) -> None:
        source = RUNTIME_PY.read_text(encoding="utf-8")
        assert (
            "    else:\n"
            "        # In-memory profile: process-local audit + usage, unchanged.\n"
            "        usage = InMemoryUsageAccounting()\n"
            "        audit = InMemoryAuditLog()\n"
        ) in source
        assert source.count("InMemoryAuditLog()") == 1
